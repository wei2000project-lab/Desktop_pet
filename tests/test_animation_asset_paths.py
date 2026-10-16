from pathlib import Path
import unittest

from app.animation.reading import ReadingAnimation
from app.animation.emotion import emotion_asset
from app.core.paths import ASSETS_DIR, PET_ANIMATIONS_DIR, PET_ASSETS_DIR, PET_EMOTIONS_DIR


class AnimationAssetPathTests(unittest.TestCase):
    def test_emotion_assets_use_squint_and_canonical_directory(self):
        for name in ("happy", "surprised", "squint"):
            with self.subTest(name=name):
                path = emotion_asset(name)
                self.assertIsNotNone(path)
                self.assertEqual(path, PET_EMOTIONS_DIR / f"Nova_{name}.png")
        self.assertIsNone(emotion_asset("gaze"))

    def test_idle_image_uses_runtime_emotions_asset(self):
        source = Path("app/animation/animator.py").read_text(encoding="utf-8")

        self.assertIn("PET_EMOTIONS_DIR", source)
        self.assertNotIn('"assets", "emotions"', source)
        self.assertTrue((PET_EMOTIONS_DIR / "Nova_idle.png").is_file())

    def test_reading_animation_uses_lowercase_directory(self):
        animation = ReadingAnimation()
        frames = [*animation.blink_frames, *animation.page_turn_frames]

        self.assertTrue(frames)
        self.assertTrue(all(PET_ANIMATIONS_DIR / "reading" == Path(path).parent for path in frames))
        self.assertTrue(all(Path(path).is_file() for path in frames))

    def test_pet_asset_directories_are_canonical(self):
        self.assertEqual(PET_ASSETS_DIR, ASSETS_DIR / "pet")
        self.assertEqual(PET_ANIMATIONS_DIR, PET_ASSETS_DIR / "animations")
        self.assertEqual(PET_EMOTIONS_DIR, PET_ASSETS_DIR / "emotions")

    def test_development_assets_are_not_a_runtime_image_directory(self):
        self.assertFalse((ASSETS_DIR / "images").exists())
        self.assertTrue((ASSETS_DIR / "素材資料").is_dir())
        self.assertFalse((ASSETS_DIR / "animations").exists())
        self.assertFalse((ASSETS_DIR / "emotions").exists())


if __name__ == "__main__":
    unittest.main()
