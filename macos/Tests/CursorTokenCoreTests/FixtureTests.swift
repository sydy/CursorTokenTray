import Foundation
import XCTest
import SQLite3
@testable import CursorTokenCore

enum Fixtures {
    static func data(_ name: String) throws -> Data {
        var dir = URL(fileURLWithPath: #filePath)
        var candidates: [URL] = []
        for _ in 0..<12 {
            dir.deleteLastPathComponent()
            candidates.append(dir.appendingPathComponent("fixtures").appendingPathComponent(name))
        }
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
        candidates.append(cwd.appendingPathComponent("fixtures").appendingPathComponent(name))
        candidates.append(cwd.appendingPathComponent("../fixtures").appendingPathComponent(name))
        for candidate in candidates where FileManager.default.fileExists(atPath: candidate.path) {
            return try Data(contentsOf: candidate)
        }
        throw NSError(domain: "Fixtures", code: 1, userInfo: [NSLocalizedDescriptionKey: "missing \(name)"])
    }

    static func json(_ name: String) throws -> Any {
        try JSONSerialization.jsonObject(with: data(name))
    }
}

private func json(_ name: String) throws -> Any {
    try Fixtures.json(name)
}

final class UsageParserFixtureTests: XCTestCase {
    func testUsageSummaryCases() throws {
        let root = try XCTUnwrap(try json("usage_summary_cases.json") as? [[String: Any]])
        for cse in root {
            let name = cse["name"] as? String ?? "?"
            let payloadData = try JSONSerialization.data(withJSONObject: cse["payload"] as Any)
            let payload = try JSONValue.parse(payloadData)
            let snap = UsageParser.parseUsageSummary(payload)
            let expected = cse["expected"] as! [String: Any]
            XCTAssertEqual(snap.usedPercent, try XCTUnwrap(num(expected["used_percent"])), accuracy: 0.0001, name)
            XCTAssertEqual(snap.remainingPercent, try XCTUnwrap(num(expected["remaining_percent"])), accuracy: 0.0001, name)
            XCTAssertEqual(opt(snap.autoPercentUsed), opt(num(expected["auto_percent_used"])), name)
            XCTAssertEqual(opt(snap.apiPercentUsed), opt(num(expected["api_percent_used"])), name)
            XCTAssertEqual(opt(snap.totalPercentUsed), opt(num(expected["total_percent_used"])), name)
            XCTAssertEqual(snap.membershipType, str(expected["membership_type"]), name)
            XCTAssertEqual(snap.billingMode, str(expected["billing_mode"]), name)
            XCTAssertEqual(opt(snap.usedCents), opt(num(expected["used_cents"])), name)
            XCTAssertEqual(opt(snap.limitCents), opt(num(expected["limit_cents"])), name)
            XCTAssertEqual(opt(snap.pooledUsedCents), opt(num(expected["pooled_used_cents"])), name)
            XCTAssertEqual(opt(snap.pooledLimitCents), opt(num(expected["pooled_limit_cents"])), name)
            XCTAssertEqual(opt(snap.onDemandUsedCents), opt(num(expected["on_demand_used_cents"])), name)
            XCTAssertEqual(opt(snap.onDemandLimitCents), opt(num(expected["on_demand_limit_cents"])), name)
            XCTAssertEqual(snap.limitType, str(expected["limit_type"]), name)
            XCTAssertEqual(snap.isUnlimited, bool(expected["is_unlimited"]), name)
            XCTAssertEqual(snap.isTeamAccount, bool(expected["is_team_account"]), name)
            XCTAssertEqual(snap.showsAmount, bool(expected["shows_amount"]), name)
            XCTAssertEqual(snap.dashboardURL, str(expected["dashboard_url"]), name)
            XCTAssertEqual(UsageParser.dashboardButtonLabel(snap), str(expected["dashboard_button_label"]), name)
            XCTAssertEqual(UsageParser.dashboardMenuLabel(snap), str(expected["dashboard_menu_label"]), name)
            XCTAssertEqual(UsageParser.dashboardLinkLabel(snap), str(expected["dashboard_link_label"]), name)
        }
    }

    func testTokenCases() throws {
        let root = try XCTUnwrap(try json("token_cases.json") as? [String: Any])
        for row in root["account_ids"] as! [[String: Any]] {
            XCTAssertEqual(Token.accountId(from: str(row["token"])), str(row["id"]))
        }
        let variants = root["variants_jwt"] as! [String: Any]
        let got = Token.variants(str(variants["input"]))
        XCTAssertEqual(got, stringArray(variants["variants"]))
        for row in root["normalize"] as! [[String: Any]] {
            XCTAssertEqual(try Token.normalize(str(row["input"])), str(row["output"]))
        }
        for row in root["normalize_errors"] as! [[String: Any]] {
            XCTAssertThrowsError(try Token.normalize(str(row["input"]))) { err in
                let msg = (err as? CursorAPIError)?.message ?? ""
                XCTAssertTrue(msg.contains(str(row["message_contains"])), msg)
            }
        }
    }

    func testFormatCases() throws {
        let root = try XCTUnwrap(try json("format_cases.json") as? [String: Any])
        for row in root["membership"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatMembershipType(row["input"] as? String), str(row["output"]))
        }
        for row in root["usd"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatUSDCents(num(row["cents"])), str(row["output"]))
        }
        for row in root["spend_range"] as! [[String: Any]] {
            XCTAssertEqual(
                UsageParser.formatSpendRange(used: num(row["used"]), limit: num(row["limit"])),
                str(row["output"])
            )
        }
        for row in root["token_count"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatTokenCount(num(row["n"])), str(row["output"]))
        }
        for row in root["plan_caption"] as! [[String: Any]] {
            XCTAssertEqual(
                StatusText.formatPlanCaption(row["membership"] as? String, accountLabel: row["label"] as? String),
                str(row["output"])
            )
        }
        for row in root["status_pill"] as! [[String: Any]] {
            XCTAssertEqual(
                StatusText.statusPillText(num(row["remaining"]), error: bool(row["error"])),
                str(row["output"])
            )
        }
        let usageRoot = try XCTUnwrap(try json("usage_summary_cases.json") as? [[String: Any]])
        let enterprise = usageRoot.first { ($0["name"] as? String) == "enterprise_overall" }!
        let payload = try JSONValue.parse(JSONSerialization.data(withJSONObject: enterprise["payload"] as Any))
        let snap = UsageParser.parseUsageSummary(payload)
        let lines = Dictionary(uniqueKeysWithValues: StatusText.buildStatusLines(snap, errorMessage: nil, updatedAt: "12:00"))
        XCTAssertTrue(lines["剩余"]?.contains("$73.84 / $100") == true)
        XCTAssertEqual(lines["金额"], "$73.84 / $100")
        XCTAssertTrue(lines["团队额度"]?.contains("$") == true)
        XCTAssertEqual(lines["计划"], "Enterprise")
    }

    func testTrayTemplateStateAndPercentLabel() {
        let idle = StatusText.trayTemplateState(errorMessage: "未配置 Token，请打开设置粘贴", remainingPercent: nil)
        XCTAssertNil(idle.remaining)
        XCTAssertFalse(idle.error)
        let fail = StatusText.trayTemplateState(errorMessage: "HTTP 401", remainingPercent: 40)
        XCTAssertNil(fail.remaining)
        XCTAssertTrue(fail.error)
        let ok = StatusText.trayTemplateState(errorMessage: nil, remainingPercent: 87.4)
        XCTAssertEqual(ok.remaining ?? -1, 87.4, accuracy: 0.0001)
        XCTAssertFalse(ok.error)
        XCTAssertEqual(StatusText.trayPercentLabel(nil, error: false), "–")
        XCTAssertEqual(StatusText.trayPercentLabel(nil, error: true), "!")
        XCTAssertEqual(StatusText.trayPercentLabel(12.4, error: false), "12")
        XCTAssertEqual(StatusText.trayPercentLabel(99.5, error: false), "100")
        XCTAssertEqual(StatusText.trayPercentLabel(0, error: false), "0")
    }

    func testAggregatedUsage() throws {
        let root = try XCTUnwrap(try json("aggregated_usage_cases.json") as? [[String: Any]])
        for cse in root {
            let payload = try JSONValue.parse(JSONSerialization.data(withJSONObject: cse["payload"] as Any))
            let parsed = UsageParser.parseAggregatedUsage(
                payload,
                autoPercent: num(cse["auto_percent"]),
                apiPercent: num(cse["api_percent"])
            )
            XCTAssertEqual(parsed.total, int(cse["total"]) ?? -1)
            let models = cse["models"] as! [[String: Any]]
            XCTAssertEqual(parsed.models.count, models.count)
            for (got, exp) in zip(parsed.models, models) {
                XCTAssertEqual(got.name, str(exp["name"]))
                XCTAssertEqual(got.tokens, int(exp["tokens"]) ?? -1)
                XCTAssertEqual(got.tier, int(exp["tier"]) ?? -1)
                XCTAssertEqual(opt(got.usagePercent), opt(num(exp["usage_percent"])))
            }
        }
    }

    func testSandUsageCases() throws {
        let root = try XCTUnwrap(try json("sand_usage_cases.json") as? [[String: Any]])
        for cse in root {
            let name = str(cse["name"])
            var now = Date()
            if let nowText = cse["now"] as? String {
                now = AccountSync.parseIso(nowText) ?? now
            }
            let payload = try JSONValue.parse(JSONSerialization.data(withJSONObject: cse["payload"] as Any))
            let got = UsageParser.parseSandUsageStatus(payload, now: now)
            let exp = cse["expected"] as! [String: Any]
            if bool(exp["shows_grok_bot"]) == false {
                XCTAssertNil(got, name)
                continue
            }
            let parsed = try XCTUnwrap(got, name)
            XCTAssertEqual(parsed.percentUsed, try XCTUnwrap(num(exp["percent_used"])), accuracy: 0.0001, name)
            XCTAssertEqual(parsed.remainingPercent, try XCTUnwrap(num(exp["remaining_percent"])), accuracy: 0.0001, name)
            XCTAssertEqual(parsed.periodStart, exp["period_start"] as? String, name)
            XCTAssertEqual(parsed.resetAt, exp["reset_at"] as? String, name)
            XCTAssertEqual(parsed.daysRemaining, int(exp["days_remaining"]), name)
        }
    }

    func testUsageEventsCases() throws {
        let root = try XCTUnwrap(try json("usage_events_cases.json") as? [String: Any])
        for row in root["kind"] as! [[String: Any]] {
            XCTAssertEqual(
                UsageEvents.classifyKind(str(row["kind"]), usageBasedCosts: str(row["usage_based_costs"]), isChargeable: bool(row["is_chargeable"])),
                str(row["output"])
            )
        }
        let labels = root["labels"] as! [String: Any]
        XCTAssertEqual(UsageEvents.kindLabel("included"), str(labels["included"]))
        XCTAssertEqual(UsageEvents.kindLabel("free"), str(labels["free"]))
        XCTAssertEqual(UsageEvents.kindLabel("on_demand"), str(labels["on_demand"]))
        let categoryLabels = root["category_labels"] as! [String: Any]
        XCTAssertEqual(UsageEvents.categoryLabel("first_party"), str(categoryLabels["first_party"]))
        XCTAssertEqual(UsageEvents.categoryLabel("api"), str(categoryLabels["api"]))
        XCTAssertEqual(UsageEvents.categoryLabel("grok_bot"), str(categoryLabels["grok_bot"]))
        for row in root["category"] as! [[String: Any]] {
            XCTAssertEqual(UsageEvents.classifyCategory(str(row["model"])), str(row["output"]))
        }
        for cse in root["parse"] as! [[String: Any]] {
            let payload = try JSONValue.parse(JSONSerialization.data(withJSONObject: cse["payload"] as Any))
            let parsed = UsageEvents.parsePage(payload)
            XCTAssertEqual(parsed.totalCount, int(cse["total_count"]) ?? -1)
            let expected = cse["events"] as! [[String: Any]]
            XCTAssertEqual(parsed.events.count, expected.count)
            for (got, exp) in zip(parsed.events, expected) {
                XCTAssertEqual(got.id, str(exp["id"]))
                XCTAssertEqual(got.timestampMs, number64(exp["timestamp_ms"]) ?? -1)
                XCTAssertEqual(got.model, str(exp["model"]))
                XCTAssertEqual(got.kind, str(exp["kind"]))
                XCTAssertEqual(got.userEmail, str(exp["user_email"]))
                XCTAssertEqual(got.owningUser, str(exp["owning_user"]))
                XCTAssertEqual(got.tokens, int(exp["tokens"]) ?? -1)
                XCTAssertEqual(opt(got.chargedCents), opt(num(exp["charged_cents"])))
                XCTAssertEqual(opt(got.totalCents), opt(num(exp["total_cents"])))
                XCTAssertEqual(got.isHeadless, bool(exp["is_headless"]))
            }
        }
        for cse in root["report"] as! [[String: Any]] {
            let events = (cse["events"] as! [[String: Any]]).compactMap(UsageEvents.fromDict)
            let filt = cse["filter"] as! [String: Any]
            let report = UsageEvents.buildReport(events, filter: UsageReportFilter(
                kind: str(filt["kind"]),
                category: str(filt["category"]),
                model: str(filt["model"]),
                headless: filt["headless"] is NSNull ? nil : (filt["headless"] as? Bool),
                owningUser: str(filt["owning_user"])
            ))
            let exp = cse["expected"] as! [String: Any]
            XCTAssertEqual(report.eventCount, int(exp["event_count"]) ?? -1)
            XCTAssertEqual(report.totalTokens, int(exp["total_tokens"]) ?? -1)
            XCTAssertEqual(report.totalCents, try XCTUnwrap(num(exp["total_cents"])), accuracy: 0.001)
            XCTAssertEqual(report.hasCost, bool(exp["has_cost"]))
            XCTAssertEqual(report.includedCount, int(exp["included_count"]) ?? -1)
            XCTAssertEqual(report.freeCount, int(exp["free_count"]) ?? -1)
            XCTAssertEqual(report.onDemandCount, int(exp["on_demand_count"]) ?? -1)
            XCTAssertEqual(report.headlessCount, int(exp["headless_count"]) ?? -1)
            if exp["first_party_count"] != nil {
                XCTAssertEqual(report.firstPartyCount, int(exp["first_party_count"]) ?? -1)
                XCTAssertEqual(report.apiCount, int(exp["api_count"]) ?? -1)
                XCTAssertEqual(report.grokBotCount, int(exp["grok_bot_count"]) ?? -1)
            }
            let daily = exp["daily"] as! [[String: Any]]
            XCTAssertEqual(report.daily.count, daily.count)
            for (got, row) in zip(report.daily, daily) {
                XCTAssertEqual(got.date, str(row["date"]))
                XCTAssertEqual(got.tokens, int(row["tokens"]) ?? -1)
                XCTAssertEqual(got.cents, try XCTUnwrap(num(row["cents"])), accuracy: 0.001)
                XCTAssertEqual(got.count, int(row["count"]) ?? -1)
            }
            let models = exp["models"] as! [[String: Any]]
            XCTAssertEqual(report.models.count, models.count)
            for (got, row) in zip(report.models, models) {
                XCTAssertEqual(got.name, str(row["name"]))
                XCTAssertEqual(got.tokens, int(row["tokens"]) ?? -1)
                XCTAssertEqual(got.cents, try XCTUnwrap(num(row["cents"])), accuracy: 0.001)
                XCTAssertEqual(got.count, int(row["count"]) ?? -1)
                XCTAssertEqual(got.headlessCount, int(row["headless_count"]) ?? -1)
            }
        }
        let cny = root["cny_spend"] as! [String: Any]
        for row in cny["defaults"] as! [[String: Any]] {
            XCTAssertEqual(UsageEvents.defaultMonthlyPlanUsd(str(row["membership"])), try XCTUnwrap(num(row["output"])))
        }
        for row in cny["format"] as! [[String: Any]] {
            XCTAssertEqual(UsageEvents.formatCNY(num(row["cny"])), str(row["output"]))
        }
        for cse in cny["cases"] as! [[String: Any]] {
            let events = (cse["events"] as! [[String: Any]]).compactMap(UsageEvents.fromDict)
            let filt = cse["filter"] as! [String: Any]
            let spendRaw = cse["spend"] as! [String: Any]
            let report = UsageEvents.buildReport(
                events,
                filter: UsageReportFilter(
                    kind: str(filt["kind"]),
                    category: str(filt["category"]),
                    model: str(filt["model"]),
                    headless: filt["headless"] is NSNull ? nil : (filt["headless"] as? Bool),
                    owningUser: str(filt["owning_user"])
                ),
                spend: CnySpendSettings(
                    monthlyPlanUsd: num(spendRaw["monthly_plan_usd"]) ?? 0,
                    usdCnyRate: num(spendRaw["usd_cny_rate"]) ?? UsageEvents.defaultUsdCnyRate,
                    membershipType: str(spendRaw["membership_type"]),
                    actualCny: num(spendRaw["actual_cny"]) ?? 0
                )
            )
            let exp = cse["expected"] as! [String: Any]
            XCTAssertEqual(report.monthlyPlanUsd, try XCTUnwrap(num(exp["monthly_plan_usd"])), accuracy: 0.001)
            XCTAssertEqual(report.usdCnyRate, try XCTUnwrap(num(exp["usd_cny_rate"])), accuracy: 0.001)
            XCTAssertEqual(report.planCny, try XCTUnwrap(num(exp["plan_cny"])), accuracy: 0.001)
            XCTAssertEqual(report.onDemandCny, try XCTUnwrap(num(exp["on_demand_cny"])), accuracy: 0.001)
            XCTAssertEqual(report.totalCny, try XCTUnwrap(num(exp["total_cny"])), accuracy: 0.001)
            if let wantActual = num(exp["actual_cny"]) {
                XCTAssertEqual(report.actualCny, wantActual, accuracy: 0.001)
            }
            if let usesActual = exp["uses_actual_cny"] as? Bool {
                XCTAssertEqual(report.usesActualCny, usesActual)
            }
            let eventCny = (exp["event_cny"] as! [Any]).compactMap { num($0) }
            XCTAssertEqual(report.events.count, eventCny.count)
            for (got, want) in zip(report.events, eventCny) {
                XCTAssertEqual(got.allocatedCny, want, accuracy: 0.001)
            }
            let models = exp["models"] as! [[String: Any]]
            XCTAssertEqual(report.models.count, models.count)
            for (got, row) in zip(report.models, models) {
                XCTAssertEqual(got.name, str(row["name"]))
                XCTAssertEqual(got.cny, try XCTUnwrap(num(row["cny"])), accuracy: 0.001)
            }
        }
        for row in root["cost_format"] as! [[String: Any]] {
            let ev = UsageEvent(
                timestampMs: 1,
                kind: str(row["kind"]),
                chargedCents: num(row["charged_cents"]),
                totalCents: num(row["total_cents"])
            )
            XCTAssertEqual(UsageEvents.formatCost(ev), str(row["output"]))
        }
        let first = (root["parse"] as! [[String: Any]])[0]
        let payload = try JSONValue.parse(JSONSerialization.data(withJSONObject: first["payload"] as Any))
        let csv = UsageEvents.toCSV(UsageEvents.parsePage(payload).events)
        XCTAssertTrue(csv.hasPrefix("\u{FEFF}"))
        XCTAssertTrue(csv.drop(while: { $0 == "\u{FEFF}" }).hasPrefix(str(root["csv_header"])))
        XCTAssertEqual(UsageEvents.csvHeader, str(root["csv_header"]))
        for row in root["times"] as! [[String: Any]] {
            let ts = number64(row["timestamp_ms"]) ?? 0
            XCTAssertEqual(UsageEvents.formatTime(ts), str(row["time"]))
            XCTAssertEqual(UsageEvents.eventDate(ts), str(row["date"]))
            XCTAssertEqual(UsageEvents.eventHour(ts), str(row["hour"]))
        }
    }

    func testAccountCompareCases() throws {
        let data = try XCTUnwrap(try json("account_compare_cases.json") as? [String: Any])
        XCTAssertEqual(UsageEvents.holdingDays, try XCTUnwrap(num(data["holding_days"])))
        let nowMs = number64(data["now_ms"])
        for row in data["channel"] as! [[String: Any]] {
            XCTAssertEqual(UsageEvents.sanitizeChannel(str(row["input"])), str(row["output"]))
            XCTAssertEqual(UsageEvents.channelLabel(str(row["input"])), str(row["label"]))
        }
        for cse in data["cases"] as! [[String: Any]] {
            let items = (cse["items"] as! [[String: Any]]).map { raw -> AccountCompareInput in
                let events = (raw["events"] as! [[String: Any]]).compactMap(UsageEvents.fromDict)
                let spend = raw["spend"] as! [String: Any]
                return AccountCompareInput(
                    accountId: str(raw["account_id"]),
                    label: str(raw["label"]),
                    channel: str(raw["channel"]),
                    membershipType: str(raw["membership_type"]),
                    accountKind: str(raw["account_kind"]),
                    tempStartAt: str(raw["temp_start_at"]),
                    tempValidDays: int(raw["temp_valid_days"]) ?? 0,
                    tempValidHours: int(raw["temp_valid_hours"]) ?? 0,
                    billingCycleStart: str(raw["billing_cycle_start"]),
                    billingCycleEnd: str(raw["billing_cycle_end"]),
                    events: events,
                    spend: CnySpendSettings(
                        monthlyPlanUsd: num(spend["monthly_plan_usd"]) ?? 0,
                        usdCnyRate: num(spend["usd_cny_rate"]) ?? UsageEvents.defaultUsdCnyRate,
                        membershipType: str(spend["membership_type"]),
                        actualCny: num(spend["actual_cny"]) ?? 0
                    )
                )
            }
            let report = UsageEvents.buildAccountCompareReport(items, nowMs: nowMs)
            let exp = cse["expected"] as! [String: Any]
            let wantRows = exp["rows"] as! [[String: Any]]
            XCTAssertEqual(report.rows.count, wantRows.count, str(cse["name"]))
            for (got, want) in zip(report.rows, wantRows) {
                XCTAssertEqual(got.accountId, str(want["account_id"]))
                XCTAssertEqual(got.channel, str(want["channel"]))
                XCTAssertEqual(got.windowSource, str(want["window_source"]))
                XCTAssertEqual(got.windowDays, try XCTUnwrap(num(want["window_days"])), accuracy: 0.001)
                XCTAssertEqual(got.planCny, try XCTUnwrap(num(want["plan_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.dailyHoldingCny, try XCTUnwrap(num(want["daily_holding_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.windowPlanCny, try XCTUnwrap(num(want["window_plan_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.onDemandCny, try XCTUnwrap(num(want["on_demand_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.totalCny, try XCTUnwrap(num(want["total_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.eventCount, int(want["event_count"]) ?? -1)
                XCTAssertEqual(got.totalTokens, int(want["total_tokens"]) ?? -1)
                XCTAssertEqual(got.cnyPerMillion ?? 0, try XCTUnwrap(num(want["cny_per_million"])), accuracy: 0.001)
                XCTAssertEqual(got.cnyPerRequest ?? 0, try XCTUnwrap(num(want["cny_per_request"])), accuracy: 0.001)
                for (cat, key) in [(got.firstParty, "first_party"), (got.api, "api"), (got.grokBot, "grok_bot")] {
                    let expCat = want[key] as! [String: Any]
                    XCTAssertEqual(cat.count, int(expCat["count"]) ?? -1, key)
                    XCTAssertEqual(cat.tokens, int(expCat["tokens"]) ?? -1, key)
                    XCTAssertEqual(cat.cny, try XCTUnwrap(num(expCat["cny"])), accuracy: 0.001, key)
                }
            }
            let wantGroups = exp["groups"] as! [[String: Any]]
            XCTAssertEqual(report.groups.count, wantGroups.count)
            for (got, want) in zip(report.groups, wantGroups) {
                XCTAssertEqual(got.channel, str(want["channel"]))
                XCTAssertEqual(got.dailyHoldingCny, try XCTUnwrap(num(want["daily_holding_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.totalCny, try XCTUnwrap(num(want["total_cny"])), accuracy: 0.001)
                XCTAssertEqual(got.eventCount, int(want["event_count"]) ?? -1)
                XCTAssertEqual(got.totalTokens, int(want["total_tokens"]) ?? -1)
            }
        }
    }

    func testUsageChartCases() throws {
        let root = try XCTUnwrap(try json("usage_chart_cases.json") as? [String: Any])
        XCTAssertEqual(UsageEvents.hourlyChartWindowHours, int(root["hourly_window_hours"]) ?? -1)
        for row in root["model_labels"] as! [[String: Any]] {
            XCTAssertEqual(UsageEvents.chartModelLabel(str(row["input"])), str(row["output"]))
        }
        for cse in root["cases"] as! [[String: Any]] {
            let events = (cse["events"] as! [[String: Any]]).compactMap(UsageEvents.fromDict)
            let hidden = Set(stringArray(cse["hidden_models"]))
            let series = UsageEvents.buildChart(events, hourly: bool(cse["hourly"]), hiddenModels: hidden)
            let exp = cse["expected"] as! [String: Any]
            XCTAssertEqual(series.hourly, bool(exp["hourly"]), str(cse["name"]))
            XCTAssertEqual(series.caption, str(exp["caption"]), str(cse["name"]))
            XCTAssertEqual(series.models, stringArray(exp["models"]), str(cse["name"]))
            if let buckets = exp["buckets"] as? [[String: Any]] {
                assertBuckets(buckets, series.buckets, str(cse["name"]))
                continue
            }
            XCTAssertEqual(series.buckets.count, int(exp["bucket_count"]) ?? -1, str(cse["name"]))
            XCTAssertEqual(series.buckets.first?.key, str(exp["first_key"]), str(cse["name"]))
            XCTAssertEqual(series.buckets.last?.key, str(exp["last_key"]), str(cse["name"]))
            let nonzero = series.buckets.filter { $0.tokens != 0 || $0.cents != 0 || $0.count != 0 }
            assertBuckets(exp["nonzero"] as! [[String: Any]], nonzero, str(cse["name"]))
        }
    }

    private func assertBuckets(_ expected: [[String: Any]], _ got: [ChartBucket], _ name: String) {
        XCTAssertEqual(got.count, expected.count, name)
        for (row, bucket) in zip(expected, got) {
            XCTAssertEqual(bucket.key, str(row["key"]), name)
            XCTAssertEqual(bucket.label, str(row["label"]), name)
            XCTAssertEqual(bucket.tokens, int(row["tokens"]) ?? -1, name)
            XCTAssertEqual(bucket.cents, try! XCTUnwrap(num(row["cents"])), accuracy: 0.001, name)
            XCTAssertEqual(bucket.count, int(row["count"]) ?? -1, name)
            let slices = row["slices"] as! [[String: Any]]
            XCTAssertEqual(bucket.slices.count, slices.count, name)
            for (srow, slice) in zip(slices, bucket.slices) {
                XCTAssertEqual(slice.model, str(srow["model"]), name)
                XCTAssertEqual(slice.tokens, int(srow["tokens"]) ?? -1, name)
                XCTAssertEqual(slice.cents, try! XCTUnwrap(num(srow["cents"])), accuracy: 0.001, name)
                XCTAssertEqual(slice.count, int(srow["count"]) ?? -1, name)
            }
        }
    }

    private func number64(_ value: Any?) -> Int64? {
        num(value).map { Int64($0.rounded()) }
    }

    func testSafariBinaryCookies() throws {
        var rec = Data(count: 56)
        let host = Data(".cursor.com\0".utf8)
        let name = Data("WorkosCursorSessionToken\0".utf8)
        let path = Data("/\0".utf8)
        let value = Data("cookie-value-abc\0".utf8)
        let strings = host + name + path + value
        rec += strings
        rec.replaceSubrange(0..<4, with: withUnsafeBytes(of: Int32(rec.count).littleEndian) { Data($0) })
        rec.replaceSubrange(16..<20, with: withUnsafeBytes(of: Int32(56).littleEndian) { Data($0) })
        rec.replaceSubrange(20..<24, with: withUnsafeBytes(of: Int32(56 + host.count).littleEndian) { Data($0) })
        rec.replaceSubrange(24..<28, with: withUnsafeBytes(of: Int32(56 + host.count + name.count).littleEndian) { Data($0) })
        rec.replaceSubrange(28..<32, with: withUnsafeBytes(of: Int32(56 + host.count + name.count + path.count).littleEndian) { Data($0) })

        let cookieOff: Int32 = 12
        var page = Data(count: Int(cookieOff) + rec.count)
        page.replaceSubrange(0..<4, with: withUnsafeBytes(of: UInt32(0x00000100).littleEndian) { Data($0) })
        page.replaceSubrange(4..<8, with: withUnsafeBytes(of: UInt32(1).littleEndian) { Data($0) })
        page.replaceSubrange(8..<12, with: withUnsafeBytes(of: UInt32(bitPattern: cookieOff).littleEndian) { Data($0) })
        page.replaceSubrange(Int(cookieOff)..<(Int(cookieOff) + rec.count), with: rec)

        var blob = Data("cook".utf8)
        blob += withUnsafeBytes(of: UInt32(1).bigEndian) { Data($0) }
        blob += withUnsafeBytes(of: UInt32(page.count).bigEndian) { Data($0) }
        blob += page
        let rows = try SessionImporter.parseSafariBinaryCookies(data: blob)
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows[0].0, ".cursor.com")
        XCTAssertEqual(rows[0].1, "WorkosCursorSessionToken")
        XCTAssertEqual(rows[0].2, "cookie-value-abc")
    }

    func testAccountMigrationAndHistory() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        let rows = (try json("token_cases.json") as! [String: Any])["account_ids"] as! [[String: Any]]
        let tokenA = rows[0]["token"] as! String
        let tokenB = rows[1]["token"] as! String
        let idA = rows[0]["id"] as! String
        let idB = rows[1]["id"] as! String

        var cfg = AppConfig.default
        cfg.sessionToken = tokenA
        cfg.alertNotifiedLevels = [20]
        cfg.authErrorNotified = true
        cfg.lowQuotaNotified = true
        cfg = ConfigStore.normalize(try ConfigStore.toDictionary(cfg))
        XCTAssertEqual(cfg.accounts.count, 1)
        XCTAssertEqual(cfg.accounts[0].id, idA)
        XCTAssertEqual(cfg.activeAccountId, idA)
        XCTAssertEqual(cfg.accounts[0].alertNotifiedLevels, [20])

        _ = try cfg.upsertAccount(token: tokenB, label: "公司", activate: true)
        XCTAssertEqual(cfg.activeAccountId, idB)
        XCTAssertTrue(cfg.setActiveAccount(idA))
        XCTAssertTrue(cfg.removeAccount(idA))
        XCTAssertEqual(cfg.accounts.map(\.id), [idB])

        UsageHistory.append(remaining: 80, ts: 1_700_000_000, accountId: "user_01A", directory: dir)
        UsageHistory.append(remaining: 20, ts: 1_700_000_100, accountId: "user_01B", directory: dir)
        XCTAssertEqual(UsageHistory.loadRecent(days: 10_000, accountId: "user_01A", directory: dir).map(\.remaining), [80])
        XCTAssertEqual(UsageHistory.loadRecent(days: 10_000, accountId: "user_01B", directory: dir).map(\.remaining), [20])

        let legacyDir = dir.appendingPathComponent("legacy", isDirectory: true)
        try FileManager.default.createDirectory(at: legacyDir, withIntermediateDirectories: true)
        let legacy = legacyDir.appendingPathComponent("usage_history.jsonl")
        try "{\"ts\":1700000000,\"remaining\":55,\"auto\":null,\"api\":null}\n".write(to: legacy, atomically: true, encoding: .utf8)
        UsageHistory.adoptLegacyHistory(accountId: "user_01LEG", directory: legacyDir)
        XCTAssertTrue(FileManager.default.fileExists(atPath: legacyDir.appendingPathComponent("usage_history.user_01LEG.jsonl").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: legacy.path))

        let skipDir = dir.appendingPathComponent("skip", isDirectory: true)
        try FileManager.default.createDirectory(at: skipDir, withIntermediateDirectories: true)
        let skipLegacy = skipDir.appendingPathComponent("usage_history.jsonl")
        try "{\"ts\":1700000000,\"remaining\":40,\"auto\":null,\"api\":null}\n".write(to: skipLegacy, atomically: true, encoding: .utf8)
        try "{\"ts\":1700000100,\"remaining\":10,\"auto\":null,\"api\":null}\n".write(
            to: skipDir.appendingPathComponent("usage_history.user_01A.jsonl"),
            atomically: true,
            encoding: .utf8
        )
        UsageHistory.adoptLegacyHistory(accountId: "user_01LEG", directory: skipDir)
        XCTAssertTrue(FileManager.default.fileExists(atPath: skipLegacy.path), "legacy file stays when another account already has history")
        XCTAssertFalse(FileManager.default.fileExists(atPath: skipDir.appendingPathComponent("usage_history.user_01LEG.jsonl").path))
    }

    func testConfigRoundtrip() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let header = Data("{\"alg\":\"none\"}".utf8).base64EncodedString()
            .replacingOccurrences(of: "=", with: "")
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
        let payload = try JSONSerialization.data(withJSONObject: ["sub": "github|user_01SAVE"])
        let p = payload.base64EncodedString().replacingOccurrences(of: "=", with: "").replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
        let token = "user_01SAVE%3A%3A\(header).\(p).sig"
        var cfg = AppConfig.default
        _ = try cfg.upsertAccount(token: token, label: "工作", activate: true)
        XCTAssertTrue(cfg.setActualCny("user_01SAVE", 79))
        XCTAssertTrue(cfg.setChannel("user_01SAVE", "自费"))
        ConfigStore.save(cfg, to: dir)
        let loaded = ConfigStore.load(from: dir)
        XCTAssertEqual(loaded.accounts.count, 1)
        XCTAssertEqual(loaded.accounts[0].label, "工作")
        XCTAssertEqual(loaded.accounts[0].actualCny, 79, accuracy: 0.001)
        XCTAssertEqual(loaded.accounts[0].channel, "self_pay")
        XCTAssertEqual(loaded.actualCny, 79, accuracy: 0.001)
        XCTAssertEqual(loaded.activeAccountId, "user_01SAVE")
        XCTAssertEqual(loaded.spendSettings().actualCny, 79, accuracy: 0.001)
    }

    func testPerAccountActualCnyAndLegacyMigration() throws {
        let header = Data("{\"alg\":\"none\"}".utf8).base64EncodedString()
            .replacingOccurrences(of: "=", with: "")
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
        func token(for user: String) throws -> String {
            let payload = try JSONSerialization.data(withJSONObject: ["sub": "github|\(user)"])
            let p = payload.base64EncodedString().replacingOccurrences(of: "=", with: "").replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            return "\(user)%3A%3A\(header).\(p).sig"
        }
        let tokenA = try token(for: "user_01A")
        let tokenB = try token(for: "user_01B")
        var cfg = AppConfig.default
        _ = try cfg.upsertAccount(token: tokenA, label: "个人", activate: true)
        _ = try cfg.upsertAccount(token: tokenB, label: "企业", activate: false)
        XCTAssertTrue(cfg.setActualCny("user_01A", 79))
        XCTAssertTrue(cfg.setActualCny("user_01B", 128))
        XCTAssertEqual(cfg.accounts.first { $0.id == "user_01A" }?.actualCny ?? 0, 79, accuracy: 0.001)
        XCTAssertEqual(cfg.accounts.first { $0.id == "user_01B" }?.actualCny ?? 0, 128, accuracy: 0.001)
        XCTAssertTrue(cfg.setActiveAccount("user_01B"))
        XCTAssertEqual(cfg.actualCny, 128, accuracy: 0.001)
        XCTAssertEqual(cfg.spendSettings().actualCny, 128, accuracy: 0.001)

        let raw: [String: Any] = [
            "actual_cny": 66,
            "accounts": [
                ["id": "user_01A", "token": tokenA, "label": "旧号"],
                ["id": "user_01C", "token": try token(for: "user_01C"), "label": "已填", "actual_cny": 12],
            ],
            "active_account_id": "user_01A",
        ]
        let migrated = ConfigStore.normalize(raw)
        XCTAssertEqual(migrated.accounts.first { $0.id == "user_01A" }?.actualCny ?? 0, 66, accuracy: 0.001)
        XCTAssertEqual(migrated.accounts.first { $0.id == "user_01C" }?.actualCny ?? 0, 12, accuracy: 0.001)
        XCTAssertEqual(migrated.actualCny, 66, accuracy: 0.001)
    }

    func testAlertMarksAllNewlyCrossedLevels() {
        var cfg = AppConfig.default
        cfg.notifyEnabled = true
        cfg.alertThresholds = [50, 20, 5]
        var acc = Account(label: "工作")
        var snap = UsageSnapshot(
            usedPercent: 96,
            remainingPercent: 4,
            membershipType: "Pro",
            raw: JSONValue([:]),
            billingMode: "percent",
            limitType: "",
            isUnlimited: false
        )
        var notices = AlertLogic.evaluate(config: cfg, account: &acc, snapshot: snap)
        XCTAssertEqual(notices.count, 1)
        XCTAssertTrue(notices[0].body.contains("5%"))
        XCTAssertEqual(acc.alertNotifiedLevels, [5, 20, 50])
        XCTAssertTrue(AlertLogic.evaluate(config: cfg, account: &acc, snapshot: snap).isEmpty)
    }

    func testCorruptConfigIsNotOverwritten() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let path = AppPaths.configPath(in: dir)
        try "{not-json".write(to: path, atomically: true, encoding: .utf8)
        let loaded = ConfigStore.load(from: dir)
        XCTAssertTrue(loaded.loadError)
        XCTAssertTrue(loaded.accounts.isEmpty)
        XCTAssertEqual(try String(contentsOf: path, encoding: .utf8), "{not-json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: path.appendingPathExtension("corrupt").path))
        ConfigStore.save(loaded, to: dir)
        XCTAssertEqual(try String(contentsOf: path, encoding: .utf8), "{not-json")
    }

    func testHistoryPruneDropsOldPoints() {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let old = Date().timeIntervalSince1970 - 100 * 86_400
        UsageHistory.append(remaining: 10, ts: old, accountId: "user_p", directory: dir)
        UsageHistory.append(remaining: 20, accountId: "user_p", directory: dir)
        let recent = UsageHistory.loadRecent(days: 200, accountId: "user_p", directory: dir)
        XCTAssertFalse(recent.contains { abs($0.remaining - 10) < 0.01 })
        XCTAssertTrue(recent.contains { abs($0.remaining - 20) < 0.01 })
    }

    func testDailyAvgBurn() {
        let start = Date().timeIntervalSince1970 - 4 * 86_400
        let points = [
            HistoryPoint(ts: start, remaining: 80),
            HistoryPoint(ts: start + 2 * 86_400, remaining: 60),
        ]
        XCTAssertEqual(UsageHistory.dailyAvgBurn(points: points), 10.0)
        XCTAssertNil(UsageHistory.dailyAvgBurn(points: [HistoryPoint(ts: start, remaining: 80)]))
        XCTAssertEqual(
            UsageHistory.dailyAvgBurn(points: [
                HistoryPoint(ts: start, remaining: 50),
                HistoryPoint(ts: start + 86_400, remaining: 60),
            ]),
            0.0
        )
    }

    func testTokenProtectorRoundtrip() throws {
        let token = "user_01PROT%3A%3Aaaa.bbb.ccc"
        XCTAssertEqual(TokenProtector.unprotect(try TokenProtector.protect(token)), token)
        XCTAssertEqual(TokenProtector.unprotect("plain"), "plain")
        XCTAssertEqual(try TokenProtector.protect(""), "")
        let blob = TokenProtector.prefix + Data([1, 2, 3, 4, 5, 6, 7, 8]).base64EncodedString()
        let unpacked = TokenProtector.tryUnprotect(blob)
        XCTAssertFalse(unpacked.ok)
        XCTAssertEqual(unpacked.value, "")
        XCTAssertEqual(TokenProtector.unprotect(blob), "")
    }

    func testEncryptedBlobIsNotUsedAsTokenAndIsPreserved() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let blob = TokenProtector.prefix + Data("not-a-real-aes-payload".utf8).base64EncodedString()
        let json = """
        {
          "session_token": "\(blob)",
          "accounts": [{ "id": "user_01X", "token": "\(blob)", "label": "坏" }],
          "active_account_id": "user_01X",
          "refresh_interval_minutes": 10
        }
        """
        try json.write(to: AppPaths.configPath(in: dir), atomically: true, encoding: .utf8)
        let loaded = ConfigStore.load(from: dir)
        XCTAssertTrue(loaded.decryptError)
        XCTAssertEqual(loaded.accounts.count, 1)
        XCTAssertTrue(loaded.accounts[0].tokenDecryptFailed)
        XCTAssertEqual(loaded.accounts[0].token, "")
        XCTAssertEqual(loaded.accounts[0].label, "坏")
        XCTAssertEqual(loaded.accounts[0].lastError, TokenProtector.decryptFailedMessage)
        ConfigStore.save(loaded, to: dir)
        let disk = try String(contentsOf: AppPaths.configPath(in: dir), encoding: .utf8)
        XCTAssertTrue(disk.contains(blob))
    }

    func testUpdateMergesOntoLatestDiskConfig() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let header = Data("{\"alg\":\"none\"}".utf8).base64EncodedString()
            .replacingOccurrences(of: "=", with: "")
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
        let payload = try JSONSerialization.data(withJSONObject: ["sub": "github|user_01SAVE"])
        let p = payload.base64EncodedString().replacingOccurrences(of: "=", with: "").replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
        let token = "user_01SAVE%3A%3A\(header).\(p).sig"
        var cfg = AppConfig.default
        cfg.refreshIntervalMinutes = 10
        _ = try cfg.upsertAccount(token: token, label: "工作", activate: true)
        ConfigStore.save(cfg, to: dir)

        var settings = ConfigStore.load(from: dir)
        settings.refreshIntervalMinutes = 15
        ConfigStore.save(settings, to: dir)

        let merged = ConfigStore.update(from: dir) { live in
            XCTAssertEqual(live.refreshIntervalMinutes, 15)
            live.applySnapshot(to: live.activeAccountId, remaining: 42)
        }
        XCTAssertEqual(merged.refreshIntervalMinutes, 15)
        XCTAssertEqual(merged.activeAccount?.lastRemaining, 42)
        let reloaded = ConfigStore.load(from: dir)
        XCTAssertEqual(reloaded.refreshIntervalMinutes, 15)
        XCTAssertEqual(reloaded.activeAccount?.lastRemaining, 42)
    }

    func testAccountValidityCases() throws {
        let root = try XCTUnwrap(try json("account_validity_cases.json") as? [String: Any])
        for row in root["kind"] as! [[String: Any]] {
            XCTAssertEqual(AccountValidity.sanitizeKind(row["input"] as? String), str(row["output"]))
        }
        for row in root["compute_end"] as! [[String: Any]] {
            let got = AccountValidity.computeEndIso(
                startAt: str(row["start"]),
                days: int(row["days"]) ?? 0,
                hours: int(row["hours"]) ?? 0
            )
            if let end = row["end"] as? String {
                XCTAssertEqual(got, end, str(row["name"]))
            } else {
                XCTAssertNil(got, str(row["name"]))
            }
        }
        for row in root["override"] as! [[String: Any]] {
            let accRaw = row["account"] as! [String: Any]
            let acc = Account(
                accountKind: str(accRaw["account_kind"]),
                tempStartAt: str(accRaw["temp_start_at"]),
                tempValidDays: int(accRaw["temp_valid_days"]) ?? 0,
                tempValidHours: int(accRaw["temp_valid_hours"]) ?? 0
            )
            var snap = UsageSnapshot(
                usedPercent: 10,
                remainingPercent: 90,
                membershipType: "Pro",
                billingCycleEnd: str(row["api_end"]),
                daysRemaining: 26
            )
            let now = AccountSync.parseIso(str(row["now"])) ?? Date()
            AccountValidity.applyEndOverride(&snap, account: acc, now: now)
            XCTAssertEqual(snap.billingCycleEnd, str(row["expected_end"]), str(row["name"]))
            XCTAssertEqual(snap.daysRemaining, int(row["expected_days_remaining"]), str(row["name"]))
            XCTAssertEqual(snap.billingCycleEndOverridden, bool(row["overridden"]), str(row["name"]))
        }
        let tmp = Account(label: "租号", accountKind: AccountValidity.temporary)
        XCTAssertTrue(tmp.caption(isActive: false).contains("临时"))
    }

    private func num(_ value: Any?) -> Double? {
        if value == nil || value is NSNull { return nil }
        if let n = value as? NSNumber { return n.doubleValue }
        if let d = value as? Double { return d }
        if let i = value as? Int { return Double(i) }
        return nil
    }

    private func int(_ value: Any?) -> Int? {
        num(value).map { Int($0.rounded()) }
    }

    private func bool(_ value: Any?) -> Bool {
        if let b = value as? Bool { return b }
        if let n = value as? NSNumber { return n.boolValue }
        return false
    }

    private func str(_ value: Any?) -> String {
        value as? String ?? ""
    }

    private func stringArray(_ value: Any?) -> [String] {
        if let arr = value as? [String] { return arr }
        if let arr = value as? [Any] { return arr.compactMap { $0 as? String } }
        return []
    }

    private func opt(_ value: Double?) -> String {
        value.map { String($0) } ?? "nil"
    }
}

final class AccountSyncFixtureTests: XCTestCase {
    func testAccountSyncCases() throws {
        let root = try XCTUnwrap(try json("account_sync_cases.json") as? [String: Any])
        XCTAssertEqual(str(root["format"]), AccountSync.format)
        XCTAssertEqual(str(root["filename"]), AccountSync.filename)
        for row in root["resolve_path"] as! [[String: Any]] {
            let got = AccountSync.resolveSyncPath(str(row["input"]))
            let suffix = str(row["output_suffix"])
            if suffix.isEmpty { XCTAssertEqual(got, "") }
            else { XCTAssertTrue(got.hasSuffix(suffix), "\(got) vs \(suffix)") }
        }
        for cse in root["merge"] as! [[String: Any]] {
            if bool(cse["apply"]) {
                var cfg = AppConfig.default
                let raw = cse["config"] as! [String: Any]
                if let rows = raw["accounts"] as? [[String: Any]] {
                    cfg.accounts = rows.map { row in
                        var acc = Account(
                            id: str(row["id"]),
                            label: str(row["label"]),
                            token: str(row["token"]),
                            membershipType: str(row["membership_type"])
                        )
                        acc.syncUpdatedAt = str(row["sync_updated_at"])
                        acc.lastRemaining = num(row["last_remaining"])
                        acc.alertNotifiedLevels = (row["alert_notified_levels"] as? [Int]) ?? []
                        acc.authErrorNotified = bool(row["auth_error_notified"])
                        acc.lowQuotaNotified = bool(row["low_quota_notified"])
                        return acc
                    }
                }
                cfg.activeAccountId = str(raw["active_account_id"])
                let snap = AccountSync.parseSnapshot(cse["snapshot"] as! [String: Any])
                _ = AccountSync.applySnapshotToConfig(&cfg, snap)
                let acc = cfg.accounts[0]
                let exp = cse["expected"] as! [String: Any]
                XCTAssertEqual(acc.label, str(exp["label"]))
                XCTAssertEqual(acc.token, str(exp["token"]))
                XCTAssertEqual(acc.membershipType, str(exp["membership_type"]))
                XCTAssertEqual(acc.lastRemaining ?? -1, num(exp["last_remaining"]) ?? -2, accuracy: 0.001)
                XCTAssertEqual(acc.alertNotifiedLevels, exp["alert_notified_levels"] as? [Int] ?? [])
                XCTAssertTrue(acc.authErrorNotified)
                XCTAssertTrue(acc.lowQuotaNotified)
                continue
            }
            let merged = AccountSync.mergeSnapshots(
                AccountSync.parseSnapshot(cse["local"] as! [String: Any]),
                AccountSync.parseSnapshot(cse["remote"] as! [String: Any])
            )
            let exp = cse["expected"] as! [String: Any]
            XCTAssertEqual(merged.activeAccountId, str(exp["active_account_id"]), str(cse["name"]))
            XCTAssertEqual(merged.accounts.map(\.id), stringArray(exp["ids"]), str(cse["name"]))
            let labels = exp["labels"] as! [String: Any]
            let tokens = exp["tokens"] as! [String: Any]
            for acc in merged.accounts {
                XCTAssertEqual(acc.label, str(labels[acc.id]))
                XCTAssertEqual(acc.token, str(tokens[acc.id]))
            }
            XCTAssertEqual(merged.deleted.map(\.id), stringArray(exp["deleted_ids"]))
            if let expSettings = exp["settings"] as? [String: Any] {
                XCTAssertNotNil(merged.settings)
                XCTAssertEqual(merged.settings?.refreshIntervalMinutes, int(expSettings["refresh_interval_minutes"]))
                XCTAssertEqual(merged.settings?.trayDisplayMode, str(expSettings["tray_display_mode"]))
                XCTAssertEqual(merged.settings?.notifyEnabled, expSettings["notify_enabled"] as? Bool)
                XCTAssertEqual(merged.settings?.monthlyPlanUsd ?? -1, num(expSettings["monthly_plan_usd"]) ?? -2, accuracy: 0.001)
            }
            if let remaining = exp["remaining"] as? [String: Any] {
                for acc in merged.accounts {
                    XCTAssertEqual(acc.lastRemaining ?? -1, num(remaining[acc.id]) ?? -2, accuracy: 0.001, str(cse["name"]))
                }
            }
            if let ends = exp["billing_cycle_end"] as? [String: Any] {
                for acc in merged.accounts {
                    XCTAssertEqual(acc.billingCycleEnd, str(ends[acc.id]), str(cse["name"]))
                }
            }
            if let hist = exp["usage_history_ts"] as? [String: Any] {
                for (aid, raw) in hist {
                    let want = (raw as? [Any] ?? []).compactMap { num($0) }
                    let got = merged.usage?.first(where: { $0.accountId == aid })?.history.map(\.ts) ?? []
                    XCTAssertEqual(got, want, str(cse["name"]))
                }
            }
            if let evs = exp["usage_event_ids"] as? [String: Any] {
                for (aid, raw) in evs {
                    let want = ((raw as? [Any]) ?? []).map { str($0) }.sorted()
                    let got = (merged.usage?.first(where: { $0.accountId == aid })?.events.map(\.id) ?? []).sorted()
                    XCTAssertEqual(got, want, str(cse["name"]))
                }
            }
            if let team = exp["usage_team_event_ids"] as? [String: Any] {
                for (aid, raw) in team {
                    let want = ((raw as? [Any]) ?? []).map { str($0) }.sorted()
                    let got = (merged.usage?.first(where: { $0.accountId == aid })?.teamEvents.map(\.id) ?? []).sorted()
                    XCTAssertEqual(got, want, str(cse["name"]))
                }
            }
        }
        let crypto = root["crypto"] as! [String: Any]
        let payload = AccountSync.parseSnapshot(crypto["plaintext"] as! [String: Any])
        let env = try AccountSync.encryptEnvelope(
            payload,
            passphrase: str(crypto["passphrase"]),
            salt: Data(base64Encoded: str(crypto["salt"])),
            nonce: Data(base64Encoded: str(crypto["nonce"])),
            iterations: int(root["iterations"]) ?? 0
        )
        XCTAssertEqual(str(env["ciphertext"]), str(crypto["ciphertext"]))
        let opened = try AccountSync.decryptEnvelope([
            "format": str(root["format"]),
            "kdf": str(root["kdf"]),
            "iterations": int(root["iterations"]) ?? 0,
            "salt": str(crypto["salt"]),
            "nonce": str(crypto["nonce"]),
            "ciphertext": str(crypto["ciphertext"]),
        ], passphrase: str(crypto["passphrase"]))
        XCTAssertEqual(opened.accounts[0].id, "user_01A")
        XCTAssertThrowsError(try AccountSync.decryptEnvelope([
            "format": str(root["format"]),
            "kdf": str(root["kdf"]),
            "iterations": int(root["iterations"]) ?? 0,
            "salt": str(crypto["salt"]),
            "nonce": str(crypto["nonce"]),
            "ciphertext": str(crypto["ciphertext"]),
        ], passphrase: "wrong-pass"))
    }

    private func json(_ name: String) throws -> Any { try Fixtures.json(name) }
    private func num(_ value: Any?) -> Double? {
        if value == nil || value is NSNull { return nil }
        if let n = value as? NSNumber { return n.doubleValue }
        if let d = value as? Double { return d }
        return nil
    }
    private func int(_ value: Any?) -> Int? { num(value).map { Int($0.rounded()) } }
    private func bool(_ value: Any?) -> Bool {
        if let b = value as? Bool { return b }
        if let n = value as? NSNumber { return n.boolValue }
        return false
    }
    private func str(_ value: Any?) -> String { value as? String ?? "" }
    private func stringArray(_ value: Any?) -> [String] {
        if let arr = value as? [String] { return arr }
        if let arr = value as? [Any] { return arr.compactMap { $0 as? String } }
        return []
    }
}

final class InstanceLockTests: XCTestCase {
    func testLooksLikeOurExecutable() {
        XCTAssertTrue(InstanceLock.looksLikeOurExecutable("/Applications/CursorTokenTray.app/Contents/MacOS/CursorTokenTray"))
        XCTAssertTrue(InstanceLock.looksLikeOurExecutable("/Users/me/Downloads/CursorTokenTray.app/Contents/MacOS/CursorTokenTray"))
        XCTAssertTrue(InstanceLock.looksLikeOurExecutable("/tmp/CursorTokenTray"))
        XCTAssertFalse(InstanceLock.looksLikeOurExecutable("/usr/bin/python3"))
        XCTAssertFalse(InstanceLock.looksLikeOurExecutable("/Applications/Safari.app/Contents/MacOS/Safari"))
        XCTAssertFalse(InstanceLock.looksLikeOurExecutable(""))
    }

    func testAcquireReplacingStaleWhenUnlocked() {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer {
            InstanceLock.release(directory: dir)
            try? FileManager.default.removeItem(at: dir)
        }
        XCTAssertTrue(InstanceLock.acquireReplacingStale(directory: dir))
    }
}

final class CursorAuthTests: XCTestCase {
    func testJwtTypeDistinguishesSessionAndWeb() throws {
        let session = try jwt(["sub": "auth0|user_01SESS", "type": "session"])
        let web = try jwt(["sub": "auth0|user_01WEB", "type": "web", "workosSessionId": "wos_x"])
        XCTAssertEqual(Token.jwtType(session), "session")
        XCTAssertEqual(Token.jwtType(web), "web")
        XCTAssertTrue(Token.canWriteToCursor(session))
        XCTAssertFalse(Token.canWriteToCursor(web))
        XCTAssertTrue(Token.canWriteToCursor("user_01SESS%3A%3A" + session))
        XCTAssertFalse(Token.canWriteToCursor("not-a-jwt-token-value"))
    }

    func testBuildValuesRefusesWebAndWritesSessionKeys() throws {
        let web = try jwt(["sub": "auth0|user_01WEB", "type": "web"])
        let refused = CursorAuth.buildValues(token: web)
        XCTAssertNil(refused.values)
        XCTAssertTrue(refused.error.contains("浏览器 Cookie"))

        let session = try jwt(["sub": "auth0|user_01SESS", "type": "session"])
        let built = CursorAuth.buildValues(
            token: "user_01SESS::" + session,
            email: "work@example.com",
            membershipType: "Pro",
            displayName: "工作号"
        )
        let values = try XCTUnwrap(built.values)
        XCTAssertEqual(values["cursorAuth/accessToken"], session)
        XCTAssertEqual(values["cursorAuth/refreshToken"], session)
        XCTAssertEqual(values["glass.lastSignedInAuthId"], "auth0|user_01SESS")
        XCTAssertEqual(values["cursorAuth/cachedEmail"], "work@example.com")
        XCTAssertEqual(values["cursorAuth/cachedSignUpType"], "Auth_0")
        XCTAssertEqual(values["cursorAuth/stripeMembershipType"], "pro")
        XCTAssertEqual(values["cursorAuth/stripeSubscriptionStatus"], "active")
        XCTAssertTrue(values["cursorAuth/cachedScopedProfile"]?.contains("工作号") == true)
    }

    func testStripePlanMapsLabels() {
        XCTAssertEqual(CursorAuth.stripePlan("Free").membership, "free")
        XCTAssertEqual(CursorAuth.stripePlan("Free").status, "unpaid")
        XCTAssertEqual(CursorAuth.stripePlan("Pro+").membership, "pro_plus")
        XCTAssertEqual(CursorAuth.stripePlan("Ultra").status, "active")
    }

    func testWriteIsSurgicalAndBacksUp() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let db = dir.appendingPathComponent("state.vscdb")
        try seedDb(db, items: [
            "cursorAuth/accessToken": "old-token",
            "cursorAuth/cachedEmail": "old@example.com",
            "cursorAuth/onboardingDate": "2024-01-01T00:00:00.000Z",
            "cursorAuth/cachedAccessToken": "old-cached",
            "mcpOAuth.secret.demo": "keep-secret",
            "theme": "dark",
        ], kv: ("chat-1", "transcript"))
        XCTAssertEqual(readKv(db), "transcript", "seed must keep cursorDiskKV")

        let session = try jwt(["sub": "auth0|user_01SESS", "type": "session"])
        let built = CursorAuth.buildValues(token: session, email: "new@example.com", membershipType: "free", displayName: "新号")
        let values = try XCTUnwrap(built.values)
        let result = CursorAuth.writeValues(dbPath: db, values: values, backup: true)
        XCTAssertTrue(result.ok, result.message)
        let backup = URL(fileURLWithPath: try XCTUnwrap(result.backupPath))
        XCTAssertEqual(CursorAuth.readValues(dbPath: backup)["cursorAuth/accessToken"], "old-token")

        let got = readAll(db)
        XCTAssertEqual(got["cursorAuth/accessToken"], session)
        XCTAssertEqual(got["cursorAuth/refreshToken"], session)
        XCTAssertEqual(got["cursorAuth/cachedAccessToken"], session)
        XCTAssertEqual(got["cursorAuth/cachedEmail"], "new@example.com")
        XCTAssertEqual(got["cursorAuth/onboardingDate"], "2024-01-01T00:00:00.000Z")
        XCTAssertEqual(got["mcpOAuth.secret.demo"], "keep-secret")
        XCTAssertEqual(got["theme"], "dark")
        XCTAssertEqual(readKv(db), "transcript")
    }

    func testApplyRefusesWhenStillRunningAndWritesWhenClosed() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let db = dir.appendingPathComponent("state.vscdb")
        try seedDb(db, items: ["cursorAuth/accessToken": "old"])
        let install = CursorInstall(name: "Cursor", stateDb: db)
        let session = try jwt(["sub": "auth0|user_01SESS", "type": "session"])

        let stillRunning = CursorAuth.apply(
            token: session,
            closeIfRunning: true,
            relaunch: true,
            installs: [install],
            isRunning: { _ in true },
            requestClose: { _ in true },
            waitGone: { _ in false },
            launch: { _ in XCTFail("must not launch"); return false },
            write: { _, _, _ in
                XCTFail("must not write")
                return CursorAuthApplyResult(ok: false, message: "must not write")
            }
        )
        XCTAssertFalse(stillRunning.ok)
        XCTAssertTrue(stillRunning.message.contains("没有退出"))
        XCTAssertEqual(CursorAuth.readValues(dbPath: db)["cursorAuth/accessToken"], "old")

        let ok = CursorAuth.apply(
            token: session,
            email: "a@b.c",
            membershipType: "Pro",
            displayName: "A",
            closeIfRunning: true,
            relaunch: true,
            installs: [install],
            isRunning: { _ in false },
            requestClose: { _ in XCTFail("must not close"); return false },
            waitGone: { _ in true },
            launch: { _ in true }
        )
        XCTAssertTrue(ok.ok, ok.message)
        XCTAssertTrue(ok.relaunched)
        XCTAssertEqual(CursorAuth.readValues(dbPath: db)["cursorAuth/accessToken"], session)
        XCTAssertTrue(ok.message.contains("已重新打开"))
    }

    private func jwt(_ payload: [String: String]) throws -> String {
        let header = try b64url(["alg": "none"])
        let body = try b64url(payload)
        return "\(header).\(body).sig"
    }

    private func b64url(_ obj: [String: String]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: obj)
        return data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .trimmingCharacters(in: CharacterSet(charactersIn: "="))
    }

    private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    private func bindText(_ stmt: OpaquePointer?, _ index: Int32, _ value: String) {
        value.withCString { sqlite3_bind_text(stmt, index, $0, -1, sqliteTransient) }
    }

    private func seedDb(_ path: URL, items: [String: String], kv: (String, String)? = nil) throws {
        var db: OpaquePointer?
        XCTAssertEqual(sqlite3_open(path.path, &db), SQLITE_OK)
        defer { sqlite3_close(db) }
        XCTAssertEqual(sqlite3_exec(db, "CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);", nil, nil, nil), SQLITE_OK)
        XCTAssertEqual(sqlite3_exec(db, "CREATE TABLE cursorDiskKV (key TEXT, value BLOB);", nil, nil, nil), SQLITE_OK)
        var stmt: OpaquePointer?
        XCTAssertEqual(sqlite3_prepare_v2(db, "INSERT INTO ItemTable(key, value) VALUES (?, ?)", -1, &stmt, nil), SQLITE_OK)
        defer { sqlite3_finalize(stmt) }
        for (k, v) in items {
            sqlite3_reset(stmt)
            sqlite3_clear_bindings(stmt)
            bindText(stmt, 1, k)
            bindText(stmt, 2, v)
            XCTAssertEqual(sqlite3_step(stmt), SQLITE_DONE)
        }
        if let kv {
            let sql = "INSERT INTO cursorDiskKV(key, value) VALUES ('\(kv.0)', '\(kv.1)');"
            XCTAssertEqual(sqlite3_exec(db, sql, nil, nil, nil), SQLITE_OK, "seed cursorDiskKV")
        }
    }

    private func readAll(_ path: URL) -> [String: String] {
        var found: [String: String] = [:]
        var db: OpaquePointer?
        guard sqlite3_open_v2(path.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else { return found }
        defer { sqlite3_close(db) }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT key, value FROM ItemTable", -1, &stmt, nil) == SQLITE_OK else { return found }
        defer { sqlite3_finalize(stmt) }
        while sqlite3_step(stmt) == SQLITE_ROW {
            let key = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let value = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            found[key] = value
        }
        return found
    }

    private func readKv(_ path: URL) -> String {
        var db: OpaquePointer?
        guard sqlite3_open_v2(path.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else { return "" }
        defer { sqlite3_close(db) }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT value FROM cursorDiskKV WHERE key = 'chat-1'", -1, &stmt, nil) == SQLITE_OK else { return "" }
        defer { sqlite3_finalize(stmt) }
        if sqlite3_step(stmt) == SQLITE_ROW {
            return sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
        }
        return ""
    }
}
