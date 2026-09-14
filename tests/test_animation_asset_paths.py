import pathlib
import unittest

from app.animation.reading import ReadingAnimation
from app.core.paths import ASSETS_DIR, PROJECT_ROOT


class AnimationAssetPathTests(unittest.TestCase):
    def test_idle_image_uses_runtime_emotions_asset(self):
        source = pathlib.Path("app/animation/animator.py").read_text(encoding="utf-8")

        self.assertIn('"assets", "emotions", "Nova_idle.png"', source)
        self.assertNotIn('"assets", "images"', source)
        self.assertTrue((ASSETS_DIR / "emotions" / "Nova_idle.png").is_file())

    def test_reading_animation_uses_lowercase_directory(self):
        animation = ReadingAnimation(str(PROJECT_ROOT))
        frames = [*animation.blink_frames, *animation.page_turn_frames]

        self.assertTrue(frames)
        self.assertTrue(all(pathlib.Path(path).parent.name == "reading" for path in frames))
        self.assertTrue(all(pathlib.Path(path).is_file() for path in frames))

    def test_development_assets_are_not_a_runtime_image_directory(self):
        self.assertFalse((ASSETS_DIR / "images").exists())
        self.assertTrue((ASSETS_DIR / "素材資料").is_dir())


if __name__ == "__main__":
    unittest.main()
