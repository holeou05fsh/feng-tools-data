import os
import json
from datetime import date, datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ================= 配置區域 =================
# API_KEY有設IP限制不需要從環境變數讀取，直接寫在這裡
API_KEY = [
    {"key":"AIzaSyBzC4FX_Vr0DK5eVL7lv2NQ_pm_JQ1GT64", "name":"fengtuber0815"},
    {"key":"AIzaSyBpr5ezpYIYUEQdxp1WBXkkmhFhrQvHpN4", "name":"holeou05fsh"},
]

OUTPUT_DIR = '.'
QUOTA_LEDGER_FILE = './quota_ledger.json'
DAILY_QUOTA_LIMIT = 10000
SEARCH_COST_UNITS = 100
MAX_RESULTS_PER_CALL = 50

# 國家清單
COUNTRIES = [
    # values (default/global fallback)
    {"id": "us", "region": "US", "lang": "en"},
    # values-zh-rTW
    {"id": "tw", "region": "TW", "lang": "zh-Hant"},
    # values-zh-rCN
    {"id": "cn", "region": "CN", "lang": "zh-Hans"},
    # values-ja
    {"id": "jp", "region": "JP", "lang": "ja"},
    # values-ko
    {"id": "kr", "region": "KR", "lang": "ko"},
    # values-en-rIN
    {"id": "in", "region": "IN", "lang": "en"},
    # values-hi
    {"id": "in_hi", "region": "IN", "lang": "hi"},
    # values-es
    {"id": "es", "region": "ES", "lang": "es"},
    # values-pt-rBR
    {"id": "br", "region": "BR", "lang": "pt"},
    # values-in (Android legacy code, use id for API language)
    {"id": "id", "region": "ID", "lang": "id"},
    # values-vi
    {"id": "vn", "region": "VN", "lang": "vi"},
    # values-fil
    {"id": "ph", "region": "PH", "lang": "fil"},
    # values-ur
    {"id": "pk", "region": "PK", "lang": "ur"},
]

# 分類映射
CATEGORIES = {
    "film":      ["1"],        # 電影與動畫
    "autos":     ["2"],        # 汽車與車輛
    "music":     ["10"],       # 音樂
    "pets":      ["15"],       # 寵物與動物
    "sports":    ["17"],       # 體育
    "gaming":    ["20"],       # 遊戲
    "people":    ["22"],       # 人物與部落格
    "funny":     ["23", "24"], # 搞笑 + 娛樂
    "news":      ["25"],       # 新聞與政治
    "lifestyle": ["26"],       # 生活與風格
    "education": ["27"],       # 教育
    "tech":      ["28"],       # 科技
}

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

def distribute_evenly(total, slots):
    """平均分配整數配額，餘數依序+1。"""
    if slots <= 0:
        return []
    base = total // slots
    remainder = total % slots
    return [base + (1 if i < remainder else 0) for i in range(slots)]


def merge_unique(existing_ids, new_ids):
    """合併兩個清單並去重，保留原本順序。"""
    return list(dict.fromkeys(existing_ids + new_ids))


def load_existing_country_data(file_path):
    """讀取既有輸出檔，若不存在或格式不正確則回傳空分類。"""
    default_data = {category: [] for category in CATEGORIES}
    if not os.path.exists(file_path):
        return default_data

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return default_data

    if not isinstance(raw, dict):
        return default_data

    result = {}
    for category in CATEGORIES:
        ids = raw.get(category, [])
        result[category] = ids if isinstance(ids, list) else []
    return result


def load_quota_ledger(file_path):
    """讀取每日配額帳本。"""
    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return {}

    return raw if isinstance(raw, dict) else {}


def save_quota_ledger(file_path, ledger):
    """寫入每日配額帳本。"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, ensure_ascii=False, separators=(',', ':'))


def quota_day_key():
    """以 UTC 日期作為配額週期 key（Google 在 UTC 00:00 = 台灣 08:00 下午3點重置）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d(UTC)")


def get_today_usage(ledger, key_name):
    """取得指定 API key 今日已用 units。"""
    today_key = quota_day_key()
    key_ledger = ledger.get(key_name, {})
    if isinstance(key_ledger, dict):
        value = key_ledger.get(today_key, 0)
        return today_key, value if isinstance(value, int) else 0

    # 向後相容: 舊格式是 {"YYYY-MM-DD": units}
    legacy_value = ledger.get(today_key, 0)
    if key_name == API_KEY[0]["name"] and isinstance(legacy_value, int):
        return today_key, legacy_value
    value = 0
    return today_key, value if isinstance(value, int) else 0


def add_quota_usage(ledger, key_name, day_key, units):
    """累加指定 API key 今日已用 units。"""
    if key_name not in ledger or not isinstance(ledger.get(key_name), dict):
        ledger[key_name] = {}
    ledger[key_name][day_key] = ledger[key_name].get(day_key, 0) + units


def has_remaining_calls(key_states):
    return any(state["remaining_units"] >= SEARCH_COST_UNITS for state in key_states)


def next_available_key_state(key_states):
    for state in key_states:
        if state["remaining_units"] >= SEARCH_COST_UNITS and not state.get("blocked", False):
            return state
    return None


def fetch_video_ids(region, lang, cat_id, calls_allowed, key_states, quota_ledger, today_key):
    """跨多把 API key 搜尋影片並回傳 (影片ID列表, 實際呼叫次數, 最後使用key名)。"""
    if calls_allowed <= 0:
        return [], 0, None

    all_ids = []
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

            all_ids.extend(item['id']['videoId'] for item in response.get('items', []))
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

    return all_ids, calls_used, last_key_name

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    quota_ledger = load_quota_ledger(QUOTA_LEDGER_FILE)
    key_states = []
    total_calls_budget = 0
    today_key = quota_day_key()

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

    used_calls = 0

    print(f"Quota ledger date: {today_key} (Google quota resets at UTC 00:00 = Taiwan 08:00 next day / 15:00 same day)")
    for state in key_states:
        print(
            f"  {state['name']}: used {state['used_before']}/{DAILY_QUOTA_LIMIT} units, "
            f"remaining {state['remaining_units']} units "
            f"({state['remaining_units'] // SEARCH_COST_UNITS} search calls)."
        )

    if total_calls_budget <= 0:
        print("Stopped: no remaining daily quota budget across all API keys in local ledger.")
        return

    # 先掃描所有 country × category 的現有 ID 數，由少到多排序
    all_pairs = []
    for country in COUNTRIES:
        fp = os.path.join(OUTPUT_DIR, f"shorts_{country['id']}.json")
        existing_data = load_existing_country_data(fp)
        for app_cat, yt_cat_ids in CATEGORIES.items():
            existing_count = len(existing_data.get(app_cat, []))
            all_pairs.append((existing_count, country, app_cat, yt_cat_ids))

    all_pairs.sort(key=lambda x: x[0])
    pair_call_plan = distribute_evenly(total_calls_budget, len(all_pairs))

    print(
        f"Quota plan: distribute {total_calls_budget} search calls across "
        f"{len(all_pairs)} slots (sorted by fewest existing IDs first)."
    )

    # 依排序後順序執行，共用 country_data cache 避免重複讀檔
    country_data_cache = {}
    for idx, (existing_count, country, app_cat, yt_cat_ids) in enumerate(all_pairs):
        country_id = country['id']
        file_path = os.path.join(OUTPUT_DIR, f"shorts_{country_id}.json")

        if country_id not in country_data_cache:
            country_data_cache[country_id] = load_existing_country_data(file_path)
        country_data = country_data_cache[country_id]

        pair_calls = pair_call_plan[idx]
        if pair_calls <= 0:
            continue

        yt_call_plan = distribute_evenly(pair_calls, len(yt_cat_ids))
        print(f"Processing: {country_id.upper()} / {app_cat} (existing={existing_count}, calls={pair_calls})...")

        for yt_id, calls_allowed in zip(yt_cat_ids, yt_call_plan):
            ids, calls_used_now, used_key_name = fetch_video_ids(
                country['region'],
                country['lang'],
                yt_id,
                calls_allowed,
                key_states,
                quota_ledger,
                today_key,
            )
            used_calls += calls_used_now

            if ids:
                country_data[app_cat] = merge_unique(country_data[app_cat], ids)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(country_data, f, ensure_ascii=False, separators=(',', ':'))
                account_note = used_key_name if used_key_name else "unknown"
                print(
                    f"  Saved: {file_path} ({app_cat} now {len(country_data[app_cat])} IDs) "
                    f"[account: {account_note}]"
                )

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
