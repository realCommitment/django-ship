import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class TestProductionSettings(SimpleTestCase):
    def test_missing_secret_key_raises(self):
        env = {key: value for key, value in os.environ.items() if key != "SECRET_KEY"}
        # Skip the .env file, as on Railway and in CI, so SECRET_KEY is really unset.
        code = "import environ; environ.Env.read_env = lambda *a, **k: None; import project.settings_production"
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ImproperlyConfigured: Set the SECRET_KEY environment variable", result.stderr)
