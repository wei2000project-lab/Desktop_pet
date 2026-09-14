import os
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QKeyEvent, QTextCharFormat, QColor, QTextCursor, QTextBlockFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, 
    QLineEdit, QPushButton, QLabel, QFrame
)
import queue
from app.utils.logger import logger
from app.core.event_bus import event_bus
from config.config_manager import config_manager
from ui.message_formatting import normalize_chat_text, normalize_stream_chunk, should_auto_scroll


class ChatBubble(QWidget):
    def __init__(self):
        super().__init__()
        self.is_thinking = False
        self.is_waiting_response = False
        self.ai_trailing_newlines = 0
        self.pending_system_notifications = []
        
        # Buffer queue for incoming stream chunks to prevent UI stuttering
        self.chunk_queue = queue.Queue()
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(30)  # Update UI every 30ms
        self.update_timer.timeout.connect(self.process_chunk_queue)
        self.update_timer.start()

        self.setup_ui()
        
        # Subscribe to AI responses
        event_bus.subscribe("ai_message_started", self.on_ai_started)
        event_bus.subscribe("ai_message_chunk", self.on_ai_chunk)
        event_bus.subscribe("ai_message_finished", self.on_ai_finished)
        event_bus.subscribe("ai_message_error", self.on_ai_error)
        event_bus.subscribe("ai_message_cancelled", self.on_ai_cancelled)
        event_bus.subscribe("chat_system_notification", self.on_system_notification)

    def setup_ui(self):
        # Frameless, Always on Top, Tool window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(QSize(320, 260))
        
        # Main background container frame
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: rgba(28, 28, 35, 230);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 16px;
            }
        """)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header (Title & Close Button)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        name = config_manager.get_prompt().get("name", "Nova")
        self.title_label = QLabel(name, self.container)
        self.title_label.setStyleSheet("color: #bb86fc; font-weight: bold; font-size: 13px; background: transparent;")
        
        self.close_btn = QPushButton("✕", self.container)
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888888;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ff5555;
            }
        """)
        self.close_btn.clicked.connect(self.hide_bubble)
        
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_btn)
        layout.addLayout(header_layout)

        # Chat Log (QTextBrowser)
        self.chat_log = QTextBrowser(self.container)
        self.chat_log.setOpenExternalLinks(True)
        # Prevent user from editing the text log
        self.chat_log.setReadOnly(True)
        self.chat_log.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
        """)
        
        # Set default text margins and zero out paragraph spacing
        doc = self.chat_log.document()
        doc.setDocumentMargin(4)
        
        self.chat_log.setHtml("<p style='color: #888888; margin: 0;'>雙擊 Nova 可以打開或關閉對話泡泡。輸入文字與我聊天吧！</p>")
        layout.addWidget(self.chat_log)

        # Input Area (Layout)
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)
        
        self.input_field = QLineEdit(self.container)
        self.input_field.setPlaceholderText("輸入訊息...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(45, 45, 55, 180);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #bb86fc;
                background-color: rgba(50, 50, 65, 220);
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("送出", self.container)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #6200ee;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #7f39fb;
            }
            QPushButton:pressed {
                background-color: #3700b3;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # Main widget layout to embed container
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container)

    def hide_bubble(self):
        event_bus.publish("hide_bubble")

    def _scroll_to_bottom(self):
        scrollbar = self.chat_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _should_follow_output(self, force: bool = False) -> bool:
        scrollbar = self.chat_log.verticalScrollBar()
        return should_auto_scroll(scrollbar.value(), scrollbar.maximum(), force=force)

    def _append_text_block(
        self,
        prefix: str,
        text: str,
        prefix_color: str,
        text_color: str = "#e0e0e0",
        force_scroll: bool = False,
    ):
        """Helper to append a text block with zero paragraph margin to keep spacing clean."""
        follow_output = self._should_follow_output(force=force_scroll)
        cursor = self.chat_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Insert block with 0 top/bottom margin
        block_fmt = QTextBlockFormat()
        block_fmt.setTopMargin(0)
        block_fmt.setBottomMargin(4)  # Small margin between chat turns
        
        # LineHeightTypes.ProportionalHeight is 1, height is float
        block_fmt.setLineHeight(115.0, 1)
        cursor.insertBlock(block_fmt)
        
        # Write prefix
        prefix_fmt = QTextCharFormat()
        prefix_fmt.setFontWeight(QFont.Weight.Bold)
        prefix_fmt.setForeground(QColor(prefix_color))
        cursor.insertText(prefix, prefix_fmt)
        
        # Write text
        text_fmt = QTextCharFormat()
        text_fmt.setFontWeight(QFont.Weight.Normal)
        text_fmt.setForeground(QColor(text_color))
        text_fmt.setFontItalic(False)
        cursor.insertText(normalize_chat_text(text), text_fmt)
        
        if follow_output:
            self._scroll_to_bottom()

    def send_message(self):
        if self.is_waiting_response:
            self.cancel_response()
            return

        text = self.input_field.text().strip()
        if not text:
            return
        
        # Append user message with custom tight block styling
        self._append_text_block("我: ", text, prefix_color="#03dac6", force_scroll=True)
        self.input_field.clear()
        
        # Publish event for AI module
        event_bus.publish("user_message_sent", text)

    def cancel_response(self):
        self.send_btn.setEnabled(False)
        event_bus.publish("chat_response_cancel_requested")

    def on_ai_started(self):
        self.is_thinking = True
        self.is_waiting_response = True
        self.ai_trailing_newlines = 0
        self.send_btn.setText("停止")
        self.send_btn.setEnabled(True)
        # Set UI title to indicate progress
        name = config_manager.get_prompt().get("name", "Nova")
        self.title_label.setText(f"{name} (思考中...)")
        
        # We start the AI turn with just the name prefix
        self._append_text_block(f"{name}: ", "", prefix_color="#bb86fc", force_scroll=True)

    def on_ai_chunk(self, chunk_text: str):
        # Place it in buffer queue to be consumed smoothly by the QTimer
        self.chunk_queue.put(chunk_text)

    def process_chunk_queue(self):
        """Processes chunks from the queue and appends them to the end of the document."""
        if self.chunk_queue.empty():
            return

        # Fetch all currently buffered chunks to print them in a batch
        text_batch = ""
        while not self.chunk_queue.empty():
            text_batch += self.chunk_queue.get_nowait()
            
        if not text_batch:
            return

        # If this is the first batch of chunks, reset the title
        if self.is_thinking:
            self.is_thinking = False
            name = config_manager.get_prompt().get("name", "Nova")
            self.title_label.setText(name)

        follow_output = self._should_follow_output()

        # Append directly to the end of the text browser
        cursor = self.chat_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        text_fmt = QTextCharFormat()
        text_fmt.setFontWeight(QFont.Weight.Normal)
        text_fmt.setForeground(QColor("#e0e0e0"))
        text_fmt.setFontFamily("Segoe UI")
        text_fmt.setFontItalic(False)
        text_batch, self.ai_trailing_newlines = normalize_stream_chunk(
            text_batch,
            self.ai_trailing_newlines,
        )
        if not text_batch:
            return

        cursor.insertText(text_batch, text_fmt)
        
        if follow_output:
            self._scroll_to_bottom()

    def on_ai_finished(self, response: str):
        self.is_thinking = False
        self.is_waiting_response = False
        name = config_manager.get_prompt().get("name", "Nova")
        self.title_label.setText(name)
        self.send_btn.setText("送出")
        self.send_btn.setEnabled(True)
        
        # Empty any remaining chunks in the queue
        self.process_chunk_queue()
        if self._should_follow_output():
            self._scroll_to_bottom()
        self._flush_system_notifications()

    def on_ai_error(self, error_msg: str):
        self.is_thinking = False
        self.is_waiting_response = False
        name = config_manager.get_prompt().get("name", "Nova")
        self.title_label.setText(name)
        self.send_btn.setText("送出")
        self.send_btn.setEnabled(True)
        
        # Log error in red
        self._append_text_block(
            "錯誤: ",
            error_msg,
            prefix_color="#ff5555",
            text_color="#ff8888",
            force_scroll=True,
        )
        self._flush_system_notifications()

    def on_ai_cancelled(self):
        self.is_thinking = False
        self.is_waiting_response = False
        self.ai_trailing_newlines = 0
        name = config_manager.get_prompt().get("name", "Nova")
        self.title_label.setText(name)
        self.send_btn.setText("送出")
        self.send_btn.setEnabled(True)
        while not self.chunk_queue.empty():
            self.chunk_queue.get_nowait()
        self._append_text_block(
            "系統: ",
            "已停止回覆。",
            prefix_color="#888888",
            text_color="#bbbbbb",
            force_scroll=True,
        )
        self._flush_system_notifications()

    def on_system_notification(self, message: str, is_error: bool = False):
        if self.is_waiting_response:
            self.pending_system_notifications.append((message, is_error))
            return
        self._append_system_notification(message, is_error)

    def _flush_system_notifications(self):
        notifications = self.pending_system_notifications
        self.pending_system_notifications = []
        for message, is_error in notifications:
            self._append_system_notification(message, is_error)

    def _append_system_notification(self, message: str, is_error: bool):
        self._append_text_block(
            "系統: ",
            message,
            prefix_color="#ff5555" if is_error else "#888888",
            text_color="#ff8888" if is_error else "#bbbbbb",
            force_scroll=True,
        )
