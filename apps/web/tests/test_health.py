from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class TestHealth(TestCase):
    def test_ok(self):
        response = self.client.get(reverse("web:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_unreachable(self):
        with patch("apps.web.views.connection") as connection:
            connection.cursor.side_effect = OperationalError("connection refused")
            with self.assertLogs("apps.web.views", level="ERROR"):
                response = self.client.get(reverse("web:health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "failed_check": "database"})
