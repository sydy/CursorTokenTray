"""云同步：注册登录后两端合并账号、设置和用量。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("JWT_SECRET", "test-secret-for-sync-please-use-32b+")

from app.db import reset_for_tests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def _requester(client: TestClient):
    def _call(method: str, url: str, headers: dict | None, body: dict | None):
        from urllib.parse import urlparse

        path = urlparse(url).path
        res = client.request(method, path, headers=headers, json=body)
        return res.status_code, res.json()

    return _call


class CloudSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        reset_for_tests(Path(self.tmp.name) / "sync.db")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_then_second_device_pulls(self) -> None:
        from accounts import upsert_account
        from cloud_sync import apply_session, login, register, reconcile

        http = _requester(self.client)
        tokens = register("a@harker.cn", "password1", requester=http)
        a = {
            "accounts": [],
            "active_account_id": "",
            "session_token": "",
            "refresh_interval_minutes": 12,
            "tray_display_mode": "dot",
            "deleted_accounts": [],
        }
        upsert_account(a, "user_01CLOUD%3A%3Ajwt.part.sig", label="云号", activate=True)
        from accounts import apply_snapshot_to_account

        apply_snapshot_to_account(a["accounts"][0], remaining=44, billing_cycle_end="2026-10-01T00:00:00.000Z")
        apply_session(a, "a@harker.cn", "password1", tokens)
        _, status = reconcile(a, requester=http)
        self.assertTrue(status["ok"], status["message"])
        self.assertTrue(status["pushed"])

        b = {
            "accounts": [],
            "active_account_id": "",
            "session_token": "",
            "refresh_interval_minutes": 10,
            "tray_display_mode": "ring",
            "deleted_accounts": [],
        }
        apply_session(b, "a@harker.cn", "password1", login("a@harker.cn", "password1", requester=http))
        _, status_b = reconcile(b, requester=http)
        self.assertTrue(status_b["ok"], status_b["message"])
        self.assertTrue(status_b["changed"])
        self.assertEqual(b["accounts"][0]["label"], "云号")
        self.assertEqual(b["accounts"][0]["last_remaining"], 44)
        self.assertEqual(b["accounts"][0]["billing_cycle_end"], "2026-10-01T00:00:00.000Z")
        self.assertEqual(b["refresh_interval_minutes"], 12)
        self.assertEqual(b["tray_display_mode"], "dot")


if __name__ == "__main__":
    unittest.main()
