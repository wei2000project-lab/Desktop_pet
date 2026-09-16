import sys

from PySide6.QtWidgets import QApplication

from app.ai.conversation_manager import ConversationManager
from app.animation.animator import Animator
from app.control.execution.request_handler import AppOpenRequestHandler
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.user_message_router import UserMessageRouter
from app.core.window_manager import WindowManager
from ui.pet.bubble import ChatBubble
from ui.pet.desktop_pet import DesktopPet
from ui.pet.dialogs.app_open_confirmation import AppOpenConfirmation
from ui.pet.dialogs.app_preference_choice import AppPreferenceChoice


class NovaApplication:
    def __init__(self):
        logger.info("Initializing Nova Application")
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.window_manager = WindowManager()
        self.animator = Animator()
        self.user_message_router = UserMessageRouter(event_bus)
        self.conversation_manager = ConversationManager()
        self.app_open_handler = AppOpenRequestHandler(event_bus)
        self.app_open_confirmation = AppOpenConfirmation(event_bus)
        self.app_preference_choice = AppPreferenceChoice(event_bus)

        self.pet_window = DesktopPet()
        self.bubble_window = ChatBubble()
        self.window_manager.set_pet_window(self.pet_window)
        self.window_manager.set_bubble_window(self.bubble_window)

        self.app.aboutToQuit.connect(self.on_shutdown)

    def run(self) -> int:
        logger.info("Starting Nova Application Main Loop")
        self.window_manager.show_pet()
        event_bus.publish("app_started")
        return self.app.exec()

    def on_shutdown(self):
        logger.info("Application shutting down...")
        event_bus.publish("app_shutdown")


def run_application() -> int:
    logger.info("========================================")
    logger.info("Starting Nova Desktop Assistant...")
    logger.info("========================================")
    return NovaApplication().run()
