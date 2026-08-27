import Foundation
import XCTest
@testable import CursorTokenCore

enum Fixtures {
    static func data(_ name: String) throws -> Data {
        var dir = URL(fileURLWithPath: #filePath)
        for _ in 0..<12 {
            dir.deleteLastPathComponent()
            let candidate = dir.appendingPathComponent("fixtures").appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: candidate.path) {
                return try Data(contentsOf: candidate)
            }
        }
        throw NSError(domain: "Fixtures", code: 1, userInfo: [NSLocalizedDescriptionKey: "missing \(name)"])
    }

    static func json(_ name: String) throws -> Any {
        try JSONSerialization.jsonObject(with: data(name))
    }
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
            XCTAssertEqual(snap.usedPercent, expected["used_percent"] as! Double, accuracy: 0.0001, name)
            XCTAssertEqual(snap.remainingPercent, expected["remaining_percent"] as! Double, accuracy: 0.0001, name)
            XCTAssertEqual(opt(snap.autoPercentUsed), opt(expected["auto_percent_used"] as? Double), name)
            XCTAssertEqual(opt(snap.apiPercentUsed), opt(expected["api_percent_used"] as? Double), name)
            XCTAssertEqual(opt(snap.totalPercentUsed), opt(expected["total_percent_used"] as? Double), name)
            XCTAssertEqual(snap.membershipType, expected["membership_type"] as? String, name)
            XCTAssertEqual(snap.billingMode, expected["billing_mode"] as? String, name)
            XCTAssertEqual(opt(snap.usedCents), opt(num(expected["used_cents"])), name)
            XCTAssertEqual(opt(snap.limitCents), opt(num(expected["limit_cents"])), name)
            XCTAssertEqual(opt(snap.pooledUsedCents), opt(num(expected["pooled_used_cents"])), name)
            XCTAssertEqual(opt(snap.pooledLimitCents), opt(num(expected["pooled_limit_cents"])), name)
            XCTAssertEqual(opt(snap.onDemandUsedCents), opt(num(expected["on_demand_used_cents"])), name)
            XCTAssertEqual(opt(snap.onDemandLimitCents), opt(num(expected["on_demand_limit_cents"])), name)
            XCTAssertEqual(snap.limitType, expected["limit_type"] as? String ?? "", name)
            XCTAssertEqual(snap.isUnlimited, expected["is_unlimited"] as? Bool, name)
            XCTAssertEqual(snap.isTeamAccount, expected["is_team_account"] as? Bool, name)
            XCTAssertEqual(snap.showsAmount, expected["shows_amount"] as? Bool, name)
            XCTAssertEqual(snap.dashboardURL, expected["dashboard_url"] as? String, name)
            XCTAssertEqual(UsageParser.dashboardButtonLabel(snap), expected["dashboard_button_label"] as? String, name)
            XCTAssertEqual(UsageParser.dashboardMenuLabel(snap), expected["dashboard_menu_label"] as? String, name)
            XCTAssertEqual(UsageParser.dashboardLinkLabel(snap), expected["dashboard_link_label"] as? String, name)
        }
    }

    func testTokenCases() throws {
        let root = try XCTUnwrap(try json("token_cases.json") as? [String: Any])
        for row in root["account_ids"] as! [[String: Any]] {
            XCTAssertEqual(Token.accountId(from: row["token"] as! String), row["id"] as? String)
        }
        let variants = root["variants_jwt"] as! [String: Any]
        let got = Token.variants(variants["input"] as! String)
        XCTAssertEqual(got, variants["variants"] as? [String])
        for row in root["normalize"] as! [[String: Any]] {
            XCTAssertEqual(try Token.normalize(row["input"] as! String), row["output"] as? String)
        }
        for row in root["normalize_errors"] as! [[String: Any]] {
            XCTAssertThrowsError(try Token.normalize(row["input"] as! String)) { err in
                let msg = (err as? CursorAPIError)?.message ?? ""
                XCTAssertTrue(msg.contains(row["message_contains"] as! String), msg)
            }
        }
    }

    func testFormatCases() throws {
        let root = try XCTUnwrap(try json("format_cases.json") as? [String: Any])
        for row in root["membership"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatMembershipType(row["input"] as? String), row["output"] as? String)
        }
        for row in root["usd"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatUSDCents(num(row["cents"])), row["output"] as? String)
        }
        for row in root["spend_range"] as! [[String: Any]] {
            XCTAssertEqual(
                UsageParser.formatSpendRange(used: num(row["used"]), limit: num(row["limit"])),
                row["output"] as? String
            )
        }
        for row in root["token_count"] as! [[String: Any]] {
            XCTAssertEqual(UsageParser.formatTokenCount(num(row["n"])), row["output"] as? String)
        }
        for row in root["plan_caption"] as! [[String: Any]] {
            XCTAssertEqual(
                StatusText.formatPlanCaption(row["membership"] as? String, accountLabel: row["label"] as? String),
                row["output"] as? String
            )
        }
        for row in root["status_pill"] as! [[String: Any]] {
            XCTAssertEqual(
                StatusText.statusPillText(num(row["remaining"]), error: row["error"] as? Bool ?? false),
                row["output"] as? String
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
            autoPercent: cse["auto_percent"] as? Double,
            apiPercent: cse["api_percent"] as? Double
        )
        XCTAssertEqual(parsed.total, cse["total"] as? Int)
        let models = cse["models"] as! [[String: Any]]
        XCTAssertEqual(parsed.models.count, models.count)
        for (got, exp) in zip(parsed.models, models) {
            XCTAssertEqual(got.name, exp["name"] as? String)
            XCTAssertEqual(got.tokens, exp["tokens"] as? Int)
            XCTAssertEqual(got.tier, exp["tier"] as? Int)
            XCTAssertEqual(opt(got.usagePercent), opt(num(exp["usage_percent"])))
        }
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
        cfg = ConfigStore.normalize(ConfigStore.toDictionary(cfg))
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

    private func num(_ value: Any?) -> Double? {
        if value == nil || value is NSNull { return nil }
        if let n = value as? NSNumber { return n.doubleValue }
        if let d = value as? Double { return d }
        if let i = value as? Int { return Double(i) }
        return nil
    }

    private func opt(_ value: Double?) -> String {
        value.map { String($0) } ?? "nil"
    }
}
