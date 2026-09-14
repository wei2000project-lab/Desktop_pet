import sys
import os
from app.utils.logger import logger
from app.core.event_bus import event_bus
from app.core.application import NovaApplication
from app.animation.animator import Animator
from app.ai.conversation_manager import ConversationManager
from app.core.user_message_router import UserMessageRouter
from app.control.execution.request_handler import AppOpenRequestHandler
from ui.desktop_pet import DesktopPet
from ui.bubble import ChatBubble
from ui.app_open_confirmation import AppOpenConfirmation
from ui.app_preference_choice import AppPreferenceChoice

def main():
    logger.info("========================================")
    logger.info("Starting Nova Desktop Assistant...")
    logger.info("========================================")
    
    # 1. Initialize Application
    nova_app = NovaApplication()
    
    # Get base directory (project root)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 2. Initialize Decoupled Modules
    # Animator
    animator = Animator(base_dir)
    
    # User message router splits chat from app-control intents.
    user_message_router = UserMessageRouter(event_bus)

    # AI Conversation Manager (handles prompts, history, memory and calls Provider)
    conv_manager = ConversationManager()

    # App-open request handler selects apps and waits for confirmation before launch.
    app_open_handler = AppOpenRequestHandler(event_bus)
    app_open_confirmation = AppOpenConfirmation(event_bus)
    app_preference_choice = AppPreferenceChoice(event_bus)

    # 3. Create Windows
    pet_window = DesktopPet()
    bubble_window = ChatBubble()

    # 4. Register windows in WindowManager
    nova_app.window_manager.set_pet_window(pet_window)
    nova_app.window_manager.set_bubble_window(bubble_window)

    # 5. Run Qt event loop
    sys.exit(nova_app.run())

if __name__ == "__main__":
    main()
