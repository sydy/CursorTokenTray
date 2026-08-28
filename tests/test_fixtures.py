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

    def test_usage_events_fixtures_match_python(self) -> None:
        from usage_report import (
            CSV_HEADER,
            KIND_LABELS,
            UsageEvent,
            UsageReportFilter,
            build_usage_report,
            classify_usage_kind,
            format_event_cost,
            parse_filtered_usage_events,
            usage_event_from_dict,
            usage_events_to_csv,
        )

        data = json.loads((ROOT / "fixtures" / "usage_events_cases.json").read_text(encoding="utf-8"))
        for row in data["kind"]:
            self.assertEqual(
                classify_usage_kind(row["kind"], row["usage_based_costs"], row["is_chargeable"]),
                row["output"],
            )
        self.assertEqual(data["labels"], KIND_LABELS)
        for cse in data["parse"]:
            events, total = parse_filtered_usage_events(cse["payload"])
            self.assertEqual(total, cse["total_count"])
            self.assertEqual(len(events), len(cse["events"]))
            for got, exp in zip(events, cse["events"]):
                self.assertEqual(got.id, exp["id"])
                self.assertEqual(got.timestamp_ms, exp["timestamp_ms"])
                self.assertEqual(got.model, exp["model"])
                self.assertEqual(got.kind, exp["kind"])
                self.assertEqual(got.user_email, exp["user_email"])
                self.assertEqual(got.owning_user, exp["owning_user"])
                self.assertEqual(got.tokens, exp["tokens"])
                self.assertEqual(got.charged_cents, exp["charged_cents"])
                self.assertEqual(got.total_cents, exp["total_cents"])
                self.assertEqual(got.is_headless, exp["is_headless"])
        for cse in data["report"]:
            events = [usage_event_from_dict(row) for row in cse["events"]]
            filt = cse["filter"]
            report = build_usage_report(
                events,
                UsageReportFilter(
                    kind=filt["kind"],
                    model=filt["model"],
                    headless=filt["headless"],
                    owning_user=filt.get("owning_user", ""),
                ),
            )
            exp = cse["expected"]
            self.assertEqual(report.event_count, exp["event_count"])
            self.assertEqual(report.total_tokens, exp["total_tokens"])
            self.assertEqual(report.total_cents, exp["total_cents"])
            self.assertEqual(report.has_cost, exp["has_cost"])
            self.assertEqual(report.included_count, exp["included_count"])
            self.assertEqual(report.free_count, exp["free_count"])
            self.assertEqual(report.on_demand_count, exp["on_demand_count"])
            self.assertEqual(report.headless_count, exp["headless_count"])
            self.assertEqual(
                [(d.date, d.tokens, d.cents, d.count) for d in report.daily],
                [(d["date"], d["tokens"], d["cents"], d["count"]) for d in exp["daily"]],
            )
            self.assertEqual(
                [(m.name, m.tokens, m.cents, m.count, m.headless_count) for m in report.models],
                [(m["name"], m["tokens"], m["cents"], m["count"], m["headless_count"]) for m in exp["models"]],
            )
        for row in data["cost_format"]:
            ev = UsageEvent(
                id="x",
                timestamp_ms=1,
                model="m",
                kind=row["kind"],
                user_email="",
                owning_user="",
                tokens=1,
                input_tokens=0,
                output_tokens=0,
                cache_write_tokens=0,
                cache_read_tokens=0,
                charged_cents=row["charged_cents"],
                total_cents=row["total_cents"],
                is_headless=False,
                is_chargeable=False,
            )
            self.assertEqual(format_event_cost(ev), row["output"])
        csv_text = usage_events_to_csv(parse_filtered_usage_events(data["parse"][0]["payload"])[0])
        self.assertTrue(csv_text.startswith("\ufeff"))
        self.assertTrue(csv_text.lstrip("\ufeff").startswith(data["csv_header"]))
        self.assertEqual(CSV_HEADER, data["csv_header"])

    def test_usage_chart_fixtures_match_python(self) -> None:
        from usage_report import (
            HOURLY_CHART_WINDOW_HOURS,
            build_usage_chart,
            chart_model_label,
            usage_event_from_dict,
        )

        data = json.loads((ROOT / "fixtures" / "usage_chart_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(HOURLY_CHART_WINDOW_HOURS, data["hourly_window_hours"])
        for row in data["model_labels"]:
            self.assertEqual(chart_model_label(row["input"]), row["output"])
        for cse in data["cases"]:
            with self.subTest(cse["name"]):
                events = [usage_event_from_dict(row) for row in cse["events"]]
                events = [e for e in events if e is not None]
                series = build_usage_chart(
                    events,
                    hourly=cse["hourly"],
                    hidden_models=set(cse["hidden_models"]),
                )
                self._assert_chart_series(series, cse["expected"])

    def _assert_chart_series(self, series, exp) -> None:
        self.assertEqual(series.hourly, exp["hourly"])
        self.assertEqual(series.caption, exp["caption"])
        self.assertEqual(list(series.models), exp["models"])
        if "buckets" in exp:
            self.assertEqual(self._chart_buckets(series.buckets), exp["buckets"])
            return
        self.assertEqual(len(series.buckets), exp["bucket_count"])
        self.assertEqual(series.buckets[0].key, exp["first_key"])
        self.assertEqual(series.buckets[-1].key, exp["last_key"])
        nonzero = [b for b in series.buckets if b.tokens or b.cents or b.count]
        self.assertEqual(self._chart_buckets(nonzero), exp["nonzero"])

    @staticmethod
    def _chart_buckets(buckets) -> list[dict]:
        return [
            {
                "key": b.key,
                "label": b.label,
                "tokens": b.tokens,
                "cents": b.cents,
                "count": b.count,
                "slices": [
                    {"model": s.model, "tokens": s.tokens, "cents": s.cents, "count": s.count}
                    for s in b.slices
                ],
            }
            for b in buckets
        ]

