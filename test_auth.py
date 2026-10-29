"""Authentication checks without a remote server or API calls."""

import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from auth_service import COOKIE_NAME, app


class AuthChecks(unittest.TestCase):
    def test_register_login_check_and_logout(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "AUTH_DB_PATH": str(Path(directory) / "auth.sqlite3"),
            "APP_ORIGIN": "https://app.traineeserver.ru",
        }):
            headers = {"origin": "https://app.traineeserver.ru"}
            with TestClient(app, base_url="https://app.traineeserver.ru", follow_redirects=False) as client:
                response = client.get("/auth/check")
                self.assertEqual(response.status_code, 401)

                response = client.post("/auth/register", data={
                    "email": "Student@Example.com", "password": "long-enough-password",
                }, headers=headers)
                self.assertEqual(response.status_code, 303)
                self.assertIn("Secure", response.headers["set-cookie"])
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn(COOKIE_NAME, client.cookies)
                self.assertEqual(client.get("/auth/check").status_code, 204)

                db = sqlite3.connect(Path(directory) / "auth.sqlite3")
                try:
                    email, stored_hash = db.execute("SELECT email, password_hash FROM users").fetchone()
                finally:
                    db.close()
                self.assertEqual(email, "student@example.com")
                self.assertNotIn("long-enough-password", stored_hash)

                self.assertEqual(client.post("/auth/logout", headers=headers).status_code, 303)
                self.assertEqual(client.get("/auth/check").status_code, 401)
                self.assertEqual(client.post("/auth/login", data={
                    "email": "student@example.com", "password": "wrong-password",
                }, headers=headers).status_code, 200)
                self.assertEqual(client.get("/auth/check").status_code, 401)
                self.assertEqual(client.post("/auth/login", data={
                    "email": "student@example.com", "password": "long-enough-password",
                }, headers=headers).status_code, 303)
                self.assertEqual(client.get("/auth/check").status_code, 204)

    def test_cross_origin_registration_is_rejected(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "AUTH_DB_PATH": str(Path(directory) / "auth.sqlite3"),
            "APP_ORIGIN": "https://app.traineeserver.ru",
        }):
            with TestClient(app) as client:
                response = client.post("/auth/register", data={
                    "email": "student@example.com", "password": "long-enough-password",
                }, headers={"origin": "https://example.org"})
                self.assertEqual(response.status_code, 403)
                self.assertFalse((Path(directory) / "auth.sqlite3").exists())

    def test_eight_character_password_is_allowed_but_seven_is_rejected(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "AUTH_DB_PATH": str(Path(directory) / "auth.sqlite3"),
            "APP_ORIGIN": "https://app.traineeserver.ru",
        }):
            headers = {"origin": "https://app.traineeserver.ru"}
            with TestClient(app, base_url="https://app.traineeserver.ru", follow_redirects=False) as client:
                rejected = client.post("/auth/register", data={
                    "email": "short@example.com", "password": "1234567",
                }, headers=headers)
                self.assertEqual(rejected.status_code, 200)
                self.assertIn("от 8 до 128", rejected.text)
                accepted = client.post("/auth/register", data={
                    "email": "student@example.com", "password": "12345678",
                }, headers=headers)
                self.assertEqual(accepted.status_code, 303)
                self.assertEqual(client.get("/auth/check").status_code, 204)


if __name__ == "__main__":
    unittest.main()
