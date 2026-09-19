"""Dashboard controls whose values change only through deliberate input."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QAbstractSpinBox, QCheckBox, QComboBox,
    QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)


def scroll_page_with_wheel(scroll_area, event):
    """Use Wheel exclusively for one page's scroll bars."""
    vertical = scroll_area.verticalScrollBar()
    horizontal = scroll_area.horizontalScrollBar()
    pixel = event.pixelDelta()
    angle = event.angleDelta()
    if pixel.y() or angle.y():
        amount = pixel.y() if pixel.y() else angle.y() / 120 * vertical.singleStep() * 3
        vertical.setValue(vertical.value() - round(amount))
    elif pixel.x() or angle.x():
        amount = pixel.x() if pixel.x() else angle.x() / 120 * horizontal.singleStep() * 3
        horizontal.setValue(horizontal.value() - round(amount))
    event.accept()


def finish_input(widget):
    """Commit an editor and remove both focus and any lingering selection."""
    if isinstance(widget, QAbstractSpinBox):
        widget.interpretText()
        line_edit = widget.lineEdit()
        line_edit.deselect()
        widget.clearFocus()
        line_edit.deselect()
        return
    if isinstance(widget, QLineEdit):
        widget.deselect()
        widget.clearFocus()
        widget.deselect()
        return
    if isinstance(widget, (QPlainTextEdit, QTextEdit)):
        cursor = widget.textCursor()
        cursor.clearSelection()
        widget.setTextCursor(cursor)
        widget.clearFocus()


class FocusClearingWidget(QWidget):
    """Commit the focused editor when the user clicks an otherwise empty surface."""

    def mousePressEvent(self, event):
        focused = QApplication.focusWidget()
        if focused is not None and self.isAncestorOf(focused):
            finish_input(focused)
        super().mousePressEvent(event)


class NoWheelComboBox(QComboBox):
    """Semantic type; DashboardWindow owns its Wheel policy."""


class NoWheelCheckBox(QCheckBox):
    """Semantic type; DashboardWindow owns its Wheel policy."""


class ToggleSwitch(QAbstractButton):
    """Compact, keyboard-accessible on/off control for Dashboard settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)

    def sizeHint(self):
        return QSize(46, 26)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        enabled = self.isEnabled()
        track = QColor("#7b4ba0" if self.isChecked() else "#aaa4b0")
        if not enabled:
            track.setAlpha(110)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(1, 3, 44, 20), 10, 10)
        knob_x = 24 if self.isChecked() else 4
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(knob_x, 5, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#5f2d82"), 2))
            painter.drawRoundedRect(QRectF(1, 1, 44, 24), 12, 12)
