from typing import Optional
from PySide6.QtCore import QPoint
from app.utils.logger import logger
from app.core.event_bus import event_bus

class WindowManager:
    def __init__(self):
        self.pet_window = None
        self.bubble_window = None
        self.settings_window = None
        self.settings_presenter = None
        
        # Subscribe to window-related events
        event_bus.subscribe("show_bubble", self.show_bubble)
        event_bus.subscribe("hide_bubble", self.hide_bubble)
        event_bus.subscribe("toggle_bubble", self.toggle_bubble)
        event_bus.subscribe("show_settings", self.show_settings)
        event_bus.subscribe("pet_moved", self.on_pet_moved)
        event_bus.subscribe("config_updated", self.on_config_updated)


    def set_pet_window(self, window):
        self.pet_window = window

    def set_bubble_window(self, window):
        self.bubble_window = window

    def show_pet(self):
        if self.pet_window:
            self.pet_window.show()
            logger.info("Pet window shown")

    def show_bubble(self):
        if self.bubble_window:
            self.update_bubble_position()
            self.bubble_window.show()
            self.bubble_window.raise_()
            logger.info("Bubble window shown")

    def hide_bubble(self):
        if self.bubble_window:
            self.bubble_window.hide()
            logger.info("Bubble window hidden")

    def toggle_bubble(self):
        if not self.bubble_window:
            return
        if self.bubble_window.isVisible():
            self.hide_bubble()
            return
        self.show_bubble()

    def show_settings(self):
        try:
            if self.settings_window is None:
                from ui.settings import SettingsWindow
                from app.settings.presenter import SettingsPresenter
                window = SettingsWindow()
                try:
                    presenter = SettingsPresenter(window)
                except Exception:
                    window.deleteLater()
                    raise
                self.settings_window = window
                self.settings_presenter = presenter
            elif not self.settings_window.isVisible():
                self.settings_presenter.reload()
        except Exception:
            logger.error("Failed to open settings", exc_info=True)
            return
        self.settings_window.showNormal()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        logger.info("Settings window shown")

    def on_pet_moved(self, x: int, y: int):
        if self.bubble_window and self.bubble_window.isVisible():
            self.update_bubble_position()

    def on_config_updated(self):
        if self.bubble_window and self.bubble_window.isVisible():
            self.update_bubble_position()

    def update_bubble_position(self):
        if self.pet_window and self.bubble_window:
            pet_pos = self.pet_window.pos()
            # Calculate position to float bubble slightly above and to the right/left of the pet
            # Pet size is 500x500. Let's place bubble above the pet
            bubble_x = pet_pos.x() + (self.pet_window.width() - self.bubble_window.width()) // 2
            bubble_y = pet_pos.y() - self.bubble_window.height() + 50 # overlap slightly for visual connection
            
            # Prevent going off screen top
            if bubble_y < 0:
                # If too high, show to the left or right side
                bubble_y = pet_pos.y() + 50
                bubble_x = pet_pos.x() - self.bubble_window.width() + 20
            
            self.bubble_window.move(bubble_x, bubble_y)
