import os
from typing import List


class LookAroundAnimation:
    def __init__(self, base_dir: str):
        self.name = "look_around"
        self.frame_rate_ms = 450
        front = self._frame(base_dir, "front")
        self.frames: List[str] = [
            front,
            self._frame(base_dir, "left"),
            front,
            self._frame(base_dir, "right"),
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
