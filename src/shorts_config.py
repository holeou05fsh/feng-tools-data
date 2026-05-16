API_KEY = [
    {"key": "AIzaSyBzC4FX_Vr0DK5eVL7lv2NQ_pm_JQ1GT64", "name": "fengtuber0815"},
    {"key": "AIzaSyBpr5ezpYIYUEQdxp1WBXkkmhFhrQvHpN4", "name": "holeou05fsh"},
]

OUTPUT_DIR = "."
QUOTA_LEDGER_FILE = "./quota_ledger.json"
DAILY_QUOTA_LIMIT = 10000
SEARCH_COST_UNITS = 100
VIDEOS_LIST_COST_UNITS = 1
CHANNELS_LIST_COST_UNITS = 1
MAX_RESULTS_PER_CALL = 50
MIN_VIEW_COUNT = 10000
MIN_LIKE_COUNT = 500
UNKNOWN_COUNTRY = "unknown"
OTHER_COUNTRY = "other"

COUNTRIES = [
    {"id": "us", "region": "US", "lang": "en"},
    {"id": "tw", "region": "TW", "lang": "zh-Hant"},
    {"id": "cn", "region": "CN", "lang": "zh-Hans"},
    {"id": "jp", "region": "JP", "lang": "ja"},
    {"id": "kr", "region": "KR", "lang": "ko"},
    {"id": "in", "region": "IN", "lang": "hi"},
    {"id": "es", "region": "ES", "lang": "es"},
    {"id": "br", "region": "BR", "lang": "pt"},
    {"id": "id", "region": "ID", "lang": "id"},
    {"id": "vn", "region": "VN", "lang": "vi"},
    {"id": "ph", "region": "PH", "lang": "fil"},
    {"id": "pk", "region": "PK", "lang": "ur"},
# ==================================================
    {"id": "ae", "region": "AE", "lang": "ar"},
    {"id": "ar", "region": "AR", "lang": "es"},
    {"id": "at", "region": "AT", "lang": "de"},
    {"id": "au", "region": "AU", "lang": "en"},
    {"id": "ba", "region": "BA", "lang": "bs"},
    {"id": "bd", "region": "BD", "lang": "bn"},
    {"id": "be", "region": "BE", "lang": "fr"},
    {"id": "bg", "region": "BG", "lang": "bg"},
    {"id": "bo", "region": "BO", "lang": "es"},
    {"id": "by", "region": "BY", "lang": "ru"},
    {"id": "ca", "region": "CA", "lang": "en"},
    {"id": "ch", "region": "CH", "lang": "de"},
    {"id": "cl", "region": "CL", "lang": "es"},
    {"id": "co", "region": "CO", "lang": "es"},
    {"id": "cy", "region": "CY", "lang": "el"},
    {"id": "cz", "region": "CZ", "lang": "cs"},
    {"id": "de", "region": "DE", "lang": "de"},
    {"id": "do", "region": "DO", "lang": "es"},
    {"id": "ec", "region": "EC", "lang": "es"},
    {"id": "ee", "region": "EE", "lang": "et"},
    {"id": "eg", "region": "EG", "lang": "ar"},
    {"id": "fi", "region": "FI", "lang": "fi"},
    {"id": "fr", "region": "FR", "lang": "fr"},
    {"id": "gb", "region": "GB", "lang": "en"},
    {"id": "ge", "region": "GE", "lang": "ka"},
    {"id": "gt", "region": "GT", "lang": "es"},
    {"id": "hk", "region": "HK", "lang": "zh-Hant"},
    {"id": "hn", "region": "HN", "lang": "es"},
    {"id": "hu", "region": "HU", "lang": "hu"},
    {"id": "ie", "region": "IE", "lang": "en"},
    {"id": "il", "region": "IL", "lang": "he"},
    {"id": "is", "region": "IS", "lang": "is"},
    {"id": "it", "region": "IT", "lang": "it"},
    {"id": "ke", "region": "KE", "lang": "en"},
    {"id": "kh", "region": "KH", "lang": "km"},
    {"id": "kz", "region": "KZ", "lang": "ru"},
    {"id": "lk", "region": "LK", "lang": "si"},
    {"id": "lt", "region": "LT", "lang": "lt"},
    {"id": "ma", "region": "MA", "lang": "ar"},
    {"id": "mc", "region": "MC", "lang": "fr"},
    {"id": "me", "region": "ME", "lang": "sr"},
    {"id": "mx", "region": "MX", "lang": "es"},
    {"id": "my", "region": "MY", "lang": "ms"},
    {"id": "ng", "region": "NG", "lang": "en"},
    {"id": "nl", "region": "NL", "lang": "nl"},
    {"id": "no", "region": "NO", "lang": "no"},
    {"id": "np", "region": "NP", "lang": "ne"},
    {"id": "nz", "region": "NZ", "lang": "en"},
    {"id": "om", "region": "OM", "lang": "ar"},
    {"id": "pe", "region": "PE", "lang": "es"},
    {"id": "pl", "region": "PL", "lang": "pl"},
    {"id": "pr", "region": "PR", "lang": "es"},
    {"id": "pt", "region": "PT", "lang": "pt"},
    {"id": "py", "region": "PY", "lang": "es"},
    {"id": "qa", "region": "QA", "lang": "ar"},
    {"id": "ro", "region": "RO", "lang": "ro"},
    {"id": "rs", "region": "RS", "lang": "sr"},
    {"id": "ru", "region": "RU", "lang": "ru"},
    {"id": "sa", "region": "SA", "lang": "ar"},
    {"id": "se", "region": "SE", "lang": "sv"},
    {"id": "sg", "region": "SG", "lang": "en"},
    {"id": "sk", "region": "SK", "lang": "sk"},
    {"id": "sn", "region": "SN", "lang": "fr"},
    {"id": "th", "region": "TH", "lang": "th"},
    {"id": "tr", "region": "TR", "lang": "tr"},
    {"id": "tz", "region": "TZ", "lang": "sw"},
    {"id": "ua", "region": "UA", "lang": "uk"},
    {"id": "ug", "region": "UG", "lang": "en"},
    {"id": "uy", "region": "UY", "lang": "es"},
    {"id": "ve", "region": "VE", "lang": "es"},
    {"id": "za", "region": "ZA", "lang": "en"},
]

COUNTRY_OUTPUT_MAP = {
    country["region"].lower(): country["id"]
    for country in COUNTRIES
}

CATEGORIES = {
    "film": ["1"],
    "autos": ["2"],
    "music": ["10"],
    "pets": ["15"],
    "sports": ["17"],
    "gaming": ["20"],
    "people": ["22"],
    "funny": ["23", "24"],
    "news": ["25"],
    "lifestyle": ["26"],
    "education": ["27"],
    "tech": ["28"],
}