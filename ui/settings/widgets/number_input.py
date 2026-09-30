"""Numeric editor with separate, reliably clickable step buttons."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDoubleSpinBox, QHBoxLayout, QPushButton, QSpinBox, QWidget,
)
from ui.settings.widgets.input_controls import finish_input


class _NumberInput(QWidget):
    def _setup(self, editor):
        self.editor = editor
        editor.setButtonSymbols(QAbstractSpinBox.NoButtons)
        editor.setKeyboardTracking(False)
        self.setFocusProxy(editor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.minus_button = QPushButton("−")
        self.plus_button = QPushButton("＋")
        for button, name in ((self.minus_button, "減少"), (self.plus_button, "增加")):
            button.setObjectName("settingsNumberStepButton")
            button.setFixedSize(36, 36)
            button.setAccessibleName(name)
            button.setToolTip(name)
        layout.addWidget(self.minus_button)
        layout.addWidget(editor, 1)
        layout.addWidget(self.plus_button)
        self.minus_button.clicked.connect(lambda: self._step(-1))
        self.plus_button.clicked.connect(lambda: self._step(1))
        editor.valueChanged.connect(self.valueChanged)
        editor.valueChanged.connect(self._update_buttons)
        self._update_buttons()

    def _step(self, amount):
        self.editor.interpretText()
        self.editor.stepBy(amount)
        finish_input(self.editor)

    def _update_buttons(self, *_args):
        self.minus_button.setEnabled(self.value() > self.minimum())
        self.plus_button.setEnabled(self.value() < self.maximum())

    def setAccessibleName(self, name):
        super().setAccessibleName(name)
        self.editor.setAccessibleName(name)
        self.minus_button.setAccessibleName(f"減少{name}")
        self.plus_button.setAccessibleName(f"增加{name}")

    def value(self):
        return self.editor.value()

    def setValue(self, value):
        self.editor.setValue(value)
        self._update_buttons()

    def setRange(self, minimum, maximum):
        self.editor.setRange(minimum, maximum)
        self._update_buttons()

    def minimum(self):
        return self.editor.minimum()

    def maximum(self):
        return self.editor.maximum()

    def setSingleStep(self, step):
        self.editor.setSingleStep(step)

    def singleStep(self):
        return self.editor.singleStep()

    def setSuffix(self, suffix):
        self.editor.setSuffix(suffix)

    def interpretText(self):
        self.editor.interpretText()


class IntegerInput(_NumberInput):
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup(QSpinBox())


class DecimalInput(_NumberInput):
    valueChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup(QDoubleSpinBox())

    def setDecimals(self, decimals):
        self.editor.setDecimals(decimals)
