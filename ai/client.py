import json
import queue
import requests
from typing import Dict, List, Any, Callable
from utils.logger import logger


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str, verify_ssl: bool = True, timeout: float = 120.0):
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
            raise Exception("已停止回覆")

    def request_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_chars: int = 150,
        on_chunk_cb: Callable[[str], None] = None,
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        """Request streaming completion. Falls back to non-streaming on error."""
        try:
            logger.info("Attempting streaming completion (stream=True)")
            return self._request_stream(messages, temperature, max_chars, on_chunk_cb, should_cancel)
        except Exception as e:
            self._raise_if_cancelled(should_cancel)
            logger.warning(f"Streaming failed: {e}. Falling back to non-streaming...")
            return self._request_non_stream(messages, temperature, max_chars, on_chunk_cb, should_cancel)

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
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
        }

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
                timeout=(10, self.timeout),  # (connect_timeout, read_timeout)
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
                    logger.warning(f"JSON parse failed for: {data_str[:80]}")
                    continue

                try:
                    delta = data_json["choices"][0]["delta"]
                except (KeyError, IndexError):
                    logger.warning(f"Unexpected structure: {data_json}")
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

        except requests.exceptions.Timeout:
            logger.error(f"Request timed out after {self.timeout}s")
            raise Exception(f"連線逾時（{self.timeout}秒）— 請確認 llama-server 是否仍在執行")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise Exception(f"無法連線至 {self.base_url}，請確認 URL 與端口是否正確")
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:300]
            except Exception:
                pass
            logger.error(f"HTTP {e.response.status_code}: {body}")
            raise Exception(f"HTTP {e.response.status_code}: {body}")
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
                timeout=(10, self.timeout),
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

        except requests.exceptions.Timeout:
            raise Exception(f"連線逾時（{self.timeout}秒）")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"無法連線至 {self.base_url}")
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:300]
            except Exception:
                pass
            raise Exception(f"HTTP {e.response.status_code}: {body}")
        finally:
            session.close()
            self._active_session = None
