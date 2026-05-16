import os
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from shorts_common import (
    add_quota_usage,
    get_today_usage,
    load_existing_country_data,
    load_quota_ledger,
    merge_unique_video_entries,
    quota_day_key,
    resolve_output_country_id,
    save_quota_ledger,
)
from shorts_config import (
    API_KEY,
    OUTPUT_DIR,
    QUOTA_LEDGER_FILE,
    DAILY_QUOTA_LIMIT,
    SEARCH_COST_UNITS,
    VIDEOS_LIST_COST_UNITS,
    CHANNELS_LIST_COST_UNITS,
    MAX_RESULTS_PER_CALL,
    MIN_VIEW_COUNT,
    MIN_LIKE_COUNT,
    UNKNOWN_COUNTRY,
    OTHER_COUNTRY,
    COUNTRIES,
    CATEGORIES,
)

# ================= 邏輯區域 =================

class ApiKeyRestrictionError(Exception):
    """Raised when API key restriction blocks current request origin."""


class QuotaExceededError(Exception):
    """Raised when YouTube Data API quota is exhausted."""


def parse_http_error(e):
    """Extract reason/message from Google API HttpError payload."""
    try:
        payload = json.loads(e.content.decode("utf-8"))
        error_obj = payload.get("error", {})
        errors = error_obj.get("errors", [])
        reason = errors[0].get("reason", "") if errors else ""
        message = error_obj.get("message", "")
        return reason, message
    except Exception:
        return "", str(e)


def create_youtube_client(api_key):
    if not api_key:
        raise ValueError(
            "Missing API key. Please set environment variable YOUTUBE_API_KEY first."
        )
    return build('youtube', 'v3', developerKey=api_key)


def has_remaining_calls(key_states):
    return any(state["remaining_units"] >= SEARCH_COST_UNITS for state in key_states)


def next_available_key_state(key_states):
    for state in key_states:
        if state["remaining_units"] >= SEARCH_COST_UNITS and not state.get("blocked", False):
            return state
    return None


def next_available_key_state_for_units(key_states, required_units):
    for state in key_states:
        if state["remaining_units"] >= required_units and not state.get("blocked", False):
            return state
    return None


def run_api_list_request(key_states, quota_ledger, today_key, required_units, resource_name, build_request):
    """用可用 API key 執行 list request，成功時回傳 response。"""
    while True:
        key_state = next_available_key_state_for_units(key_states, required_units)
        if not key_state:
            return None, None

        try:
            response = build_request(key_state["client"]).execute()
            key_state["remaining_units"] -= required_units
            add_quota_usage(quota_ledger, key_state["name"], today_key, required_units)
            save_quota_ledger(QUOTA_LEDGER_FILE, quota_ledger)
            return response, key_state["name"]
        except HttpError as e:
            reason, message = parse_http_error(e)

            if reason == "quotaExceeded":
                key_state["remaining_units"] = 0
                print(f"Key quota exhausted during {resource_name}, switch key: {key_state['name']}")
                continue

            if e.resp.status == 403 and "ip address restriction" in message.lower():
                key_state["blocked"] = True
                key_state["remaining_units"] = 0
                print(
                    f"Key blocked by IP restriction during {resource_name}, switch key: {key_state['name']}. "
                    "Please add current public IPv6/IPv4 to this key allowlist."
                )
                continue

            print(f"HttpError {e.resp.status} ({reason or 'unknown'}) during {resource_name}: {message or str(e)}")
            return None, None
        except Exception as e:
            print(f"Unexpected error during {resource_name}: {e}")
            return None, None


def fetch_channel_country_map(channel_ids, key_states, quota_ledger, today_key):
    """依 channel ID 查詢頻道所屬國家。"""
    channel_country_map = {}
    unique_channel_ids = list(dict.fromkeys(channel_ids))

    for i in range(0, len(unique_channel_ids), MAX_RESULTS_PER_CALL):
        batch_ids = unique_channel_ids[i:i + MAX_RESULTS_PER_CALL]
        response, _ = run_api_list_request(
            key_states,
            quota_ledger,
            today_key,
            CHANNELS_LIST_COST_UNITS,
            "channels.list",
            lambda client: client.channels().list(
                part="snippet",
                id=",".join(batch_ids),
                maxResults=MAX_RESULTS_PER_CALL,
            ),
        )

        if response is None:
            for channel_id in batch_ids:
                channel_country_map[channel_id] = UNKNOWN_COUNTRY
            continue

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            channel_country_map[item.get("id")] = snippet.get("country", UNKNOWN_COUNTRY)

        for channel_id in batch_ids:
            channel_country_map.setdefault(channel_id, UNKNOWN_COUNTRY)

    return channel_country_map


def build_video_entries(video_ids, key_states, quota_ledger, today_key, target_region=None):
    """查詢影片 statistics 與 channel country，回傳符合門檻的影片資料。"""
    if not video_ids:
        return []

    filtered_entries = []
    channel_ids_to_lookup = []

    for i in range(0, len(video_ids), MAX_RESULTS_PER_CALL):
        batch_ids = video_ids[i:i + MAX_RESULTS_PER_CALL]
        response, _ = run_api_list_request(
            key_states,
            quota_ledger,
            today_key,
            VIDEOS_LIST_COST_UNITS,
            "videos.list",
            lambda client: client.videos().list(
                part="snippet,statistics,status,contentDetails",
                id=",".join(batch_ids),
                maxResults=MAX_RESULTS_PER_CALL,
            ),
        )

        if response is None:
            print("No usable response from videos.list; skip current batch.")
            continue

        for item in response.get("items", []):
            status = item.get("status", {})
            upload_status = status.get("uploadStatus", "")
            privacy_status = status.get("privacyStatus", "")
            embeddable = status.get("embeddable", False)

            # Exclude videos that are not publicly playable or not embeddable in third-party players.
            if upload_status != "processed" or privacy_status != "public" or not embeddable:
                continue

            # Optional region-level playback check when we know which region this query is for.
            if isinstance(target_region, str) and target_region:
                restriction = item.get("contentDetails", {}).get("regionRestriction", {})
                blocked = restriction.get("blocked", [])
                allowed = restriction.get("allowed", [])
                if isinstance(blocked, list) and target_region in blocked:
                    continue
                if isinstance(allowed, list) and allowed and target_region not in allowed:
                    continue

            stats = item.get("statistics", {})
            view_count = int(stats.get("viewCount", 0))
            like_count = int(stats.get("likeCount", 0))
            if view_count < MIN_VIEW_COUNT or like_count < MIN_LIKE_COUNT:
                continue

            snippet = item.get("snippet", {})
            channel_id = snippet.get("channelId")
            video_id = item.get("id")
            default_lang = snippet.get("defaultLanguage")
            default_audio_lang = snippet.get("defaultAudioLanguage")
            if not video_id:
                continue

            filtered_entries.append(
                {
                    "video_id": video_id,
                    "channel_id": channel_id,
                    "channel_country": UNKNOWN_COUNTRY,
                    "default_language": default_lang,
                    "default_audio_language": default_audio_lang,
                }
            )
            if channel_id:
                channel_ids_to_lookup.append(channel_id)

    if not filtered_entries:
        return []

    channel_country_map = fetch_channel_country_map(
        channel_ids_to_lookup,
        key_states,
        quota_ledger,
        today_key,
    )

    # Language-based secondary classification
    def classify_country(channel_country, default_lang, default_audio_lang):
        # Normalize
        lang_set = set()
        for lang in (default_lang, default_audio_lang):
            if isinstance(lang, str):
                lang_set.add(lang.lower())
        # zh-hant, zh-tw => tw; zh-hans, zh-cn => cn
        if channel_country in (None, "", UNKNOWN_COUNTRY, OTHER_COUNTRY):
            if any(l in ("zh-hant", "zh-tw") for l in lang_set):
                return "tw"
            if any(l in ("zh-hans", "zh-cn") for l in lang_set):
                return "cn"
        return channel_country if channel_country not in (None, "") else UNKNOWN_COUNTRY

    for entry in filtered_entries:
        channel_id = entry.pop("channel_id", None)
        channel_country = channel_country_map.get(channel_id, UNKNOWN_COUNTRY)
        default_lang = entry.get("default_language")
        default_audio_lang = entry.get("default_audio_language")
        entry["channel_country"] = classify_country(channel_country, default_lang, default_audio_lang)

    return filtered_entries


def fetch_video_ids(region, lang, cat_id, calls_allowed, key_states, quota_ledger, today_key):
    """跨多把 API key 搜尋影片並回傳 (影片資料列表, 實際呼叫次數, 最後使用key名)。"""
    if calls_allowed <= 0:
        return [], 0, None

    all_entries = []
    calls_used = 0
    next_page_token = None
    last_key_name = None

    while calls_used < calls_allowed:
        key_state = next_available_key_state(key_states)
        if not key_state:
            break

        try:
            print(
                f"    Using API account: {key_state['name']} "
                f"(region={region}, category={cat_id}, call={calls_used + 1}/{calls_allowed})"
            )
            params = {
                "part": "id",
                "q": "#Shorts",
                "type": "video",
                "videoDuration": "short",
                "regionCode": region,
                "relevanceLanguage": lang,
                "videoCategoryId": cat_id,
                "maxResults": MAX_RESULTS_PER_CALL,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            request = key_state["client"].search().list(**params)
            response = request.execute()
            calls_used += 1
            last_key_name = key_state["name"]
            key_state["remaining_units"] -= SEARCH_COST_UNITS
            add_quota_usage(quota_ledger, key_state["name"], today_key, SEARCH_COST_UNITS)
            save_quota_ledger(QUOTA_LEDGER_FILE, quota_ledger)

            raw_ids = [item['id']['videoId'] for item in response.get('items', [])]
            filtered_entries = build_video_entries(
                raw_ids,
                key_states,
                quota_ledger,
                today_key,
                target_region=region,
            )
            all_entries.extend(filtered_entries)
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            reason, message = parse_http_error(e)

            if reason == "quotaExceeded":
                key_state["remaining_units"] = 0
                print(f"Key quota exhausted, switch key: {key_state['name']}")
                continue

            if e.resp.status == 403 and "ip address restriction" in message.lower():
                key_state["blocked"] = True
                key_state["remaining_units"] = 0
                print(
                    f"Key blocked by IP restriction, switch key: {key_state['name']}. "
                    "Please add current public IPv6/IPv4 to this key allowlist."
                )
                continue

            print(f"HttpError {e.resp.status} ({reason or 'unknown'}): {message or str(e)}")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

    return all_entries, calls_used, last_key_name


def build_key_states(quota_ledger):
    key_states = []
    total_calls_budget = 0
    for key_item in API_KEY:
        key_name = key_item["name"]
        _, used_units_before_run = get_today_usage(quota_ledger, key_name)
        remaining_units = max(0, DAILY_QUOTA_LIMIT - used_units_before_run)
        total_calls_budget += remaining_units // SEARCH_COST_UNITS
        key_states.append(
            {
                "name": key_name,
                "client": create_youtube_client(key_item["key"]),
                "used_before": used_units_before_run,
                "remaining_units": remaining_units,
                "blocked": False,
            }
        )
    return key_states, total_calls_budget


def to_output_file_payload(country_id, country_data):
    """非 other 檔輸出字串 ID；other 檔保留完整物件。"""
    payload = {}
    for category in CATEGORIES:
        entries = country_data.get(category, [])
        if country_id == OTHER_COUNTRY:
            payload[category] = entries
        else:
            payload[category] = [
                entry.get("video_id")
                for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("video_id"), str) and entry.get("video_id")
            ]
    return payload

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    quota_ledger = load_quota_ledger(QUOTA_LEDGER_FILE)
    today_key = quota_day_key()
    key_states, total_calls_budget = build_key_states(quota_ledger)

    used_calls = 0

    print(f"Quota ledger date: {today_key} (Google quota resets at UTC 00:00 = Taiwan 08:00 next day / 15:00 same day)")
    print(
        f"Filter thresholds: viewCount >= {MIN_VIEW_COUNT}, likeCount >= {MIN_LIKE_COUNT} "
        "(evaluated via videos.list statistics)."
    )
    print("Country detection: use uploader channel.snippet.country; missing values are stored as unknown.")
    for state in key_states:
        print(
            f"  {state['name']}: used {state['used_before']}/{DAILY_QUOTA_LIMIT} units, "
            f"remaining {state['remaining_units']} units "
            f"({state['remaining_units'] // SEARCH_COST_UNITS} search calls)."
        )

    if total_calls_budget <= 0:
        print("Stopped: no remaining daily quota budget across all API keys in local ledger.")
        return

    country_data_cache = {}
    for country in COUNTRIES:
        output_file_path = os.path.join(OUTPUT_DIR, f"shorts_{country['id']}.json")
        country_data_cache[country["id"]] = load_existing_country_data(output_file_path)

    pair_states = []
    for country in COUNTRIES:
        for app_cat, yt_cat_ids in CATEGORIES.items():
            pair_states.append(
                {
                    "country": country,
                    "category": app_cat,
                    "yt_cat_ids": yt_cat_ids,
                    "yt_rr_idx": 0,
                }
            )

    print(
        f"Quota plan: dynamically pick lowest language/category before each call "
        f"for {total_calls_budget} calls across {len(pair_states)} slots."
    )

    for plan_idx in range(total_calls_budget):
        if not has_remaining_calls(key_states):
            print("\nStopped: all API keys quota exhausted for today.")
            print(
                f"Usage before stop: {used_calls} calls / {total_calls_budget} planned calls "
                f"({used_calls * SEARCH_COST_UNITS} units this run)."
            )
            print("Per-key ledger now:")
            for state in key_states:
                key_today = quota_ledger.get(state["name"], {}).get(today_key, 0)
                status = "blocked" if state.get("blocked", False) else "ok"
                print(f"  {state['name']}: {key_today}/{DAILY_QUOTA_LIMIT} units ({status})")
            return

        target_pair = min(
            pair_states,
            key=lambda pair: len(
                country_data_cache[pair["country"]["id"]].get(pair["category"], [])
            ),
        )

        country = target_pair["country"]
        country_id = country["id"]
        app_cat = target_pair["category"]
        yt_cat_ids = target_pair["yt_cat_ids"]
        current_count = len(country_data_cache[country_id].get(app_cat, []))

        yt_id = yt_cat_ids[target_pair["yt_rr_idx"] % len(yt_cat_ids)]
        target_pair["yt_rr_idx"] += 1

        print(
            f"Processing[{plan_idx + 1}/{total_calls_budget}]: "
            f"{country_id.upper()}({country['lang']}) / {app_cat} "
            f"(existing={current_count}, ytCategory={yt_id})..."
        )

        entries, calls_used_now, used_key_name = fetch_video_ids(
            country["region"],
            country["lang"],
            yt_id,
            1,
            key_states,
            quota_ledger,
            today_key,
        )
        used_calls += calls_used_now

        if entries:
            entries_by_country = {}
            for entry in entries:
                output_country_id = resolve_output_country_id(entry.get("channel_country"))
                entries_by_country.setdefault(output_country_id, []).append(entry)

            account_note = used_key_name if used_key_name else "unknown"
            for output_country_id, country_entries in entries_by_country.items():
                output_file_path = os.path.join(OUTPUT_DIR, f"shorts_{output_country_id}.json")
                if output_country_id not in country_data_cache:
                    country_data_cache[output_country_id] = load_existing_country_data(output_file_path)

                output_country_data = country_data_cache[output_country_id]
                previous_category_entries = list(output_country_data[app_cat])
                output_country_data[app_cat] = merge_unique_video_entries(
                    output_country_data[app_cat],
                    country_entries,
                )

                if output_country_data[app_cat] == previous_category_entries:
                    print(
                        f"  Skipped unchanged: {output_file_path} "
                        f"({app_cat} remains {len(output_country_data[app_cat])} entries) "
                        f"[account: {account_note}]"
                    )
                    continue

                file_payload = to_output_file_payload(output_country_id, output_country_data)
                with open(output_file_path, 'w', encoding='utf-8') as f:
                    json.dump(file_payload, f, ensure_ascii=False, separators=(',', ':'))

                print(
                    f"  Saved: {output_file_path} ({app_cat} now {len(output_country_data[app_cat])} entries) "
                    f"[account: {account_note}]"
                )

    print(
        f"Done. Used {used_calls} calls ({used_calls * SEARCH_COST_UNITS} units), "
        f"planned budget {total_calls_budget} calls across {len(key_states)} keys."
    )
    print("Per-key ledger today:")
    for state in key_states:
        key_today = quota_ledger.get(state["name"], {}).get(today_key, 0)
        status = "blocked" if state.get("blocked", False) else "ok"
        print(f"  {state['name']}: {key_today}/{DAILY_QUOTA_LIMIT} units ({status})")

if __name__ == "__main__":
    main()
