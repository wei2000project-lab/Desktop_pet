from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ui.dashboard.page_registry import PageDefinition


class DashboardSidebar(QWidget):
    page_selected = Signal(str)
    collapsed_changed = Signal(bool)

    EXPANDED_WIDTH = 212
    COLLAPSED_WIDTH = 60

    def __init__(self, pages: tuple[PageDefinition, ...], parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardSidebar")
        self._pages = pages
        self._buttons: dict[str, QPushButton] = {}
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 2, 8)
        self.title_label = QLabel("Nova 設定")
        self.title_label.setObjectName("dashboardSidebarTitle")
        header.addWidget(self.title_label, 1)

        self.toggle_button = QPushButton("‹")
        self.toggle_button.setObjectName("dashboardSidebarToggle")
        self.toggle_button.setAccessibleName("收合導覽列")
        self.toggle_button.setToolTip("收合導覽列")
        self.toggle_button.setFixedSize(34, 34)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        header.addWidget(self.toggle_button)
        layout.addLayout(header)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        for page in pages:
            button = QPushButton(page.title)
            button.setObjectName(f"dashboardNav_{page.key}")
            button.setAccessibleName(page.title)
            button.setToolTip(page.title)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.StrongFocus)
            button.setIcon(self.style().standardIcon(page.icon))
            button.setMinimumHeight(42)
            button.clicked.connect(
                lambda checked=False, key=page.key: self.page_selected.emit(key)
            )
            self.button_group.addButton(button)
            self._buttons[page.key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.set_collapsed(False, emit_signal=False)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def button_for_key(self, key: str) -> QPushButton:
        return self._buttons[key]

    def set_selected(self, key: str) -> None:
        self.button_for_key(key).setChecked(True)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, *, emit_signal: bool = True) -> None:
        collapsed = bool(collapsed)
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)
        self.title_label.setVisible(not collapsed)
        self.toggle_button.setText("›" if collapsed else "‹")
        self.toggle_button.setAccessibleName("展開導覽列" if collapsed else "收合導覽列")
        self.toggle_button.setToolTip("展開導覽列" if collapsed else "收合導覽列")
        for page in self._pages:
            button = self._buttons[page.key]
            button.setText("" if collapsed else page.title)
            button.setToolTip(page.title)
        if changed and emit_signal:
            self.collapsed_changed.emit(collapsed)
