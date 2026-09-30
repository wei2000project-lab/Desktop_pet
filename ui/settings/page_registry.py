"""The ordered pages shown by the settings window."""

from PySide6.QtWidgets import QStyle

from ui.dashboard.page_registry import PageDefinition
from ui.settings.pages import AIPage, AppearancePage, BehaviorPage, GeneralPage, PersonalityPage


def default_page_definitions() -> tuple[PageDefinition, ...]:
    """Return the single ordered source used by both navigation and content."""
    return (
        PageDefinition("general", "一般", QStyle.SP_FileDialogInfoView, GeneralPage),
        PageDefinition("appearance", "外觀", QStyle.SP_DesktopIcon, AppearancePage),
        PageDefinition("behavior", "行為", QStyle.SP_BrowserReload, BehaviorPage),
        PageDefinition("ai", "AI", QStyle.SP_ComputerIcon, AIPage),
        PageDefinition("personality", "人格", QStyle.SP_DialogYesButton, PersonalityPage),
    )
