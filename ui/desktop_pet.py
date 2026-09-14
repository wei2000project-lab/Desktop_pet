import os
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QPixmap, QMouseEvent, QAction
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu
from app.utils.logger import logger
from app.core.event_bus import event_bus
from config.config_manager import config_manager

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()
        self.drag_position = QPoint()
        self.is_dragging = False
        
        # Load size configs
        self.pet_width = config_manager.get_general_int("Width", 500)
        self.pet_height = config_manager.get_general_int("Height", 500)
        self.current_image_path = ""
        
        self.setup_ui()
        
        # Subscribe to updates
        event_bus.subscribe("update_pet_image", self.update_image)
        event_bus.subscribe("config_updated", self.on_config_updated)
        
        # Restore position
        self.restore_position()

    def setup_ui(self):
        # Frameless, Always on Top, Tool window (does not show in taskbar)
        flags = Qt.FramelessWindowHint | Qt.Tool
        if config_manager.get_general_bool("AlwaysOnTop", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        
        # Translucent background
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Set window size slightly larger than configured size to prevent clipping (10px padding on each side)
        self.setFixedSize(QSize(self.pet_width + 20, self.pet_height + 20))

        # Use layout contents margins to establish the boundary, avoiding manual label positioning (no displacement)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(0)
        
        self.image_label = QLabel(self)
        self.image_label.setScaledContents(True)
        self.layout.addWidget(self.image_label)

    def update_image(self, path: str):
        if not os.path.exists(path):
            logger.error(f"Image not found at path: {path}")
            return
        
        self.current_image_path = path
        pixmap = QPixmap(path)
        # Scale directly to configured pet size, ignoring aspect ratio to stretch to exact bounds
        scaled_pixmap = pixmap.scaled(
            self.pet_width, self.pet_height, 
            Qt.IgnoreAspectRatio, 
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        
        # Center of the window
        x = (self.width() - scaled_pixmap.width()) // 2
        y = (self.height() - scaled_pixmap.height()) // 2
        
        # Create a combined transparent pixmap matching window size to calculate shifted mask
        combined_pixmap = QPixmap(self.size())
        combined_pixmap.fill(Qt.transparent)
        
        from PySide6.QtGui import QPainter
        painter = QPainter(combined_pixmap)
        painter.drawPixmap(x, y, scaled_pixmap)
        painter.end()
        
        self.setMask(combined_pixmap.mask())

    def on_config_updated(self):
        logger.info("Applying updated configurations to DesktopPet")
        
        # 1. Capture current size and center point
        old_width = self.width()
        old_height = self.height()
        old_center_x = self.x() + old_width / 2
        old_center_y = self.y() + old_height / 2
        
        # 2. Load new size settings
        self.pet_width = config_manager.get_general_int("Width", 250)
        self.pet_height = config_manager.get_general_int("Height", 250)
        new_width = self.pet_width + 20
        new_height = self.pet_height + 20
        
        # 3. Resize window
        self.setFixedSize(QSize(new_width, new_height))

        # 4. Calculate new position to align with the same center point
        new_x = int(old_center_x - new_width / 2)
        new_y = int(old_center_y - new_height / 2)
        
        # 5. Clamp to screen coordinates to prevent the pet from floating off-screen
        try:
            screen = self.screen().geometry()
            new_x = max(screen.left(), min(screen.right() - new_width, new_x))
            new_y = max(screen.top(), min(screen.bottom() - new_height, new_y))
        except Exception as e:
            logger.warning(f"Failed to get screen geometry: {e}")

        # 6. Re-apply stays-on-top flags only if flag value changed
        always_on_top = config_manager.get_general_bool("AlwaysOnTop", True)
        current_flags = self.windowFlags()
        has_stay_on_top = bool(current_flags & Qt.WindowStaysOnTopHint)
        
        if always_on_top != has_stay_on_top:
            flags = Qt.FramelessWindowHint | Qt.Tool
            if always_on_top:
                flags |= Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()

        # 7. Move to the new center-preserving clamped position
        self.move(new_x, new_y)
        
        # 8. Save updated coordinates back to config.ini
        config_manager.set_general("PositionX", new_x)
        config_manager.set_general("PositionY", new_y)

        # 9. Re-render image with new size
        if self.current_image_path:
            self.update_image(self.current_image_path)






    def restore_position(self):
        x = config_manager.get_general_int("PositionX", -1)
        y = config_manager.get_general_int("PositionY", -1)
        if x != -1 and y != -1:
            self.move(x, y)
        else:
            # Default to bottom right of screen
            screen = self.screen().geometry()
            self.move(screen.width() - self.width() - 50, screen.height() - self.height() - 100)

    # Mouse drag and click handlers
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging = True
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.is_dragging:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            event_bus.publish("pet_moved", new_pos.x(), new_pos.y())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_dragging:
            self.is_dragging = False
            # Save position to config
            config_manager.set_general("PositionX", self.x())
            config_manager.set_general("PositionY", self.y())
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Toggle chat bubble
            event_bus.publish("show_bubble")
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        chat_action = QAction("對話 (Chat)", self)
        chat_action.triggered.connect(lambda: event_bus.publish("show_bubble"))
        
        settings_action = QAction("設定 (Settings)", self)
        settings_action.triggered.connect(lambda: event_bus.publish("show_settings"))
        
        exit_action = QAction("結束 (Exit)", self)
        from PySide6.QtWidgets import QApplication
        exit_action.triggered.connect(QApplication.quit)
        
        menu.addAction(chat_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        
        menu.exec(event.globalPos())
