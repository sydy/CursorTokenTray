"""账号多端同步：合并规则、路径解析、加密信封与配置往返。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _cases() -> dict:
    return json.loads((ROOT / "fixtures" / "account_sync_cases.json").read_text(encoding="utf-8"))


class ResolvePathTests(unittest.TestCase):
    def test_resolve_path_fixtures(self) -> None:
        from account_sync import resolve_sync_path

        for row in _cases()["resolve_path"]:
            got = resolve_sync_path(row["input"])
            if not row["output_suffix"]:
                self.assertEqual(got, "")
            else:
                self.assertTrue(got.endswith(row["output_suffix"]), f"{got} vs {row['output_suffix']}")


class MergeFixtureTests(unittest.TestCase):
    def test_merge_cases(self) -> None:
        from account_sync import apply_snapshot_to_config, merge_snapshots

        for cse in _cases()["merge"]:
            with self.subTest(cse["name"]):
                if cse.get("apply"):
                    cfg = json.loads(json.dumps(cse["config"]))
                    apply_snapshot_to_config(cfg, cse["snapshot"])
                    acc = cfg["accounts"][0]
                    exp = cse["expected"]
                    self.assertEqual(acc["label"], exp["label"])
                    self.assertEqual(acc["token"], exp["token"])
                    self.assertEqual(acc["membership_type"], exp["membership_type"])
                    self.assertEqual(acc["last_remaining"], exp["last_remaining"])
                    self.assertEqual(acc["alert_notified_levels"], exp["alert_notified_levels"])
                    self.assertTrue(acc["auth_error_notified"])
                    self.assertTrue(acc["low_quota_notified"])
                    continue
                merged = merge_snapshots(cse["local"], cse["remote"])
                exp = cse["expected"]
                self.assertEqual(merged["active_account_id"], exp["active_account_id"])
                ids = [a["id"] for a in merged["accounts"]]
                self.assertEqual(ids, exp["ids"])
                labels = {a["id"]: a["label"] for a in merged["accounts"]}
                tokens = {a["id"]: a["token"] for a in merged["accounts"]}
                self.assertEqual(labels, exp["labels"])
                self.assertEqual(tokens, exp["tokens"])
                self.assertEqual([d["id"] for d in merged["deleted"]], exp["deleted_ids"])


class CryptoFixtureTests(unittest.TestCase):
    def test_known_vector_and_wrong_passphrase(self) -> None:
        from account_sync import decrypt_envelope, encrypt_envelope

        data = _cases()
        crypto = data["crypto"]
        envelope = encrypt_envelope(
            crypto["plaintext"],
            crypto["passphrase"],
            salt=__import__("base64").b64decode(crypto["salt"]),
            nonce=__import__("base64").b64decode(crypto["nonce"]),
            iterations=data["iterations"],
        )
        self.assertEqual(envelope["ciphertext"], crypto["ciphertext"])
        self.assertEqual(envelope["format"], data["format"])
        got = decrypt_envelope(
            {
                "format": data["format"],
                "kdf": data["kdf"],
                "iterations": data["iterations"],
                "salt": crypto["salt"],
                "nonce": crypto["nonce"],
                "ciphertext": crypto["ciphertext"],
            },
            crypto["passphrase"],
        )
        self.assertEqual(got["accounts"][0]["id"], "user_01A")
        self.assertEqual(got["accounts"][0]["token"], crypto["plaintext"]["accounts"][0]["token"])
        with self.assertRaises(ValueError):
            decrypt_envelope(
                {
                    "format": data["format"],
                    "kdf": data["kdf"],
                    "iterations": data["iterations"],
                    "salt": crypto["salt"],
                    "nonce": crypto["nonce"],
                    "ciphertext": crypto["ciphertext"],
                },
                "wrong-pass",
            )


class ReconcileFileTests(unittest.TestCase):
    def test_push_then_pull_on_second_config(self) -> None:
        from account_sync import reconcile
        from accounts import upsert_account

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "cloud"
            a = {
                "accounts": [],
                "active_account_id": "",
                "session_token": "",
                "sync_enabled": True,
                "sync_path": str(folder),
                "sync_secret": "folder-pass-123",
                "deleted_accounts": [],
            }
            upsert_account(a, "user_01SYNC%3A%3Ajwt.part.sig", label="工作", activate=True)
            _, status = reconcile(a)
            self.assertTrue(status["ok"], status["message"])
            self.assertTrue(status["pushed"])
            self.assertTrue((folder / "CursorTokenTray.accounts.sync").is_file())

            b = {
                "accounts": [],
                "active_account_id": "",
                "session_token": "",
                "sync_enabled": True,
                "sync_path": str(folder),
                "sync_secret": "folder-pass-123",
                "deleted_accounts": [],
            }
            _, status_b = reconcile(b)
            self.assertTrue(status_b["ok"], status_b["message"])
            self.assertTrue(status_b["changed"])
            self.assertEqual(b["accounts"][0]["label"], "工作")
            self.assertEqual(b["active_account_id"], a["active_account_id"])

    def test_channel_syncs_with_account(self) -> None:
        from account_sync import apply_snapshot_to_config, snapshot_account, snapshot_from_config
        from accounts import set_account_channel, upsert_account

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": "", "deleted_accounts": []}
        upsert_account(cfg, "user_01CHAN%3A%3Ajwt.part.sig", label="自费号", activate=True)
        set_account_channel(cfg, cfg["active_account_id"], "self_pay")
        snap = snapshot_from_config(cfg)
        self.assertEqual(snap["accounts"][0]["channel"], "self_pay")
        self.assertEqual(snapshot_account(snap["accounts"][0])["channel"], "self_pay")

        other: dict = {"accounts": [], "active_account_id": "", "session_token": "", "deleted_accounts": []}
        apply_snapshot_to_config(other, snap)
        self.assertEqual(other["accounts"][0]["channel"], "self_pay")

    def test_actual_cny_syncs_with_account(self) -> None:
        from account_sync import apply_snapshot_to_config, snapshot_account, snapshot_from_config
        from accounts import set_account_actual_cny, upsert_account

        cfg: dict = {"accounts": [], "active_account_id": "", "session_token": "", "deleted_accounts": []}
        upsert_account(cfg, "user_01COST%3A%3Ajwt.part.sig", label="企业", activate=True)
        set_account_actual_cny(cfg, cfg["active_account_id"], 88)
        snap = snapshot_from_config(cfg)
        self.assertEqual(snap["accounts"][0]["actual_cny"], 88)
        self.assertEqual(snapshot_account(snap["accounts"][0])["actual_cny"], 88)

        other: dict = {"accounts": [], "active_account_id": "", "session_token": "", "deleted_accounts": []}
        apply_snapshot_to_config(other, snap)
        self.assertEqual(other["accounts"][0]["actual_cny"], 88)
        self.assertEqual(other["actual_cny"], 88)


class ConfigRoundtripTests(unittest.TestCase):
    def test_sync_fields_survive_save(self) -> None:
        import config

        old_dir = config.CONFIG_DIR
        old_path = config.CONFIG_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_DIR = Path(tmp)
            config.CONFIG_PATH = Path(tmp) / "config.json"
            try:
                cfg = dict(config.DEFAULT_CONFIG)
                cfg["sync_enabled"] = True
                cfg["sync_path"] = "/tmp/cloud"
                cfg["sync_secret"] = "secret"
                cfg["deleted_accounts"] = [{"id": "user_gone", "deleted_at": "2026-09-01T00:00:00.000Z"}]
                config.save_config(cfg)
                loaded = config.load_config()
                self.assertTrue(loaded["sync_enabled"])
                self.assertEqual(loaded["sync_path"], "/tmp/cloud")
                self.assertEqual(loaded["sync_secret"], "secret")
                self.assertEqual(loaded["deleted_accounts"][0]["id"], "user_gone")
            finally:
                config.CONFIG_DIR = old_dir
                config.CONFIG_PATH = old_path


if __name__ == "__main__":
    unittest.main()
