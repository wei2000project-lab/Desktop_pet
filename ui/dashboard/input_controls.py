"""Dashboard controls whose values change only through deliberate input."""
from PySide6.QtWidgets import (
    QApplication, QAbstractSpinBox, QCheckBox, QComboBox,
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
