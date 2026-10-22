from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase

from apps.web.meta import absolute_url, get_protocol, get_server_root


class MetaUrlTest(TestCase):
    def setUp(self):
        self.http_request = RequestFactory().get("/", HTTP_HOST="example.com")
        self.https_request = RequestFactory().get("/", HTTP_HOST="example.com", secure=True)

    def test_get_protocol(self):
        self.assertEqual(get_protocol(is_secure=False), "http")
        self.assertEqual(get_protocol(is_secure=True), "https")

    def test_get_server_root(self):
        self.assertEqual(get_server_root(request=self.https_request), "https://example.com")
        self.assertEqual(get_server_root(request=self.http_request), "http://example.com")

    def test_absolute_url(self):
        self.assertEqual(absolute_url("/dashboard/", request=self.https_request), "https://example.com/dashboard/")
        self.assertEqual(absolute_url("/dashboard/", request=self.http_request), "http://example.com/dashboard/")

    def test_without_request_raises(self):
        # there is no SITE_ID, so the current site only comes from a request
        with self.assertRaises(ImproperlyConfigured):
            get_server_root()
