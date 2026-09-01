import json
from typing import Any, Iterable


def decode_api_key_entries(raw_text: str, legacy_key: str = "") -> list[dict[str, str]]:
    entries = []
    try:
        payload = json.loads(raw_text or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = []

    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            name = str(item.get("name") or f"Key {index}").strip() or f"Key {index}"
            if key:
                entries.append({"name": name, "key": key})

    fallback_key = (legacy_key or "").strip()
    if not entries and fallback_key:
        entries.append({"name": "Key 1", "key": fallback_key})

    return entries


def encode_api_key_entries(entries: Iterable[dict[str, Any]]) -> str:
    cleaned = []
    for index, item in enumerate(entries, start=1):
        key = str(item.get("key") or "").strip()
        name = str(item.get("name") or f"Key {index}").strip() or f"Key {index}"
        if key:
            cleaned.append({"name": name, "key": key})
    return json.dumps(cleaned, ensure_ascii=False)


def first_api_key(entries: Iterable[dict[str, Any]]) -> str:
    for item in entries:
        key = str(item.get("key") or "").strip()
        if key:
            return key
    return ""
