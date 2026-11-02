"""Smoke test for executing the Streamlit page without an external API call."""

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class StreamlitAppChecks(unittest.TestCase):
    def test_app_renders_without_runtime_exceptions(self):
        app_path = Path(__file__).with_name("app.py")
        app = AppTest.from_file(str(app_path)).run()

        errors = [exception.message for exception in app.exception]
        self.assertEqual(errors, [], "Streamlit app raised an exception:\n" + "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
