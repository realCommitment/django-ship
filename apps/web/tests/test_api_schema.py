from apps.multisite.tests.base import SiteTestCase
from apps.users.models import CustomUser


class TestApiSchema(SiteTestCase):
    def test_schema_returns_success(self):
        self.client.force_login(CustomUser.objects.create_user(username="staff@example.com", is_staff=True))
        response = self.client.get("/api/schema/")
        self.assertEqual(200, response.status_code)

    def test_schema_urls_forbidden_for_anonymous(self):
        for url in ["/api/schema/", "/api/schema/swagger-ui/", "/api/schema/redoc/"]:
            with self.subTest(url=url):
                self.assertEqual(403, self.client.get(url).status_code)
