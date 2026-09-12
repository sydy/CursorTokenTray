from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-for-sync-please-use-32b+")

from fastapi.testclient import TestClient

from app.db import reset_for_tests
from app.main import app


ENVELOPE = {
    "format": "cursortokentray.sync.v2",
    "kdf": "pbkdf2-sha256",
    "iterations": 210000,
    "salt": "AQEBAQEBAQEBAQEBAQEBAQ==",
    "nonce": "AgICAgICAgICAgIC",
    "ciphertext": "AAAAAAAAAAAAAAAAAAAAAA==",
}


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        reset_for_tests(Path(self.tmp.name) / "sync.db")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_health(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

    def test_register_login_sync_conflict(self) -> None:
        bad = self.client.post("/v1/auth/register", json={"email": "not-email", "password": "password1"})
        self.assertEqual(bad.status_code, 400)

        short = self.client.post("/v1/auth/register", json={"email": "a@b.com", "password": "123"})
        self.assertEqual(short.status_code, 400)

        created = self.client.post(
            "/v1/auth/register",
            json={"email": "User@Harker.cn", "password": "password1"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        tokens = created.json()
        self.assertEqual(tokens["email"], "user@harker.cn")
        access = tokens["access_token"]

        again = self.client.post(
            "/v1/auth/register",
            json={"email": "user@harker.cn", "password": "password1"},
        )
        self.assertEqual(again.status_code, 409)

        wrong = self.client.post(
            "/v1/auth/login",
            json={"email": "user@harker.cn", "password": "password2"},
        )
        self.assertEqual(wrong.status_code, 401)

        logged = self.client.post(
            "/v1/auth/login",
            json={"email": "user@harker.cn", "password": "password1"},
        )
        self.assertEqual(logged.status_code, 200)
        access = logged.json()["access_token"]
        refresh = logged.json()["refresh_token"]

        me = self.client.get("/v1/me", headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "user@harker.cn")

        empty = self.client.get("/v1/sync", headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["revision"], 0)
        self.assertIsNone(empty.json()["envelope"])

        put = self.client.put(
            "/v1/sync",
            headers={"Authorization": f"Bearer {access}"},
            json={"revision": 0, "envelope": ENVELOPE},
        )
        self.assertEqual(put.status_code, 200, put.text)
        self.assertEqual(put.json()["revision"], 1)

        conflict = self.client.put(
            "/v1/sync",
            headers={"Authorization": f"Bearer {access}"},
            json={"revision": 0, "envelope": ENVELOPE},
        )
        self.assertEqual(conflict.status_code, 409)

        got = self.client.get("/v1/sync", headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(got.json()["revision"], 1)
        self.assertEqual(got.json()["envelope"]["format"], ENVELOPE["format"])
        self.assertNotIn("accounts", got.json()["envelope"])

        refreshed = self.client.post("/v1/auth/refresh", json={"refresh_token": refresh})
        self.assertEqual(refreshed.status_code, 200)
        new_access = refreshed.json()["access_token"]
        me2 = self.client.get("/v1/me", headers={"Authorization": f"Bearer {new_access}"})
        self.assertEqual(me2.status_code, 200)

        self.client.post("/v1/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]})
        reused = self.client.post("/v1/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
        self.assertEqual(reused.status_code, 401)

    def test_rejects_plaintext_blob(self) -> None:
        created = self.client.post(
            "/v1/auth/register",
            json={"email": "b@harker.cn", "password": "password1"},
        )
        access = created.json()["access_token"]
        res = self.client.put(
            "/v1/sync",
            headers={"Authorization": f"Bearer {access}"},
            json={"revision": 0, "envelope": {"accounts": [{"token": "secret"}]}},
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
