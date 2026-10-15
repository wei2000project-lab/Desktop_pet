"""Background connection checks with credential-free result messages."""
import re

from dataclasses import dataclass, replace
from app.settings.api_groups import APIGroupSettings
from app.settings.api_group_resolver import resolve_api_request
from app.settings.model import SettingsValidationError

from app.ai.client import AIClient
from app.ai.errors import AIErrorCategory, AIRequestError


def safe_failure_message(error: Exception) -> str:
    # Never forward server bodies, URLs, headers or exception text to the UI/log.
    if isinstance(error, AIRequestError):
        messages = {
            AIErrorCategory.AUTHENTICATION: "驗證失敗，請確認金鑰。",
            AIErrorCategory.PERMISSION: "存取遭拒，請確認帳號、模型與權限。",
            AIErrorCategory.RATE_LIMIT: "服務限制請求，請稍後再試。",
            AIErrorCategory.QUOTA: "服務額度不足，請確認帳號與方案。",
            AIErrorCategory.MODEL: "模型不存在或目前無法使用。",
            AIErrorCategory.TIMEOUT: "連線逾時，請確認服務狀態或稍後再試。",
            AIErrorCategory.TLS: "TLS 憑證驗證失敗，請確認 SSL 設定。",
            AIErrorCategory.CONNECTION: "無法連線，請確認網址、網路與服務狀態。",
        }
        return messages.get(error.category, "連線測試失敗，請確認網址、模型、金鑰及服務狀態。")
    text = str(error)
    match = re.search(r"\bHTTP (\d{3})\b", text)
    if match:
        status = int(match.group(1))
        if status in (401, 403):
            return "驗證失敗，請確認金鑰與存取權限。"
        if status == 429:
            return "服務限制請求，請確認額度或稍後再試。"
        return f"服務回傳 HTTP {status}，請確認網址與模型設定。"
    if "逾時" in text or "timeout" in text.lower():
        return "連線逾時，請確認服務狀態或稍後再試。"
    return "連線測試失敗，請確認網址、模型、金鑰及服務狀態。"


@dataclass(frozen=True)
class ConnectionCheckResult:
    success: bool
    message: str


def run_connection_test(base_url, api_key, model, verify_ssl):
    """One synchronous check; callers choose how to schedule it."""
    try:
        client = AIClient(base_url=base_url, api_key=api_key, model=model,
                          verify_ssl=verify_ssl, timeout=15.0)
        client.test_connection()
    except Exception as error:
        return ConnectionCheckResult(False, safe_failure_message(error))
    return ConnectionCheckResult(True, "連線測試成功。")


def legacy_fingerprint(snapshot, key):
    if key is None:
        return None
    return (snapshot.base_url.strip(), key.strip(), snapshot.model.strip(), snapshot.verify_ssl)


def prepare_legacy_test(snapshot, key):
    fingerprint = legacy_fingerprint(snapshot, key)
    if fingerprint is None:
        return None
    if not fingerprint[1]:
        raise SettingsValidationError("請先輸入 API Key。")
    # Keep legacy validation consistent with saving. Import only when needed;
    # importing or executing the single network check needs no Qt services.
    from app.settings.service import SettingsService
    SettingsService().validate(snapshot)
    return fingerprint


def prepare_group_test(settings, group_id, key_id):
    group = next((group for group in settings.groups if group.id == group_id), None)
    if group is None:
        raise ValueError("群組已刪除。")
    if key_id:
        key = next((key for key in group.keys if key.id == key_id), None)
        if key is None:
            raise ValueError("請先輸入 API Key。")
        if group.auth_mode != "api_key":
            raise ValueError("此群組目前使用免金鑰模式。")
        group = replace(group, keys=(replace(key, enabled=True),))
    elif group.auth_mode != "none":
        raise ValueError("請指定要測試的 Key。")
    else:
        group = replace(group, keys=())
    return resolve_api_request(APIGroupSettings((group,), group.id, settings.schema_version))


def connection_arguments(snapshot):
    return (snapshot.base_url, snapshot.api_key, snapshot.model, snapshot.verify_ssl)
