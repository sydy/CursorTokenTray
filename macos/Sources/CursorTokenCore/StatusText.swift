import Foundation

public enum StatusText {
    public static func formatSummary(
        _ usage: UsageSnapshot?,
        errorMessage: String?,
        updatedAt: String?,
        accountLabel: String? = nil
    ) -> String {
        if let errorMessage {
            return "状态: \(errorMessage) | 更新 \(updatedAt ?? "—")"
        }
        guard let usage else { return "状态: 等待刷新…" }
        let auto = usage.autoPercentUsed.map { String(format: "%.1f%%", $0) } ?? "—"
        let api = usage.apiPercentUsed.map { String(format: "%.1f%%", $0) } ?? "—"
        let est = formatEstimatedDays(usage)
        var tokens = ""
        if let total = usage.totalTokens, total > 0 {
            tokens = "消耗 \(UsageParser.formatTokenCount(Double(total))) Token | "
        }
        var spend = ""
        if usage.showsAmount {
            spend = "金额 \(UsageParser.formatSpendRange(used: usage.usedCents, limit: usage.limitCents)) | "
        }
        var plan = formatPlanCaption(usage.membershipType, accountLabel: accountLabel)
        if usage.isUnlimited { plan += " · 不限量" }
        return "剩余 \(String(format: "%.1f", usage.remainingPercent))% | \(plan) | \(spend)\(tokens)First-party \(auto) | API \(api) | 预计可用 \(est) | 更新 \(updatedAt ?? "—")"
    }

    public static func formatEstimatedDays(_ usage: UsageSnapshot) -> String {
        guard let est = usage.estimatedUsableDays else {
            if usage.usedPercent < 0.2 { return "用量过低，暂无法估算" }
            if let elapsed = usage.daysElapsed, elapsed < 0.04 { return "周期刚开始，统计中" }
            return "暂无法估算"
        }
        var text: String
        if est <= 0 {
            text = "已耗尽"
        } else if est < 1 {
            text = "约 \(max(1, Int(est * 24))) 小时"
        } else {
            text = String(format: "约 %.1f 天", est).replacingOccurrences(of: ".0 天", with: " 天")
        }
        if let resetLeft = usage.daysRemaining, est > 0 {
            if est >= Double(resetLeft) {
                text += "  ·  可撑过本周期"
            } else {
                text += "  ·  可能提前耗尽"
            }
        }
        return text
    }

    public static func statusPillText(_ remaining: Double?, error: Bool = false) -> String {
        if error { return "异常" }
        guard let remaining else { return "等待刷新" }
        if remaining <= 0 { return "已耗尽" }
        if remaining < 20 { return "额度紧张" }
        if remaining < 50 { return "略偏低" }
        return "状态良好"
    }

    public static func formatPlanCaption(_ membership: String?, accountLabel: String? = nil) -> String {
        let raw = (membership ?? "").trimmingCharacters(in: .whitespaces)
        var name: String
        if raw.isEmpty {
            name = "—"
        } else {
            name = UsageParser.formatMembershipType(raw)
            if !name.contains("套餐") { name = "\(name) 套餐" }
        }
        let label = (accountLabel ?? "").trimmingCharacters(in: .whitespaces)
        let known: Set<String> = [
            name.lowercased(),
            raw.lowercased(),
            UsageParser.formatMembershipType(raw).lowercased(),
        ]
        if !label.isEmpty, !known.contains(label.lowercased()) {
            if name == "—" { return label }
            return "\(label) · \(name)"
        }
        return name
    }

    public static func formatEstimateCaption(_ usage: UsageSnapshot) -> String {
        let text = formatEstimatedDays(usage)
        if text.contains("可撑过本周期") { return "预计可撑过本周期" }
        if text.contains("提前耗尽") { return "预计可能提前耗尽" }
        if text == "已耗尽" { return "额度已耗尽" }
        return text
    }

    public static func formatResetDate(_ isoValue: String) -> String {
        let text = isoValue.replacingOccurrences(of: "Z", with: "+00:00")
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var dt = f.date(from: text)
        if dt == nil {
            let f2 = ISO8601DateFormatter()
            f2.formatOptions = [.withInternetDateTime]
            dt = f2.date(from: text) ?? f2.date(from: isoValue)
        }
        guard let dt else { return isoValue }
        let cal = Calendar(identifier: .gregorian)
        let m = cal.component(.month, from: dt)
        let d = cal.component(.day, from: dt)
        return "\(m)月\(d)日"
    }

    public static func buildStatusLines(
        _ usage: UsageSnapshot?,
        errorMessage: String?,
        updatedAt: String? = nil,
        accountLabel: String? = nil
    ) -> [(String, String)] {
        if let errorMessage { return [("状态", errorMessage)] }
        guard let usage else { return [("状态", "等待刷新…")] }

        var rows: [(String, String)] = []
        if usage.isUnlimited {
            rows.append(("剩余", "不限量"))
        } else if usage.showsAmount {
            rows.append((
                "剩余",
                String(format: "%.1f%%（%@）", usage.remainingPercent, UsageParser.formatSpendRange(used: usage.usedCents, limit: usage.limitCents))
            ))
        } else {
            rows.append(("剩余", String(format: "%.1f%%（已用 %.1f%%）", usage.remainingPercent, usage.usedPercent)))
        }
        let label = (accountLabel ?? "").trimmingCharacters(in: .whitespaces)
        let memb = usage.membershipType.isEmpty ? "" : UsageParser.formatMembershipType(usage.membershipType)
        if !label.isEmpty, label.lowercased() != memb.lowercased() {
            rows.append(("账号", label))
        }
        var plan = memb.isEmpty ? "—" : memb
        if usage.isUnlimited { plan += " · 不限量" }
        rows.append(("计划", plan))
        if usage.showsAmount {
            rows.append(("金额", UsageParser.formatSpendRange(used: usage.usedCents, limit: usage.limitCents)))
        }
        if let pu = usage.pooledUsedCents, let pl = usage.pooledLimitCents, pl > 0,
           usage.usedCents != pu || usage.limitCents != pl
        {
            rows.append(("团队额度", UsageParser.formatSpendRange(used: pu, limit: pl)))
        }
        if let ou = usage.onDemandUsedCents, let ol = usage.onDemandLimitCents, ol > 0,
           usage.usedCents != ou || usage.limitCents != ol
        {
            rows.append(("按需用量", UsageParser.formatSpendRange(used: ou, limit: ol)))
        }
        if let tokens = usage.totalTokens, tokens > 0 {
            rows.append(("消耗 Token", UsageParser.formatTokenCount(Double(tokens))))
        }
        if usage.autoPercentUsed != nil || usage.apiPercentUsed != nil {
            let auto = usage.autoPercentUsed.map { String(format: "%.1f%%", $0) } ?? "—"
            let api = usage.apiPercentUsed.map { String(format: "%.1f%%", $0) } ?? "—"
            rows.append(("明细", "First-party \(auto) · API \(api)"))
        }
        if let end = usage.billingCycleEnd {
            let endText = formatResetDate(end)
            if let days = usage.daysRemaining {
                rows.append(("重置", "\(endText)（还剩 \(days) 天）"))
            } else {
                rows.append(("重置", endText))
            }
            rows.append(("预计可用", formatEstimatedDays(usage)))
        } else if usage.estimatedUsableDays != nil {
            rows.append(("预计可用", formatEstimatedDays(usage)))
        }
        let stamp = updatedAt ?? {
            let f = DateFormatter()
            f.dateFormat = "HH:mm:ss"
            return f.string(from: Date())
        }()
        rows.append(("更新", stamp))
        return rows
    }
}
