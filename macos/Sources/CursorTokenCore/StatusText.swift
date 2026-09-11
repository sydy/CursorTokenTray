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
        var grok = ""
        if usage.showsGrokBot, let left = usage.grokBotRemainingPercent {
            grok = String(format: " | Grok Bot 剩余 %.1f%%", left)
        }
        return "剩余 \(String(format: "%.1f", usage.remainingPercent))% | \(plan) | \(spend)\(tokens)First-party \(auto) | API \(api)\(grok) | 预计可用 \(est) | 更新 \(updatedAt ?? "—")"
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

    public static func formatResetDate(_ isoValue: String, includeTime: Bool = false) -> String {
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
        let cal = Calendar.current
        let m = cal.component(.month, from: dt)
        let d = cal.component(.day, from: dt)
        var label = "\(m)月\(d)日"
        if includeTime {
            let hour = cal.component(.hour, from: dt)
            let minute = cal.component(.minute, from: dt)
            if hour != 0 || minute != 0 {
                label += String(format: " %02d:%02d", hour, minute)
            }
        }
        return label
    }

    public static func formatCycleRemaining(_ endIso: String?, daysRemaining: Int?, now: Date = Date()) -> String {
        guard let endIso, let end = AccountSync.parseIso(endIso) else {
            if let daysRemaining { return "还剩 \(daysRemaining) 天" }
            return ""
        }
        let seconds = end.timeIntervalSince(now)
        if seconds <= 0 { return "已到期" }
        let hours = Int(seconds / 3600)
        if hours < 24 {
            if hours < 1 {
                let minutes = max(1, Int(seconds / 60))
                return "还剩 \(minutes) 分钟"
            }
            return "还剩 \(hours) 小时"
        }
        let days = daysRemaining ?? Int(seconds / 86_400)
        return "还剩 \(days) 天"
    }

    public static func cycleEndLabel(_ usage: UsageSnapshot) -> String {
        usage.billingCycleEndOverridden ? "到期" : "重置"
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
        if usage.showsGrokBot, let grokUsed = usage.grokBotPercentUsed {
            var grok = String(format: "剩余 %.1f%%（本周已用 %.1f%%）", usage.grokBotRemainingPercent ?? 0, grokUsed)
            if let reset = usage.grokBotResetAt {
                let resetText = formatResetDate(reset)
                let remaining = formatCycleRemaining(reset, daysRemaining: usage.grokBotDaysRemaining)
                grok += remaining.isEmpty ? " · \(resetText) 重置" : " · \(resetText)（\(remaining)）"
            }
            rows.append(("Grok Bot", grok))
        }
        if let end = usage.billingCycleEnd {
            let endText = formatResetDate(end, includeTime: usage.billingCycleEndOverridden)
            let remaining = formatCycleRemaining(end, daysRemaining: usage.daysRemaining)
            let label = cycleEndLabel(usage)
            if remaining.isEmpty {
                rows.append((label, endText))
            } else {
                rows.append((label, "\(endText)（\(remaining)）"))
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

    /// Menu-bar template: unconfigured is idle (not error); other failures show "!".
    public static func trayTemplateState(errorMessage: String?, remainingPercent: Double?) -> (remaining: Double?, error: Bool) {
        if let err = errorMessage, err.hasPrefix("未配置") {
            return (nil, false)
        }
        if errorMessage != nil {
            return (nil, true)
        }
        return (remainingPercent, false)
    }

    public static func trayPercentLabel(_ remaining: Double?, error: Bool) -> String {
        if error { return "!" }
        guard let remaining else { return "–" }
        let pct = min(100, max(0, remaining))
        if pct >= 99.5 { return "100" }
        return String(Int(pct.rounded()))
    }
}
