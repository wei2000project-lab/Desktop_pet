"""Application-styled modal dialogs used inside the Settings."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox as _NativeMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)


class SettingsDialog(QDialog):
    """Small frameless dialog with a QMessageBox-compatible public facade."""

    StandardButton = _NativeMessageBox.StandardButton
    Ok = StandardButton.Ok
    Save = StandardButton.Save
    Discard = StandardButton.Discard
    Cancel = StandardButton.Cancel
    Yes = StandardButton.Yes
    No = StandardButton.No

    _BUTTON_ORDER = (Save, Discard, Yes, No, Ok, Cancel)
    _BUTTON_TEXT = {
        Save: "儲存",
        Discard: "不儲存",
        Cancel: "取消",
        Yes: "確認",
        No: "取消",
        Ok: "確定",
    }

    def __init__(self, parent, title, message, buttons, default_button, kind="question"):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setModal(True)
        self.setMinimumWidth(390)
        self.setMaximumWidth(520)
        self._buttons = {}
        self._fallback = self._fallback_button(buttons, default_button)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("settingsDialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(14)

        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("settingsDialogTitle")
        title_label.setWordWrap(True)
        close_button = QPushButton("×")
        close_button.setObjectName("settingsDialogClose")
        close_button.setAccessibleName("關閉對話框")
        close_button.setFixedSize(32, 32)
        close_button.clicked.connect(self.reject)
        heading.addWidget(title_label, 1)
        heading.addWidget(close_button)
        card_layout.addLayout(heading)

        message_label = QLabel(message)
        message_label.setObjectName("settingsDialogMessage")
        message_label.setTextFormat(Qt.PlainText)
        message_label.setWordWrap(True)
        message_label.setMinimumWidth(330)
        card_layout.addWidget(message_label)

        actions = QHBoxLayout()
        actions.setSpacing(9)
        actions.addStretch(1)
        destructive = kind == "warning" or "刪除" in title
        for choice in self._BUTTON_ORDER:
            if not buttons & choice:
                continue
            button = QPushButton(self._BUTTON_TEXT[choice])
            if choice == default_button:
                button.setDefault(True)
            if choice in (self.Cancel, self.No, self.Discard):
                button.setObjectName("settingsDialogSecondary")
            elif destructive and choice == self.Yes:
                button.setObjectName("settingsDialogDanger")
            else:
                button.setObjectName("settingsDialogPrimary")
            button.clicked.connect(lambda _checked=False, result=choice: self.done(int(result)))
            self._buttons[choice] = button
            actions.addWidget(button)
        card_layout.addLayout(actions)
        outer.addWidget(card)
        self.setStyleSheet(self._style_sheet())

    @classmethod
    def question(cls, parent, title, message, buttons, default_button):
        return cls._run(parent, title, message, buttons, default_button, "question")

    @classmethod
    def warning(cls, parent, title, message):
        return cls._run(parent, title, message, cls.Ok, cls.Ok, "warning")

    @classmethod
    def information(cls, parent, title, message):
        return cls._run(parent, title, message, cls.Ok, cls.Ok, "information")

    @classmethod
    def _run(cls, parent, title, message, buttons, default_button, kind):
        dialog = cls(parent, title, message, buttons, default_button, kind)
        return cls.StandardButton(dialog.exec())

    @classmethod
    def _fallback_button(cls, buttons, default_button):
        if buttons & cls.Cancel:
            return cls.Cancel
        if buttons & cls.No:
            return cls.No
        if buttons & default_button:
            return default_button
        return next((choice for choice in cls._BUTTON_ORDER if buttons & choice), cls.Ok)

    def button(self, choice):
        return self._buttons.get(choice)

    def reject(self):
        self.done(int(self._fallback))

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            frame = self.frameGeometry()
            frame.moveCenter(parent.frameGeometry().center())
            self.move(frame.topLeft())

    @staticmethod
    def _style_sheet():
        return """
            QDialog#settingsDialog {
                background-color: transparent;
            }
            #settingsDialogCard {
                background-color: #ffffff;
                border: 1px solid #d8d2dd;
                border-radius: 12px;
            }
            #settingsDialogTitle {
                color: #2e2932;
                font-size: 17px;
                font-weight: 650;
            }
            #settingsDialogMessage {
                color: #5e5864;
                font-size: 14px;
            }
            #settingsDialogClose {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                color: #6d6673;
                font-size: 20px;
                padding: 0;
            }
            #settingsDialogClose:hover, #settingsDialogClose:focus {
                background-color: #f0ecf3;
                border-color: #d8cfdf;
            }
            #settingsDialogPrimary, #settingsDialogDanger,
            #settingsDialogSecondary {
                border-radius: 7px;
                min-height: 34px;
                padding: 0 16px;
            }
            #settingsDialogPrimary {
                background-color: #7b4ba0;
                border: 1px solid #6d3c92;
                color: #ffffff;
            }
            #settingsDialogPrimary:hover, #settingsDialogPrimary:focus {
                background-color: #6d3c92;
                border: 2px solid #4f246d;
            }
            #settingsDialogSecondary {
                background-color: #ffffff;
                border: 1px solid #cfc8d4;
                color: #514b59;
            }
            #settingsDialogSecondary:hover, #settingsDialogSecondary:focus {
                background-color: #f2eef5;
                border: 2px solid #7b4ba0;
            }
            #settingsDialogDanger {
                background-color: #b3261e;
                border: 1px solid #961b15;
                color: #ffffff;
            }
            #settingsDialogDanger:hover, #settingsDialogDanger:focus {
                background-color: #961b15;
                border: 2px solid #74110d;
            }
        """
