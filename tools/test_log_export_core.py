import unittest

from log_export_core import Cleaner


class CleanerTests(unittest.TestCase):
    def test_mimo_and_common_tokens_are_redacted_recursively(self):
        mimo = "tp-" + "A1_b" * 8
        openai = "sk-proj-" + "Z9_-" * 7
        bearer = "Bearer " + "abc.DEF_123-xyz" * 2
        cleaner = Cleaner([])

        value = cleaner.value({
            "message": "key=" + mimo,
            "nested": [openai, {"authorization": bearer}],
        })

        self.assertNotIn(mimo, str(value))
        self.assertNotIn(openai, str(value))
        self.assertNotIn(bearer, str(value))
        self.assertEqual(value["message"], "key=[API token redacted]")
        self.assertEqual(value["nested"][0], "[API token redacted]")
        self.assertEqual(value["nested"][1]["authorization"],
                         "Bearer [redacted]")
        self.assertEqual(cleaner.counts["api_key"], 2)
        self.assertEqual(cleaner.counts["bearer"], 1)

    def test_known_secret_json_escaped_forms_are_redacted(self):
        secret = 'wifi"password\\line'
        cleaner = Cleaner([secret])
        escaped = 'wifi\\"password\\\\line'

        self.assertEqual(cleaner.text(secret), "[Wi-Fi password redacted]")
        self.assertEqual(cleaner.text(escaped), "[Wi-Fi password redacted]")
        self.assertEqual(cleaner.counts["wifi_password"], 2)

    def test_private_key_and_media_blocks_are_omitted(self):
        cleaner = Cleaner([])
        value = cleaner.value({
            "text": "-----BEGIN PRIVATE KEY-----\nsecret\n"
                    "-----END PRIVATE KEY-----",
            "content": [{"type": "input_audio", "data": "opaque"}],
        })

        self.assertEqual(value["text"], "[private key redacted]")
        self.assertEqual(value["content"], [
            {"type": "omitted_media", "source_type": "input_audio"}
        ])


if __name__ == "__main__":
    unittest.main()
