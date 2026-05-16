import json
import os

from shorts_config import (
    CATEGORIES,
    DAILY_QUOTA_LIMIT,
    OTHER_COUNTRY,
    OUTPUT_DIR,
    QUOTA_LEDGER_FILE,
    UNKNOWN_COUNTRY,
)
from shorts_common import (
    load_existing_country_data,
    load_quota_ledger,
    merge_unique_video_entries,
    quota_day_key,
    resolve_output_country_id,
)

from youtube_shorts import (
    build_video_entries,
    build_key_states,
)

SOURCE_PREFIX = "shorts_"
TARGET_PREFIX = "new_shorts_"
SKIP_SOURCE_FILES = {"shorts_product.json"}


def list_source_files():
    files = []
    for name in sorted(os.listdir(OUTPUT_DIR)):
        if not name.startswith(SOURCE_PREFIX) or not name.endswith(".json"):
            continue
        if name.startswith(TARGET_PREFIX) or name in SKIP_SOURCE_FILES:
            continue
        files.append(os.path.join(OUTPUT_DIR, name))
    return files


def collect_video_categories(source_files):
    video_categories = {}
    for file_path in source_files:
        country_data = load_existing_country_data(file_path)
        for category in CATEGORIES:
            for entry in country_data.get(category, []):
                video_id = entry.get("video_id")
                if not video_id:
                    continue
                video_categories.setdefault(video_id, set()).add(category)
    return video_categories


def merge_unique_ids(existing_ids, new_ids):
    return list(dict.fromkeys(existing_ids + new_ids))


def build_output_data(video_categories, entries):
    output_data = {}
    for entry in entries:
        video_id = entry.get("video_id")
        if not video_id:
            continue

        output_country_id = resolve_output_country_id(entry.get("channel_country"))
        output_data.setdefault(output_country_id, {category: [] for category in CATEGORIES})

        for category in video_categories.get(video_id, set()):
            if output_country_id == OTHER_COUNTRY:
                output_data[output_country_id][category] = merge_unique_video_entries(
                    output_data[output_country_id][category],
                    [entry],
                )
            else:
                output_data[output_country_id][category] = merge_unique_ids(
                    output_data[output_country_id][category],
                    [video_id],
                )
    return output_data


def write_output_files(output_data):
    target_country_ids = set(output_data.keys()) | {UNKNOWN_COUNTRY, OTHER_COUNTRY}
    written = 0
    skipped = 0

    for country_id in sorted(target_country_ids):
        file_path = os.path.join(OUTPUT_DIR, f"{TARGET_PREFIX}{country_id}.json")
        data = output_data.get(country_id, {category: [] for category in CATEGORIES})
        new_content = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

        old_content = None
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                old_content = f.read()

        if old_content == new_content:
            skipped += 1
            continue

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        written += 1

    return written, skipped


def clear_source_files(source_files):
    cleared = 0
    for file_path in source_files:
        source_data = load_existing_country_data(file_path)
        if not any(source_data.get(category) for category in CATEGORIES):
            continue

        empty_data = {category: [] for category in CATEGORIES}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(empty_data, f, ensure_ascii=False, separators=(",", ":"))
        cleared += 1

    return cleared


def print_quota_status(key_states, quota_ledger, today_key):
    print("Per-key ledger today:")
    for state in key_states:
        key_today = quota_ledger.get(state["name"], {}).get(today_key, 0)
        status = "blocked" if state.get("blocked", False) else "ok"
        print(f"  {state['name']}: {key_today}/{DAILY_QUOTA_LIMIT} units ({status})")


def main():
    source_files = list_source_files()
    if not source_files:
        print("Stopped: no source shorts_*.json files found.")
        return

    print(f"Source files: {len(source_files)}")
    for file_path in source_files:
        print(f"  {os.path.basename(file_path)}")

    video_categories = collect_video_categories(source_files)
    video_ids = list(video_categories.keys())
    if not video_ids:
        print("Stopped: no video IDs found in source files.")
        return

    quota_ledger = load_quota_ledger(QUOTA_LEDGER_FILE)
    today_key = quota_day_key()
    key_states, _ = build_key_states(quota_ledger)

    print(f"Quota ledger date: {today_key}")
    for state in key_states:
        print(
            f"  {state['name']}: used {state['used_before']}/{DAILY_QUOTA_LIMIT} units, "
            f"remaining {state['remaining_units']} units."
        )

    print(f"Checking {len(video_ids)} unique IDs against current thresholds and channel country...")
    entries = build_video_entries(video_ids, key_states, quota_ledger, today_key)
    output_data = build_output_data(video_categories, entries)
    written_count, skipped_count = write_output_files(output_data)
    cleared_source_count = clear_source_files(source_files)

    retained_ids = {entry["video_id"] for entry in entries if entry.get("video_id")}
    dropped_count = len(video_ids) - len(retained_ids)
    print(f"Done. Retained {len(retained_ids)} IDs, dropped {dropped_count} IDs.")

    for country_id in sorted(output_data):
        total_entries = sum(len(output_data[country_id][category]) for category in CATEGORIES)
        print(f"  {TARGET_PREFIX}{country_id}.json: {total_entries} entries")

    print(f"Files written: {written_count}, unchanged skipped: {skipped_count}")
    print(f"Source files cleared: {cleared_source_count}")

    print_quota_status(key_states, quota_ledger, today_key)


if __name__ == "__main__":
    main()