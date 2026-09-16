from pathlib import Path
from typing import List

from app.core.paths import PET_ANIMATIONS_DIR

class BlinkAnimation:
    def __init__(self, animations_dir: Path = PET_ANIMATIONS_DIR):
        self.name = "blink"
        frames_dir = Path(animations_dir) / "eyes_closing"
        self.frames: List[str] = [
            str(frames_dir / "Nova_eyes_closing_01.png"),
            str(frames_dir / "Nova_eyes_closing_02.png"),
            str(frames_dir / "Nova_eyes_closing_03.png"),
            str(frames_dir / "Nova_eyes_closing_02.png"),
            str(frames_dir / "Nova_eyes_closing_01.png"),
        ]
        self.frame_rate_ms = 80
