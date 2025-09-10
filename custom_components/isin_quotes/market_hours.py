"""Market hours scaffold for isin_quotes.

Add/modify entries in MARKET_HOURS to control polling by exchange.
If an exchange code is **not** present in MARKET_HOURS, the coordinator
will poll continuously using the **user-provided** interval.

Schema per exchange code (example):
{
    "TGT": {
        "name": "Direkthandel",
        "tz": "Europe/Berlin",  # IANA timezone for local market time
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
}
"""
from __future__ import annotations
from typing import Dict, Any

# Weekday order helper: 0..6 matches datetime.weekday()
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Empty string for a day means: closed that day.
MARKET_HOURS: Dict[str, Dict[str, Any]] = {
    "TGT": {
        "name": "Direkthandel",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "FRA": {
        "name": "Frankfurt",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "STU": {
        "name": "Stuttgart",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "DUS": {
        "name": "Düsseldorf",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"20:00","tue":"20:00","wed":"20:00","thu":"20:00","fri":"20:00","sat":"","sun":""},
    },
    "ETR": {
        "name": "XETRA",
        "tz": "Europe/Berlin",
        "open":  {"mon":"09:00","tue":"09:00","wed":"09:00","thu":"09:00","fri":"09:00","sat":"","sun":""},
        "close": {"mon":"17:30","tue":"17:30","wed":"17:30","thu":"17:30","fri":"17:30","sat":"","sun":""},
    },
    "MUC": {
        "name": "München",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "BEB": {
        "name": "Berlin",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"20:00","tue":"20:00","wed":"20:00","thu":"20:00","fri":"20:00","sat":"","sun":""},
    },
    "HAM": {
        "name": "Hamburg",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "HAJ": {
        "name": "Hannover",
        "tz": "Europe/Berlin",
        "open":  {"mon":"08:00","tue":"08:00","wed":"08:00","thu":"08:00","fri":"08:00","sat":"","sun":""},
        "close": {"mon":"22:00","tue":"22:00","wed":"22:00","thu":"22:00","fri":"22:00","sat":"","sun":""},
    },
    "UTC": {
        "name": "Nasdaq",
        "tz": "Amerika/New_York",
        "open":  {"mon":"09:30","tue":"09:30","wed":"09:30","thu":"09:30","fri":"09:30","sat":"","sun":""},
        "close": {"mon":"16:00","tue":"16:00","wed":"16:00","thu":"16:00","fri":"16:00","sat":"","sun":""},
    },
    "USC": {
        "name": "New York Stock Exchange",
        "tz": "Amerika/New_York",
        "open":  {"mon":"09:30","tue":"09:30","wed":"09:30","thu":"09:30","fri":"09:30","sat":"","sun":""},
        "close": {"mon":"16:00","tue":"16:00","wed":"16:00","thu":"16:00","fri":"16:00","sat":"","sun":""},
    },
}