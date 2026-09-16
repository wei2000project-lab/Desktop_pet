from dataclasses import dataclass
from functools import partial
from typing import Callable

from PySide6.QtWidgets import QStyle, QWidget

from ui.dashboard.pages import AppearancePage, GeneralPage, PlaceholderPage


PageFactory = Callable[[], QWidget]


@dataclass(frozen=True)
class PageDefinition:
    key: str
    title: str
    icon: QStyle.StandardPixmap
    factory: PageFactory


def default_page_definitions() -> tuple[PageDefinition, ...]:
    """Return the single ordered source used by both navigation and content."""
    pages = (
        ("behavior", "行為", QStyle.SP_BrowserReload, "管理桌寵待機與動畫行為。"),
        ("ai", "AI", QStyle.SP_ComputerIcon, "管理模型、連線與記憶設定。"),
        ("personality", "人格", QStyle.SP_DialogYesButton, "選擇內建人格或編輯自訂人格。"),
    )
    placeholders = tuple(
        PageDefinition(key, title, icon, partial(PlaceholderPage, title, description))
        for key, title, icon, description in pages
    )
    return (
        PageDefinition("general", "一般", QStyle.SP_FileDialogInfoView, GeneralPage),
        PageDefinition("appearance", "外觀", QStyle.SP_DesktopIcon, AppearancePage),
        *placeholders,
    )
