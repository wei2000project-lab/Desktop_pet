import pathlib
import unittest


class MainEntrypointTests(unittest.TestCase):
    def test_main_only_delegates_to_application_entrypoint(self):
        source = pathlib.Path("main.py").read_text(encoding="utf-8")
        meaningful_lines = [line for line in source.splitlines() if line.strip()]

        self.assertEqual(
            meaningful_lines,
            [
                "from app.core.application import run_application",
                'if __name__ == "__main__":',
                "    raise SystemExit(run_application())",
            ],
        )


if __name__ == "__main__":
    unittest.main()
