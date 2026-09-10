import Foundation

public enum AccountValidity {
    public static let longTerm = "long_term"
    public static let temporary = "temporary"
    public static let maxDays = 999
    public static let maxHours = 23

    public static func sanitizeKind(_ raw: String?) -> String {
        let key = (raw ?? "").trimmingCharacters(in: .whitespaces).lowercased().replacingOccurrences(of: "-", with: "_")
        if key == "temporary" || key == "temp" || key == "short" { return temporary }
        return longTerm
    }

    public static func clampDays(_ raw: Any?) -> Int { clampInt(raw, lo: 0, hi: maxDays) }
    public static func clampHours(_ raw: Any?) -> Int { clampInt(raw, lo: 0, hi: maxHours) }

    public static func isTemporary(_ account: Account?) -> Bool {
        guard let account else { return false }
        return sanitizeKind(account.accountKind) == temporary
    }

    public static func computeEndIso(startAt: String?, days: Int, hours: Int) -> String? {
        guard let start = AccountSync.parseIso(startAt) else { return nil }
        let d = clampDays(days)
        let h = clampHours(hours)
        if d == 0 && h == 0 { return nil }
        let end = start.addingTimeInterval(TimeInterval(d * 86_400 + h * 3_600))
        return AccountSync.nowIso(end)
    }

    public static func accountEndIso(_ account: Account?) -> String? {
        guard isTemporary(account), let account else { return nil }
        return computeEndIso(startAt: account.tempStartAt, days: account.tempValidDays, hours: account.tempValidHours)
    }

    public static func applyEndOverride(_ snap: inout UsageSnapshot, account: Account?, now: Date = Date()) {
        guard let end = accountEndIso(account) else { return }
        snap.billingCycleEnd = end
        snap.daysRemaining = UsageParser.daysUntil(end, now: now)
        snap.billingCycleEndOverridden = true
    }

    static func clampInt(_ raw: Any?, lo: Int, hi: Int) -> Int {
        let n: Int
        if let i = raw as? Int { n = i }
        else if let d = raw as? Double { n = Int(d) }
        else if let s = raw as? String, let v = Int(s) { n = v }
        else if let n0 = raw as? NSNumber { n = n0.intValue }
        else { return 0 }
        return min(hi, max(lo, n))
    }
}
