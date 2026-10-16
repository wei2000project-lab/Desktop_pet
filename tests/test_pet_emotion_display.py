"""Exercise worker reply -> real Qt bus -> visible pet, without forced repaint/grab."""
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ai.conversation_manager import ConversationManager
from app.animation.animator import Animator
from app.core.event_bus import event_bus
from app.core.paths import PET_EMOTIONS_DIR
from ui.pet.desktop_pet import DesktopPet


class PetEmotionDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_background_reply_reaches_real_pet_and_paints_happy(self):
        store = Mock()
        values = dict(Width=300, Height=300, PositionX=30, PositionY=30,
                      EmotionRate=1, ReadingIdleSeconds=300)
        store.get_general.side_effect = lambda key, default=None: values.get(key, default)
        store.get_general_int.side_effect = lambda key, default=0: values.get(key, default)
        store.get_general_bool.side_effect = lambda key, default=False: default
        store.get_prompt.return_value = {"system_prompt": "Synthetic test"}
        store.get_memory.return_value = {}
        store.get_history.return_value = []
        web = Mock()
        web.build_context_if_needed.return_value = ""
        provider = Mock()
        finished = threading.Event()
        workers = []

        def request(**callbacks):
            def deliver():
                try:
                    raw = "[[emotion:happy]]\nSynthetic reply"
                    for char in raw:
                        callbacks["on_chunk_cb"](char)
                    callbacks["on_finished_cb"](raw)
                finally:
                    finished.set()
            worker = threading.Thread(target=deliver)
            workers.append(worker)
            worker.start()

        provider.request.side_effect = request
        with ExitStack() as stack:
            for module in ("app.animation.animator", "app.ai.conversation_manager", "ui.pet.desktop_pet"):
                stack.enter_context(patch(module + ".config_manager", store))
            stack.enter_context(patch("app.ai.conversation_manager.AIProvider", return_value=provider))
            stack.enter_context(patch("app.ai.conversation_manager.WebToolService", return_value=web))
            animator = Animator()
            manager = ConversationManager(group_backend=Mock())
            pet = DesktopPet()
            painted = []
            pet.image_label.frame_painted.connect(painted.append)
            try:
                pet.show()
                animator.on_app_started()
                self.app.processEvents()
                manager.handle_user_message("Synthetic input")
                happy = str(PET_EMOTIONS_DIR / "Nova_happy.png")
                for _ in range(200):
                    QTest.qWait(10)
                    if happy in painted and finished.is_set():
                        break
                self.assertTrue(finished.is_set())
                self.assertIn(happy, painted)
                self.assertEqual(pet.current_image_path, happy)
                self.assertEqual(animator.current_state, "emotion")
                self.assertFalse(animator.animation_timer.isActive())
                expected = QPixmap(happy).scaled(300, 300, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self.assertEqual(pet.image_label.pixmap().toImage(), expected.toImage())
                self.assertEqual(store.save_history.call_args.args[0][-1]["content"], "Synthetic reply")
            finally:
                for worker in workers:
                    worker.join(timeout=2)
                animator.shutdown()
                event_bus.unsubscribe("chat_message_requested", manager.handle_user_message)
                event_bus.unsubscribe("chat_response_cancel_requested", manager.handle_cancel_requested)
                event_bus.unsubscribe("update_pet_image", pet.update_image)
                event_bus.unsubscribe("config_updated", pet.on_config_updated)
                pet.close()
                pet.deleteLater()
                animator.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
