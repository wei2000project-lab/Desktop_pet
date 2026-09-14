import os
from typing import List


class LookAroundAnimation:
    def __init__(self, base_dir: str):
        self.name = "look_around"
        self.frame_rate_ms = 250
        front = self._frame(base_dir, "front")
        left = self._frame(base_dir, "left")
        right = self._frame(base_dir, "right")
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
    def _frame(base_dir: str, direction: str) -> str:
        return os.path.join(
            base_dir,
            "assets",
            "animations",
            "look_around",
            f"Nova_looking_{direction}.png",
        )
