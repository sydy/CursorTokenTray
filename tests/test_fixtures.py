import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GoldenFixtureTests(unittest.TestCase):
    def test_usage_summary_fixtures_match_python(self) -> None:
        from cursor_api import (
            dashboard_button_label,
            dashboard_link_label,
            dashboard_menu_label,
            dashboard_url_for,
            parse_usage_summary,
        )

        cases = json.loads((ROOT / "fixtures" / "usage_summary_cases.json").read_text(encoding="utf-8"))
        for cse in cases:
            with self.subTest(cse["name"]):
                snap = parse_usage_summary(cse["payload"])
                exp = cse["expected"]
                self.assertEqual(snap.used_percent, exp["used_percent"])
                self.assertEqual(snap.remaining_percent, exp["remaining_percent"])
                self.assertEqual(snap.auto_percent_used, exp["auto_percent_used"])
                self.assertEqual(snap.api_percent_used, exp["api_percent_used"])
                self.assertEqual(snap.membership_type, exp["membership_type"])
                self.assertEqual(snap.billing_mode, exp["billing_mode"])
                self.assertEqual(snap.used_cents, exp["used_cents"])
                self.assertEqual(snap.limit_cents, exp["limit_cents"])
                self.assertEqual(snap.is_team_account(), exp["is_team_account"])
                self.assertEqual(snap.shows_amount(), exp["shows_amount"])
                self.assertEqual(dashboard_url_for(snap), exp["dashboard_url"])
                self.assertEqual(dashboard_button_label(snap), exp["dashboard_button_label"])
                self.assertEqual(dashboard_menu_label(snap), exp["dashboard_menu_label"])
                self.assertEqual(dashboard_link_label(snap), exp["dashboard_link_label"])

    def test_token_fixtures_match_python(self) -> None:
        from cursor_api import CursorApiError, account_id_from_token, normalize_workos_token, session_token_variants

        data = json.loads((ROOT / "fixtures" / "token_cases.json").read_text(encoding="utf-8"))
        for row in data["account_ids"]:
            self.assertEqual(account_id_from_token(row["token"]), row["id"])
        self.assertEqual(session_token_variants(data["variants_jwt"]["input"]), data["variants_jwt"]["variants"])
        for row in data["normalize"]:
            self.assertEqual(normalize_workos_token(row["input"]), row["output"])
        for row in data["normalize_errors"]:
            with self.assertRaises(CursorApiError) as cm:
                normalize_workos_token(row["input"])
            self.assertIn(row["message_contains"], str(cm.exception))

    def test_format_fixtures_match_python(self) -> None:
        from cursor_api import format_membership_type, format_spend_range, format_token_count, format_usd_cents
        from status_text import format_plan_caption, status_pill_text

        data = json.loads((ROOT / "fixtures" / "format_cases.json").read_text(encoding="utf-8"))
        for row in data["membership"]:
            self.assertEqual(format_membership_type(row["input"]), row["output"])
        for row in data["usd"]:
            self.assertEqual(format_usd_cents(row["cents"]), row["output"])
        for row in data["spend_range"]:
            self.assertEqual(format_spend_range(row["used"], row["limit"]), row["output"])
        for row in data["token_count"]:
            self.assertEqual(format_token_count(row["n"]), row["output"])
        for row in data["plan_caption"]:
            self.assertEqual(format_plan_caption(row["membership"], row.get("label")), row["output"])
        for row in data["status_pill"]:
            self.assertEqual(status_pill_text(row["remaining"], error=row["error"]), row["output"])

    def test_aggregated_usage_fixtures_match_python(self) -> None:
        from cursor_api import parse_aggregated_usage

        cases = json.loads((ROOT / "fixtures" / "aggregated_usage_cases.json").read_text(encoding="utf-8"))
        cse = cases[0]
        models, total = parse_aggregated_usage(
            cse["payload"],
            auto_percent=cse["auto_percent"],
            api_percent=cse["api_percent"],
        )
        self.assertEqual(total, cse["total"])
        self.assertEqual(len(models), len(cse["models"]))
        for got, exp in zip(models, cse["models"]):
            self.assertEqual(got.name, exp["name"])
            self.assertEqual(got.tokens, exp["tokens"])
            self.assertEqual(got.tier, exp["tier"])
            self.assertEqual(got.usage_percent, exp["usage_percent"])
