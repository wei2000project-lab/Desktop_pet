"""Background connection checks with credential-free result messages."""
import re

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

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


class ConnectionTestSignals(QObject):
    finished = Signal(int, bool, str)


class ConnectionTestWorker(QRunnable):
    def __init__(self, request_id, base_url, api_key, model, verify_ssl):
        super().__init__()
        self.request_id = request_id
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.signals = ConnectionTestSignals()

    @Slot()
    def run(self):
        try:
            client = AIClient(
                base_url=self.base_url, api_key=self.api_key, model=self.model,
                verify_ssl=self.verify_ssl, timeout=15.0,
            )
            client.test_connection()
        except Exception as error:
            self.signals.finished.emit(self.request_id, False, safe_failure_message(error))
        else:
            self.signals.finished.emit(self.request_id, True, "連線測試成功。")
        finally:
            self.api_key = ""
