from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class PlaceholderPage(QScrollArea):
    """Scrollable placeholder used while existing settings are migrated page by page."""

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setObjectName(f"{title}Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        content.setObjectName("dashboardPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("dashboardPageHeading")
        heading.setAccessibleName(f"{title}頁面標題")

        message = QLabel(description)
        message.setObjectName("dashboardPageDescription")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        status = QLabel("設定內容將在下一階段逐頁搬入。")
        status.setObjectName("dashboardPlaceholderStatus")
        status.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(message)
        layout.addSpacing(12)
        layout.addWidget(status)
        layout.addStretch(1)
        self.setWidget(content)
