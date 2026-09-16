from pathlib import Path
from typing import List

from app.core.paths import PET_ANIMATIONS_DIR


class LookAroundAnimation:
    def __init__(self, animations_dir: Path = PET_ANIMATIONS_DIR):
        self.name = "look_around"
        self.frame_rate_ms = 250
        animations_dir = Path(animations_dir)
        front = self._frame(animations_dir, "front")
        left = self._frame(animations_dir, "left")
        right = self._frame(animations_dir, "right")
        self.frames: List[str] = [
            front,
            left,
            left,
            left,
            left,
            front,
            right,
            right,
            right,
            right,
            front,
        ]

    @staticmethod
    def _frame(animations_dir: Path, direction: str) -> str:
        return str(animations_dir / "look_around" / f"Nova_looking_{direction}.png")
