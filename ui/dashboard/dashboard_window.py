"""Reusable navigation shell with no knowledge of settings or persistence."""
from PySide6.QtWidgets import (
    QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.dashboard.page_registry import PageDefinition
from ui.dashboard.sidebar import DashboardSidebar
from ui.dashboard.styles import DASHBOARD_STYLES


class DashboardWindow(QMainWindow):
    DEFAULT_WIDTH = 900
    DEFAULT_HEIGHT = 650
    MINIMUM_WIDTH = 650
    MINIMUM_HEIGHT = 600
    AUTO_COLLAPSE_WIDTH = 800

    def __init__(
        self,
        parent=None,
        page_definitions: tuple[PageDefinition, ...] = (),
        *,
        title: str = "Nova",
    ):
        super().__init__(parent)
        self.page_definitions = tuple(page_definitions)
        self._page_indexes = {
            definition.key: index
            for index, definition in enumerate(self.page_definitions)
        }
        if len(self._page_indexes) != len(self.page_definitions):
            raise ValueError("Dashboard page keys must be unique")
        self._manual_collapsed = False
        self._was_narrow = self.DEFAULT_WIDTH < self.AUTO_COLLAPSE_WIDTH
        self.setObjectName("dashboardWindow")
        self.setWindowTitle(title)
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        central = QWidget()
        central.setObjectName("dashboardCentralWidget")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = DashboardSidebar(self.page_definitions, title=title)
        self.sidebar.page_selected.connect(self.select_page)
        self.sidebar.collapsed_changed.connect(self._remember_sidebar_choice)
        layout.addWidget(self.sidebar)

        content_container = QWidget()
        content_container.setObjectName("dashboardContentContainer")
        self._content_layout = QVBoxLayout(content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("dashboardContentStack")
        for definition in self.page_definitions:
            page = definition.factory()
            page.setObjectName(f"dashboardPage_{definition.key}")
            self.content_stack.addWidget(page)
        self._content_layout.addWidget(self.content_stack, 1)
        layout.addWidget(content_container, 1)
        self.setCentralWidget(central)

        if self.page_definitions:
            self.select_page(self.page_definitions[0].key)
        self.setStyleSheet(DASHBOARD_STYLES)

    @property
    def current_page_key(self) -> str | None:
        index = self.content_stack.currentIndex()
        if index < 0:
            return None
        return self.page_definitions[index].key

    def page_for_key(self, key: str) -> QWidget:
        return self.content_stack.widget(self._page_index(key))

    def _page_index(self, key: str) -> int:
        try:
            return self._page_indexes[key]
        except KeyError:
            raise KeyError(f"Unknown dashboard page: {key}") from None

    def select_page(self, key: str) -> None:
        self.content_stack.setCurrentIndex(self._page_index(key))
        self.sidebar.set_selected(key)

    def add_content_footer(self, widget: QWidget) -> None:
        """Place a caller-owned footer below the content stack."""
        self._content_layout.addWidget(widget)

    def _remember_sidebar_choice(self, collapsed: bool) -> None:
        self._manual_collapsed = collapsed

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        is_narrow = event.size().width() < self.AUTO_COLLAPSE_WIDTH
        if is_narrow != self._was_narrow:
            self._was_narrow = is_narrow
            self.sidebar.set_collapsed(
                True if is_narrow else self._manual_collapsed,
                emit_signal=False,
            )
