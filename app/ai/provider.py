import threading
from threading import Event
from typing import Dict, List, Callable
from app.utils.logger import logger
from app.ai.errors import AIRequestError
from app.ai.request_executor import AIRequestExecutor, RequestExecutionLimits
from app.settings.api_group_resolver import APIRequestSnapshot


class AIProvider:
    def __init__(self, executor_factory=AIRequestExecutor):
        self._lock = threading.Lock()
        self._active_thread: threading.Thread = None
        self._cancel_event = Event()
        self._active_executor: AIRequestExecutor | None = None
        self.executor_factory = executor_factory
        logger.info("AIProvider initialized")

    def cancel(self):
        self._cancel_event.set()
        with self._lock:
            if self._active_executor:
                self._active_executor.cancel()

    def request(
        self,
        messages: List[Dict[str, str]],
        snapshot: APIRequestSnapshot,
        max_chars: int,
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

        # Each request owns its cancellation token; a new request must not revive an old one.
        cancel_event = Event()
        with self._lock:
            self._cancel_event = cancel_event

        t = threading.Thread(
            target=self._run_request,
            args=(
                messages, snapshot, max_chars, on_chunk_cb,
                on_finished_cb, on_error_cb, cancel_event
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
        snapshot: APIRequestSnapshot,
        max_chars: int,
        on_chunk_cb: Callable[[str], None],
        on_finished_cb: Callable[[str], None],
        on_error_cb: Callable[[str], None],
        cancel_event=None,
    ):
        cancel_event = self._cancel_event if cancel_event is None else cancel_event
        executor = None
        try:
            if cancel_event.is_set():
                return
            logger.info(
                "Request to selected API group | group=%s | model=%s | max_chars=%s",
                snapshot.group_id,
                snapshot.model,
                max_chars,
            )
            executor = self.executor_factory(
                limits=RequestExecutionLimits(operation_timeout=120.0)
            )
            with self._lock:
                if cancel_event is self._cancel_event:
                    self._active_executor = executor
            full_response = executor.execute(
                snapshot,
                messages,
                max_chars=max_chars,
                on_chunk_cb=on_chunk_cb,
                should_cancel=cancel_event.is_set,
            )
            if cancel_event.is_set():
                logger.info("AI request cancelled before finish callback.")
                return
            logger.info(f"Request finished. Response length: {len(full_response)} chars")
            on_finished_cb(full_response)
        except AIRequestError as error:
            if cancel_event.is_set():
                logger.info("AI request cancelled.")
                return
            logger.error(
                "AI request failed | category=%s | code=%s | status=%s",
                error.category,
                error.service_code,
                error.http_status,
            )
            on_error_cb(str(error))
        except Exception:
            if cancel_event.is_set():
                logger.info("AI request cancelled.")
                return
            logger.error("Unexpected AI provider failure.")
            on_error_cb("AI 請求失敗，請稍後再試。")
        finally:
            with self._lock:
                if self._active_executor is executor:
                    self._active_executor = None
