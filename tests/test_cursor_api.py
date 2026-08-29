import unittest

from cursor_api import (
    USAGE_URL,
    BILLING_URL,
    dashboard_button_label,
    dashboard_link_label,
    dashboard_menu_label,
    dashboard_url_for,
    format_membership_type,
    format_spend_range,
    format_usd_cents,
    parse_usage_summary,
)


PERSONAL_ULTRA = {
    "billingCycleStart": "2026-07-04T00:35:51.000Z",
    "billingCycleEnd": "2026-08-04T00:35:51.000Z",
    "membershipType": "ultra",
    "limitType": "user",
    "isUnlimited": False,
    "autoModelSelectedDisplayMessage": "You've used 98% of your included total usage",
    "namedModelSelectedDisplayMessage": "You've used 100% of your included API usage",
    "individualUsage": {
        "plan": {
            "enabled": True,
            "used": 40000,
            "limit": 40000,
            "remaining": 0,
            "autoPercentUsed": 98.109,
            "apiPercentUsed": 100,
            "totalPercentUsed": 98.5128,
        },
        "onDemand": {"enabled": False, "used": 0, "limit": None, "remaining": None},
    },
    "teamUsage": {},
}

ENTERPRISE_OVERALL = {
    "billingCycleStart": "2026-07-01T00:00:00.000Z",
    "billingCycleEnd": "2026-08-01T00:00:00.000Z",
    "membershipType": "enterprise",
    "limitType": "team",
    "isUnlimited": False,
    "individualUsage": {
        "overall": {"enabled": True, "used": 7384, "limit": 10000, "remaining": 2616}
    },
    "teamUsage": {
        "onDemand": {"enabled": True, "used": 0, "limit": None, "remaining": None},
        "pooled": {"enabled": True, "used": 12725135, "limit": 28122000, "remaining": 15396865},
    },
}

ENTERPRISE_PLAN_PERCENT = {
    "billingCycleStart": "2026-03-01T00:00:00.000Z",
    "billingCycleEnd": "2026-04-01T00:00:00.000Z",
    "membershipType": "enterprise",
    "limitType": "team",
    "isUnlimited": False,
    "autoModelSelectedDisplayMessage": "You've used 7% of your included total usage",
    "namedModelSelectedDisplayMessage": "You've used 7% of your included API usage",
    "individualUsage": {
        "plan": {
            "enabled": True,
            "used": 0,
            "limit": 0,
            "remaining": 0,
            "breakdown": {"included": 0, "bonus": 300, "total": 300},
            "autoPercentUsed": 0,
            "apiPercentUsed": 6.9,
            "totalPercentUsed": 6.9,
        },
        "onDemand": {"enabled": False, "used": 0, "limit": 0, "remaining": 0},
    },
    "teamUsage": {
        "onDemand": {"enabled": True, "used": 0, "limit": 10000, "remaining": 10000}
    },
}

ENTERPRISE_DISPLAY_ONLY = {
    "billingCycleEnd": "2026-08-04T00:35:51.000Z",
    "membershipType": "team",
    "isUnlimited": False,
    "autoModelSelectedDisplayMessage": "You've used 42% of your included total usage",
    "namedModelSelectedDisplayMessage": "You've used 15% of your included API usage",
    "teamUsage": {"onDemand": {"enabled": True}},
}

ENTERPRISE_UNLIMITED = {
    "billingCycleEnd": "2026-08-04T00:00:00Z",
    "membershipType": "enterprise",
    "isUnlimited": True,
}

TEAM_OVERALL_STALE_ZERO = {
    "billingCycleStart": "2026-08-19T00:00:00.000Z",
    "billingCycleEnd": "2026-09-19T00:00:00.000Z",
    "membershipType": "team",
    "limitType": "team",
    "isUnlimited": False,
    "individualUsage": {
        "plan": {
            "enabled": True,
            "used": 0,
            "limit": 0,
            "remaining": 0,
            "autoPercentUsed": 0,
            "apiPercentUsed": 0,
            "totalPercentUsed": 0,
        },
        "overall": {"enabled": True, "used": 7180, "limit": 100000, "remaining": 92820},
        "onDemand": {"enabled": False, "used": 0, "limit": None, "remaining": None},
    },
    "teamUsage": {"onDemand": {"enabled": True, "used": 0, "limit": None, "remaining": None}},
}

TEAM_OVERALL_STALE_FULL = {
    "billingCycleStart": "2026-08-19T00:00:00.000Z",
    "billingCycleEnd": "2026-09-19T00:00:00.000Z",
    "membershipType": "team",
    "limitType": "team",
    "isUnlimited": False,
    "individualUsage": {
        "plan": {
            "enabled": True,
            "used": 0,
            "limit": 0,
            "remaining": 0,
            "autoPercentUsed": 100,
            "apiPercentUsed": 100,
            "totalPercentUsed": 100,
        },
        "overall": {"enabled": True, "used": 7180, "limit": 100000, "remaining": 92820},
    },
    "teamUsage": {},
}


class ParseUsageSummaryTests(unittest.TestCase):
    def test_personal_percent_plan_unchanged(self) -> None:
        snap = parse_usage_summary(PERSONAL_ULTRA)
        self.assertEqual(snap.membership_type, "Ultra")
        self.assertEqual(snap.billing_mode, "percent")
        self.assertEqual(snap.used_percent, 98.5)
        self.assertEqual(snap.remaining_percent, 1.5)
        self.assertEqual(snap.auto_percent_used, 98.1)
        self.assertEqual(snap.api_percent_used, 100.0)
        self.assertFalse(snap.is_team_account())
        self.assertFalse(snap.shows_amount())
        self.assertEqual(dashboard_url_for(snap), BILLING_URL)
        self.assertEqual(dashboard_button_label(snap), "账单")
        self.assertEqual(dashboard_menu_label(snap), "打开用量账单")
        self.assertEqual(dashboard_link_label(snap), "查看用量账单 →")

    def test_enterprise_overall_amount_billing(self) -> None:
        snap = parse_usage_summary(ENTERPRISE_OVERALL)
        self.assertEqual(snap.membership_type, "Enterprise")
        self.assertEqual(snap.billing_mode, "amount")
        self.assertTrue(snap.is_team_account())
        self.assertTrue(snap.shows_amount())
        self.assertEqual(snap.used_percent, 73.8)
        self.assertEqual(snap.remaining_percent, 26.2)
        self.assertEqual(snap.used_cents, 7384)
        self.assertEqual(snap.limit_cents, 10000)
        self.assertEqual(snap.pooled_used_cents, 12725135)
        self.assertEqual(snap.pooled_limit_cents, 28122000)
        self.assertEqual(dashboard_url_for(snap), USAGE_URL)
        self.assertEqual(dashboard_button_label(snap), "用量")
        self.assertEqual(dashboard_menu_label(snap), "打开用量")
        self.assertEqual(dashboard_link_label(snap), "查看用量 →")
        self.assertEqual(format_spend_range(snap.used_cents, snap.limit_cents), "$73.84 / $100")

    def test_enterprise_plan_percent_keeps_included_usage(self) -> None:
        snap = parse_usage_summary(ENTERPRISE_PLAN_PERCENT)
        self.assertEqual(snap.billing_mode, "percent")
        self.assertEqual(snap.used_percent, 6.9)
        self.assertEqual(snap.remaining_percent, 93.1)
        self.assertEqual(snap.api_percent_used, 6.9)
        self.assertTrue(snap.is_team_account())
        self.assertFalse(snap.shows_amount())
        self.assertEqual(snap.on_demand_used_cents, 0)
        self.assertEqual(snap.on_demand_limit_cents, 10000)
        self.assertEqual(dashboard_url_for(snap), USAGE_URL)

    def test_team_display_message_fallback(self) -> None:
        snap = parse_usage_summary(ENTERPRISE_DISPLAY_ONLY)
        self.assertEqual(snap.membership_type, "Team")
        self.assertEqual(snap.auto_percent_used, 42.0)
        self.assertEqual(snap.api_percent_used, 15.0)
        self.assertEqual(snap.used_percent, 42.0)
        self.assertEqual(snap.remaining_percent, 58.0)
        self.assertTrue(snap.is_team_account())
        self.assertEqual(dashboard_url_for(snap), USAGE_URL)

    def test_enterprise_pooled_only_fallback(self) -> None:
        snap = parse_usage_summary(
            {
                "membershipType": "enterprise",
                "limitType": "team",
                "teamUsage": {
                    "pooled": {
                        "enabled": True,
                        "used": 3479810,
                        "limit": 60000000,
                        "remaining": 56520190,
                    }
                },
            }
        )
        self.assertEqual(snap.billing_mode, "amount")
        self.assertEqual(snap.used_percent, 5.8)
        self.assertEqual(snap.remaining_percent, 94.2)
        self.assertEqual(snap.used_cents, 3479810)
        self.assertEqual(snap.limit_cents, 60000000)
        self.assertTrue(snap.shows_amount())
        self.assertEqual(dashboard_url_for(snap), USAGE_URL)

    def test_unlimited_enterprise(self) -> None:
        snap = parse_usage_summary(ENTERPRISE_UNLIMITED)
        self.assertTrue(snap.is_unlimited)
        self.assertEqual(snap.used_percent, 0.0)
        self.assertEqual(snap.remaining_percent, 100.0)
        self.assertTrue(snap.is_team_account())
        self.assertEqual(dashboard_url_for(snap), USAGE_URL)

    def test_legacy_plan_used_limit_ratio(self) -> None:
        snap = parse_usage_summary(
            {
                "membershipType": "pro",
                "individualUsage": {"plan": {"used": 25, "limit": 100}},
            }
        )
        self.assertEqual(snap.billing_mode, "percent")
        self.assertEqual(snap.used_percent, 25.0)
        self.assertEqual(snap.remaining_percent, 75.0)
        self.assertIsNone(snap.used_cents)
        self.assertFalse(snap.shows_amount())

    def test_team_overall_spend_beats_stale_plan_percent(self) -> None:
        snap = parse_usage_summary(TEAM_OVERALL_STALE_ZERO)
        self.assertEqual(snap.billing_mode, "amount")
        self.assertEqual(snap.used_percent, 7.2)
        self.assertEqual(snap.remaining_percent, 92.8)
        self.assertEqual(snap.used_cents, 7180)
        self.assertEqual(snap.limit_cents, 100000)
        self.assertEqual(snap.total_percent_used, 0.0)
        self.assertTrue(snap.shows_amount())
        self.assertEqual(format_spend_range(snap.used_cents, snap.limit_cents), "$71.80 / $1000")

        capped = parse_usage_summary(TEAM_OVERALL_STALE_FULL)
        self.assertEqual(capped.used_percent, 7.2)
        self.assertEqual(capped.remaining_percent, 92.8)
        self.assertEqual(capped.total_percent_used, 100.0)
        self.assertEqual(capped.auto_percent_used, 100.0)


class FormatHelpersTests(unittest.TestCase):
    def test_membership_and_money(self) -> None:
        self.assertEqual(format_membership_type("enterprise"), "Enterprise")
        self.assertEqual(format_membership_type("pro_plus"), "Pro+")
        self.assertEqual(format_usd_cents(7384), "$73.84")
        self.assertEqual(format_usd_cents(10000), "$100")
        self.assertEqual(format_usd_cents(0), "$0")
        self.assertEqual(format_spend_range(71, 10000), "$0.71 / $100")

    def test_dashboard_url_from_membership_only(self) -> None:
        self.assertEqual(dashboard_url_for(membership="enterprise"), USAGE_URL)
        self.assertEqual(dashboard_url_for(membership="Pro"), BILLING_URL)
        self.assertEqual(dashboard_url_for(membership="ultra", limit_type="team"), USAGE_URL)


class StatusTextEnterpriseTests(unittest.TestCase):
    def test_amount_rows(self) -> None:
        from status_text import build_status_lines

        snap = parse_usage_summary(ENTERPRISE_OVERALL)
        rows = dict(build_status_lines(snap, None, "12:00"))
        self.assertIn("$73.84 / $100", rows["剩余"])
        self.assertEqual(rows["金额"], "$73.84 / $100")
        self.assertIn("$", rows["团队额度"])
        self.assertEqual(rows["计划"], "Enterprise")

    def test_stale_plan_percent_does_not_override_monthly_spend(self) -> None:
        from status_text import build_status_lines

        snap = parse_usage_summary(TEAM_OVERALL_STALE_ZERO)
        rows = dict(build_status_lines(snap, None, "12:00"))
        self.assertIn("92.8%", rows["剩余"])
        self.assertIn("$71.80 / $1000", rows["剩余"])
        self.assertEqual(rows["金额"], "$71.80 / $1000")


class SourceGuardTests(unittest.TestCase):
    def test_native_usage_report_entry_points(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        win_prog = (root / "windows" / "CursorTokenTray" / "Program.cs").read_text(encoding="utf-8")
        win_parser = (root / "windows" / "CursorTokenCore" / "UsageParser.cs").read_text(encoding="utf-8")
        win_report = (root / "windows" / "CursorTokenTray" / "ReportForm.cs").read_text(encoding="utf-8")
        win_chart = (root / "windows" / "CursorTokenTray" / "UsageChartPanel.cs").read_text(encoding="utf-8")
        mac_menu = (root / "macos" / "Sources" / "CursorTokenTray" / "StatusItemController.swift").read_text(encoding="utf-8")
        mac_parser = (root / "macos" / "Sources" / "CursorTokenCore" / "UsageParser.swift").read_text(encoding="utf-8")
        mac_report = (root / "macos" / "Sources" / "CursorTokenTray" / "ReportView.swift").read_text(encoding="utf-8")
        mac_chart = (root / "macos" / "Sources" / "CursorTokenTray" / "UsageChartView.swift").read_text(encoding="utf-8")
        self.assertIn("用量报表", win_prog)
        self.assertIn("OpenReport", win_prog)
        self.assertIn("get-filtered-usage-events", win_parser)
        self.assertIn("UsageChartPanel", win_report)
        self.assertIn("按小时", win_chart)
        self.assertIn("BuildChart", win_chart)
        self.assertNotIn("SparklineBox", win_report)
        self.assertIn("用量报表", mac_menu)
        self.assertIn("openReport", mac_menu)
        self.assertIn("get-filtered-usage-events", mac_parser)
        self.assertIn("UsageChartView", mac_report)
        self.assertIn("chartHourly", mac_report)
        self.assertIn("按小时", mac_chart)
        self.assertIn("buildChart", mac_report)
        self.assertNotIn("dailyChart", mac_report)
