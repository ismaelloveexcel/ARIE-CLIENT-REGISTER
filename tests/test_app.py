import os
import tempfile
import unittest

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

    def login(self):
        return self.client.post(
            "/login",
            data={"username": "admin", "password": "password"},
            follow_redirects=True,
        )

    def test_login_is_required_for_dashboard(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_create_client_and_contact_and_note(self):
        self.login()

        response = self.client.post(
            "/clients/new",
            data={
                "name": "Acme Corp",
                "status": "prospect",
                "kyc_stage": "documents_requested",
                "document_status": "pending",
                "kind": "lead",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Acme Corp", response.data)

        self.client.post(
            "/clients/1/contacts",
            data={"name": "Jane Doe", "email": "jane@example.com", "phone": "123", "role": "CFO"},
            follow_redirects=True,
        )
        note_resp = self.client.post(
            "/clients/1/notes",
            data={"content": "Call next week", "follow_up_date": "2030-01-10"},
            follow_redirects=True,
        )
        self.assertIn(b"Jane Doe", note_resp.data)
        self.assertIn(b"Call next week", note_resp.data)
        self.assertIn(b"Audit Activity History", note_resp.data)

    def test_search_filter(self):
        self.login()
        self.client.post(
            "/clients/new",
            data={"name": "Alpha Holdings", "status": "qualified", "kyc_stage": "in_review", "document_status": "pending", "kind": "lead"},
        )
        self.client.post(
            "/clients/new",
            data={"name": "Beta Finance", "status": "active", "kyc_stage": "complete", "document_status": "complete", "kind": "client"},
        )

        response = self.client.get("/clients?q=Alpha&status=qualified&kind=lead")
        self.assertIn(b"Alpha Holdings", response.data)
        self.assertNotIn(b"Beta Finance", response.data)


if __name__ == "__main__":
    unittest.main()
