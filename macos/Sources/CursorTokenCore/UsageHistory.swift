import Foundation

public struct HistoryPoint: Equatable, Sendable {
    public var ts: Double
    public var remaining: Double
    public var auto: Double?
    public var api: Double?

    public init(ts: Double, remaining: Double, auto: Double? = nil, api: Double? = nil) {
        self.ts = ts
        self.remaining = remaining
        self.auto = auto
        self.api = api
    }
}

public enum UsageHistory {
    public static let keepDays = 90
    public static let pruneInterval: TimeInterval = 6 * 3_600
    static var lastPruneAt: [String: TimeInterval] = [:]
    static let pruneLock = NSLock()

    public static func adoptLegacyHistory(accountId: String, directory: URL) {
        let dest = AppPaths.historyPath(accountId: accountId, in: directory)
        let legacy = directory.appendingPathComponent("usage_history.jsonl")
        if accountId.isEmpty { return }
        if FileManager.default.fileExists(atPath: dest.path) { return }
        if !FileManager.default.fileExists(atPath: legacy.path) { return }
        let others = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
        // Match usage_history.<id>.jsonl only — the legacy file is usage_history.jsonl
        // and must not count as "another account already claimed history".
        if others.contains(where: { isPerAccountHistoryFile($0) && $0.standardizedFileURL != dest.standardizedFileURL }) {
            return
        }
        try? FileManager.default.moveItem(at: legacy, to: dest)
    }

    static func isPerAccountHistoryFile(_ url: URL) -> Bool {
        let name = url.lastPathComponent
        return name.hasPrefix("usage_history.")
            && name.hasSuffix(".jsonl")
            && name != "usage_history.jsonl"
    }

    public static func append(
        remaining: Double,
        auto: Double? = nil,
        api: Double? = nil,
        ts: Double? = nil,
        accountId: String? = nil,
        directory: URL? = nil
    ) {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        var aid = (accountId ?? "").trimmingCharacters(in: .whitespaces)
        if aid.isEmpty {
            aid = ConfigStore.load(from: dir).activeAccount?.id ?? ""
        }
        if !aid.isEmpty { adoptLegacyHistory(accountId: aid, directory: dir) }
        let path = AppPaths.historyPath(accountId: aid.isEmpty ? nil : aid, in: dir)
        let point: [String: Any?] = [
            "ts": ts ?? Date().timeIntervalSince1970,
            "remaining": round2(remaining),
            "auto": auto.map(round2),
            "api": api.map(round2),
            "account_id": aid,
        ]
        var obj: [String: Any] = [:]
        for (k, v) in point {
            obj[k] = v ?? NSNull()
        }
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              var line = String(data: data, encoding: .utf8)
        else { return }
        line += "\n"
        if let handle = try? FileHandle(forWritingTo: path) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(line.utf8))
        } else {
            try? line.write(to: path, atomically: true, encoding: .utf8)
        }
        if ts == nil { maybePrune(path) }
    }

    static func maybePrune(_ path: URL) {
        let now = Date().timeIntervalSince1970
        let key = path.standardizedFileURL.path
        pruneLock.lock()
        if let last = lastPruneAt[key], now - last < pruneInterval {
            pruneLock.unlock()
            return
        }
        lastPruneAt[key] = now
        pruneLock.unlock()
        prune(path)
    }

    public static func prune(_ path: URL, keepDays: Int = keepDays) {
        let cutoff = Date().timeIntervalSince1970 - Double(max(1, keepDays)) * 86_400
        var kept: [String] = []
        for raw in iterRaw(path) {
            guard let ts = number(raw["ts"]), ts >= cutoff else { continue }
            guard let data = try? JSONSerialization.data(withJSONObject: raw),
                  let line = String(data: data, encoding: .utf8)
            else { continue }
            kept.append(line)
        }
        let text = kept.isEmpty ? "" : kept.joined(separator: "\n") + "\n"
        try? text.write(to: path, atomically: true, encoding: .utf8)
    }

    public static func loadRecent(days: Int = 7, accountId: String? = nil, directory: URL? = nil) -> [HistoryPoint] {
        let dir = directory ?? AppPaths.configDirectory()
        var aid = (accountId ?? "").trimmingCharacters(in: .whitespaces)
        if aid.isEmpty {
            aid = ConfigStore.load(from: dir).activeAccount?.id ?? ""
        }
        if !aid.isEmpty { adoptLegacyHistory(accountId: aid, directory: dir) }
        let cutoff = Date().timeIntervalSince1970 - Double(max(1, days)) * 86_400
        var points: [HistoryPoint] = []
        for raw in iterRaw(AppPaths.historyPath(accountId: aid.isEmpty ? nil : aid, in: dir)) {
            guard let ts = number(raw["ts"]), ts >= cutoff,
                  let remaining = number(raw["remaining"])
            else { continue }
            points.append(HistoryPoint(ts: ts, remaining: remaining, auto: number(raw["auto"]), api: number(raw["api"])))
        }
        points.sort { $0.ts < $1.ts }
        return points
    }

    public static func dailyAvgBurn(days: Int = 7, accountId: String? = nil, directory: URL? = nil) -> Double? {
        dailyAvgBurn(points: loadRecent(days: days, accountId: accountId, directory: directory))
    }

    public static func dailyAvgBurn(points: [HistoryPoint]) -> Double? {
        guard points.count >= 2 else { return nil }
        let first = points[0]
        let last = points[points.count - 1]
        let elapsed = (last.ts - first.ts) / 86_400.0
        if elapsed < 0.04 { return nil }
        let delta = first.remaining - last.remaining
        if delta <= 0 { return 0 }
        return round2(delta / elapsed)
    }

    static func iterRaw(_ path: URL) -> [[String: Any]] {
        guard let text = try? String(contentsOf: path, encoding: .utf8) else { return [] }
        var rows: [[String: Any]] = []
        for line in text.split(whereSeparator: \.isNewline) {
            let t = line.trimmingCharacters(in: .whitespaces)
            guard !t.isEmpty, let data = t.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { continue }
            rows.append(obj)
        }
        return rows
    }

    static func number(_ value: Any?) -> Double? {
        if value == nil || value is NSNull { return nil }
        if let n = value as? NSNumber { return n.doubleValue }
        if let s = value as? String { return Double(s) }
        return nil
    }
}

public enum AlertLogic {
    public static func isExhaustionRisk(_ snapshot: UsageSnapshot) -> Bool {
        guard let est = snapshot.estimatedUsableDays, let resetLeft = snapshot.daysRemaining else { return false }
        if est <= 0 { return true }
        return est < Double(resetLeft)
    }

    public struct Notice: Equatable {
        public var title: String
        public var body: String
    }

    public static func evaluate(
        config: AppConfig,
        account: inout Account,
        snapshot: UsageSnapshot
    ) -> [Notice] {
        guard config.notifyEnabled else { return [] }
        var notices: [Notice] = []
        let remaining = snapshot.remainingPercent
        let thresholds = Set(config.alertThresholds.filter { (1...100).contains($0) }).sorted(by: >)
        var notified = Set(account.alertNotifiedLevels)
        var changed = false
        let name = account.displayLabel
        let who = name.isEmpty ? "套餐" : "账号「\(name)」"

        let still = notified.filter { remaining < Double($0) }
        if still != notified {
            notified = still
            changed = true
        }
        let newly = thresholds.filter { remaining < Double($0) && !notified.contains($0) }
        if !newly.isEmpty {
            let hit = newly.min() ?? newly[0]
            notices.append(Notice(title: "额度告警", body: String(format: "%@剩余 %.1f%%，已低于 %d%% 档。", who, remaining, hit)))
            newly.forEach { notified.insert($0) }
            changed = true
        }
        if config.notifyExhaustionRisk {
            let atRisk = isExhaustionRisk(snapshot)
            let was = account.exhaustionNotified
            if atRisk && !was {
                notices.append(Notice(title: "耗尽风险", body: String(format: "%@按当前速度可能提前耗尽（剩余 %.1f%%）。", who, remaining)))
                account.exhaustionNotified = true
                changed = true
            } else if !atRisk && was {
                account.exhaustionNotified = false
                changed = true
            }
        }
        if changed {
            account.alertNotifiedLevels = notified.sorted()
            let minThr = thresholds.min() ?? 20
            account.lowQuotaNotified = remaining < Double(minThr)
        }
        return notices
    }
}
