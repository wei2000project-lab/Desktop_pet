import random
from pathlib import Path
from typing import Callable, List

from app.core.paths import PET_ANIMATIONS_DIR


class ReadingAnimation:
    def __init__(self, animations_dir: Path = PET_ANIMATIONS_DIR):
        self.name = "reading"
        self.frame_rate_ms = 140
        animations_dir = Path(animations_dir)
        self.idle_frame = self._frame(animations_dir, 1)
        self.blink_frames: List[str] = [
            self._frame(animations_dir, 1),
            self._frame(animations_dir, 2),
            self._frame(animations_dir, 3),
            self._frame(animations_dir, 2),
            self._frame(animations_dir, 1),
        ]
        self.page_turn_frames: List[str] = [
            self._frame(animations_dir, 1),
            self._frame(animations_dir, 4),
            self._frame(animations_dir, 5),
            self._frame(animations_dir, 1),
        ]

    def next_sequence(self, random_func: Callable[[], float] = random.random) -> List[str]:
        if random_func() < 0.7:
            return list(self.blink_frames)
        return list(self.page_turn_frames)

    @staticmethod
    def _frame(animations_dir: Path, index: int) -> str:
        return str(animations_dir / "reading" / f"reading_{index:02d}.png")
