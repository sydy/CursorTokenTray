"""多账号配置、历史隔离与 Token 识别。"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path


def _jwt_for(user_id: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": f"github|{user_id}"}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def _token_for(user_id: str) -> str:
    return f"{user_id}%3A%3A{_jwt_for(user_id)}"


class AccountIdTests(unittest.TestCase):
    def test_id_from_prefixed_jwt(self) -> None:
        from cursor_api import account_id_from_token

        self.assertEqual(account_id_from_token(_token_for("user_01ABC")), "user_01ABC")

    def test_id_from_bare_jwt(self) -> None:
        from cursor_api import account_id_from_token

        self.assertEqual(account_id_from_token(_jwt_for("user_01XYZ")), "user_01XYZ")

    def test_fallback_hash_for_opaque_token(self) -> None:
        from cursor_api import account_id_from_token

        aid = account_id_from_token("not-a-jwt-token-value")
        self.assertTrue(aid.startswith("tok_"))
        self.assertEqual(aid, account_id_from_token("not-a-jwt-token-value"))


class AccountStateTests(unittest.TestCase):
    def test_legacy_session_token_migrates_to_accounts(self) -> None:
        from accounts import active_account, display_label, list_accounts, normalize_account_state

        token = _token_for("user_01OLD")
        cfg = {
            "session_token": token,
            "accounts": [],
            "active_account_id": "",
            "alert_notified_levels": [20],
            "auth_error_notified": True,
            "exhaustion_notified": False,
            "low_quota_notified": True,
        }
        normalize_account_state(cfg, raw=cfg)
        accounts = list_accounts(cfg)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "user_01OLD")
        self.assertEqual(accounts[0]["token"], token)
        self.assertEqual(accounts[0]["alert_notified_levels"], [20])
        self.assertTrue(accounts[0]["auth_error_notified"])
        self.assertEqual(cfg["active_account_id"], "user_01OLD")
        self.assertEqual(cfg["session_token"], token)
        self.assertEqual(active_account(cfg)["id"], "user_01OLD")
        self.assertEqual(display_label(accounts[0]), "user_01OLD")

    def test_second_account_has_independent_alerts(self) -> None:
        from accounts import list_accounts, upsert_account

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": ""}
        a, _ = upsert_account(cfg, _token_for("user_01A"), activate=True)
        a["alert_notified_levels"] = [50, 20]
        a["auth_error_notified"] = True
        b, created = upsert_account(cfg, _token_for("user_01B"), activate=False)
        self.assertTrue(created)
        self.assertEqual(a["alert_notified_levels"], [50, 20])
        self.assertEqual(b["alert_notified_levels"], [])
        self.assertFalse(b["auth_error_notified"])
        self.assertEqual(len(list_accounts(cfg)), 2)
        from accounts import list_accounts, upsert_account

        first = _token_for("user_01SAME")
        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": ""}
        upsert_account(cfg, first, membership_type="Pro", remaining=80, activate=True)
        newer = _token_for("user_01SAME")
        acc, created = upsert_account(cfg, newer, membership_type="Pro", remaining=40, activate=True)
        self.assertFalse(created)
        self.assertEqual(len(list_accounts(cfg)), 1)
        self.assertEqual(acc["last_remaining"], 40)
        self.assertEqual(cfg["session_token"], newer)

    def test_switch_and_remove_preserve_other_accounts(self) -> None:
        from accounts import (
            list_accounts,
            remove_account,
            set_active_account,
            upsert_account,
        )

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": ""}
        upsert_account(cfg, _token_for("user_01A"), label="个人", activate=True)
        upsert_account(cfg, _token_for("user_01B"), label="公司", activate=True)
        self.assertEqual(cfg["active_account_id"], "user_01B")
        self.assertTrue(set_active_account(cfg, "user_01A"))
        self.assertEqual(cfg["active_account_id"], "user_01A")
        self.assertIn("user_01A", cfg["session_token"])
        self.assertTrue(remove_account(cfg, "user_01A"))
        self.assertEqual([a["id"] for a in list_accounts(cfg)], ["user_01B"])
        self.assertEqual(cfg["active_account_id"], "user_01B")
        self.assertTrue(remove_account(cfg, "user_01B"))
        self.assertEqual(list_accounts(cfg), [])
        self.assertEqual(cfg["session_token"], "")

    def test_config_roundtrip_keeps_accounts(self) -> None:
        import config
        from accounts import list_accounts, upsert_account

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                cfg = dict(config.DEFAULT_CONFIG)
                upsert_account(cfg, _token_for("user_01SAVE"), label="工作", activate=True)
                config.save_config(cfg)
                loaded = config.load_config()
                accounts = list_accounts(loaded)
                self.assertEqual(len(accounts), 1)
                self.assertEqual(accounts[0]["label"], "工作")
                self.assertEqual(loaded["active_account_id"], "user_01SAVE")
                self.assertTrue(loaded["session_token"])
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path

    def test_old_json_without_accounts_key(self) -> None:
        import config

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                Path(tmp).mkdir(parents=True, exist_ok=True)
                config.CONFIG_PATH.write_text(
                    json.dumps(
                        {
                            "session_token": _token_for("user_01LEG"),
                            "refresh_interval_minutes": 8,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                loaded = config.load_config()
                self.assertEqual(loaded["active_account_id"], "user_01LEG")
                self.assertEqual(len(loaded["accounts"]), 1)
                self.assertEqual(loaded["refresh_interval_minutes"], 8)
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


class HistoryPartitionTests(unittest.TestCase):
    def test_history_is_per_account(self) -> None:
        import config
        import usage_history

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                usage_history.append(remaining=80, account_id="user_01A", ts=1_700_000_000)
                usage_history.append(remaining=20, account_id="user_01B", ts=1_700_000_100)
                a = usage_history.load_recent(10_000, account_id="user_01A")
                b = usage_history.load_recent(10_000, account_id="user_01B")
                self.assertEqual([p.remaining for p in a], [80])
                self.assertEqual([p.remaining for p in b], [20])
                self.assertTrue((Path(tmp) / "usage_history.user_01A.jsonl").exists())
                self.assertTrue((Path(tmp) / "usage_history.user_01B.jsonl").exists())
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path

    def test_legacy_history_adopted_once(self) -> None:
        import config
        import usage_history

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                legacy = Path(tmp) / "usage_history.jsonl"
                legacy.write_text(
                    json.dumps({"ts": 1_700_000_000, "remaining": 55, "auto": None, "api": None})
                    + "\n",
                    encoding="utf-8",
                )
                usage_history.adopt_legacy_history("user_01LEG")
                dest = Path(tmp) / "usage_history.user_01LEG.jsonl"
                self.assertTrue(dest.exists())
                self.assertFalse(legacy.exists())
                points = usage_history.load_recent(10_000, account_id="user_01LEG")
                self.assertEqual(points[0].remaining, 55)
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


class MultiAccountUiGuardTests(unittest.TestCase):
    def test_popup_launch_accepts_switch_key(self) -> None:
        from popup_launch import MENU_ACTIONS

        self.assertIn("settings", MENU_ACTIONS)
        text = Path(__file__).resolve().parents[1].joinpath("popup_launch.py").read_text(encoding="utf-8")
        self.assertIn("switch:", text)

    def test_tray_and_settings_have_account_switcher(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tray = (root / "tray_app.py").read_text(encoding="utf-8")
        self.assertIn("切换账号", tray)
        self.assertIn("_switch_account", tray)
        win_settings = (root / "settings_ui.py").read_text(encoding="utf-8")
        self.assertIn("添加此 Token", win_settings)
        self.assertIn("upsert_account", win_settings)
        mac_settings = (root / "macos_settings.py").read_text(encoding="utf-8")
        self.assertIn("changeAccount_", mac_settings)
        self.assertIn("添加此 Token", mac_settings)


if __name__ == "__main__":
    unittest.main()
