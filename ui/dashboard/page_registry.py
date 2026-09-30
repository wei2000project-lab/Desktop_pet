"""Page metadata shared by the dashboard navigation and content stack."""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QStyle, QWidget


PageFactory = Callable[[], QWidget]


@dataclass(frozen=True)
class PageDefinition:
    key: str
    title: str
    icon: QStyle.StandardPixmap
    factory: PageFactory
