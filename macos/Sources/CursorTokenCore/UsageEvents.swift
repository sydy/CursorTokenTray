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
    public var allocatedCny: Double

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
        isChargeable: Bool = false,
        allocatedCny: Double = 0
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
        self.allocatedCny = allocatedCny
    }
}

public struct DailyUsageRow: Equatable, Sendable {
    public var date: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
    public var cny: Double

    public init(date: String, tokens: Int, cents: Double, count: Int, cny: Double = 0) {
        self.date = date
        self.tokens = tokens
        self.cents = cents
        self.count = count
        self.cny = cny
    }
}

public struct ModelUsageRow: Equatable, Sendable {
    public var name: String
    public var tokens: Int
    public var cents: Double
    public var count: Int
    public var headlessCount: Int
    public var cny: Double

    public init(name: String, tokens: Int, cents: Double, count: Int, headlessCount: Int, cny: Double = 0) {
        self.name = name
        self.tokens = tokens
        self.cents = cents
        self.count = count
        self.headlessCount = headlessCount
        self.cny = cny
    }
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
    public var category: String
    public var model: String
    public var headless: Bool?
    public var owningUser: String

    public init(kind: String = "", category: String = "", model: String = "", headless: Bool? = nil, owningUser: String = "") {
        self.kind = kind
        self.category = category
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
    public var firstPartyCount: Int = 0
    public var apiCount: Int = 0
    public var grokBotCount: Int = 0
    public var daily: [DailyUsageRow]
    public var models: [ModelUsageRow]
    public var events: [UsageEvent]
    public var totalCny: Double = 0
    public var planCny: Double = 0
    public var onDemandCny: Double = 0
    public var usdCnyRate: Double = 0
    public var monthlyPlanUsd: Double = 0
    public var actualCny: Double = 0
    public var usesActualCny: Bool = false
}

public struct CnySpendSettings: Equatable, Sendable {
    public var monthlyPlanUsd: Double
    public var usdCnyRate: Double
    public var membershipType: String
    public var actualCny: Double

    public init(monthlyPlanUsd: Double = 0, usdCnyRate: Double = UsageEvents.defaultUsdCnyRate, membershipType: String = "", actualCny: Double = 0) {
        self.monthlyPlanUsd = monthlyPlanUsd
        self.usdCnyRate = usdCnyRate
        self.membershipType = membershipType
        self.actualCny = actualCny
    }
}

public struct AccountCompareCategory: Equatable, Sendable {
    public var category: String
    public var count: Int
    public var tokens: Int
    public var cny: Double

    public init(category: String, count: Int = 0, tokens: Int = 0, cny: Double = 0) {
        self.category = category
        self.count = count
        self.tokens = tokens
        self.cny = cny
    }

    public var cnyPerMillion: Double? { UsageEvents.unitCny(cny, tokens > 0 ? Double(tokens) / 1_000_000.0 : 0) }
    public var cnyPerRequest: Double? { UsageEvents.unitCny(cny, Double(count)) }
}

public struct AccountCompareInput: Sendable {
    public var accountId: String
    public var label: String
    public var channel: String
    public var membershipType: String
    public var accountKind: String
    public var tempStartAt: String
    public var tempValidDays: Int
    public var tempValidHours: Int
    public var billingCycleStart: String
    public var billingCycleEnd: String
    public var lastRemaining: Double?
    public var events: [UsageEvent]
    public var spend: CnySpendSettings?

    public init(
        accountId: String,
        label: String = "",
        channel: String = "",
        membershipType: String = "",
        accountKind: String = "long_term",
        tempStartAt: String = "",
        tempValidDays: Int = 0,
        tempValidHours: Int = 0,
        billingCycleStart: String = "",
        billingCycleEnd: String = "",
        lastRemaining: Double? = nil,
        events: [UsageEvent] = [],
        spend: CnySpendSettings? = nil
    ) {
        self.accountId = accountId
        self.label = label
        self.channel = channel
        self.membershipType = membershipType
        self.accountKind = accountKind
        self.tempStartAt = tempStartAt
        self.tempValidDays = tempValidDays
        self.tempValidHours = tempValidHours
        self.billingCycleStart = billingCycleStart
        self.billingCycleEnd = billingCycleEnd
        self.lastRemaining = lastRemaining
        self.events = events
        self.spend = spend
    }
}

public struct AccountCompareRow: Equatable, Sendable {
    public var accountId: String
    public var label: String
    public var channel: String
    public var membershipType: String
    public var windowSource: String
    public var windowStartMs: Int64
    public var windowEndMs: Int64
    public var windowDays: Double
    public var planCny: Double
    public var dailyHoldingCny: Double
    public var windowPlanCny: Double
    public var onDemandCny: Double
    public var totalCny: Double
    public var eventCount: Int
    public var totalTokens: Int
    public var firstParty: AccountCompareCategory
    public var api: AccountCompareCategory
    public var grokBot: AccountCompareCategory
    public var lastRemaining: Double?
    public var usesActualCny: Bool

    public var channelLabel: String { UsageEvents.channelLabel(channel) }
    public var windowLabel: String { UsageEvents.windowLabel(windowSource) }
    public var cnyPerMillion: Double? { UsageEvents.unitCny(totalCny, totalTokens > 0 ? Double(totalTokens) / 1_000_000.0 : 0) }
    public var cnyPerRequest: Double? { UsageEvents.unitCny(totalCny, Double(eventCount)) }
}

public struct AccountCompareGroup: Equatable, Sendable {
    public var channel: String
    public var rows: [AccountCompareRow]
    public var dailyHoldingCny: Double
    public var totalCny: Double
    public var eventCount: Int
    public var totalTokens: Int
    public var firstParty: AccountCompareCategory
    public var api: AccountCompareCategory
    public var grokBot: AccountCompareCategory

    public var channelLabel: String { UsageEvents.channelLabel(channel) }
    public var cnyPerMillion: Double? { UsageEvents.unitCny(totalCny, totalTokens > 0 ? Double(totalTokens) / 1_000_000.0 : 0) }
    public var cnyPerRequest: Double? { UsageEvents.unitCny(totalCny, Double(eventCount)) }
}

public struct AccountCompareReport: Equatable, Sendable {
    public var rows: [AccountCompareRow]
    public var groups: [AccountCompareGroup]
    public var holdingDays: Double

    public init(rows: [AccountCompareRow] = [], groups: [AccountCompareGroup] = [], holdingDays: Double = UsageEvents.holdingDays) {
        self.rows = rows
        self.groups = groups
        self.holdingDays = holdingDays
    }
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
    public static let categoryFirstParty = "first_party"
    public static let categoryAPI = "api"
    public static let categoryGrokBot = "grok_bot"
    public static let channelSelfPay = "self_pay"
    public static let channelThirdParty = "third_party"
    public static let holdingDays = 30.0
    public static let windowCycle = "cycle"
    public static let windowValidity = "validity"
    public static let windowFallback = "fallback"
    static let channelOrder = [channelSelfPay, channelThirdParty, ""]
    public static let tzLabel = "北京时间"
    public static let csvHeader = "日期(北京时间),用户,类型,模型,Token,费用,实付,云端Agent"
    public static let defaultUsdCnyRate = 7.50
    public static let hourlyChartWindowHours = 48
    static let msHour: Int64 = 3_600_000
    static let msDay: Int64 = 86_400_000
    static let msBeijingOffset: Int64 = 8 * msHour
    static let displayTimeZone = TimeZone(secondsFromGMT: 8 * 3600)!

    public static func kindLabel(_ kind: String?) -> String {
        switch (kind ?? "").trimmingCharacters(in: .whitespaces).lowercased() {
        case kindIncluded: return "套餐内"
        case kindFree: return "免费"
        case kindOnDemand: return "按需"
        default: return "其他"
        }
    }

    public static func classifyCategory(_ model: String?) -> String {
        UsageParser.usageCategory(model)
    }

    public static func categoryLabel(_ category: String?) -> String {
        switch (category ?? "").trimmingCharacters(in: .whitespaces).lowercased() {
        case categoryFirstParty: return "First-party"
        case categoryGrokBot: return "Grok Bot"
        default: return "API"
        }
    }

    public static func clampActualCny(_ amount: Double) -> Double {
        if amount.isNaN || amount.isInfinite || amount < 0 { return 0 }
        return min(1_000_000, amount)
    }

    public static func resolvePlanCny(_ spend: CnySpendSettings) -> (planCny: Double, monthly: Double, rate: Double, actual: Double, usesActual: Bool) {
        let rate = clampUsdCnyRate(spend.usdCnyRate)
        let monthly = resolveMonthlyPlanUsd(spend.monthlyPlanUsd, membership: spend.membershipType)
        let actual = clampActualCny(spend.actualCny)
        if actual > 0 { return (actual, monthly, rate, actual, true) }
        return (monthly * rate, monthly, rate, 0, false)
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

    public static func clampUsdCnyRate(_ rate: Double) -> Double {
        if rate.isNaN || rate.isInfinite { return defaultUsdCnyRate }
        return min(100, max(0.01, rate))
    }

    public static func clampMonthlyPlanUsd(_ usd: Double) -> Double {
        if usd.isNaN || usd.isInfinite || usd < 0 { return 0 }
        return min(10_000, usd)
    }

    public static func defaultMonthlyPlanUsd(_ membership: String?) -> Double {
        var key = (membership ?? "").trimmingCharacters(in: .whitespaces).lowercased()
            .replacingOccurrences(of: " ", with: "")
        if key.hasSuffix("套餐") {
            key = String(key.dropLast(2))
        }
        switch key {
        case "pro": return 20
        case "pro+", "pro_plus", "proplus": return 60
        case "ultra": return 200
        default: return 0
        }
    }

    public static func resolveMonthlyPlanUsd(_ monthlyPlanUsd: Double, membership: String? = nil) -> Double {
        let stored = clampMonthlyPlanUsd(monthlyPlanUsd)
        return stored > 0 ? stored : defaultMonthlyPlanUsd(membership)
    }

    public static func isPlanCovered(_ kind: String?) -> Bool {
        let key = (kind ?? "").trimmingCharacters(in: .whitespaces).lowercased()
        return key != kindOnDemand && key != kindFree
    }

    public static func sanitizeChannel(_ raw: String?) -> String {
        let key = (raw ?? "").trimmingCharacters(in: .whitespaces).lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "")
        if ["self_pay", "self", "selfpay", "自费"].contains(key) { return channelSelfPay }
        if ["third_party", "third", "thirdparty", "第三方"].contains(key) { return channelThirdParty }
        return ""
    }

    public static func channelLabel(_ channel: String?) -> String {
        switch sanitizeChannel(channel) {
        case channelSelfPay: return "自费"
        case channelThirdParty: return "第三方"
        default: return "未标"
        }
    }

    public static func windowLabel(_ source: String?) -> String {
        switch (source ?? "").trimmingCharacters(in: .whitespaces).lowercased() {
        case windowCycle: return "本周期"
        case windowValidity: return "有效期"
        default: return "近30天"
        }
    }

    public static func unitCny(_ amount: Double, _ denom: Double) -> Double? {
        if denom <= 1e-12 { return nil }
        return max(0, amount) / denom
    }

    public static func formatCnyUnit(_ amount: Double?, suffix: String) -> String {
        guard let amount else { return "—" }
        return formatCNY(amount) + suffix
    }

    public static func resolveCompareWindow(
        accountKind: String = "",
        tempStartAt: String = "",
        tempValidDays: Int = 0,
        tempValidHours: Int = 0,
        billingCycleStart: String = "",
        billingCycleEnd: String = "",
        nowMs: Int64? = nil
    ) -> (startMs: Int64, endMs: Int64, source: String) {
        let now = nowMs ?? Int64(Date().timeIntervalSince1970 * 1000)
        let kind = accountKind.trimmingCharacters(in: .whitespaces).lowercased().replacingOccurrences(of: "-", with: "_")
        if ["temporary", "temp", "short"].contains(kind) {
            if let start = UsageParser.isoToMs(tempStartAt).map({ Int64($0) }) {
                let end = tempEndMs(tempStartAt, days: tempValidDays, hours: tempValidHours) ?? now
                return (start, min(end, now), windowValidity)
            }
        }
        if let start = UsageParser.isoToMs(billingCycleStart).map({ Int64($0) }) {
            let end = UsageParser.isoToMs(billingCycleEnd).map({ Int64($0) }) ?? now
            return (start, min(end, now), windowCycle)
        }
        return (now - 30 * msDay, now, windowFallback)
    }

    static func tempEndMs(_ startAt: String, days: Int, hours: Int) -> Int64? {
        guard let iso = AccountValidity.computeEndIso(startAt: startAt, days: days, hours: hours) else { return nil }
        return UsageParser.isoToMs(iso).map { Int64($0) }
    }

    public static func compareWindowDays(_ startMs: Int64, _ endMs: Int64) -> Double {
        let span = max(0, endMs - startMs)
        return max(Double(span) / Double(msDay), 1.0 / 24.0)
    }

    public static func compareInput(from account: Account, events: [UsageEvent], monthlyPlanUsd: Double, usdCnyRate: Double) -> AccountCompareInput {
        AccountCompareInput(
            accountId: account.id,
            label: account.label,
            channel: account.channel,
            membershipType: account.membershipType,
            accountKind: account.accountKind,
            tempStartAt: account.tempStartAt,
            tempValidDays: account.tempValidDays,
            tempValidHours: account.tempValidHours,
            billingCycleStart: account.billingCycleStart,
            billingCycleEnd: account.billingCycleEnd,
            lastRemaining: account.lastRemaining,
            events: events,
            spend: CnySpendSettings(
                monthlyPlanUsd: monthlyPlanUsd,
                usdCnyRate: usdCnyRate,
                membershipType: account.membershipType,
                actualCny: account.actualCny
            )
        )
    }

    public static func buildAccountCompareRow(_ item: AccountCompareInput, nowMs: Int64? = nil) -> AccountCompareRow {
        let window = resolveCompareWindow(
            accountKind: item.accountKind,
            tempStartAt: item.tempStartAt,
            tempValidDays: item.tempValidDays,
            tempValidHours: item.tempValidHours,
            billingCycleStart: item.billingCycleStart,
            billingCycleEnd: item.billingCycleEnd,
            nowMs: nowMs
        )
        let windowDays = compareWindowDays(window.startMs, window.endMs)
        let windowEvents = item.events.filter { $0.timestampMs >= window.startMs && $0.timestampMs <= window.endMs }
        let spend = item.spend ?? CnySpendSettings()
        let resolved = resolvePlanCny(spend)
        let dailyHolding = resolved.planCny > 0 ? resolved.planCny / holdingDays : 0
        let windowPlan = dailyHolding * windowDays
        let included = windowEvents.filter { isPlanCovered($0.kind) }
        let includedCostSum = included.reduce(0.0) { $0 + costCents($1) }
        let includedCount = included.count
        var cats: [String: (Int, Int, Double)] = [
            categoryFirstParty: (0, 0, 0),
            categoryAPI: (0, 0, 0),
            categoryGrokBot: (0, 0, 0),
        ]
        var onDemandCny = 0.0
        var totalCny = 0.0
        var totalTokens = 0
        for ev in windowEvents {
            let amount = allocateEventCny(ev, includedCostSum: includedCostSum, includedCount: includedCount, planCny: windowPlan, rate: resolved.rate)
            totalCny += amount
            totalTokens += ev.tokens
            if ev.kind == kindOnDemand { onDemandCny += amount }
            let bucket = classifyCategory(ev.model)
            var row = cats[bucket] ?? (0, 0, 0)
            row.0 += 1
            row.1 += ev.tokens
            row.2 += amount
            cats[bucket] = row
        }
        func cat(_ name: String) -> AccountCompareCategory {
            let row = cats[name] ?? (0, 0, 0)
            return AccountCompareCategory(category: name, count: row.0, tokens: row.1, cny: row.2)
        }
        return AccountCompareRow(
            accountId: item.accountId,
            label: item.label.isEmpty ? item.accountId : item.label,
            channel: sanitizeChannel(item.channel),
            membershipType: item.membershipType,
            windowSource: window.source,
            windowStartMs: window.startMs,
            windowEndMs: window.endMs,
            windowDays: windowDays,
            planCny: resolved.planCny,
            dailyHoldingCny: dailyHolding,
            windowPlanCny: windowPlan,
            onDemandCny: onDemandCny,
            totalCny: totalCny,
            eventCount: windowEvents.count,
            totalTokens: totalTokens,
            firstParty: cat(categoryFirstParty),
            api: cat(categoryAPI),
            grokBot: cat(categoryGrokBot),
            lastRemaining: item.lastRemaining,
            usesActualCny: resolved.usesActual
        )
    }

    public static func buildAccountCompareReport(_ items: [AccountCompareInput], nowMs: Int64? = nil) -> AccountCompareReport {
        let rows = items.map { buildAccountCompareRow($0, nowMs: nowMs) }
        var grouped: [String: [AccountCompareRow]] = [:]
        for key in channelOrder { grouped[key] = [] }
        for row in rows {
            grouped[row.channel, default: []].append(row)
        }
        var groups: [AccountCompareGroup] = []
        for channel in channelOrder {
            let bucket = grouped[channel] ?? []
            if !bucket.isEmpty { groups.append(sumCompareGroup(channel, bucket)) }
        }
        return AccountCompareReport(rows: rows, groups: groups, holdingDays: holdingDays)
    }

    static func sumCompareGroup(_ channel: String, _ rows: [AccountCompareRow]) -> AccountCompareGroup {
        func add(_ name: String, _ parts: [AccountCompareCategory]) -> AccountCompareCategory {
            AccountCompareCategory(
                category: name,
                count: parts.reduce(0) { $0 + $1.count },
                tokens: parts.reduce(0) { $0 + $1.tokens },
                cny: parts.reduce(0) { $0 + $1.cny }
            )
        }
        return AccountCompareGroup(
            channel: channel,
            rows: rows,
            dailyHoldingCny: rows.reduce(0) { $0 + $1.dailyHoldingCny },
            totalCny: rows.reduce(0) { $0 + $1.totalCny },
            eventCount: rows.reduce(0) { $0 + $1.eventCount },
            totalTokens: rows.reduce(0) { $0 + $1.totalTokens },
            firstParty: add(categoryFirstParty, rows.map(\.firstParty)),
            api: add(categoryAPI, rows.map(\.api)),
            grokBot: add(categoryGrokBot, rows.map(\.grokBot))
        )
    }

    public static func accountCompareToCSV(_ report: AccountCompareReport) -> String {
        var lines = [
            "账号,渠道,套餐,窗口,窗口天数,日均持有,窗口实付,请求,Token,¥/百万Token,¥/次,First-party次数,First-party Token,First-party实付,First-party ¥/百万,First-party ¥/次,API次数,API Token,API实付,API ¥/百万,API ¥/次,Grok Bot次数,Grok Bot Token,Grok Bot实付,Grok Bot ¥/百万,Grok Bot ¥/次",
        ]
        for row in report.rows {
            lines.append(compareCSVCells(row.label, row.channelLabel, row.membershipType, row.windowLabel, row.windowDays, row))
        }
        for group in report.groups {
            lines.append(compareCSVCells("\(group.channelLabel)合计", group.channelLabel, "", "", 0, group))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    static func compareCSVCells(_ name: String, _ channel: String, _ membership: String, _ window: String, _ days: Double, _ row: AccountCompareRow) -> String {
        compareCSVCells(
            name, channel, membership, window, days,
            dailyHolding: row.dailyHoldingCny, totalCny: row.totalCny,
            eventCount: row.eventCount, totalTokens: row.totalTokens,
            perMillion: row.cnyPerMillion, perRequest: row.cnyPerRequest,
            firstParty: row.firstParty, api: row.api, grokBot: row.grokBot
        )
    }

    static func compareCSVCells(_ name: String, _ channel: String, _ membership: String, _ window: String, _ days: Double, _ group: AccountCompareGroup) -> String {
        compareCSVCells(
            name, channel, membership, window, days,
            dailyHolding: group.dailyHoldingCny, totalCny: group.totalCny,
            eventCount: group.eventCount, totalTokens: group.totalTokens,
            perMillion: group.cnyPerMillion, perRequest: group.cnyPerRequest,
            firstParty: group.firstParty, api: group.api, grokBot: group.grokBot
        )
    }

    static func compareCSVCells(
        _ name: String,
        _ channel: String,
        _ membership: String,
        _ window: String,
        _ days: Double,
        dailyHolding: Double,
        totalCny: Double,
        eventCount: Int,
        totalTokens: Int,
        perMillion: Double?,
        perRequest: Double?,
        firstParty: AccountCompareCategory,
        api: AccountCompareCategory,
        grokBot: AccountCompareCategory
    ) -> String {
        func catCells(_ cat: AccountCompareCategory) -> [String] {
            [
                String(cat.count),
                String(cat.tokens),
                String(format: "%.4f", cat.cny),
                cat.cnyPerMillion.map { String(format: "%.4f", $0) } ?? "",
                cat.cnyPerRequest.map { String(format: "%.4f", $0) } ?? "",
            ]
        }
        var cols = [
            escapeCSV(name),
            escapeCSV(channel),
            escapeCSV(membership),
            escapeCSV(window),
            days > 0 ? String(format: "%.2f", days) : "",
            String(format: "%.4f", dailyHolding),
            String(format: "%.4f", totalCny),
            String(eventCount),
            String(totalTokens),
            perMillion.map { String(format: "%.4f", $0) } ?? "",
            perRequest.map { String(format: "%.4f", $0) } ?? "",
        ]
        cols.append(contentsOf: catCells(firstParty))
        cols.append(contentsOf: catCells(api))
        cols.append(contentsOf: catCells(grokBot))
        return cols.joined(separator: ",")
    }

    public static func formatCNY(_ yuan: Double?) -> String {
        guard let yuan else { return "—" }
        let n = max(0, yuan)
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.minimumFractionDigits = 2
        f.maximumFractionDigits = 2
        f.numberStyle = .decimal
        return "¥" + (f.string(from: NSNumber(value: n)) ?? "0.00")
    }

    public static func formatEventCny(_ ev: UsageEvent, amount: Double? = nil) -> String {
        if ev.kind == kindFree { return "—" }
        return formatCNY(amount ?? ev.allocatedCny)
    }

    public static func allocateEventCny(
        _ ev: UsageEvent,
        includedCostSum: Double,
        includedCount: Int,
        planCny: Double,
        rate: Double
    ) -> Double {
        if ev.kind == kindFree { return 0 }
        if ev.kind == kindOnDemand { return costCents(ev) / 100.0 * rate }
        let cents = costCents(ev)
        if includedCostSum > 1e-9 { return planCny * (cents / includedCostSum) }
        if includedCount > 0 && planCny > 0 { return planCny / Double(includedCount) }
        return 0
    }

    static func cnyById(_ events: [UsageEvent], spend: CnySpendSettings?) -> (byId: [String: Double], planCny: Double, onDemandCny: Double, monthly: Double, rate: Double, actual: Double, usesActual: Bool) {
        guard let spend else { return ([:], 0, 0, 0, 0, 0, false) }
        let resolved = resolvePlanCny(spend)
        let included = events.filter { isPlanCovered($0.kind) }
        let includedCostSum = included.reduce(0.0) { $0 + costCents($1) }
        let includedCount = included.count
        var byId: [String: Double] = [:]
        var onDemandCny = 0.0
        for (i, ev) in events.enumerated() {
            let amount = allocateEventCny(ev, includedCostSum: includedCostSum, includedCount: includedCount, planCny: resolved.planCny, rate: resolved.rate)
            let key = ev.id.isEmpty ? "#\(i)" : ev.id
            byId[key] = amount
            if ev.kind == kindOnDemand { onDemandCny += amount }
        }
        return (byId, resolved.planCny, onDemandCny, resolved.monthly, resolved.rate, resolved.actual, resolved.usesActual)
    }

    public static func formatTime(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(max(0, timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = displayTimeZone
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.string(from: dt)
    }

    public static func eventDate(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(max(0, timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = displayTimeZone
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: dt)
    }

    public static func eventHour(_ timestampMs: Int64) -> String {
        let dt = Date(timeIntervalSince1970: Double(floorHourMs(timestampMs)) / 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = displayTimeZone
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
        let visibleSet = Set(visible)
        if events.isEmpty {
            return UsageChartSeries(hourly: hourly, caption: chartCaption(hourly: hourly, keys: []), models: models, buckets: [])
        }

        let keys: [String]
        let keyOf: (Int64) -> String
        if hourly {
            let lastMs = floorHourMs(events.map(\.timestampMs).max() ?? 0)
            var firstMs = floorHourMs(events.map(\.timestampMs).min() ?? 0)
            let window = Int64(max(1, hourlyWindowHours))
            let span = (lastMs - firstMs) / msHour + 1
            if span > window { firstMs = lastMs - (window - 1) * msHour }
            let count = Int((lastMs - firstMs) / msHour + 1)
            keys = (0..<count).map { eventHour(firstMs + Int64($0) * msHour) }
            keyOf = eventHour
        } else {
            let lastMs = floorDayMs(events.map(\.timestampMs).max() ?? 0)
            let firstMs = floorDayMs(events.map(\.timestampMs).min() ?? 0)
            let count = Int((lastMs - firstMs) / msDay + 1)
            keys = (0..<count).map { eventDate(firstMs + Int64($0) * msDay) }
            keyOf = eventDate
        }

        var cells: [String: (Int, Double, Int)] = [:]
        for ev in events {
            let key = keyOf(ev.timestampMs)
            if key < keys[0] || key > keys[keys.count - 1] { continue }
            let name = ev.model.isEmpty ? "—" : ev.model
            if !visibleSet.contains(name) { continue }
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
        let shifted = max(0, timestampMs) + msBeijingOffset
        return shifted / msDay * msDay - msBeijingOffset
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
        let kind = hourly ? "按小时 Token" : "按日 Token"
        if keys.isEmpty { return "\(kind)（\(tzLabel)）" }
        let first = keys[0], last = keys[keys.count - 1]
        if first == last { return "\(kind)（\(tzLabel) · \(first)）" }
        if hourly && first.prefix(10) == last.prefix(10) {
            return "\(kind)（\(tzLabel) · \(first.prefix(10)) \(first.dropFirst(11))–\(last.dropFirst(11))）"
        }
        return "\(kind)（\(tzLabel) · \(first) 至 \(last)）"
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

    public static func buildReport(_ events: [UsageEvent], filter: UsageReportFilter = UsageReportFilter(), spend: CnySpendSettings? = nil) -> UsageReport {
        let kind = filter.kind.trimmingCharacters(in: .whitespaces).lowercased()
        let category = filter.category.trimmingCharacters(in: .whitespaces).lowercased()
        let model = filter.model.trimmingCharacters(in: .whitespaces)
        let owning = filter.owningUser.trimmingCharacters(in: .whitespaces)
        let allocated = cnyById(events, spend: spend)
        var selected: [UsageEvent] = []
        for (i, ev) in events.enumerated() {
            if !kind.isEmpty && ev.kind != kind { continue }
            if !category.isEmpty && classifyCategory(ev.model) != category { continue }
            if !model.isEmpty && ev.model != model { continue }
            if let h = filter.headless, ev.isHeadless != h { continue }
            if !owning.isEmpty && ev.owningUser != owning { continue }
            var copy = ev
            let key = ev.id.isEmpty ? "#\(i)" : ev.id
            copy.allocatedCny = allocated.byId[key] ?? 0
            selected.append(copy)
        }
        selected.sort { $0.timestampMs > $1.timestampMs }

        var dailyMap: [String: (Int, Double, Int, Double)] = [:]
        var modelMap: [String: (Int, Double, Int, Int, Double)] = [:]
        var included = 0, free = 0, onDemand = 0, other = 0, headless = 0
        var firstParty = 0, api = 0, grokBot = 0
        var totalTokens = 0
        var totalCents = 0.0
        var totalCny = 0.0
        var hasCost = false
        for ev in selected {
            let cents = costCents(ev)
            totalTokens += ev.tokens
            totalCents += cents
            totalCny += ev.allocatedCny
            if cents > 0 { hasCost = true }
            switch ev.kind {
            case kindIncluded: included += 1
            case kindFree: free += 1
            case kindOnDemand: onDemand += 1
            default: other += 1
            }
            switch classifyCategory(ev.model) {
            case categoryGrokBot: grokBot += 1
            case categoryFirstParty: firstParty += 1
            default: api += 1
            }
            if ev.isHeadless { headless += 1 }
            let day = eventDate(ev.timestampMs)
            let d = dailyMap[day] ?? (0, 0, 0, 0)
            dailyMap[day] = (d.0 + ev.tokens, d.1 + cents, d.2 + 1, d.3 + ev.allocatedCny)
            let name = ev.model.isEmpty ? "—" : ev.model
            let m = modelMap[name] ?? (0, 0, 0, 0, 0)
            modelMap[name] = (m.0 + ev.tokens, m.1 + cents, m.2 + 1, m.3 + (ev.isHeadless ? 1 : 0), m.4 + ev.allocatedCny)
        }
        let daily = dailyMap.keys.sorted().map { key in
            let v = dailyMap[key]!
            return DailyUsageRow(date: key, tokens: v.0, cents: v.1, count: v.2, cny: v.3)
        }
        let models = modelMap.map { key, v in
            ModelUsageRow(name: key, tokens: v.0, cents: v.1, count: v.2, headlessCount: v.3, cny: v.4)
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
            firstPartyCount: firstParty,
            apiCount: api,
            grokBotCount: grokBot,
            daily: daily,
            models: models,
            events: selected,
            totalCny: totalCny,
            planCny: allocated.planCny,
            onDemandCny: allocated.onDemandCny,
            usdCnyRate: allocated.rate,
            monthlyPlanUsd: allocated.monthly,
            actualCny: allocated.actual,
            usesActualCny: allocated.usesActual
        )
    }

    public static func toCSV(_ events: [UsageEvent], spend: CnySpendSettings? = nil, allocationBase: [UsageEvent]? = nil) -> String {
        let allocated = spend == nil ? (byId: [String: Double](), planCny: 0.0, onDemandCny: 0.0, monthly: 0.0, rate: 0.0, actual: 0.0, usesActual: false) : cnyById(allocationBase ?? events, spend: spend)
        var lines = ["\u{FEFF}\(csvHeader)"]
        for (i, ev) in events.enumerated() {
            let cnyText: String
            if spend != nil {
                let key = ev.id.isEmpty ? "#\(i)" : ev.id
                cnyText = formatEventCny(ev, amount: allocated.byId[key] ?? 0)
            } else if ev.allocatedCny > 0 {
                cnyText = formatEventCny(ev)
            } else {
                cnyText = "—"
            }
            let cols = [
                escapeCSV(formatTime(ev.timestampMs)),
                escapeCSV(ev.userEmail),
                escapeCSV(kindLabel(ev.kind)),
                escapeCSV(ev.model),
                escapeCSV(String(ev.tokens)),
                escapeCSV(formatCost(ev)),
                escapeCSV(cnyText),
                escapeCSV(ev.isHeadless ? "是" : "否"),
            ]
            lines.append(cols.joined(separator: ","))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    public static func fromDict(_ raw: [String: Any]) -> UsageEvent? {
        let ts: Int64?
        if let n = number64(raw["timestamp_ms"]) ?? number64(raw["timestampMs"]) {
            ts = n
        } else if let iso = raw["timestamp"] as? String, !iso.isEmpty {
            ts = UsageParser.isoToMs(iso).map { Int64($0) }
        } else {
            ts = number64(raw["timestamp"])
        }
        guard let ts else { return nil }
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
            chargedCents: number(raw["charged_cents"] ?? raw["chargedCents"]),
            totalCents: number(raw["total_cents"] ?? raw["totalCents"]),
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
            else if rawTeam > 0 {
                // Team feed without userId is the whole org; do not pollute the personal cache.
                return UsageEventsSyncResult(events: existing, fetched: 0, totalAvailable: existing.count, truncated: false)
            }
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
