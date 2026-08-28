import Foundation

public struct UsageEvent: Equatable, Sendable {
    public var id: String
    public var timestampMs: Int64
    public var model: String
    public var kind: String
    public var userEmail: String
    public var owningUser: String
    public var tokens: Int
    public var inputTokens: Int
    public var outputTokens: Int
    public var cacheWriteTokens: Int
    public var cacheReadTokens: Int
    public var chargedCents: Double?
    public var totalCents: Double?
    public var isHeadless: Bool
    public var isChargeable: Bool

    public init(
        id: String = "",
        timestampMs: Int64,
        model: String = "",
        kind: String = UsageEvents.kindOther,
        userEmail: String = "",
        owningUser: String = "",
        tokens: Int = 0,
        inputTokens: Int = 0,
        outputTokens: Int = 0,
        cacheWriteTokens: Int = 0,
        cacheReadTokens: Int = 0,
        chargedCents: Double? = nil,
        totalCents: Double? = nil,
        isHeadless: Bool = false,
        isChargeable: Bool = false
    ) {
        self.id = id
        self.timestampMs = timestampMs
        self.model = model
        self.kind = kind
        self.userEmail = userEmail
        self.owningUser = owningUser
        self.tokens = tokens
        self.inputTokens = inputTokens
        self.outputTokens = outputTokens
        self.cacheWriteTokens = cacheWriteTokens
        self.cacheReadTokens = cacheReadTokens
        self.chargedCents = chargedCents
        self.totalCents = totalCents
        self.isHeadless = isHeadless
        self.isChargeable = isChargeable
    }
}

public struct DailyUsageRow: Equatable, Sendable {
    public var date: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
}

public struct ModelUsageRow: Equatable, Sendable {
    public var name: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
    public var headlessCount: Int
}

public struct ChartSlice: Equatable, Sendable {
    public var model: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
}

public struct ChartBucket: Equatable, Sendable, Identifiable {
    public var id: String { key }
    public var key: String
    public var label: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
    public var slices: [ChartSlice]
}

public struct UsageChartSeries: Equatable, Sendable {
    public var hourly: Bool
    public var caption: String
    public var models: [String]
    public var buckets: [ChartBucket]
}

public struct UsageReportFilter: Equatable, Sendable {
    public var kind: String
    public var model: String
    public var headless: Bool?
    public var owningUser: String

    public init(kind: String = "", model: String = "", headless: Bool? = nil, owningUser: String = "") {
        self.kind = kind
        self.model = model
        self.headless = headless
        self.owningUser = owningUser
    }
}

public struct UsageReport: Equatable, Sendable {
    public var eventCount: Int
    public var totalTokens: Int
    public var totalCents: Double
    public var hasCost: Bool
    public var includedCount: Int
    public var freeCount: Int
    public var onDemandCount: Int
    public var otherCount: Int
    public var headlessCount: Int
    public var daily: [DailyUsageRow]
    public var models: [ModelUsageRow]
    public var events: [UsageEvent]
}

public struct UsageEventsSyncResult: Sendable {
    public var events: [UsageEvent]
    public var fetched: Int
    public var totalAvailable: Int
    public var truncated: Bool
}

public enum UsageEvents {
    public static let kindIncluded = "included"
    public static let kindFree = "free"
    public static let kindOnDemand = "on_demand"
    public static let kindOther = "other"
    public static let csvHeader = "日期(UTC),用户,类型,模型,Token,费用,云端Agent"
    public static let hourlyChartWindowHours = 48
    static let msHour: Int64 = 3_600_000
    static let msDay: Int64 = 86_400_000

    public static func kindLabel(_ kind: String?) -> String {
        switch (kind ?? "").trimmingCharacters(in: .whitespaces).lowercased() {
        case kindIncluded: return "套餐内"
        case kindFree: return "免费"
        case kindOnDemand: return "按需"
        default: return "其他"
        }
    }

    public static func classifyKind(_ kind: String?, usageBasedCosts: String? = nil, isChargeable: Bool = false) -> String {
        let blob = "\(kind ?? "") \(usageBasedCosts ?? "")".trimmingCharacters(in: .whitespaces).lowercased()
        if blob.contains("free") { return kindFree }
        if blob.contains("included") { return kindIncluded }
        if blob.contains("usage_based") || blob.contains("usage-based") || blob.contains("ondemand")
            || blob.contains("on_demand") || blob.contains("on-demand") {
            return kindOnDemand
        }
        return isChargeable ? kindOnDemand : kindIncluded
    }

    public static func costCents(_ ev: UsageEvent) -> Double {
        if let charged = ev.chargedCents { return max(0, charged) }
        if let total = ev.totalCents { return max(0, total) }
        return 0
    }

    public static func formatCost(_ ev: UsageEvent) -> String {
        let cents = costCents(ev)
        if ev.kind == kindFree { return "免费" }
        if ev.kind == kindIncluded {
            return cents > 0 ? "\(UsageParser.formatUSDCents(cents)) 套餐内" : "套餐内"
        }
        return cents > 0 ? UsageParser.formatUSDCents(cents) : "—"
    }

    public static func formatTime(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(max(0, timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.string(from: dt)
    }

    public static func dateUtc(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(max(0, timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: dt)
    }

    public static func hourUtc(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(floorHourMs(timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd HH:'00'"
        return f.string(from: dt)
    }

    public static func chartModelLabel(_ name: String?) -> String {
        let text = (name ?? "").trimmingCharacters(in: .whitespaces)
        if text.hasPrefix("cursor-") {
            return String(text.dropFirst(7))
        }
        return text
    }

    public static func buildChart(
        _ events: [UsageEvent],
        hourly: Bool,
        hiddenModels: Set<String> = [],
        hourlyWindowHours: Int = hourlyChartWindowHours
    ) -> UsageChartSeries {
        let models = chartModels(events)
        let visible = models.filter { !hiddenModels.contains($0) }
        if events.isEmpty {
            return UsageChartSeries(hourly: hourly, caption: chartCaption(hourly: hourly, keys: []), models: models, buckets: [])
        }

        let keys: [String]
        let keyOf: (Int64) -> String
        if hourly {
            var lastMs = floorHourMs(events.map(\.timestampMs).max() ?? 0)
            var firstMs = floorHourMs(events.map(\.timestampMs).min() ?? 0)
            let window = Int64(max(1, hourlyWindowHours))
            let span = (lastMs - firstMs) / msHour + 1
            if span > window { firstMs = lastMs - (window - 1) * msHour }
            let count = Int((lastMs - firstMs) / msHour + 1)
            keys = (0..<count).map { hourUtc(firstMs + Int64($0) * msHour) }
            keyOf = hourUtc
        } else {
            let lastMs = floorDayMs(events.map(\.timestampMs).max() ?? 0)
            let firstMs = floorDayMs(events.map(\.timestampMs).min() ?? 0)
            let count = Int((lastMs - firstMs) / msDay + 1)
            keys = (0..<count).map { dateUtc(firstMs + Int64($0) * msDay) }
            keyOf = dateUtc
        }

        var cells: [String: (Int, Double, Int)] = [:]
        for ev in events {
            let key = keyOf(ev.timestampMs)
            if key < keys[0] || key > keys[keys.count - 1] { continue }
            let name = ev.model.isEmpty ? "—" : ev.model
            if !visible.contains(name) { continue }
            let cellKey = key + "\u{1f}" + name
            let cell = cells[cellKey] ?? (0, 0, 0)
            cells[cellKey] = (cell.0 + ev.tokens, cell.1 + costCents(ev), cell.2 + 1)
        }

        let multiDay = hourly && keys[0].prefix(10) != keys[keys.count - 1].prefix(10)
        var buckets: [ChartBucket] = []
        buckets.reserveCapacity(keys.count)
        for key in keys {
            var slices: [ChartSlice] = []
            var tokens = 0
            var cents = 0.0
            var count = 0
            for name in visible {
                let cellKey = key + "\u{1f}" + name
                guard let cell = cells[cellKey] else { continue }
                if cell.0 <= 0 && cell.1 <= 0 && cell.2 <= 0 { continue }
                slices.append(ChartSlice(model: name, tokens: cell.0, cents: cell.1, count: cell.2))
                tokens += cell.0
                cents += cell.1
                count += cell.2
            }
            buckets.append(ChartBucket(
                key: key,
                label: bucketLabel(key, hourly: hourly, multiDay: multiDay),
                tokens: tokens,
                cents: cents,
                count: count,
                slices: slices
            ))
        }
        return UsageChartSeries(
            hourly: hourly,
            caption: chartCaption(hourly: hourly, keys: keys),
            models: models,
            buckets: buckets
        )
    }

    static func floorHourMs(_ timestampMs: Int64) -> Int64 {
        max(0, timestampMs) / msHour * msHour
    }

    static func floorDayMs(_ timestampMs: Int64) -> Int64 {
        max(0, timestampMs) / msDay * msDay
    }

    static func chartModels(_ events: [UsageEvent]) -> [String] {
        var totals: [String: (Int, Double, Int)] = [:]
        for ev in events {
            let name = ev.model.isEmpty ? "—" : ev.model
            let row = totals[name] ?? (0, 0, 0)
            totals[name] = (row.0 + ev.tokens, row.1 + costCents(ev), row.2 + 1)
        }
        return totals.keys.sorted { lhs, rhs in
            let a = totals[lhs]!, b = totals[rhs]!
            if a.0 != b.0 { return a.0 > b.0 }
            if a.1 != b.1 { return a.1 > b.1 }
            if a.2 != b.2 { return a.2 > b.2 }
            return lhs < rhs
        }
    }

    static func bucketLabel(_ key: String, hourly: Bool, multiDay: Bool) -> String {
        if !hourly {
            return key.count >= 10 ? String(key.dropFirst(5)) : key
        }
        let hour: String
        if key.count >= 13 {
            let start = key.index(key.startIndex, offsetBy: 11)
            let end = key.index(start, offsetBy: 2)
            hour = String(key[start..<end])
        } else {
            hour = key
        }
        if multiDay {
            let mdStart = key.index(key.startIndex, offsetBy: 5)
            let mdEnd = key.index(mdStart, offsetBy: 5)
            return "\(key[mdStart..<mdEnd]) \(hour)"
        }
        return hour
    }

    static func chartCaption(hourly: Bool, keys: [String]) -> String {
        if hourly {
            if keys.isEmpty { return "按小时 Token（UTC）" }
            let first = keys[0], last = keys[keys.count - 1]
            if first == last { return "按小时 Token（UTC · \(first)）" }
            if first.prefix(10) == last.prefix(10) {
                return "按小时 Token（UTC · \(first.prefix(10)) \(first.dropFirst(11))–\(last.dropFirst(11))）"
            }
            return "按小时 Token（UTC · \(first) 至 \(last)）"
        }
        if keys.isEmpty { return "按日 Token（UTC）" }
        if keys[0] == keys[keys.count - 1] { return "按日 Token（UTC · \(keys[0])）" }
        return "按日 Token（UTC · \(keys[0]) 至 \(keys[keys.count - 1])）"
    }

    public static func parsePage(_ payload: JSONValue) -> (events: [UsageEvent], totalCount: Int) {
        var rows = payload["usageEventsDisplay"].array
        if rows.isEmpty { rows = payload["usageEvents"].array }
        let events = rows.compactMap(parseEvent)
        var total = payload["totalUsageEventsCount"].asInt()
        if total == nil {
            let paging = payload["pagination"]
            total = paging["numEvents"].asInt() ?? paging["totalNumEvents"].asInt() ?? paging["total"].asInt()
        }
        if total == nil || (total ?? 0) < events.count { total = events.count }
        return (events, total ?? events.count)
    }

    public static func parseEvent(_ item: JSONValue) -> UsageEvent? {
        guard item.isObject else { return nil }
        guard let ts = int64(item["timestamp"]) ?? int64(item["timestampMs"]) ?? int64(item["createdAt"]), ts > 0 else {
            return nil
        }
        let tokenUsage = item["tokenUsage"].isObject ? item["tokenUsage"] : JSONValue([:])
        let model = displayModel(item["model"].asString() ?? item["modelIntent"].asString() ?? "")
        let kindRaw = item["kind"].asString() ?? item["type"].asString() ?? ""
        let costsRaw = item["usageBasedCosts"].asString() ?? item["cost"].asString() ?? ""
        let isChargeable = item["isChargeable"].asBool()
        let kind = classifyKind(kindRaw, usageBasedCosts: costsRaw, isChargeable: isChargeable)
        let input = max(0, tokenUsage["inputTokens"].asInt() ?? item["inputTokens"].asInt() ?? 0)
        let output = max(0, tokenUsage["outputTokens"].asInt() ?? item["outputTokens"].asInt() ?? 0)
        let cacheWrite = max(0, tokenUsage["cacheWriteTokens"].asInt() ?? item["cacheWriteTokens"].asInt() ?? 0)
        let cacheRead = max(0, tokenUsage["cacheReadTokens"].asInt() ?? item["cacheReadTokens"].asInt() ?? 0)
        var tokens = sumTokens(tokenUsage)
        if tokens <= 0 { tokens = sumTokens(item) }
        if tokens <= 0 { tokens = input + output + cacheWrite + cacheRead }
        let charged = item["chargedCents"].asDouble() ?? parseMoneyCents(item["usageBasedCosts"])
        let totalCents = tokenUsage["totalCents"].asDouble() ?? item["totalCents"].asDouble()
        var email = (item["email"].asString() ?? item["userEmail"].asString() ?? item["user"].asString() ?? "").trimmingCharacters(in: .whitespaces)
        if email.isEmpty, item["user"].isObject {
            email = (item["user"]["email"].asString() ?? "").trimmingCharacters(in: .whitespaces)
        }
        let owning = (item["owningUser"].asString() ?? item["userId"].asString() ?? "").trimmingCharacters(in: .whitespaces)
        let givenId = (item["id"].asString() ?? item["eventId"].asString() ?? "").trimmingCharacters(in: .whitespaces)
        let id = givenId.isEmpty
            ? [String(ts), owning, model, String(input), String(output), String(cacheWrite), String(cacheRead), kindRaw].joined(separator: "|")
            : givenId
        return UsageEvent(
            id: id,
            timestampMs: ts,
            model: model,
            kind: kind,
            userEmail: email,
            owningUser: owning,
            tokens: max(0, tokens),
            inputTokens: input,
            outputTokens: output,
            cacheWriteTokens: cacheWrite,
            cacheReadTokens: cacheRead,
            chargedCents: charged,
            totalCents: totalCents,
            isHeadless: item["isHeadless"].asBool() || item["isCloudAgent"].asBool(),
            isChargeable: isChargeable
        )
    }

    public static func parseMoneyCents(_ value: JSONValue) -> Double? {
        if let n = value.asDouble(), value.asString() == nil { return n }
        let text = (value.asString() ?? "").trimmingCharacters(in: .whitespaces)
        if text.isEmpty { return nil }
        let lower = text.lowercased()
        if ["included", "free", "n/a", "—", "-", "none"].contains(lower) { return nil }
        if !lower.contains("us$") && !text.contains("$") { return nil }
        var cleaned = text.replacingOccurrences(of: "US$", with: "", options: .caseInsensitive)
        cleaned = cleaned.replacingOccurrences(of: "$", with: "")
        cleaned = cleaned.replacingOccurrences(of: ",", with: "")
        cleaned = cleaned.replacingOccurrences(of: "Included", with: "", options: .caseInsensitive)
        cleaned = cleaned.replacingOccurrences(of: "Free", with: "", options: .caseInsensitive)
        cleaned = cleaned.trimmingCharacters(in: .whitespaces)
        guard let dollars = Double(cleaned) else { return nil }
        return dollars * 100.0
    }

    public static func buildReport(_ events: [UsageEvent], filter: UsageReportFilter = UsageReportFilter()) -> UsageReport {
        let kind = filter.kind.trimmingCharacters(in: .whitespaces).lowercased()
        let model = filter.model.trimmingCharacters(in: .whitespaces)
        let owning = filter.owningUser.trimmingCharacters(in: .whitespaces)
        let selected = events.filter { ev in
            if !kind.isEmpty && ev.kind != kind { return false }
            if !model.isEmpty && ev.model != model { return false }
            if let h = filter.headless, ev.isHeadless != h { return false }
            if !owning.isEmpty && ev.owningUser != owning { return false }
            return true
        }.sorted { $0.timestampMs > $1.timestampMs }

        var dailyMap: [String: (Int, Double, Int)] = [:]
        var modelMap: [String: (Int, Double, Int, Int)] = [:]
        var included = 0, free = 0, onDemand = 0, other = 0, headless = 0
        var totalTokens = 0
        var totalCents = 0.0
        var hasCost = false
        for ev in selected {
            let cents = costCents(ev)
            totalTokens += ev.tokens
            totalCents += cents
            if cents > 0 { hasCost = true }
            switch ev.kind {
            case kindIncluded: included += 1
            case kindFree: free += 1
            case kindOnDemand: onDemand += 1
            default: other += 1
            }
            if ev.isHeadless { headless += 1 }
            let day = dateUtc(ev.timestampMs)
            let d = dailyMap[day] ?? (0, 0, 0)
            dailyMap[day] = (d.0 + ev.tokens, d.1 + cents, d.2 + 1)
            let name = ev.model.isEmpty ? "—" : ev.model
            let m = modelMap[name] ?? (0, 0, 0, 0)
            modelMap[name] = (m.0 + ev.tokens, m.1 + cents, m.2 + 1, m.3 + (ev.isHeadless ? 1 : 0))
        }
        let daily = dailyMap.keys.sorted().map { key in
            let v = dailyMap[key]!
            return DailyUsageRow(date: key, tokens: v.0, cents: v.1, count: v.2)
        }
        let models = modelMap.map { key, v in
            ModelUsageRow(name: key, tokens: v.0, cents: v.1, count: v.2, headlessCount: v.3)
        }.sorted { lhs, rhs in
            if lhs.tokens != rhs.tokens { return lhs.tokens > rhs.tokens }
            if lhs.cents != rhs.cents { return lhs.cents > rhs.cents }
            return lhs.count > rhs.count
        }
        return UsageReport(
            eventCount: selected.count,
            totalTokens: totalTokens,
            totalCents: totalCents,
            hasCost: hasCost,
            includedCount: included,
            freeCount: free,
            onDemandCount: onDemand,
            otherCount: other,
            headlessCount: headless,
            daily: daily,
            models: models,
            events: selected
        )
    }

    public static func toCSV(_ events: [UsageEvent]) -> String {
        var lines = ["\u{FEFF}\(csvHeader)"]
        for ev in events {
            let cols = [
                escapeCSV(formatTime(ev.timestampMs)),
                escapeCSV(ev.userEmail),
                escapeCSV(kindLabel(ev.kind)),
                escapeCSV(ev.model),
                escapeCSV(String(ev.tokens)),
                escapeCSV(formatCost(ev)),
                escapeCSV(ev.isHeadless ? "是" : "否"),
            ]
            lines.append(cols.joined(separator: ","))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    public static func fromDict(_ raw: [String: Any]) -> UsageEvent? {
        guard let ts = number64(raw["timestamp_ms"]) else { return nil }
        return UsageEvent(
            id: str(raw["id"]),
            timestampMs: ts,
            model: str(raw["model"]),
            kind: str(raw["kind"]).isEmpty ? kindOther : str(raw["kind"]),
            userEmail: str(raw["user_email"]),
            owningUser: str(raw["owning_user"]),
            tokens: max(0, intVal(raw["tokens"])),
            inputTokens: max(0, intVal(raw["input_tokens"])),
            outputTokens: max(0, intVal(raw["output_tokens"])),
            cacheWriteTokens: max(0, intVal(raw["cache_write_tokens"])),
            cacheReadTokens: max(0, intVal(raw["cache_read_tokens"])),
            chargedCents: number(raw["charged_cents"]),
            totalCents: number(raw["total_cents"]),
            isHeadless: boolVal(raw["is_headless"]),
            isChargeable: boolVal(raw["is_chargeable"])
        )
    }

    public static func merge(_ existing: [UsageEvent], incoming: [UsageEvent]) -> [UsageEvent] {
        var byId: [String: UsageEvent] = [:]
        for ev in existing where !ev.id.isEmpty { byId[ev.id] = ev }
        for ev in incoming where !ev.id.isEmpty { byId[ev.id] = ev }
        return byId.values.sorted { $0.timestampMs > $1.timestampMs }
    }

    public static func prune(_ events: [UsageEvent], minTimestampMs: Int64) -> [UsageEvent] {
        events.filter { $0.timestampMs >= minTimestampMs }.sorted { $0.timestampMs > $1.timestampMs }
    }

    public static func load(accountId: String, teamScope: Bool, directory: URL? = nil) -> [UsageEvent] {
        let path = AppPaths.usageEventsPath(accountId: accountId, teamScope: teamScope, in: directory)
        guard let text = try? String(contentsOf: path, encoding: .utf8) else { return [] }
        var events: [UsageEvent] = []
        for line in text.split(whereSeparator: \.isNewline) {
            let t = line.trimmingCharacters(in: .whitespaces)
            guard !t.isEmpty, let data = t.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let ev = fromDict(obj)
            else { continue }
            events.append(ev)
        }
        return merge(events, incoming: [])
    }

    public static func save(_ events: [UsageEvent], accountId: String, teamScope: Bool, directory: URL? = nil) {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        let path = AppPaths.usageEventsPath(accountId: accountId, teamScope: teamScope, in: dir)
        let lines = events.compactMap { serialize($0) }
        let text = lines.isEmpty ? "" : lines.joined(separator: "\n") + "\n"
        try? text.write(to: path, atomically: true, encoding: .utf8)
    }

    public static func sync(
        client: CursorClient,
        token: String,
        accountId: String,
        usage: UsageSnapshot?,
        teamScope: Bool,
        directory: URL? = nil
    ) async throws -> UsageEventsSyncResult {
        let existing = load(accountId: accountId, teamScope: teamScope, directory: directory)
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        var cycleStart = Int64(UsageParser.isoToMs(usage?.billingCycleStart) ?? Int(nowMs - 30 * 86_400 * 1000))
        var cycleEnd = Int64(UsageParser.isoToMs(usage?.billingCycleEnd) ?? Int(nowMs))
        if cycleEnd > nowMs { cycleEnd = nowMs }
        let watermark = existing.map(\.timestampMs).max() ?? 0
        var startMs = cycleStart
        var stopAt: Int64?
        if watermark > 0 {
            startMs = max(cycleStart, watermark - 60_000)
            stopAt = watermark
        }
        let rawTeam = usage.map { UsageParser.teamId(from: $0.raw) } ?? -1
        let teamId: Int? = rawTeam > 0 ? rawTeam : nil
        var userId: Int?
        if !teamScope {
            var uid = usage.map { UsageParser.userId(from: $0.raw) } ?? -1
            if uid <= 0 {
                var counts: [Int: Int] = [:]
                for ev in existing {
                    if let n = Int(ev.owningUser), n > 0 { counts[n, default: 0] += 1 }
                }
                uid = counts.max(by: { $0.value < $1.value })?.key ?? 0
            }
            if uid > 0 { userId = uid }
        }
        let fetched = try await client.fetchUsageEvents(
            sessionToken: token,
            startMs: startMs,
            endMs: cycleEnd,
            teamId: teamId,
            userId: teamScope ? nil : userId,
            stopAtMs: stopAt
        )
        var merged = merge(existing, incoming: fetched.events)
        if !teamScope, let userId {
            let uidText = String(userId)
            merged = merged.filter { $0.owningUser.isEmpty || $0.owningUser == uidText }
        }
        let minTs = min(cycleStart, nowMs - 120 * 86_400 * 1000)
        let pruned = prune(merged, minTimestampMs: minTs)
        save(pruned, accountId: accountId, teamScope: teamScope, directory: directory)
        return UsageEventsSyncResult(events: pruned, fetched: fetched.events.count, totalAvailable: fetched.totalCount, truncated: fetched.truncated)
    }

    static func sumTokens(_ item: JSONValue) -> Int {
        let keys = [
            "inputTokens", "outputTokens", "cacheWriteTokens", "cacheReadTokens",
            "totalInputTokens", "totalOutputTokens", "totalCacheWriteTokens", "totalCacheReadTokens",
        ]
        var total = 0
        var found = false
        for key in keys {
            if let n = item[key].asInt() {
                found = true
                total += max(0, n)
            }
        }
        if found { return total }
        if let n = item["totalTokens"].asInt() { return max(0, n) }
        return 0
    }

    static func displayModel(_ raw: String) -> String {
        let name = raw.trimmingCharacters(in: .whitespaces)
        if name.isEmpty { return "" }
        return name == "default" ? "auto" : name
    }

    static func escapeCSV(_ value: String) -> String {
        if value.contains(where: { $0 == "," || $0 == "\"" || $0 == "\n" || $0 == "\r" }) {
            return "\"" + value.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        return value
    }

    static func int64(_ value: JSONValue) -> Int64? {
        guard let n = value.asDouble() else { return nil }
        return Int64(n.rounded())
    }

    static func serialize(_ ev: UsageEvent) -> String? {
        var obj: [String: Any] = [
            "id": ev.id,
            "timestamp_ms": NSNumber(value: ev.timestampMs),
            "model": ev.model,
            "kind": ev.kind,
            "user_email": ev.userEmail,
            "owning_user": ev.owningUser,
            "tokens": ev.tokens,
            "input_tokens": ev.inputTokens,
            "output_tokens": ev.outputTokens,
            "cache_write_tokens": ev.cacheWriteTokens,
            "cache_read_tokens": ev.cacheReadTokens,
            "is_headless": ev.isHeadless,
            "is_chargeable": ev.isChargeable,
        ]
        if let v = ev.chargedCents { obj["charged_cents"] = v } else { obj["charged_cents"] = NSNull() }
        if let v = ev.totalCents { obj["total_cents"] = v } else { obj["total_cents"] = NSNull() }
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let line = String(data: data, encoding: .utf8)
        else { return nil }
        return line
    }

    static func str(_ value: Any?) -> String {
        if value == nil || value is NSNull { return "" }
        return value as? String ?? ""
    }

    static func number(_ value: Any?) -> Double? {
        if value == nil || value is NSNull { return nil }
        if let n = value as? NSNumber { return n.doubleValue }
        if let s = value as? String { return Double(s) }
        return nil
    }

    static func number64(_ value: Any?) -> Int64? {
        guard let n = number(value) else { return nil }
        return Int64(n.rounded())
    }

    static func intVal(_ value: Any?) -> Int {
        number(value).map { Int($0.rounded()) } ?? 0
    }

    static func boolVal(_ value: Any?) -> Bool {
        if let b = value as? Bool { return b }
        if let n = value as? NSNumber { return n.boolValue }
        return false
    }
}
