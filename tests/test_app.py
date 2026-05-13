import os
import re
import tempfile
import unittest
from urllib.parse import urlparse

from app import create_app


class CRMAppTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": self.db_path,
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "password",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def extract_csrf_token(self, body):
        html = body.decode("utf-8")
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(match)
        return match.group(1)

    def get_csrf_token_for(self, path):
        response = self.client.get(path, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return self.extract_csrf_token(response.data)

    def login(self):
        csrf_token = self.get_csrf_token_for("/login")
        return self.client.post(
            "/login",
            data={"username": "admin", "password": "password", "csrf_token": csrf_token},
            follow_redirects=True,
        )

    def test_login_is_required_for_dashboard(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_create_client_and_contact_and_note(self):
        self.login()
        create_csrf = self.get_csrf_token_for("/clients/new")

        response = self.client.post(
            "/clients/new",
            data={
                "csrf_token": create_csrf,
                "name": "Acme Corp",
                "status": "prospect",
                "kyc_stage": "documents_requested",
                "document_status": "pending",
                "kind": "lead",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        client_url = urlparse(response.headers["Location"]).path
        self.assertRegex(client_url, r"^/clients/\d+$")
        client_page = self.client.get(client_url, follow_redirects=True)
        self.assertIn(b"Acme Corp", client_page.data)
        client_csrf = self.extract_csrf_token(client_page.data)

        self.client.post(
            f"{client_url}/contacts",
            data={
                "csrf_token": client_csrf,
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "123",
                "role": "CFO",
            },
            follow_redirects=True,
        )
        note_resp = self.client.post(
            f"{client_url}/notes",
            data={
                "csrf_token": client_csrf,
                "content": "Call next week",
                "follow_up_date": "2030-01-10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Jane Doe", note_resp.data)
        self.assertIn(b"Call next week", note_resp.data)
        self.assertIn(b"Audit Activity History", note_resp.data)

    def test_search_filter(self):
        self.login()
        create_csrf = self.get_csrf_token_for("/clients/new")
        self.client.post(
            "/clients/new",
            data={
                "csrf_token": create_csrf,
                "name": "Alpha Holdings",
                "status": "qualified",
                "kyc_stage": "in_review",
                "document_status": "pending",
                "kind": "lead",
            },
        )
        self.client.post(
            "/clients/new",
            data={
                "csrf_token": create_csrf,
                "name": "Beta Finance",
                "status": "active",
                "kyc_stage": "complete",
                "document_status": "complete",
                "kind": "client",
            },
        )

        response = self.client.get("/clients?q=Alpha&status=qualified&kind=lead")
        self.assertIn(b"Alpha Holdings", response.data)
        self.assertNotIn(b"Beta Finance", response.data)

    def test_create_client_requires_valid_kind(self):
        self.login()
        create_csrf = self.get_csrf_token_for("/clients/new")
        response = self.client.post(
            "/clients/new",
            data={
                "csrf_token": create_csrf,
                "name": "Gamma",
                "status": "prospect",
                "kyc_stage": "not_started",
                "document_status": "not_started",
                "kind": "invalid",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Type must be either lead or client", response.data)

    def test_contact_and_note_for_missing_client_return_404(self):
        self.login()
        create_csrf = self.get_csrf_token_for("/clients/new")
        contact_response = self.client.post(
            "/clients/999/contacts",
            data={"csrf_token": create_csrf, "name": "Jane"},
            follow_redirects=False,
        )
        note_response = self.client.post(
            "/clients/999/notes",
            data={"csrf_token": create_csrf, "content": "Missing client note"},
            follow_redirects=False,
        )
        self.assertEqual(contact_response.status_code, 404)
        self.assertEqual(note_response.status_code, 404)

    def test_csrf_required_for_login_and_mutations(self):
        login_response = self.client.post(
            "/login",
            data={"username": "admin", "password": "password"},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 400)

        self.login()
        response = self.client.post(
            "/clients/new",
            data={
                "name": "No CSRF Corp",
                "status": "prospect",
                "kyc_stage": "not_started",
                "document_status": "not_started",
                "kind": "lead",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_password_rotation_updates_existing_admin_user(self):
        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": self.db_path,
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "first-password",
            }
        )
        rotated_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": self.db_path,
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "rotated-password",
            }
        )
        rotated_client = rotated_app.test_client()
        login_page = rotated_client.get("/login")
        csrf_token = self.extract_csrf_token(login_page.data)
        login_response = rotated_client.post(
            "/login",
            data={"username": "admin", "password": "rotated-password", "csrf_token": csrf_token},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/", login_response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
