import Foundation

public let cursorBaseURL = "https://cursor.com"
public let usageEndpoints = ["/api/usage-summary", "/api/dashboard/usage-summary"]
public let aggregatedUsageEndpoint = "/api/dashboard/get-aggregated-usage-events"
public let filteredUsageEndpoint = "/api/dashboard/get-filtered-usage-events"
public let sandUsageEndpoint = "/api/dashboard/get-sand-usage-status"
public let sandUsageTimeout: TimeInterval = 8
public let usageEventsPageSize = 100
public let usageEventsMaxPages = 50
public let usageURL = "https://cursor.com/dashboard/usage"
public let spendingURL = "https://cursor.com/dashboard/spending"
public let billingURL = "https://cursor.com/dashboard/billing"

public let cursorModelTier = 2

private let teamMemberships: Set<String> = [
    "enterprise", "enterprise_trial", "team", "teams", "business",
]
private let membershipLabels: [String: String] = [
    "pro": "Pro",
    "pro_plus": "Pro+",
    "pro+": "Pro+",
    "ultra": "Ultra",
    "free": "Free",
    "hobby": "Hobby",
    "enterprise": "Enterprise",
    "enterprise_trial": "Enterprise",
    "team": "Team",
    "teams": "Team",
    "business": "Business",
    "unpaid": "Free",
]
private let modelNameAliases: [String: String] = ["default": "auto"]

public struct ModelTokenUsage: Equatable, Sendable {
    public var name: String
    public var tokens: Int
    public var cents: Double
    public var tier: Int
    public var usagePercent: Double?

    public init(name: String, tokens: Int, cents: Double, tier: Int, usagePercent: Double? = nil) {
        self.name = name
        self.tokens = tokens
        self.cents = cents
        self.tier = tier
        self.usagePercent = usagePercent
    }

    public var isCursorModel: Bool { tier == cursorModelTier }
    public var isGrokBot: Bool { UsageParser.isGrokBotModel(name) }
}

public struct UsageSnapshot: Equatable {
    public var usedPercent: Double
    public var remainingPercent: Double
    public var autoPercentUsed: Double?
    public var apiPercentUsed: Double?
    public var totalPercentUsed: Double?
    public var membershipType: String
    public var billingCycleStart: String?
    public var billingCycleEnd: String?
    public var daysRemaining: Int?
    public var daysElapsed: Double?
    public var estimatedUsableDays: Double?
    public var raw: JSONValue
    public var totalTokens: Int?
    public var modelUsages: [ModelTokenUsage]
    public var billingMode: String
    public var usedCents: Double?
    public var limitCents: Double?
    public var remainingCents: Double?
    public var onDemandUsedCents: Double?
    public var onDemandLimitCents: Double?
    public var pooledUsedCents: Double?
    public var pooledLimitCents: Double?
    public var limitType: String
    public var isUnlimited: Bool
    public var billingCycleEndOverridden: Bool
    public var grokBotPercentUsed: Double?
    public var grokBotRemainingPercent: Double?
    public var grokBotPeriodStart: String?
    public var grokBotResetAt: String?
    public var grokBotDaysRemaining: Int?

    public init(
        usedPercent: Double,
        remainingPercent: Double,
        autoPercentUsed: Double? = nil,
        apiPercentUsed: Double? = nil,
        totalPercentUsed: Double? = nil,
        membershipType: String = "",
        billingCycleStart: String? = nil,
        billingCycleEnd: String? = nil,
        daysRemaining: Int? = nil,
        daysElapsed: Double? = nil,
        estimatedUsableDays: Double? = nil,
        raw: JSONValue = .null,
        totalTokens: Int? = nil,
        modelUsages: [ModelTokenUsage] = [],
        billingMode: String = "percent",
        usedCents: Double? = nil,
        limitCents: Double? = nil,
        remainingCents: Double? = nil,
        onDemandUsedCents: Double? = nil,
        onDemandLimitCents: Double? = nil,
        pooledUsedCents: Double? = nil,
        pooledLimitCents: Double? = nil,
        limitType: String = "",
        isUnlimited: Bool = false,
        billingCycleEndOverridden: Bool = false,
        grokBotPercentUsed: Double? = nil,
        grokBotRemainingPercent: Double? = nil,
        grokBotPeriodStart: String? = nil,
        grokBotResetAt: String? = nil,
        grokBotDaysRemaining: Int? = nil
    ) {
        self.usedPercent = usedPercent
        self.remainingPercent = remainingPercent
        self.autoPercentUsed = autoPercentUsed
        self.apiPercentUsed = apiPercentUsed
        self.totalPercentUsed = totalPercentUsed
        self.membershipType = membershipType
        self.billingCycleStart = billingCycleStart
        self.billingCycleEnd = billingCycleEnd
        self.daysRemaining = daysRemaining
        self.daysElapsed = daysElapsed
        self.estimatedUsableDays = estimatedUsableDays
        self.raw = raw
        self.totalTokens = totalTokens
        self.modelUsages = modelUsages
        self.billingMode = billingMode
        self.usedCents = usedCents
        self.limitCents = limitCents
        self.remainingCents = remainingCents
        self.onDemandUsedCents = onDemandUsedCents
        self.onDemandLimitCents = onDemandLimitCents
        self.pooledUsedCents = pooledUsedCents
        self.pooledLimitCents = pooledLimitCents
        self.limitType = limitType
        self.isUnlimited = isUnlimited
        self.billingCycleEndOverridden = billingCycleEndOverridden
        self.grokBotPercentUsed = grokBotPercentUsed
        self.grokBotRemainingPercent = grokBotRemainingPercent
        self.grokBotPeriodStart = grokBotPeriodStart
        self.grokBotResetAt = grokBotResetAt
        self.grokBotDaysRemaining = grokBotDaysRemaining
    }

    public var isTeamAccount: Bool {
        UsageParser.isTeamMembership(membershipType, limitType: limitType)
    }

    public var showsAmount: Bool {
        guard usedCents != nil, let limit = limitCents, limit > 0 else { return false }
        return billingMode == "amount" || isTeamAccount
    }

    public var showsGrokBot: Bool { grokBotPercentUsed != nil }

    public var dashboardURL: String {
        UsageParser.dashboardURL(for: self)
    }
}

public struct GrokBotUsage: Equatable, Sendable {
    public var percentUsed: Double
    public var remainingPercent: Double
    public var periodStart: String?
    public var resetAt: String?
    public var daysRemaining: Int?

    public init(
        percentUsed: Double,
        remainingPercent: Double,
        periodStart: String? = nil,
        resetAt: String? = nil,
        daysRemaining: Int? = nil
    ) {
        self.percentUsed = percentUsed
        self.remainingPercent = remainingPercent
        self.periodStart = periodStart
        self.resetAt = resetAt
        self.daysRemaining = daysRemaining
    }
}

extension UsageSnapshot {
    public static func == (lhs: UsageSnapshot, rhs: UsageSnapshot) -> Bool {
        lhs.usedPercent == rhs.usedPercent
            && lhs.remainingPercent == rhs.remainingPercent
            && lhs.autoPercentUsed == rhs.autoPercentUsed
            && lhs.apiPercentUsed == rhs.apiPercentUsed
            && lhs.membershipType == rhs.membershipType
            && lhs.billingMode == rhs.billingMode
            && lhs.usedCents == rhs.usedCents
            && lhs.limitCents == rhs.limitCents
            && lhs.isUnlimited == rhs.isUnlimited
    }
}

public enum UsageParser {
    public static func formatMembershipType(_ raw: String?) -> String {
        let key = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if key.isEmpty { return "未知" }
        return membershipLabels[key.lowercased()] ?? key
    }

    public static func isTeamMembership(_ membership: String?, limitType: String? = nil) -> Bool {
        if (limitType ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "team" {
            return true
        }
        return teamMemberships.contains((membership ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    public static func dashboardURL(for usage: UsageSnapshot? = nil, membership: String = "", limitType: String = "") -> String {
        var memb = membership
        var limit = limitType
        if let usage {
            memb = usage.membershipType
            limit = usage.limitType
        }
        return isTeamMembership(memb, limitType: limit) ? usageURL : billingURL
    }

    public static func dashboardMenuLabel(_ usage: UsageSnapshot? = nil, membership: String = "", limitType: String = "") -> String {
        var memb = membership
        var limit = limitType
        if let usage {
            memb = usage.membershipType
            limit = usage.limitType
        }
        return isTeamMembership(memb, limitType: limit) ? "打开用量" : "打开用量账单"
    }

    public static func dashboardButtonLabel(_ usage: UsageSnapshot? = nil, membership: String = "", limitType: String = "") -> String {
        var memb = membership
        var limit = limitType
        if let usage {
            memb = usage.membershipType
            limit = usage.limitType
        }
        return isTeamMembership(memb, limitType: limit) ? "用量" : "账单"
    }

    public static func dashboardLinkLabel(_ usage: UsageSnapshot?) -> String {
        if let usage, usage.isTeamAccount { return "查看用量 →" }
        return "查看用量账单 →"
    }

    public static func formatUSDCents(_ cents: Double?) -> String {
        guard let cents else { return "—" }
        var dollars = cents / 100.0
        if dollars < 0 { dollars = 0 }
        if abs(dollars - dollars.rounded()) < 0.005 {
            return "$\(Int(dollars.rounded()))"
        }
        return String(format: "$%.2f", dollars)
    }

    public static func formatSpendRange(used: Double?, limit: Double?) -> String {
        "\(formatUSDCents(used)) / \(formatUSDCents(limit))"
    }

    public static func isGrokBotModel(_ name: String?) -> Bool {
        let key = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return key.hasPrefix("grok-bot-") || key.hasPrefix("sand-")
    }

    public static func isFirstPartyModel(_ name: String?) -> Bool {
        let key = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if key.isEmpty || isGrokBotModel(key) { return false }
        return key == "auto" || key == "default" || key.hasPrefix("cursor-") || key.hasPrefix("composer-")
    }

    public static func usageCategory(_ name: String?) -> String {
        if isGrokBotModel(name) { return "grok_bot" }
        if isFirstPartyModel(name) { return "first_party" }
        return "api"
    }

    public static func applySandUsage(_ snapshot: inout UsageSnapshot, _ payload: JSONValue, now: Date = Date()) {
        guard let parsed = parseSandUsageStatus(payload, now: now) else { return }
        snapshot.grokBotPercentUsed = parsed.percentUsed
        snapshot.grokBotRemainingPercent = parsed.remainingPercent
        snapshot.grokBotPeriodStart = parsed.periodStart
        snapshot.grokBotResetAt = parsed.resetAt
        snapshot.grokBotDaysRemaining = parsed.daysRemaining
    }

    public static func parseSandUsageStatus(_ payload: JSONValue, now: Date = Date()) -> GrokBotUsage? {
        guard payload.isObject, !payload.isEmpty else { return nil }
        if optBool(payload, "usesPooledEnterpriseAllowance", "uses_pooled_enterprise_allowance") == true { return nil }
        if optBool(payload, "includedLimitZero", "included_limit_zero") == true { return nil }
        if optBool(payload, "hasNonZeroIncludedLimit", "has_non_zero_included_limit") != true { return nil }
        guard let percent = firstPresent(payload, "usagePercent", "usage_percent").asDouble() else { return nil }
        let used = clampPercent(percent)
        let start = timestampToIso(firstPresent(payload, "currentPeriodStart", "current_period_start"))
        let reset = timestampToIso(firstPresent(payload, "nextResetTimestampUtc", "next_reset_timestamp_utc"))
        return GrokBotUsage(
            percentUsed: round1(used),
            remainingPercent: round1(100.0 - used),
            periodStart: start,
            resetAt: reset,
            daysRemaining: reset.flatMap { daysUntil($0, now: now) }
        )
    }

    public static func formatTokenCount(_ count: Double?) -> String {
        guard let count else { return "—" }
        var n = Int(count.rounded())
        n = max(0, n)
        if n >= 100_000_000 { return String(format: "%.1f亿", Double(n) / 100_000_000.0) }
        if n >= 10_000 { return String(format: "%.1f万", Double(n) / 10_000.0) }
        return String(n)
    }

    public static func parseUsageSummary(_ payload: JSONValue, now: Date = Date()) -> UsageSnapshot {
        let individual = object(payload["individualUsage"])
        let team = object(payload["teamUsage"])
        let plan = object(individual["plan"])
        let overall = object(individual["overall"])
        let pooled = object(team["pooled"])
        let individualOD = object(individual["onDemand"])
        let teamOD = object(team["onDemand"])

        var auto = plan["autoPercentUsed"].asDouble()
        var api = plan["apiPercentUsed"].asDouble()
        let total = plan["totalPercentUsed"].asDouble()
        if auto == nil {
            auto = percentFromDisplayMessage(payload["autoModelSelectedDisplayMessage"].asString())
        }
        if api == nil {
            api = percentFromDisplayMessage(payload["namedModelSelectedDisplayMessage"].asString())
        }

        let membership = formatMembershipType(
            payload["membershipType"].asString() ?? payload["plan"].asString() ?? ""
        )
        let limitType = (payload["limitType"].asString() ?? "").trimmingCharacters(in: .whitespaces)
        let isUnlimited = payload["isUnlimited"].asBool()

        let planMeter = spendMeter(plan)
        let planMeterBreakdown = spendMeter(plan, allowBreakdown: true)
        let overallMeter = spendMeter(overall)
        let pooledMeter = spendMeter(pooled)
        var odBlock = onDemandEnabled(individualOD) ? individualOD : teamOD
        if !onDemandEnabled(odBlock) && onDemandEnabled(teamOD) {
            odBlock = teamOD
        }
        let odMeter = onDemandEnabled(odBlock) ? spendMeter(odBlock) : nil

        var billingMode = "percent"
        var usedCents: Double?
        var limitCents: Double?
        var remainingCents: Double?
        var usedPercent: Double?

        if isUnlimited {
            usedPercent = 0
        } else {
            // Team usage page "Your monthly usage $X / $Y" comes from overall/pooled/plan cents.
            // plan.totalPercentUsed is a separate cached metric and can freeze at 0% or 100%.
            if isTeamMembership(membership, limitType: limitType) {
                for meter in [overallMeter, pooledMeter, planMeter] {
                    guard let applied = percentFromSpendMeter(meter) else { continue }
                    usedCents = applied.used
                    limitCents = applied.limit
                    remainingCents = applied.remaining
                    usedPercent = applied.percent
                    billingMode = "amount"
                    break
                }
            }
            if usedPercent == nil {
                if let total {
                    usedPercent = total
                    if let meter = meterWithLimit(planMeter) ?? meterWithLimit(overallMeter) {
                        usedCents = meter.0
                        limitCents = meter.1
                        remainingCents = meter.2
                    }
                } else if auto != nil || api != nil {
                    usedPercent = [auto, api].compactMap { $0 }.max()
                    if let meter = meterWithLimit(planMeter) ?? meterWithLimit(overallMeter) {
                        usedCents = meter.0
                        limitCents = meter.1
                        remainingCents = meter.2
                    }
                } else {
                    var pickedSource = ""
                    let candidates: [(Meter?, String)] = [
                        (overallMeter, "overall"),
                        (planMeter, "plan"),
                        (planMeterBreakdown, "plan"),
                        (pooledMeter, "pooled"),
                        (odMeter, "on_demand"),
                    ]
                    for (meter, source) in candidates {
                        guard let applied = percentFromSpendMeter(meter) else { continue }
                        usedCents = applied.used
                        limitCents = applied.limit
                        remainingCents = applied.remaining
                        usedPercent = applied.percent
                        pickedSource = source
                        break
                    }
                    if usedPercent == nil {
                        usedPercent = 0
                    } else if ["overall", "pooled", "on_demand"].contains(pickedSource)
                        || isTeamMembership(membership, limitType: limitType)
                    {
                        billingMode = "amount"
                    } else {
                        usedCents = nil
                        limitCents = nil
                        remainingCents = nil
                        billingMode = "percent"
                    }
                }
            }
        }

        if usedCents == nil {
            if let fallback = meterWithLimit(overallMeter) ?? meterWithLimit(pooledMeter) {
                usedCents = fallback.0
                limitCents = fallback.1
                remainingCents = fallback.2
            }
        }

        let used = clampPercent(usedPercent ?? 0)
        let remaining = clampPercent(100.0 - used)
        if remainingCents == nil, let u = usedCents, let l = limitCents {
            remainingCents = max(0, l - u)
        }

        let cycleStart = payload["billingCycleStart"].asString() ?? payload["startOfMonth"].asString()
        let cycleEnd = payload["billingCycleEnd"].asString()
        let daysRemaining = daysUntil(cycleEnd, now: now)
        let daysElapsed = daysSince(cycleStart, now: now)
        let estimated = estimateUsableDays(usedPercent: used, remainingPercent: remaining, daysElapsed: daysElapsed)

        var pooledUsed: Double?
        var pooledLimit: Double?
        if let pooledMeter {
            pooledUsed = pooledMeter.0
            pooledLimit = pooledMeter.1
        }
        var odUsed: Double?
        var odLimit: Double?
        if let odMeter {
            odUsed = odMeter.0
            odLimit = odMeter.1
        }

        return UsageSnapshot(
            usedPercent: round1(used),
            remainingPercent: round1(remaining),
            autoPercentUsed: auto.map(round1),
            apiPercentUsed: api.map(round1),
            totalPercentUsed: total.map(round1),
            membershipType: membership,
            billingCycleStart: isoOrNone(cycleStart),
            billingCycleEnd: isoOrNone(cycleEnd),
            daysRemaining: daysRemaining,
            daysElapsed: daysElapsed.map { round2($0) },
            estimatedUsableDays: estimated,
            raw: payload,
            billingMode: billingMode,
            usedCents: usedCents,
            limitCents: limitCents,
            remainingCents: remainingCents,
            onDemandUsedCents: odUsed,
            onDemandLimitCents: odLimit,
            pooledUsedCents: pooledUsed,
            pooledLimitCents: pooledLimit,
            limitType: limitType,
            isUnlimited: isUnlimited
        )
    }

    public static func parseAggregatedUsage(
        _ payload: JSONValue,
        autoPercent: Double? = nil,
        apiPercent: Double? = nil
    ) -> (models: [ModelTokenUsage], total: Int) {
        var rows: [ModelTokenUsage] = []
        for item in payload["aggregations"].array {
            let name = displayModelName(item["modelIntent"].asString() ?? item["model"].asString() ?? "")
            if name.isEmpty { continue }
            let tokens = sumTokenFields(item)
            if tokens <= 0 { continue }
            let cents = item["totalCents"].asDouble() ?? 0
            let tier = modelTier(name, item["tier"])
            rows.append(ModelTokenUsage(name: name, tokens: tokens, cents: cents, tier: tier))
        }
        if rows.isEmpty {
            let total = sumTokenFields(payload)
            return ([], total > 0 ? total : 0)
        }
        var grokRows = allocateUsagePercents(rows.filter(\.isGrokBot), categoryPercent: nil)
        var cursorRows = allocateUsagePercents(rows.filter { $0.isCursorModel && !$0.isGrokBot }, categoryPercent: autoPercent)
        var otherRows = allocateUsagePercents(rows.filter { !$0.isCursorModel && !$0.isGrokBot }, categoryPercent: apiPercent)
        cursorRows.sort { ($0.usagePercent ?? 0, $0.tokens) > ($1.usagePercent ?? 0, $1.tokens) }
        otherRows.sort { ($0.usagePercent ?? 0, $0.tokens) > ($1.usagePercent ?? 0, $1.tokens) }
        grokRows.sort { $0.tokens > $1.tokens }
        let allocated = cursorRows + otherRows + grokRows
        var total = allocated.reduce(0) { $0 + $1.tokens }
        let headerTotal = sumTokenFields(payload)
        if headerTotal > total { total = headerTotal }
        return (allocated, total)
    }

    typealias Meter = (Double, Double, Double?)

    static func firstPresent(_ obj: JSONValue, _ keys: String...) -> JSONValue {
        for key in keys where obj.object[key] != nil {
            return obj[key]
        }
        return .null
    }

    static func optBool(_ obj: JSONValue, _ keys: String...) -> Bool? {
        for key in keys where obj.object[key] != nil {
            return obj[key].asBool()
        }
        return nil
    }

    public static func timestampToIso(_ value: JSONValue) -> String? {
        if let raw = value.asString()?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty {
            if raw.contains("T") || raw.hasSuffix("Z") {
                return parseISO(raw) == nil ? nil : raw
            }
        }
        guard let num = value.asDouble() else { return nil }
        let seconds = abs(num) > 10_000_000_000 ? num / 1000.0 : num
        let dt = Date(timeIntervalSince1970: seconds)
        let ms = Int((seconds.truncatingRemainder(dividingBy: 1)) * 1000.0)
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        if abs(seconds - seconds.rounded()) < 0.0005 || ms == 0 {
            f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        } else {
            f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
        }
        return f.string(from: dt)
    }

    static func object(_ value: JSONValue) -> JSONValue {
        value.isObject ? value : JSONValue([:])
    }

    static func onDemandEnabled(_ block: JSONValue) -> Bool {
        if !block.isObject || block.isEmpty { return false }
        if block.object["enabled"] != nil { return block["enabled"].asBool() }
        return spendMeter(block) != nil
    }

    static func spendMeter(_ block: JSONValue, allowBreakdown: Bool = false) -> Meter? {
        if !block.isObject || block.isEmpty { return nil }
        var used = block["used"].asDouble()
        var limit = block["limit"].asDouble()
        let remaining = block["remaining"].asDouble()
        if (limit == nil || (limit ?? 0) <= 0) && allowBreakdown {
            limit = object(block["breakdown"])["total"].asDouble()
        }
        if used == nil, let remaining, let limit {
            used = max(0, limit - remaining)
        }
        guard let used, let limit else { return nil }
        return (used, limit, remaining)
    }

    static func meterWithLimit(_ meter: Meter?) -> Meter? {
        guard let meter, meter.1 > 0 else { return nil }
        return meter
    }

    struct SpendPercent {
        var used: Double
        var limit: Double
        var remaining: Double?
        var percent: Double
    }

    static func percentFromSpendMeter(_ meter: Meter?) -> SpendPercent? {
        guard let picked = meterWithLimit(meter) else { return nil }
        return SpendPercent(
            used: picked.0,
            limit: picked.1,
            remaining: picked.2,
            percent: clampPercent(picked.0 / picked.1 * 100.0)
        )
    }

    static func percentFromDisplayMessage(_ message: String?) -> Double? {
        let text = message ?? ""
        guard let idx = text.firstIndex(of: "%"), idx > text.startIndex else { return nil }
        let before = String(text[..<idx])
        var start = before.startIndex
        for i in before.indices {
            let ch = before[i]
            if ch.isNumber || ch == "." { continue }
            start = before.index(after: i)
        }
        let raw = String(before[start...]).trimmingCharacters(in: .whitespaces)
        guard !raw.isEmpty, let value = Double(raw) else { return nil }
        return clampPercent(value)
    }

    public static func teamId(from payload: JSONValue) -> Int {
        for key in ["teamId", "owningTeam"] {
            if let n = payload[key].asInt(), n > 0 { return n }
        }
        let team = object(payload["teamUsage"])
        if let n = (team["teamId"].asInt() ?? team["id"].asInt()), n > 0 { return n }
        return -1
    }

    public static func userId(from payload: JSONValue) -> Int {
        for key in ["userId", "numericUserId", "currentUserId"] {
            if let n = payload[key].asInt(), n > 0 { return n }
        }
        let individual = object(payload["individualUsage"])
        if let n = (individual["userId"].asInt() ?? individual["id"].asInt()), n > 0 { return n }
        return -1
    }

    public static func isoToMs(_ iso: String?) -> Int? {
        guard let dt = parseISO(iso) else { return nil }
        return Int(dt.timeIntervalSince1970 * 1000)
    }

    static func sumTokenFields(_ item: JSONValue) -> Int {
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

    static func displayModelName(_ raw: String) -> String {
        let name = raw.trimmingCharacters(in: .whitespaces)
        if name.isEmpty { return "" }
        return modelNameAliases[name] ?? name
    }

    static func modelTier(_ name: String, _ tier: JSONValue) -> Int {
        if let t = tier.asInt() { return t }
        return isFirstPartyModel(name) ? cursorModelTier : 1
    }

    static func allocateUsagePercents(_ models: [ModelTokenUsage], categoryPercent: Double?) -> [ModelTokenUsage] {
        if models.isEmpty { return [] }
        let centsSum = models.reduce(0.0) { $0 + $1.cents }
        let tokensSum = models.reduce(0) { $0 + $1.tokens }
        return models.map { model in
            var share = 0.0
            if centsSum > 1e-6 {
                share = model.cents / centsSum
            } else if tokensSum > 0 {
                share = Double(model.tokens) / Double(tokensSum)
            }
            let pct = categoryPercent.map { round1(share * $0) }
            return ModelTokenUsage(name: model.name, tokens: model.tokens, cents: model.cents, tier: model.tier, usagePercent: pct)
        }
    }

    static func isoOrNone(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value
    }

    static func parseISO(_ iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        let text = iso.replacingOccurrences(of: "Z", with: "+00:00")
        let f1 = ISO8601DateFormatter()
        f1.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f1.date(from: text) ?? f1.date(from: iso) { return d }
        let f2 = ISO8601DateFormatter()
        f2.formatOptions = [.withInternetDateTime]
        if let d = f2.date(from: text) ?? f2.date(from: iso) { return d }
        let f3 = DateFormatter()
        f3.locale = Locale(identifier: "en_US_POSIX")
        f3.timeZone = TimeZone(secondsFromGMT: 0)
        f3.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSXXXXX"
        if let d = f3.date(from: text) { return d }
        f3.dateFormat = "yyyy-MM-dd'T'HH:mm:ssXXXXX"
        return f3.date(from: text)
    }

    public static func daysUntil(_ iso: String?, now: Date) -> Int? {
        guard let end = parseISO(iso) else { return nil }
        let delta = end.timeIntervalSince(now)
        return max(0, Int(delta / 86_400.0))
    }

    static func daysSince(_ iso: String?, now: Date) -> Double? {
        guard let start = parseISO(iso) else { return nil }
        let hours = now.timeIntervalSince(start) / 3600.0
        if hours < 0 { return 0 }
        return hours / 24.0
    }

    public static func estimateUsableDays(usedPercent: Double, remainingPercent: Double, daysElapsed: Double?) -> Double? {
        guard let daysElapsed else { return nil }
        if remainingPercent <= 0 { return 0 }
        if daysElapsed < 0.04 { return nil }
        if usedPercent < 0.2 { return nil }
        let burn = usedPercent / daysElapsed
        if burn <= 1e-6 { return nil }
        return round1(remainingPercent / burn)
    }
}
