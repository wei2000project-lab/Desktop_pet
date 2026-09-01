import os
import random
from typing import Callable, List


class ReadingAnimation:
    def __init__(self, base_dir: str):
        self.name = "reading"
        self.frame_rate_ms = 140
        self.idle_frame = os.path.join(base_dir, "assets", "animations", "Reading", "reading_01.png")
        self.blink_frames: List[str] = [
            self._frame(base_dir, 1),
            self._frame(base_dir, 2),
            self._frame(base_dir, 3),
            self._frame(base_dir, 2),
            self._frame(base_dir, 1),
        ]
        self.page_turn_frames: List[str] = [
            self._frame(base_dir, 1),
            self._frame(base_dir, 4),
            self._frame(base_dir, 5),
            self._frame(base_dir, 1),
        ]

    def next_sequence(self, random_func: Callable[[], float] = random.random) -> List[str]:
        if random_func() < 0.7:
            return list(self.blink_frames)
        return list(self.page_turn_frames)

    @staticmethod
    def _frame(base_dir: str, index: int) -> str:
        return os.path.join(base_dir, "assets", "animations", "Reading", f"reading_{index:02d}.png")
