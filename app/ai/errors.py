"""Structured, credential-safe errors for AI HTTP requests."""
from __future__ import annotations

from enum import Enum
import re


class AIErrorCategory(str, Enum):
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    TLS = "tls"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    MODEL = "model"
    INVALID_REQUEST = "invalid_request"
    SERVER = "server"
    HTTP = "http"
    INVALID_RESPONSE = "invalid_response"
    INTERNAL = "internal"


KEY_SPECIFIC_CODES = frozenset({
    "api_key_expired",
    "incorrect_api_key",
    "invalid_api_key",
    "key_expired",
    "revoked_api_key",
})

STREAM_FALLBACK_CODES = frozenset({
    "streaming_not_supported",
    "unsupported_streaming",
})

QUOTA_CODES = frozenset({
    "billing_hard_limit_reached",
    "insufficient_quota",
    "quota_exceeded",
})

MODEL_CODES = frozenset({
    "invalid_model",
    "model_not_found",
    "unsupported_model",
})

_SAFE_CODE = re.compile(r"^[a-z0-9_.-]{1,64}$")


class AIRequestError(Exception):
    """An AI request failure containing only bounded, non-sensitive metadata."""

    def __init__(
        self,
        category: AIErrorCategory,
        safe_message: str,
        *,
        http_status: int | None = None,
        service_code: str | None = None,
        output_started: bool = False,
        can_switch_key: bool = False,
        can_fallback_non_stream: bool = False,
    ):
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message
        self.http_status = http_status
        self.service_code = service_code
        self.output_started = output_started
        self.can_switch_key = can_switch_key
        self.can_fallback_non_stream = can_fallback_non_stream

    def __repr__(self):
        return (
            "AIRequestError("
            f"category={self.category.value!r}, http_status={self.http_status!r}, "
            f"service_code={self.service_code!r}, output_started={self.output_started!r}, "
            f"can_switch_key={self.can_switch_key!r}, "
            f"can_fallback_non_stream={self.can_fallback_non_stream!r})"
        )


def cancelled_error() -> AIRequestError:
    return AIRequestError(AIErrorCategory.CANCELLED, "已停止回覆。")


def timeout_error(*, output_started=False) -> AIRequestError:
    return AIRequestError(
        AIErrorCategory.TIMEOUT,
        "連線逾時，請確認服務狀態或稍後再試。",
        output_started=output_started,
    )


def connection_error(*, output_started=False) -> AIRequestError:
    return AIRequestError(
        AIErrorCategory.CONNECTION,
        "無法連線至 API 服務，請確認網址、網路與服務狀態。",
        output_started=output_started,
    )


def tls_error(*, output_started=False) -> AIRequestError:
    return AIRequestError(
        AIErrorCategory.TLS,
        "TLS 憑證驗證失敗，請確認服務憑證與 SSL 設定。",
        output_started=output_started,
    )


def invalid_response_error(*, output_started=False) -> AIRequestError:
    return AIRequestError(
        AIErrorCategory.INVALID_RESPONSE,
        "API 回應格式無法解析。",
        output_started=output_started,
    )


def internal_error(*, output_started=False) -> AIRequestError:
    return AIRequestError(
        AIErrorCategory.INTERNAL,
        "處理 API 回應時發生錯誤。",
        output_started=output_started,
    )


def classify_http_response(response, *, output_started=False) -> AIRequestError:
    status = _safe_status(getattr(response, "status_code", None))
    code = _extract_service_code(response)
    category, message = _http_category_and_message(status, code)
    return AIRequestError(
        category,
        message,
        http_status=status,
        service_code=code,
        output_started=output_started,
        can_switch_key=(
            not output_started
            and status == 401
            and code in KEY_SPECIFIC_CODES
        ),
        can_fallback_non_stream=(
            not output_started and code in STREAM_FALLBACK_CODES
        ),
    )


def _extract_service_code(response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    candidates = []
    if isinstance(error, dict):
        candidates.extend((error.get("code"), error.get("type")))
    candidates.append(payload.get("code"))
    for value in candidates:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if _SAFE_CODE.fullmatch(normalized):
            return normalized
    return None


def _safe_status(value) -> int | None:
    return value if type(value) is int and 100 <= value <= 599 else None


def _http_category_and_message(status, code):
    if status == 401:
        return AIErrorCategory.AUTHENTICATION, "API 驗證失敗，請確認金鑰。"
    if status == 403:
        return AIErrorCategory.PERMISSION, "API 拒絕存取，請確認帳號、模型與權限。"
    if status == 429 and code in QUOTA_CODES:
        return AIErrorCategory.QUOTA, "API 額度不足，請確認帳號與方案。"
    if status == 429:
        return AIErrorCategory.RATE_LIMIT, "API 暫時限制請求，請稍後再試。"
    if code in MODEL_CODES:
        return AIErrorCategory.MODEL, "API 模型不存在或目前無法使用。"
    if status == 400:
        return AIErrorCategory.INVALID_REQUEST, "API 拒絕請求參數。"
    if status is not None and status >= 500:
        return AIErrorCategory.SERVER, f"API 服務暫時異常（HTTP {status}）。"
    if status is not None:
        return AIErrorCategory.HTTP, f"API 請求失敗（HTTP {status}）。"
    return AIErrorCategory.HTTP, "API 請求失敗。"
