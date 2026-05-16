import json
import os
from datetime import datetime, timezone

from shorts_config import (
    API_KEY,
    CATEGORIES,
    COUNTRY_OUTPUT_MAP,
    OTHER_COUNTRY,
    UNKNOWN_COUNTRY,
)


def distribute_evenly(total, slots):
    """平均分配整數配額，餘數依序+1。"""
    if slots <= 0:
        return []
    base = total // slots
    remainder = total % slots
    return [base + (1 if i < remainder else 0) for i in range(slots)]


def normalize_video_entry(entry):
    """將舊格式字串 ID 與新格式物件統一成相同資料結構。"""
    if isinstance(entry, str):
        return {
            "video_id": entry,
            "channel_country": UNKNOWN_COUNTRY,
        }

    if isinstance(entry, dict):
        video_id = entry.get("video_id") or entry.get("id")
        if isinstance(video_id, str) and video_id:
            return {
                "video_id": video_id,
                "channel_country": entry.get("channel_country", UNKNOWN_COUNTRY),
            }

    return None


def merge_unique_video_entries(existing_entries, new_entries):
    """依 video_id 合併清單，保留原本順序並用較完整的新資料覆蓋舊資料。"""
    merged = {}
    ordered_ids = []

    for entry in existing_entries + new_entries:
        normalized = normalize_video_entry(entry)
        if not normalized:
            continue

        video_id = normalized["video_id"]
        if video_id not in merged:
            ordered_ids.append(video_id)
            merged[video_id] = normalized
            continue

        if (
            merged[video_id].get("channel_country", UNKNOWN_COUNTRY) == UNKNOWN_COUNTRY
            and normalized.get("channel_country", UNKNOWN_COUNTRY) != UNKNOWN_COUNTRY
        ):
            merged[video_id] = normalized

    return [merged[video_id] for video_id in ordered_ids]


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
        items = raw.get(category, [])
        if not isinstance(items, list):
            result[category] = []
            continue

        normalized_items = []
        for item in items:
            normalized = normalize_video_entry(item)
            if normalized:
                normalized_items.append(normalized)
        result[category] = normalized_items
    return result


def resolve_output_country_id(channel_country):
    """將 channel country code 映射成輸出檔使用的 country id。"""
    if not isinstance(channel_country, str) or not channel_country.strip():
        return UNKNOWN_COUNTRY

    normalized_country = channel_country.strip().lower()
    return COUNTRY_OUTPUT_MAP.get(normalized_country, OTHER_COUNTRY)


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
