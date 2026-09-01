import pathlib
import unittest

from animation.reading import ReadingAnimation


class ReadingAnimationTests(unittest.TestCase):
    def test_reading_blink_and_page_turn_sequences(self):
        animation = ReadingAnimation("root")

        self.assertEqual(
            [pathlib.Path(path).name for path in animation.blink_frames],
            ["reading_01.png", "reading_02.png", "reading_03.png", "reading_02.png", "reading_01.png"],
        )
        self.assertEqual(
            [pathlib.Path(path).name for path in animation.page_turn_frames],
            ["reading_01.png", "reading_04.png", "reading_05.png", "reading_01.png"],
        )

    def test_next_sequence_uses_seven_to_three_ratio_boundary(self):
        animation = ReadingAnimation("root")

        self.assertEqual(animation.next_sequence(lambda: 0.69), animation.blink_frames)
        self.assertEqual(animation.next_sequence(lambda: 0.7), animation.page_turn_frames)


if __name__ == "__main__":
    unittest.main()
