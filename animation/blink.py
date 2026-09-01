import os
from typing import List

class BlinkAnimation:
    def __init__(self, base_dir: str):
        self.name = "blink"
        self.frames: List[str] = [
            os.path.join(base_dir, "assets", "animations", "eyes_closing", "Nova_eyes_closing_01.png"),
            os.path.join(base_dir, "assets", "animations", "eyes_closing", "Nova_eyes_closing_02.png"),
            os.path.join(base_dir, "assets", "animations", "eyes_closing", "Nova_eyes_closing_03.png"),
            os.path.join(base_dir, "assets", "animations", "eyes_closing", "Nova_eyes_closing_02.png"),
            os.path.join(base_dir, "assets", "animations", "eyes_closing", "Nova_eyes_closing_01.png"),
        ]
        self.frame_rate_ms = 80
