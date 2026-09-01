import sys
from PySide6.QtWidgets import QApplication
from utils.logger import logger
from core.event_bus import event_bus
from core.window_manager import WindowManager

class NovaApplication:
    def __init__(self):
        logger.info("Initializing Nova Application")
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Initialize WindowManager
        self.window_manager = WindowManager()
        
        # Connect app clean up on shutdown
        self.app.aboutToQuit.connect(self.on_shutdown)

    def run(self) -> int:
        logger.info("Starting Nova Application Main Loop")
        self.window_manager.show_pet()
        
        # Publish startup event
        event_bus.publish("app_started")
        
        ret = self.app.exec()
        return ret

    def on_shutdown(self):
        logger.info("Application shutting down...")
        event_bus.publish("app_shutdown")
