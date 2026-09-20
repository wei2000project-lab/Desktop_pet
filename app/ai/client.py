import json
import queue
import requests
from typing import Dict, List, Any, Callable
from app.ai.errors import (
    AIRequestError, classify_http_response, connection_error, internal_error,
    invalid_response_error, timeout_error, tls_error, cancelled_error,
)
from app.utils.logger import logger


_TIMEOUT_EXCEPTIONS = (requests.exceptions.Timeout,)
_CONNECTION_EXCEPTIONS = (requests.exceptions.ConnectionError,)
_HTTP_EXCEPTIONS = (requests.exceptions.HTTPError,)
_ssl_exception = getattr(requests.exceptions, "SSLError", None)
_SSL_EXCEPTIONS = (_ssl_exception,) if isinstance(_ssl_exception, type) else ()
_request_exception = getattr(requests.exceptions, "RequestException", None)
_REQUEST_EXCEPTIONS = (_request_exception,) if isinstance(_request_exception, type) else ()


class AIClient:
    def __init__(self, base_url: str, api_key: str | None, model: str, verify_ssl: bool = True, timeout: float = 120.0):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._cancelled = False
        self._active_session = None

    def cancel(self):
        self._cancelled = True
        session = self._active_session
        if session:
            try:
                session.close()
            except Exception:
                pass

    def _raise_if_cancelled(self, should_cancel=None):
        if self._cancelled or (should_cancel and should_cancel()):
            raise cancelled_error()

    def request_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_chars: int = 150,
        on_chunk_cb: Callable[[str], None] = None,
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        """Request a completion, using only explicitly safe stream fallback."""
        try:
            logger.info("Attempting streaming completion (stream=True)")
            return self.request_once(
                messages, temperature, max_chars, on_chunk_cb, should_cancel, stream=True,
            )
        except AIRequestError as error:
            self._raise_if_cancelled(should_cancel)
            if error.output_started or not error.can_fallback_non_stream:
                raise
            logger.warning(
                "Streaming is explicitly unsupported; retrying once without streaming "
                "(status=%s, code=%s)",
                error.http_status,
                error.service_code,
            )
            return self.request_once(
                messages, temperature, max_chars, on_chunk_cb, should_cancel, stream=False,
            )

    def request_once(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_chars: int = 150,
        on_chunk_cb: Callable[[str], None] = None,
        should_cancel: Callable[[], bool] = None,
        *,
        stream: bool,
    ) -> str:
        """Perform exactly one HTTP request; retry policy belongs to the executor."""
        request = self._request_stream if stream else self._request_non_stream
        return request(messages, temperature, max_chars, on_chunk_cb, should_cancel)

    def test_connection(self) -> bool:
        self._request_non_stream(
            messages=[
                {"role": "system", "content": "Reply with ok."},
                {"role": "user", "content": "ping"},
            ],
            temperature=0.0,
            max_chars=20,
            on_chunk_cb=None,
        )
        return True

    def _build_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(self, messages, temperature, max_chars, stream) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

    def _request_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_chars: int,
        on_chunk_cb: Callable[[str], None],
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        payload = self._build_payload(messages, temperature, max_chars, stream=True)
        self._raise_if_cancelled(should_cancel)

        full_text = ""
        chunk_count = 0

        # Use a fresh Session per request to avoid connection pooling issues
        session = requests.Session()
        self._active_session = session
        try:
            response = session.post(
                url,
                json=payload,
                headers=headers,
                timeout=(min(10, self.timeout), self.timeout),
                verify=self.verify_ssl,
                stream=True,
            )
            response.raise_for_status()

            logger.info(f"Stream connected. Status: {response.status_code}")

            # Read line-by-line with default buffering (no chunk_size override)
            for raw_line in response.iter_lines():
                self._raise_if_cancelled(should_cancel)
                if not raw_line:
                    continue

                # raw_line is bytes
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    continue

                if not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()

                if data_str == "[DONE]":
                    logger.info(f"Stream [DONE]. Total chunks: {chunk_count}, chars: {len(full_text)}")
                    break

                try:
                    data_json = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning("Ignoring malformed streaming event.")
                    continue

                try:
                    delta = data_json["choices"][0]["delta"]
                except (KeyError, IndexError):
                    logger.warning("Ignoring unexpected streaming event structure.")
                    continue

                # Only process visible content tokens; skip reasoning/thinking tokens
                chunk_text = delta.get("content") or ""
                if not chunk_text:
                    continue

                full_text += chunk_text
                chunk_count += 1
                if on_chunk_cb:
                    self._raise_if_cancelled(should_cancel)
                    on_chunk_cb(chunk_text)

        except Exception as error:
            structured = self._structured_error(
                error,
                response=locals().get("response"),
                output_started=bool(full_text),
            )
            logger.error(
                "AI stream request failed (category=%s, status=%s, code=%s, output_started=%s)",
                structured.category.value,
                structured.http_status,
                structured.service_code,
                structured.output_started,
            )
            raise structured from None
        finally:
            session.close()
            self._active_session = None

        return full_text

    def _request_non_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_chars: int,
        on_chunk_cb: Callable[[str], None],
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        payload = self._build_payload(messages, temperature, max_chars, stream=False)
        self._raise_if_cancelled(should_cancel)

        session = requests.Session()
        self._active_session = session
        try:
            response = session.post(
                url,
                json=payload,
                headers=headers,
                timeout=(min(10, self.timeout), self.timeout),
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            self._raise_if_cancelled(should_cancel)

            res_json = response.json()
            message = res_json["choices"][0]["message"]
            content = (message.get("content") or "").strip()

            if on_chunk_cb and content:
                self._raise_if_cancelled(should_cancel)
                on_chunk_cb(content)

            return content

        except Exception as error:
            structured = self._structured_error(
                error,
                response=locals().get("response"),
                output_started=bool(locals().get("content", "")),
            )
            logger.error(
                "AI non-stream request failed (category=%s, status=%s, code=%s)",
                structured.category.value,
                structured.http_status,
                structured.service_code,
            )
            raise structured from None
        finally:
            session.close()
            self._active_session = None

    @staticmethod
    def _structured_error(error, *, response=None, output_started=False):
        if isinstance(error, AIRequestError):
            return error
        if _SSL_EXCEPTIONS and isinstance(error, _SSL_EXCEPTIONS):
            return tls_error(output_started=output_started)
        if isinstance(error, _TIMEOUT_EXCEPTIONS):
            return timeout_error(output_started=output_started)
        if isinstance(error, _CONNECTION_EXCEPTIONS):
            return connection_error(output_started=output_started)
        if isinstance(error, _HTTP_EXCEPTIONS):
            error_response = getattr(error, "response", None)
            return classify_http_response(
                error_response if error_response is not None else response,
                output_started=output_started,
            )
        if _REQUEST_EXCEPTIONS and isinstance(error, _REQUEST_EXCEPTIONS):
            return connection_error(output_started=output_started)
        if isinstance(error, (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError)):
            return invalid_response_error(output_started=output_started)
        return internal_error(output_started=output_started)
