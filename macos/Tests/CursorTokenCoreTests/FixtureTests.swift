import Foundation
import XCTest
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

    func testAggregatedUsage() throws {
        let root = try XCTUnwrap(try json("aggregated_usage_cases.json") as? [[String: Any]])
        let cse = root[0]
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
        ConfigStore.save(cfg, to: dir)
        let loaded = ConfigStore.load(from: dir)
        XCTAssertEqual(loaded.accounts.count, 1)
        XCTAssertEqual(loaded.accounts[0].label, "工作")
        XCTAssertEqual(loaded.activeAccountId, "user_01SAVE")
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
