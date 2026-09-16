from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from ui.dashboard.page_registry import PageDefinition, default_page_definitions
from ui.dashboard.sidebar import DashboardSidebar


class DashboardWindow(QMainWindow):
    DEFAULT_WIDTH = 900
    DEFAULT_HEIGHT = 850
    MINIMUM_WIDTH = 650
    MINIMUM_HEIGHT = 600
    AUTO_COLLAPSE_WIDTH = 800

    def __init__(
        self,
        parent=None,
        page_definitions: tuple[PageDefinition, ...] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("dashboardWindow")
        self.setWindowTitle("Nova 設定")
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        self.page_definitions = page_definitions or default_page_definitions()
        self._page_indexes = {
            definition.key: index
            for index, definition in enumerate(self.page_definitions)
        }
        self._manual_collapsed = False
        self._was_narrow = self.width() < self.AUTO_COLLAPSE_WIDTH

        central = QWidget()
        central.setObjectName("dashboardCentralWidget")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = DashboardSidebar(self.page_definitions)
        self.sidebar.page_selected.connect(self.select_page)
        self.sidebar.collapsed_changed.connect(self._remember_sidebar_choice)
        layout.addWidget(self.sidebar)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("dashboardContentStack")
        for definition in self.page_definitions:
            page = definition.factory()
            page.setObjectName(f"dashboardPage_{definition.key}")
            self.content_stack.addWidget(page)
        layout.addWidget(self.content_stack, 1)
        self.setCentralWidget(central)

        if self.page_definitions:
            self.select_page(self.page_definitions[0].key)
        self._apply_styles()

    @property
    def current_page_key(self) -> str | None:
        index = self.content_stack.currentIndex()
        if index < 0:
            return None
        return self.page_definitions[index].key

    def select_page(self, key: str) -> None:
        if key not in self._page_indexes:
            raise KeyError(f"Unknown dashboard page: {key}")
        self.content_stack.setCurrentIndex(self._page_indexes[key])
        self.sidebar.set_selected(key)

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

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, #dashboardCentralWidget, #dashboardContentStack,
            #dashboardPageContent {
                background-color: #ffffff;
                color: #24212a;
            }
            #dashboardSidebar {
                background-color: #f6f5f8;
                border-right: 1px solid #dedbe3;
            }
            #dashboardSidebarTitle {
                color: #24212a;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton#dashboardSidebarToggle {
                background-color: transparent;
                border: 1px solid #cbc7d0;
                border-radius: 7px;
                color: #514b59;
                font-size: 20px;
            }
            QPushButton#dashboardSidebarToggle:hover,
            QPushButton#dashboardSidebarToggle:focus {
                background-color: #ece8f2;
                border-color: #7b4ba0;
                color: #5f2d82;
            }
            #dashboardSidebar QPushButton[checkable="true"] {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: #514b59;
                padding: 8px 10px;
                text-align: left;
            }
            #dashboardSidebar QPushButton[checkable="true"]:hover,
            #dashboardSidebar QPushButton[checkable="true"]:focus {
                background-color: #ece8f2;
                border-color: #d4c7df;
            }
            #dashboardSidebar QPushButton[checkable="true"]:checked {
                background-color: #eadcf5;
                border-color: #9b69bd;
                color: #51276d;
                font-weight: 600;
            }
            #dashboardPageHeading {
                color: #24212a;
                font-size: 26px;
                font-weight: 650;
            }
            #dashboardPageDescription {
                color: #625d68;
                font-size: 14px;
            }
            #dashboardPlaceholderStatus {
                background-color: #f7f5f9;
                border: 1px solid #ded8e4;
                border-radius: 10px;
                color: #6d6673;
                padding: 18px;
            }
            """
        )
