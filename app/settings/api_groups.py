"""Versioned API group contracts; no environment or filesystem access."""
import json
import math
import re
from hashlib import sha256
from dataclasses import asdict, dataclass, field
from uuid import uuid4
from urllib.parse import urlsplit

from app.settings.model import SettingsValidationError


SCHEMA_VERSION = 1
ENV_SCHEMA_VERSION = 2
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def managed_key_name(key_id: str) -> str:
    digest = sha256(key_id.encode("utf-8")).hexdigest()[:24].upper()
    return f"NOVA_API_KEY_{digest}"


class APIGroupDataError(SettingsValidationError):
    """Safe errors must never include input payloads or credentials."""


@dataclass(frozen=True)
class APIGroupKey:
    id: str
    name: str
    key: str = field(default="", repr=False)
    priority: int = 1
    enabled: bool = True
    source: str = "stored"
    environment_variable: str = ""


@dataclass(frozen=True)
class APIGroup:
    id: str
    name: str
    base_url: str
    model: str
    temperature: float = 0.7
    verify_ssl: bool = True
    auth_mode: str = "api_key"
    keys: tuple[APIGroupKey, ...] = ()


@dataclass(frozen=True)
class APIGroupSettings:
    groups: tuple[APIGroup, ...] = ()
    active_group_id: str | None = None
    schema_version: int = SCHEMA_VERSION


def _require(condition, message):
    if not condition:
        raise APIGroupDataError(message)


def _text(value, label, allow_empty=False):
    _require(type(value) is str and (allow_empty or bool(value.strip())), f"{label}格式無效。")


def validate_api_groups(settings: APIGroupSettings) -> None:
    _require(type(settings) is APIGroupSettings, "API 群組容器格式無效。")
    _require(type(settings.schema_version) is int and settings.schema_version in (SCHEMA_VERSION, ENV_SCHEMA_VERSION),
             "不支援的 API 群組版本。")
    _require(type(settings.groups) is tuple, "API 群組列表格式無效。")
    _require(settings.active_group_id is None or type(settings.active_group_id) is str,
             "目前 API 群組引用格式無效。")
    group_ids, key_ids, managed_variables = set(), set(), set()
    for group in settings.groups:
        _require(type(group) is APIGroup, "API 群組格式無效。")
        for value, label in ((group.id, "群組 ID"), (group.name, "群組名稱"),
                             (group.base_url, "Base URL"), (group.model, "模型")):
            _text(value, label)
        _require(group.id == group.id.strip() and group.id not in group_ids, "群組 ID 重複或無效。")
        group_ids.add(group.id)
        try:
            parsed = urlsplit(group.base_url)
            _ = parsed.port  # Validate malformed/out-of-range port values as well.
            valid_url = (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                         and parsed.username is None and parsed.password is None
                         and not parsed.query and not parsed.fragment
                         and not any(c.isspace() for c in group.base_url))
        except ValueError:
            valid_url = False
        _require(valid_url, "Base URL 必須是無帳密、查詢參數或片段的 HTTP／HTTPS 網址。")
        _require(type(group.temperature) in (int, float) and 0 <= group.temperature <= 2
                 and math.isfinite(group.temperature), "溫度必須介於 0.0–2.0。")
        _require(type(group.verify_ssl) is bool, "SSL 驗證狀態格式無效。")
        _require(group.auth_mode in ("api_key", "none"), "驗證模式無效。")
        _require(type(group.keys) is tuple, "API Key 列表格式無效。")
        for entry in group.keys:
            _require(type(entry) is APIGroupKey, "API Key 格式無效。")
            _text(entry.id, "Key ID")
            _text(entry.name, "Key 名稱")
            _require(entry.id == entry.id.strip() and entry.id not in key_ids, "Key ID 重複或無效。")
            key_ids.add(entry.id)
            _require(type(entry.priority) is int and 1 <= entry.priority <= 10, "Key 順位必須為 1–10 整數。")
            _require(type(entry.enabled) is bool, "Key 啟用狀態格式無效。")
            _text(entry.key, "Key 內容", allow_empty=True)
            _text(entry.environment_variable, "環境變數引用", allow_empty=True)
            if settings.schema_version == SCHEMA_VERSION and entry.source == "stored":
                _require(bool(entry.key.strip()) and not entry.environment_variable, "儲存 Key 內容或來源無效。")
            elif settings.schema_version == SCHEMA_VERSION and entry.source == "environment":
                _require(not entry.key and entry.environment_variable == "OPENAI_API_KEY", "環境 Key 只能保存 OPENAI_API_KEY 引用。")
            elif settings.schema_version == ENV_SCHEMA_VERSION and entry.source == "stored":
                _require(bool(entry.key.strip()) or bool(_ENV_NAME.fullmatch(entry.environment_variable)),
                         "儲存 Key 缺少內容或環境變數引用。")
                _require(not entry.environment_variable or entry.environment_variable == managed_key_name(entry.id),
                         "環境變數引用格式無效。")
                if entry.environment_variable:
                    _require(entry.environment_variable not in managed_variables, "儲存 Key 的環境變數引用重複。")
                    managed_variables.add(entry.environment_variable)
            elif settings.schema_version == ENV_SCHEMA_VERSION and entry.source == "environment":
                _require(not entry.key and bool(_ENV_NAME.fullmatch(entry.environment_variable)),
                         "環境變數引用格式無效。")
            else:
                raise APIGroupDataError("Key 來源無效。")
    _require(settings.active_group_id is None or settings.active_group_id in group_ids,
             "目前 API 群組引用不存在。")


def serialize_api_groups(settings: APIGroupSettings) -> str:
    validate_api_groups(settings)
    payload = asdict(settings)
    if settings.schema_version == ENV_SCHEMA_VERSION:
        for group in payload["groups"]:
            for key in group["keys"]:
                _require(not key["key"] and key["environment_variable"],
                         "尚有未存入 .env 的金鑰；設定未保存。")
                key.pop("key")
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def deserialize_api_groups(text: str) -> APIGroupSettings:
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
        _require(type(payload) is dict and set(payload) == {"schema_version", "active_group_id", "groups"},
                 "API 群組容器欄位無效。")
        _require(type(payload["schema_version"]) is int and payload["schema_version"] in (SCHEMA_VERSION, ENV_SCHEMA_VERSION),
                 "不支援的 API 群組版本。")
        _require(type(payload["groups"]) is list, "API 群組列表格式無效。")
        groups = []
        for item in payload["groups"]:
            _require(type(item) is dict and set(item) == set(APIGroup.__dataclass_fields__), "API 群組欄位無效。")
            _require(type(item["keys"]) is list, "API Key 列表格式無效。")
            keys = []
            for key in item["keys"]:
                expected = set(APIGroupKey.__dataclass_fields__)
                if payload["schema_version"] == ENV_SCHEMA_VERSION:
                    expected.remove("key")
                _require(type(key) is dict and set(key) == expected, "API Key 欄位無效。")
                keys.append(APIGroupKey(**key))
            groups.append(APIGroup(**{**item, "keys": tuple(keys)}))
        settings = APIGroupSettings(tuple(groups), payload["active_group_id"], payload["schema_version"])
        validate_api_groups(settings)
        return settings
    except APIGroupDataError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise APIGroupDataError("API 群組檔案無法解析；原資料未修改。") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "API 群組檔案包含重複欄位。")
        result[key] = value
    return result


def migrate_legacy_api(legacy: dict, environment_available: bool = False) -> APIGroupSettings:
    """Pure conversion of stored INI fields; environment contents are never passed in."""
    _require(type(environment_available) is bool, "環境來源狀態無效。")
    _require(type(legacy) is dict and all(type(k) is str and type(v) is str for k, v in legacy.items()),
             "舊 API 設定格式無效。")
    values = {k.lower(): v for k, v in legacy.items()}
    try:
        raw_keys = json.loads(values.get("apikeys") or "[]", object_pairs_hook=_unique_object)
        _require(type(raw_keys) is list, "舊 API Key 列表格式無效。")
        entries = []
        for item in raw_keys:
            _require(type(item) is dict and set(item) <= {"name", "key"}, "舊 API Key 欄位無效。")
            key = item.get("key", "")
            name = item.get("name", "")
            _text(key, "舊 Key", allow_empty=True)
            _text(name, "舊 Key 名稱", allow_empty=True)
            if key.strip():
                entries.append((name.strip() or f"Key {len(entries) + 1}", key.strip()))
        if not entries and values.get("apikey", "").strip():
            entries.append(("Key 1", values["apikey"].strip()))
        configured = bool(entries or environment_available or any(
            values.get(field, "").strip() for field in ("baseurl", "model")))
        if not configured:
            return APIGroupSettings()
        keys = [APIGroupKey(str(uuid4()), name, key, min(i, 10))
                for i, (name, key) in enumerate(entries, 1)]
        if environment_available:
            keys.insert(0, APIGroupKey(str(uuid4()), "環境變數", source="environment",
                                      environment_variable="OPENAI_API_KEY"))
        ssl = values.get("verifyssl", "true").strip().lower()
        _require(ssl in ("true", "false"), "舊 SSL 驗證設定格式無效。")
        group = APIGroup(str(uuid4()), "預設 API", values.get("baseurl", "https://api.openai.com/v1").strip(),
                         values.get("model", "gpt-4o-mini").strip(), float(values.get("temperature", "0.7")),
                         ssl == "true", keys=tuple(keys))
        settings = APIGroupSettings((group,), group.id)
        validate_api_groups(settings)
        return settings
    except APIGroupDataError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise APIGroupDataError("舊 API 設定無法轉換；原資料未修改。") from None
