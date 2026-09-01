import unittest

from ai.api_keys import decode_api_key_entries, encode_api_key_entries, first_api_key


class ApiKeysTests(unittest.TestCase):
    def test_decodes_api_key_entries_from_json(self):
        entries = decode_api_key_entries(
            '[{"name":"Groq","key":"key-1"},{"name":"Backup","key":"key-2"}]',
            legacy_key="legacy",
        )

        self.assertEqual(entries, [{"name": "Groq", "key": "key-1"}, {"name": "Backup", "key": "key-2"}])

    def test_falls_back_to_legacy_api_key(self):
        entries = decode_api_key_entries("", legacy_key="legacy-key")

        self.assertEqual(entries, [{"name": "Key 1", "key": "legacy-key"}])

    def test_ignores_empty_keys_when_encoding(self):
        raw = encode_api_key_entries(
            [
                {"name": "Primary", "key": "key-1"},
                {"name": "Empty", "key": ""},
            ]
        )

        self.assertEqual(raw, '[{"name": "Primary", "key": "key-1"}]')

    def test_first_api_key_returns_first_non_empty_key(self):
        self.assertEqual(first_api_key([{"name": "A", "key": ""}, {"name": "B", "key": "key-2"}]), "key-2")


if __name__ == "__main__":
    unittest.main()
