import unittest

from app.core.window_manager import WindowManager


class FakeBubbleWindow:
    def __init__(self, visible=False):
        self.visible = visible
        self.show_count = 0
        self.hide_count = 0
        self.raise_count = 0

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True
        self.show_count += 1

    def hide(self):
        self.visible = False
        self.hide_count += 1

    def raise_(self):
        self.raise_count += 1


class BubbleToggleTests(unittest.TestCase):
    def make_manager(self, visible=False):
        manager = object.__new__(WindowManager)
        manager.pet_window = None
        manager.bubble_window = FakeBubbleWindow(visible=visible)
        manager.settings_window = None
        return manager

    def test_toggle_shows_hidden_bubble(self):
        manager = self.make_manager(visible=False)

        manager.toggle_bubble()

        self.assertTrue(manager.bubble_window.visible)
        self.assertEqual(manager.bubble_window.show_count, 1)
        self.assertEqual(manager.bubble_window.raise_count, 1)
        self.assertEqual(manager.bubble_window.hide_count, 0)

    def test_toggle_hides_visible_bubble(self):
        manager = self.make_manager(visible=True)

        manager.toggle_bubble()

        self.assertFalse(manager.bubble_window.visible)
        self.assertEqual(manager.bubble_window.hide_count, 1)
        self.assertEqual(manager.bubble_window.show_count, 0)


if __name__ == "__main__":
    unittest.main()
