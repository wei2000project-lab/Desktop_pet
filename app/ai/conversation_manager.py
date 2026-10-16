import json
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.config_manager import config_manager
from app.ai.conversation_memory import build_conversation_context_messages
from app.ai.provider import AIProvider
from app.ai.prompt_builder import build_system_prompt
from app.ai.emotion_response import EmotionResponseParser
from app.contracts.emotion import EmotionStarted, EmotionRequest, EmotionFinished
from app.web.service import WebToolService
from app.settings import APIGroupService, SettingsValidationError

@dataclass
class _ReplyState:
    parser: EmotionResponseParser = field(default_factory=EmotionResponseParser)
    text: list[str] = field(default_factory=list)
    received_content: bool = False
    emotion_sent: bool = False


class ConversationManager:
    def __init__(self, group_backend=None):
        self.group_backend = APIGroupService() if group_backend is None else group_backend
        self.provider = AIProvider()
        self.web_tool = WebToolService()
        self._is_waiting = False  # Prevent concurrent requests
        self._cancel_requested = False
        self._request_id = 0
        self._response_lock = threading.RLock()
        self._reply = None
        # Subscribe to routed chat messages
        event_bus.subscribe("chat_message_requested", self.handle_user_message)
        event_bus.subscribe("chat_response_cancel_requested", self.handle_cancel_requested)
        logger.info("ConversationManager initialized")

    def handle_user_message(self, user_text: str):
        # Guard against concurrent/stacked requests
        with self._response_lock:
            if self._is_waiting:
                logger.warning("Ignoring new message: previous request still in flight.")
                return
            self._is_waiting = True
            self._cancel_requested = False
            self._request_id += 1
            request_id = self._request_id
            self._reply = _ReplyState()
            event_bus.publish("emotion_request_started", EmotionStarted(request_id))
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
            args=(user_text, request_id, snapshot, max_chars),
            daemon=True,
            name="ConversationPrepareThread",
        ).start()

    def prepare_and_request(
        self,
        user_text: str,
        request_id: int,
        snapshot,
        max_chars: int,
    ):
        if not self._is_current_request(request_id) or self._cancel_requested:
            return

        # 4. Assemble prompt, history and memory
        messages = []

        try:
            # A. System prompt
            prompt_data = config_manager.get_prompt()
            system_prompt = build_system_prompt(prompt_data, max_chars, emotion_enabled=True)
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
                snapshot=snapshot,
                should_cancel=lambda: self._cancel_requested or not self._is_current_request(request_id),
            )
            if web_context:
                messages.append({"role": "system", "content": web_context})

            # E. Current User Message
            messages.append({"role": "user", "content": user_text})
        except Exception as exc:
            self.on_api_error(str(exc), request_id)
            return

        # Serialize submission against cancellation so a cancelled preparation
        # cannot start a provider request after cancel() has already returned.
        with self._response_lock:
            if not self._accepts_response(request_id):
                return
            try:
                self.provider.request(
                    messages=messages,
                    snapshot=snapshot,
                    max_chars=max_chars,
                    on_chunk_cb=lambda chunk: self.on_api_chunk(chunk, request_id),
                    on_finished_cb=lambda full_response: self.on_api_finished(user_text, full_response, request_id),
                    on_error_cb=lambda error_msg: self.on_api_error(error_msg, request_id)
                )
            except Exception:
                self.on_api_error("無法啟動 AI 回覆，請稍後再試。", request_id)

    def handle_cancel_requested(self):
        with self._response_lock:
            if not self._is_waiting:
                return
            request_id = self._request_id
            self._cancel_requested = True
            self._is_waiting = False
            self._request_id += 1
            self._reply = None
            self.provider.cancel()
            event_bus.publish("emotion_request_finished", EmotionFinished(request_id))
            event_bus.publish("ai_message_cancelled")

    def _is_current_request(self, request_id: int) -> bool:
        return request_id == self._request_id

    def _accepts_response(self, request_id):
        return (self._is_waiting and not self._cancel_requested and self._reply is not None
                and (request_id is None or self._is_current_request(request_id)))

    def _publish_emotion(self):
        reply = self._reply
        if not reply.emotion_sent and reply.parser.emotion is not None:
            reply.emotion_sent = True
            logger.info(
                "Emotion parsed | request=%s | header=%s | choice=%s",
                self._request_id, reply.parser.header_status, reply.parser.emotion.value,
            )
            event_bus.publish("emotion_requested", EmotionRequest(self._request_id, reply.parser.emotion))

    def _publish_text(self, text):
        if text:
            self._reply.text.append(text)
            event_bus.publish("ai_message_chunk", text)

    def on_api_chunk(self, chunk: str, request_id: int = None):
        with self._response_lock:
            if not self._accepts_response(request_id):
                return
            self._reply.received_content |= bool(chunk)
            text = self._reply.parser.feed(chunk)
            self._publish_emotion()
            self._publish_text(text)

    def on_api_finished(self, user_text: str, full_response: str, request_id: int = None):
        with self._response_lock:
            if not self._accepts_response(request_id):
                return
            # Some providers deliver only a final response. A provider that has
            # streamed content already must not feed the complete response twice.
            if not self._reply.received_content:
                self.on_api_chunk(full_response, request_id)
            self._publish_text(self._reply.parser.finish())
            self._publish_emotion()
            text = "".join(self._reply.text)
            finished_request_id = self._request_id
            self._is_waiting = False
            self._reply = None
            logger.info("AI response complete. Saving history.")
            try:
                history = config_manager.get_history()
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": text})
                config_manager.save_history(history)
            except Exception:
                logger.error("Failed to save conversation history", exc_info=True)
                event_bus.publish("ai_message_error", "回覆已完成，但無法儲存對話紀錄。")
            else:
                event_bus.publish("ai_message_finished", text)
            finally:
                event_bus.publish("emotion_request_finished", EmotionFinished(finished_request_id))

    def on_api_error(self, error_msg: str, request_id: int = None):
        with self._response_lock:
            if not self._accepts_response(request_id):
                return
            self._publish_text(self._reply.parser.finish())
            self._is_waiting = False
            self._reply = None
            logger.error(f"AI response error: {error_msg}")
            event_bus.publish("emotion_request_finished", EmotionFinished(self._request_id))
            event_bus.publish("ai_message_error", error_msg)
