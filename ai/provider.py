import threading
from threading import Event
from typing import Dict, List, Any, Callable
from app.utils.logger import logger
from ai.client import AIClient


class AIProvider:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_thread: threading.Thread = None
        self._cancel_event = Event()
        self._active_client: AIClient | None = None
        logger.info("AIProvider initialized")

    def cancel(self):
        self._cancel_event.set()
        with self._lock:
            if self._active_client:
                self._active_client.cancel()

    def request(
        self,
        messages: List[Dict[str, str]],
        api_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_chars: int,
        verify_ssl: bool,
        on_chunk_cb: Callable[[str], None],
        on_finished_cb: Callable[[str], None],
        on_error_cb: Callable[[str], None]
    ):
        """Spawn a background daemon thread for the HTTP request.
        
        If a previous request is still running, it will be allowed to finish
        (we don't cancel it) but we log a warning to help diagnose stacking issues.
        """
        with self._lock:
            if self._active_thread and self._active_thread.is_alive():
                logger.warning(
                    "A previous AI request thread is still alive. "
                    "The new request will be queued but the old one may still respond."
                )

        self._cancel_event.clear()

        t = threading.Thread(
            target=self._run_request,
            args=(
                messages, api_url, api_key, model, temperature,
                max_chars, verify_ssl, on_chunk_cb, on_finished_cb, on_error_cb
            ),
            daemon=True,
            name="AIRequestThread"
        )

        with self._lock:
            self._active_thread = t

        t.start()
        logger.info(f"AIRequestThread started (id={t.ident})")

    def _run_request(
        self,
        messages: List[Dict[str, str]],
        api_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_chars: int,
        verify_ssl: bool,
        on_chunk_cb: Callable[[str], None],
        on_finished_cb: Callable[[str], None],
        on_error_cb: Callable[[str], None]
    ):
        try:
            logger.info(f"Request to: {api_url} | model: {model} | max_chars: {max_chars}")
            client = AIClient(
                base_url=api_url,
                api_key=api_key,
                model=model,
                verify_ssl=verify_ssl,
                timeout=120.0
            )
            with self._lock:
                self._active_client = client
            full_response = client.request_completion(
                messages=messages,
                temperature=temperature,
                max_chars=max_chars,
                on_chunk_cb=on_chunk_cb,
                should_cancel=self._cancel_event.is_set,
            )
            if self._cancel_event.is_set():
                logger.info("AI request cancelled before finish callback.")
                return
            logger.info(f"Request finished. Response length: {len(full_response)} chars")
            on_finished_cb(full_response)
        except Exception as e:
            if self._cancel_event.is_set():
                logger.info(f"AI request cancelled: {e}")
                return
            logger.error(f"AIProvider request error: {e}", exc_info=True)
            on_error_cb(str(e))
        finally:
            with self._lock:
                self._active_client = None
