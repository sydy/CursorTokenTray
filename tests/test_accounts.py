"""多账号配置、历史隔离与 Token 识别。"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import datetime
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

    def test_channel_and_billing_cycle_are_per_account(self) -> None:
        from accounts import (
            apply_snapshot_to_account,
            set_account_channel,
            upsert_account,
        )

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": ""}
        a, _ = upsert_account(cfg, _token_for("user_01A"), activate=True)
        b, _ = upsert_account(cfg, _token_for("user_01B"), activate=False)
        self.assertTrue(set_account_channel(cfg, a["id"], "自费"))
        self.assertTrue(set_account_channel(cfg, b["id"], "third_party"))
        self.assertEqual(a["channel"], "self_pay")
        self.assertEqual(b["channel"], "third_party")
        apply_snapshot_to_account(
            a,
            billing_cycle_start="2026-09-01T00:00:00.000Z",
            billing_cycle_end="2026-10-01T00:00:00.000Z",
        )
        self.assertEqual(a["billing_cycle_start"], "2026-09-01T00:00:00.000Z")
        self.assertEqual(a["billing_cycle_end"], "2026-10-01T00:00:00.000Z")
        self.assertEqual(b.get("billing_cycle_start"), "")

    def test_actual_cny_is_per_account(self) -> None:
        from accounts import (
            normalize_account_state,
            resolved_actual_cny,
            set_account_actual_cny,
            set_active_account,
            upsert_account,
        )

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": "", "actual_cny": 0}
        a, _ = upsert_account(cfg, _token_for("user_01A"), activate=True)
        b, _ = upsert_account(cfg, _token_for("user_01B"), activate=False)
        self.assertTrue(set_account_actual_cny(cfg, a["id"], 79))
        self.assertTrue(set_account_actual_cny(cfg, b["id"], 128))
        self.assertEqual(a["actual_cny"], 79)
        self.assertEqual(b["actual_cny"], 128)
        self.assertTrue(set_active_account(cfg, a["id"]))
        self.assertEqual(resolved_actual_cny(cfg), 79)
        self.assertEqual(cfg["actual_cny"], 79)
        self.assertTrue(set_active_account(cfg, b["id"]))
        self.assertEqual(resolved_actual_cny(cfg), 128)
        self.assertEqual(cfg["actual_cny"], 128)
        self.assertEqual(a["actual_cny"], 79)

        imported = {
            "actual_cny": 66,
            "accounts": [
                {"id": "user_01A", "token": _token_for("user_01A"), "label": "旧号"},
                {
                    "id": "user_01C",
                    "token": _token_for("user_01C"),
                    "label": "已填",
                    "actual_cny": 12,
                },
            ],
            "active_account_id": "user_01A",
            "session_token": "",
        }
        normalize_account_state(imported, raw=imported)
        by_id = {row["id"]: row for row in imported["accounts"]}
        self.assertEqual(by_id["user_01A"]["actual_cny"], 66)
        self.assertEqual(by_id["user_01C"]["actual_cny"], 12)
        self.assertEqual(imported["actual_cny"], 66)

        fresh, created = upsert_account(imported, _token_for("user_01D"), activate=False)
        self.assertTrue(created)
        self.assertEqual(fresh["actual_cny"], 0)

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
                upsert_account(cfg, _token_for("user_01COST"), label="企业", activate=False)
                from accounts import set_account_actual_cny

                set_account_actual_cny(cfg, "user_01SAVE", 79)
                set_account_actual_cny(cfg, "user_01COST", 128)
                config.save_config(cfg)
                loaded = config.load_config()
                accounts = list_accounts(loaded)
                self.assertEqual(len(accounts), 2)
                by_id = {row["id"]: row for row in accounts}
                self.assertEqual(by_id["user_01SAVE"]["label"], "工作")
                self.assertEqual(by_id["user_01SAVE"]["actual_cny"], 79)
                self.assertEqual(by_id["user_01COST"]["actual_cny"], 128)
                self.assertEqual(loaded["active_account_id"], "user_01SAVE")
                self.assertEqual(loaded["actual_cny"], 79)
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

    def test_daily_avg_burn(self) -> None:
        import config
        import usage_history

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                start = 1_700_000_000.0
                usage_history.append(remaining=80, account_id="user_burn", ts=start)
                usage_history.append(remaining=60, account_id="user_burn", ts=start + 2 * 86400)
                self.assertEqual(usage_history.daily_avg_burn(days=10_000, account_id="user_burn"), 10.0)
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


class AccountValidityTests(unittest.TestCase):
    def test_kind_and_end_fixtures(self) -> None:
        from accounts import (
            apply_account_end_override,
            compute_temp_end_iso,
            sanitize_account_kind,
        )
        from cursor_api import UsageSnapshot

        data = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "account_validity_cases.json").read_text(encoding="utf-8"))
        for row in data["kind"]:
            self.assertEqual(sanitize_account_kind(row["input"]), row["output"], row["input"])
        for row in data["compute_end"]:
            got = compute_temp_end_iso(row["start"], row["days"], row["hours"])
            self.assertEqual(got, row["end"], row["name"])
        for row in data["override"]:
            snap = UsageSnapshot(
                used_percent=10,
                remaining_percent=90,
                auto_percent_used=None,
                api_percent_used=None,
                total_percent_used=None,
                membership_type="Pro",
                billing_cycle_start="2026-09-01T00:00:00.000Z",
                billing_cycle_end=row["api_end"],
                days_remaining=26,
                days_elapsed=4,
                estimated_usable_days=None,
                raw={},
            )
            now = datetime.fromisoformat(row["now"].replace("Z", "+00:00"))
            apply_account_end_override(snap, row["account"], now=now)
            self.assertEqual(snap.billing_cycle_end, row["expected_end"], row["name"])
            self.assertEqual(snap.days_remaining, row["expected_days_remaining"], row["name"])
            self.assertEqual(snap.billing_cycle_end_overridden, row["overridden"], row["name"])

    def test_sanitize_and_caption_keep_validity(self) -> None:
        from accounts import format_account_caption, sanitize_account, update_account_validity, upsert_account

        raw = {
            "id": "user_01TMP",
            "token": _token_for("user_01TMP"),
            "account_kind": "temporary",
            "temp_start_at": "2026-09-10T00:00:00.000Z",
            "temp_valid_days": 2,
            "temp_valid_hours": 5,
        }
        acc = sanitize_account(raw)
        assert acc is not None
        self.assertEqual(acc["account_kind"], "temporary")
        self.assertEqual(acc["temp_valid_days"], 2)
        self.assertEqual(acc["temp_valid_hours"], 5)
        self.assertIn("临时", format_account_caption(acc))

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": ""}
        upsert_account(cfg, _token_for("user_01TMP"), activate=True)
        self.assertTrue(
            update_account_validity(
                cfg,
                "user_01TMP",
                kind="temporary",
                start_at="2026-09-10T00:00:00.000Z",
                valid_days=1,
                valid_hours=2,
            )
        )
        saved = cfg["accounts"][0]
        self.assertEqual(saved["account_kind"], "temporary")
        self.assertEqual(saved["temp_valid_days"], 1)
        self.assertEqual(saved["temp_valid_hours"], 2)

        import config

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                config.save_config(cfg)
                loaded = config.load_config()
                got = loaded["accounts"][0]
                self.assertEqual(got["account_kind"], "temporary")
                self.assertEqual(got["temp_start_at"], "2026-09-10T00:00:00.000Z")
                self.assertEqual(got["temp_valid_days"], 1)
                self.assertEqual(got["temp_valid_hours"], 2)
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


class ValiditySyncTests(unittest.TestCase):
    def test_newer_remote_validity_wins(self) -> None:
        from account_sync import apply_snapshot_to_config, merge_snapshots

        local = {
            "updated_at": "2026-09-01T00:00:00.000Z",
            "active_account_id": "user_01A",
            "accounts": [
                {
                    "id": "user_01A",
                    "label": "个人",
                    "token": "tok-a",
                    "membership_type": "pro",
                    "account_kind": "long_term",
                    "sync_updated_at": "2026-09-01T00:00:00.000Z",
                }
            ],
            "deleted": [],
        }
        remote = {
            "updated_at": "2026-09-02T00:00:00.000Z",
            "active_account_id": "user_01A",
            "accounts": [
                {
                    "id": "user_01A",
                    "label": "个人",
                    "token": "tok-a",
                    "membership_type": "pro",
                    "account_kind": "temporary",
                    "temp_start_at": "2026-09-10T00:00:00.000Z",
                    "temp_valid_days": 3,
                    "temp_valid_hours": 5,
                    "sync_updated_at": "2026-09-02T00:00:00.000Z",
                }
            ],
            "deleted": [],
        }
        merged = merge_snapshots(local, remote)
        acc = merged["accounts"][0]
        self.assertEqual(acc["account_kind"], "temporary")
        self.assertEqual(acc["temp_start_at"], "2026-09-10T00:00:00.000Z")
        self.assertEqual(acc["temp_valid_days"], 3)
        self.assertEqual(acc["temp_valid_hours"], 5)

        cfg = {
            "accounts": [
                {
                    "id": "user_01A",
                    "label": "个人",
                    "token": "tok-a",
                    "membership_type": "pro",
                    "last_remaining": 42.5,
                    "alert_notified_levels": [50],
                    "auth_error_notified": True,
                    "low_quota_notified": True,
                    "sync_updated_at": "2026-09-01T00:00:00.000Z",
                }
            ],
            "active_account_id": "user_01A",
            "deleted_accounts": [],
        }
        apply_snapshot_to_config(cfg, merged)
        got = cfg["accounts"][0]
        self.assertEqual(got["account_kind"], "temporary")
        self.assertEqual(got["temp_valid_days"], 3)
        self.assertEqual(got["last_remaining"], 42.5)
        self.assertTrue(got["auth_error_notified"])


if __name__ == "__main__":
    unittest.main()
