import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ai.conversation_manager import ConversationManager
from app.contracts.emotion import Emotion, EmotionRequest, EmotionFinished
from tests.emotion_helpers import EmotionTestBus


class ConversationEmotionTests(unittest.TestCase):
    def setUp(self):
        self.bus = EmotionTestBus()
        self.store = Mock()
        self.store.get_prompt.return_value = {"system_prompt": "你是 Nova。"}
        self.store.get_memory.return_value = {}
        self.store.get_history.side_effect = lambda: []
        self.store.get_general_int.side_effect = lambda key, default: default
        self.store.get_general_bool.side_effect = lambda key, default: default
        self.provider = Mock()
        web = Mock()
        web.build_context_if_needed.return_value = ""
        for target, value in (("event_bus", self.bus), ("config_manager", self.store),
                              ("AIProvider", Mock(return_value=self.provider)),
                              ("WebToolService", Mock(return_value=web))):
            patcher = patch("app.ai.conversation_manager." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        thread = patch("app.ai.conversation_manager.threading.Thread", side_effect=
                       lambda *, target, args, **kwargs: SimpleNamespace(start=lambda: target(*args)))
        thread.start()
        self.addCleanup(thread.stop)
        self.manager = ConversationManager(group_backend=Mock())

    def start(self):
        self.manager.handle_user_message("問題")
        return self.provider.request.call_args.kwargs

    def test_stream_is_clean_and_one_candidate_precedes_text(self):
        request = self.start()
        self.assertIn("回覆表情協定", request["messages"][0]["content"])
        raw = "[[emotion:squint]]\n真的嗎？"
        for char in raw:
            request["on_chunk_cb"](char)
        request["on_finished_cb"](raw)
        self.assertEqual("".join(self.bus.values("ai_message_chunk")), "真的嗎？")
        self.assertEqual(self.bus.values("ai_message_finished"), ["真的嗎？"])
        self.assertEqual(self.store.save_history.call_args.args[0][-1]["content"], "真的嗎？")
        self.assertEqual(self.bus.values("emotion_requested"), [EmotionRequest(1, Emotion.SQUINT)])
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(1)])
        names = [name for name, args in self.bus.events]
        self.assertLess(names.index("emotion_requested"), names.index("ai_message_chunk"))
        self.provider.request.assert_called_once()
        request["on_finished_cb"](raw)
        request["on_chunk_cb"]("遲到")
        self.store.save_history.assert_called_once()
        self.assertEqual(len(self.bus.values("emotion_requested")), 1)

    def test_diagnostic_log_records_choice_once_without_response_body(self):
        request = self.start()
        with self.assertLogs("nova", level="INFO") as logs:
            for char in "[[emotion:happy]]\nprivate response":
                request["on_chunk_cb"](char)
            request["on_finished_cb"]("[[emotion:happy]]\nprivate response")
        parsed = [line for line in logs.output if "Emotion parsed" in line]
        self.assertEqual(len(parsed), 1)
        self.assertIn("request=1 | header=valid | choice=happy", parsed[0])
        self.assertNotIn("private response", "\n".join(logs.output))

    def test_final_only_and_single_chunk_fallback_have_same_result(self):
        for with_chunk in (False, True):
            self.bus.events.clear()
            request = self.start()
            raw = "[[emotion:happy]]\r\n太好了"
            if with_chunk:
                request["on_chunk_cb"](raw)
            request["on_finished_cb"](raw)
            self.assertEqual(self.bus.values("ai_message_chunk"), ["太好了"])
            self.assertEqual(self.bus.values("ai_message_finished"), ["太好了"])
            self.assertEqual(len(self.bus.values("emotion_requested")), 1)

    def test_none_plain_and_malformed_responses_keep_answer(self):
        for raw, expected in (("正常回答", "正常回答"), ("[[emotion:none]]\n回答", "回答"),
                              ("[[emotion:gaze]]\n回答", "回答"), ("[[emotion:happy", ""),
                              ("[", "[")):
            with self.subTest(raw=raw):
                self.bus.events.clear()
                request = self.start()
                request["on_chunk_cb"](raw)
                request["on_finished_cb"](raw)
                self.assertEqual("".join(self.bus.values("ai_message_chunk")), expected)
                self.assertEqual(self.bus.values("ai_message_finished"), [expected])
                self.assertEqual(self.bus.values("emotion_requested")[0].emotion, Emotion.NONE)

    def test_cancel_then_new_request_ignores_old_callbacks(self):
        old = self.start()
        old["on_chunk_cb"]("[[emotion:happy]]\n舊回覆")
        self.manager.handle_cancel_requested()
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(1)])
        new = self.start()
        self.bus.events.clear()
        old["on_chunk_cb"]("old")
        old["on_finished_cb"]("old")
        old["on_error_cb"]("old")
        self.assertEqual(self.bus.events, [])
        new["on_finished_cb"]("[[emotion:surprised]]\n新回覆")
        self.assertEqual(self.bus.values("emotion_requested"), [EmotionRequest(3, Emotion.SURPRISED)])
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(3)])
        self.store.save_history.assert_called_once()

    def test_error_ends_request_without_activating_partial_marker(self):
        request = self.start()
        request["on_chunk_cb"]("[[emotion:hap")
        request["on_error_cb"]("synthetic error")
        self.assertEqual(self.bus.values("emotion_requested"), [])
        self.assertEqual(self.bus.values("ai_message_chunk"), [])
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(1)])
        request["on_chunk_cb"]("py]]")
        self.assertEqual(self.bus.values("emotion_requested"), [])
        self.store.save_history.assert_not_called()

    def test_storage_failure_still_finishes_emotion(self):
        request = self.start()
        self.store.save_history.side_effect = OSError("synthetic storage failure")
        with patch("app.ai.conversation_manager.logger.error"):
            request["on_finished_cb"]("[[emotion:happy]]\n回答")
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(1)])
        self.assertTrue(self.bus.values("ai_message_error"))
        self.assertFalse(self.manager._is_waiting)

    def test_provider_submission_failure_ends_request(self):
        self.provider.request.side_effect = RuntimeError("synthetic failure")
        self.start()
        self.assertEqual(self.bus.values("emotion_request_finished"), [EmotionFinished(1)])
        self.assertFalse(self.manager._is_waiting)

    def test_conversation_and_animator_share_completion_cancel_and_error_lifecycle(self):
        # The real components share an event source; HTTP, time and configuration
        # are controlled so no user data or network is involved.
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.animation.animator import Animator
        app = QApplication.instance() or QApplication([])
        now = [100.0]
        store = Mock()
        store.get_general.return_value = "1"
        store.get_general_int.return_value = 300
        with patch("app.animation.animator.event_bus", self.bus), patch(
                "app.animation.animator.config_manager", store):
            animator = Animator(clock=lambda: now[0])
            try:
                for ending in ("complete", "cancel", "error"):
                    animator.enter_reading()
                    request = self.start()
                    self.assertEqual(animator.current_state, "reading")
                    request["on_chunk_cb"]("[[emotion:squint]]\n真的嗎")
                    self.assertEqual(animator.current_state, "emotion")
                    self.assertFalse(animator.emotion_timer.isActive())
                    if ending == "complete":
                        request["on_finished_cb"]("[[emotion:squint]]\n真的嗎")
                    elif ending == "cancel":
                        self.manager.handle_cancel_requested()
                    else:
                        request["on_error_cb"]("synthetic error")
                    self.assertTrue(animator.emotion_timer.isActive())
                    now[0] += 3
                    animator.on_emotion_timeout()
                    self.assertEqual(animator.current_state, "idle")
            finally:
                animator.shutdown()
                animator.deleteLater()
                app.processEvents()
