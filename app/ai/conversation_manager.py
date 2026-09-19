import json
import threading
from typing import Dict, List, Any
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.config_manager import config_manager
from app.ai.conversation_memory import build_conversation_context_messages
from app.ai.provider import AIProvider
from app.ai.prompt_builder import build_system_prompt
from app.web.service import WebToolService
from app.settings import APIGroupService, SettingsValidationError

class ConversationManager:
    def __init__(self, group_backend=None):
        self.group_backend = APIGroupService() if group_backend is None else group_backend
        self.provider = AIProvider()
        self.web_tool = WebToolService()
        self._is_waiting = False  # Prevent concurrent requests
        self._cancel_requested = False
        self._request_id = 0
        # Subscribe to routed chat messages
        event_bus.subscribe("chat_message_requested", self.handle_user_message)
        event_bus.subscribe("chat_response_cancel_requested", self.handle_cancel_requested)
        logger.info("ConversationManager initialized")

    def handle_user_message(self, user_text: str):
        # Guard against concurrent/stacked requests
        if self._is_waiting:
            logger.warning("Ignoring new message: previous request still in flight.")
            return
        self._is_waiting = True
        self._cancel_requested = False
        self._request_id += 1
        request_id = self._request_id

        # 1. Publish starting signal for UI loading state
        event_bus.publish("ai_message_started")
        
        # Resolve once before background preparation; group changes affect new requests only.
        try:
            snapshot = self.group_backend.resolve_runtime_request()
        except SettingsValidationError as error:
            self.on_api_error(str(error), request_id)
            return
        max_chars = 0

        threading.Thread(
            target=self.prepare_and_request,
            args=(user_text, request_id, snapshot.api_key, snapshot.base_url, snapshot.model,
                  snapshot.temperature, max_chars, snapshot.verify_ssl),
            daemon=True,
            name="ConversationPrepareThread",
        ).start()

    def prepare_and_request(
        self,
        user_text: str,
        request_id: int,
        api_key: str | None,
        base_url: str,
        model: str,
        temp: float,
        max_chars: int,
        verify_ssl: bool,
    ):
        if not self._is_current_request(request_id) or self._cancel_requested:
            return

        # 4. Assemble prompt, history and memory
        messages = []

        try:
            # A. System prompt
            prompt_data = config_manager.get_prompt()
            system_prompt = build_system_prompt(prompt_data, max_chars)
            messages.append({"role": "system", "content": system_prompt})

            # B. Memory prompt (inject as a separate System Message)
            memory_data = config_manager.get_memory()
            if memory_data:
                memory_str = json.dumps(memory_data, ensure_ascii=False)
                messages.append({"role": "system", "content": f"關於使用者的長期記憶：{memory_str}"})

            # C. Recent history and optional summary of older conversations
            history = config_manager.get_history()
            max_memory_turns = config_manager.get_general_int("MaxMemoryTurns", 6)
            summary_enabled = config_manager.get_general_bool("ConversationSummaryEnabled", True)
            messages.extend(
                build_conversation_context_messages(
                    history,
                    max_memory_turns=max_memory_turns,
                    summary_enabled=summary_enabled,
                )
            )

            # D. Optional one-turn web context. It starts with "網路查詢摘要" and is not saved to history.
            web_context = self.web_tool.build_context_if_needed(
                user_text=user_text,
                api_url=base_url,
                api_key=api_key,
                model=model,
                verify_ssl=verify_ssl,
                should_cancel=lambda: self._cancel_requested or not self._is_current_request(request_id),
            )
            if web_context:
                messages.append({"role": "system", "content": web_context})

            # E. Current User Message
            messages.append({"role": "user", "content": user_text})
        except Exception as exc:
            self.on_api_error(str(exc), request_id)
            return

        if not self._is_current_request(request_id) or self._cancel_requested:
            return

        # 5. Call Provider in background
        self.provider.request(
            messages=messages,
            api_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temp,
            max_chars=max_chars,
            verify_ssl=verify_ssl,
            on_chunk_cb=lambda chunk: self.on_api_chunk(chunk, request_id),
            on_finished_cb=lambda full_response: self.on_api_finished(user_text, full_response, request_id),
            on_error_cb=lambda error_msg: self.on_api_error(error_msg, request_id)
        )

    def handle_cancel_requested(self):
        if not self._is_waiting:
            return
        self._cancel_requested = True
        self._is_waiting = False
        self._request_id += 1
        self.provider.cancel()
        event_bus.publish("ai_message_cancelled")

    def _is_current_request(self, request_id: int) -> bool:
        return request_id == self._request_id

    def on_api_chunk(self, chunk: str, request_id: int = None):
        if request_id is not None and not self._is_current_request(request_id):
            return
        if self._cancel_requested:
            return
        event_bus.publish("ai_message_chunk", chunk)

    def on_api_finished(self, user_text: str, full_response: str, request_id: int = None):
        if request_id is not None and not self._is_current_request(request_id):
            return
        if self._cancel_requested:
            return
        self._is_waiting = False
        logger.info("AI response complete. Saving history.")
        # Update and save history
        history = config_manager.get_history()
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": full_response})
        config_manager.save_history(history)
        
        # Publish final finished message
        event_bus.publish("ai_message_finished", full_response)

    def on_api_error(self, error_msg: str, request_id: int = None):
        if request_id is not None and not self._is_current_request(request_id):
            return
        if self._cancel_requested:
            return
        self._is_waiting = False
        logger.error(f"AI response error: {error_msg}")
        event_bus.publish("ai_message_error", error_msg)
