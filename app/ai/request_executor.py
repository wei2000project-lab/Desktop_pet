"""Bounded orchestration for one API operation across resolved candidate keys."""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time

from app.ai.client import AIClient
from app.ai.errors import (
    AIRequestError, budget_exhausted_error, cancelled_error, internal_error,
    operation_timeout_error,
)
from app.settings.api_group_resolver import APIRequestSnapshot


@dataclass(frozen=True)
class RequestExecutionLimits:
    max_candidates: int = 3
    max_http_attempts: int = 6
    operation_timeout: float = 120.0

    def __post_init__(self):
        if type(self.max_candidates) is not int or self.max_candidates < 1:
            raise ValueError("max_candidates must be a positive integer")
        if type(self.max_http_attempts) is not int or self.max_http_attempts < 1:
            raise ValueError("max_http_attempts must be a positive integer")
        if not (
            type(self.operation_timeout) in (int, float)
            and math.isfinite(self.operation_timeout)
            and self.operation_timeout > 0
        ):
            raise ValueError("operation_timeout must be a positive finite number")


class AIRequestExecutor:
    """Execute one bounded operation without crossing groups or repeating a key."""

    def __init__(self, *, limits=None, client_factory=AIClient, clock=time.monotonic):
        self.limits = limits or RequestExecutionLimits()
        self.client_factory = client_factory
        self.clock = clock
        self._lock = threading.Lock()
        self._cancelled = False
        self._active_client = None

    def cancel(self):
        with self._lock:
            self._cancelled = True
            client = self._active_client
        if client is not None:
            client.cancel()

    def execute(
        self,
        snapshot: APIRequestSnapshot,
        messages,
        *,
        max_chars=150,
        on_chunk_cb=None,
        should_cancel=None,
    ) -> str:
        deadline = self.clock() + float(self.limits.operation_timeout)
        attempts = 0
        candidates = self._candidate_keys(snapshot)
        last_error = None

        for index, api_key in enumerate(candidates):
            self._check_stop(deadline, should_cancel)
            client = self._create_client(snapshot, api_key, deadline)
            self._set_active_client(client)
            try:
                attempts = self._reserve_attempt(attempts, deadline, should_cancel)
                try:
                    return client.request_once(
                        messages,
                        snapshot.temperature,
                        max_chars,
                        on_chunk_cb,
                        should_cancel,
                        stream=True,
                    )
                except AIRequestError as error:
                    last_error = error
                    self._check_stop(deadline, should_cancel)
                    if error.output_started:
                        raise
                    if error.can_fallback_non_stream:
                        attempts = self._reserve_attempt(attempts, deadline, should_cancel)
                        try:
                            return client.request_once(
                                messages,
                                snapshot.temperature,
                                max_chars,
                                on_chunk_cb,
                                should_cancel,
                                stream=False,
                            )
                        except AIRequestError:
                            self._check_stop(deadline, should_cancel)
                            raise
                    has_next = index + 1 < len(candidates)
                    if error.can_switch_key and has_next:
                        continue
                    raise
            finally:
                self._clear_active_client(client)

        if last_error is not None:
            raise last_error
        raise internal_error()

    def _candidate_keys(self, snapshot):
        if snapshot.auth_mode == "none":
            return (None,)
        candidates = snapshot.candidates[:self.limits.max_candidates]
        if not candidates:
            raise internal_error()
        return tuple(candidate.key for candidate in candidates)

    def _create_client(self, snapshot, api_key, deadline):
        remaining = self._remaining(deadline)
        return self.client_factory(
            base_url=snapshot.base_url,
            api_key=api_key,
            model=snapshot.model,
            verify_ssl=snapshot.verify_ssl,
            timeout=remaining,
        )

    def _reserve_attempt(self, attempts, deadline, should_cancel):
        self._check_stop(deadline, should_cancel)
        if attempts >= self.limits.max_http_attempts:
            raise budget_exhausted_error()
        return attempts + 1

    def _check_stop(self, deadline, should_cancel):
        with self._lock:
            cancelled = self._cancelled
        if cancelled or (should_cancel is not None and should_cancel()):
            raise cancelled_error()
        if self.clock() >= deadline:
            raise operation_timeout_error()

    def _remaining(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise operation_timeout_error()
        return remaining

    def _set_active_client(self, client):
        with self._lock:
            if self._cancelled:
                raise cancelled_error()
            self._active_client = client

    def _clear_active_client(self, client):
        with self._lock:
            if self._active_client is client:
                self._active_client = None
