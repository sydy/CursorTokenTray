import AppKit
import CursorTokenCore
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class CompareStore: ObservableObject {
    let app: AppStore
    @Published var status = "已加载本地明细。点「同步」按各账号最新周期拉取。"
    @Published var syncing = false
    @Published var report = AccountCompareReport(rows: [], groups: [], holdingDays: UsageEvents.holdingDays)

    init(app: AppStore) {
        self.app = app
    }

    func loadCache() {
        report = buildReport()
        if report.rows.isEmpty {
            status = app.config.accounts.isEmpty
                ? "还没有账号。请先在设置里导入。"
                : "本地还没有明细。点「同步」按各账号最新周期拉取。"
        }
    }

    func sync() async {
        if syncing { return }
        if app.config.accounts.isEmpty {
            status = "还没有账号。请先在设置里导入。"
            return
        }
        syncing = true
        defer { syncing = false }
        status = "正在同步各账号最新周期…"
        var ok = 0
        var fail = 0
        for acc in app.config.accounts {
            let token = acc.token.trimmingCharacters(in: .whitespaces)
            if token.isEmpty {
                fail += 1
                continue
            }
            do {
                var snap = try await app.client.fetchUsageSummary(sessionToken: token, timeout: 20)
                AccountValidity.applyEndOverride(&snap, account: acc)
                app.persistCompareCycle(
                    accountId: acc.id,
                    membership: snap.membershipType,
                    start: snap.billingCycleStart,
                    end: snap.billingCycleEnd
                )
                _ = try await UsageEvents.sync(
                    client: app.client,
                    token: token,
                    accountId: acc.id,
                    usage: snap,
                    teamScope: false,
                    directory: app.settingsDirectory
                )
                ok += 1
            } catch let err as CursorAPIError {
                fail += 1
                AppLog.log("compare sync \(acc.id): \(err.message)")
            } catch {
                fail += 1
                AppLog.log("compare sync \(acc.id): \(error.localizedDescription)")
            }
        }
        report = buildReport()
        let stamp: String = {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = TimeZone(secondsFromGMT: 8 * 3600)
            f.dateFormat = "HH:mm:ss"
            return f.string(from: Date())
        }()
        if fail == 0 {
            status = "已同步 \(ok) 个账号  ·  \(stamp)"
        } else {
            status = "已同步 \(ok) 个账号，\(fail) 个失败  ·  \(stamp)"
        }
    }

    func exportCSV() {
        guard !report.rows.isEmpty else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.commaSeparatedText]
        panel.nameFieldStringValue = {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = TimeZone(secondsFromGMT: 8 * 3600)
            f.dateFormat = "yyyyMMdd"
            return "cursor-account-compare-\(f.string(from: Date())).csv"
        }()
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try UsageEvents.accountCompareToCSV(report).write(to: url, atomically: true, encoding: .utf8)
            status = "已导出 \(url.path)"
        } catch {
            status = "导出失败：\(error.localizedDescription)"
        }
    }

    func buildReport() -> AccountCompareReport {
        let items = app.config.accounts.map { acc in
            UsageEvents.compareInput(
                from: acc,
                events: UsageEvents.load(accountId: acc.id, teamScope: false, directory: app.settingsDirectory),
                monthlyPlanUsd: app.config.monthlyPlanUsd,
                usdCnyRate: app.config.usdCnyRate
            )
        }
        return UsageEvents.buildAccountCompareReport(items)
    }
}

struct CompareDisplayRow: Identifiable {
    var id: String
    var isGroup: Bool
    var name: String
    var channel: String
    var membership: String
    var window: String
    var days: String
    var dailyHolding: String
    var totalCny: String
    var requests: String
    var tokens: String
    var perMillion: String
    var perRequest: String
    var fpCount: String
    var fpTokens: String
    var fpCny: String
    var fpPerMillion: String
    var fpPerRequest: String
    var apiCount: String
    var apiTokens: String
    var apiCny: String
    var apiPerMillion: String
    var apiPerRequest: String
    var grokCount: String
    var grokTokens: String
    var grokCny: String
    var grokPerMillion: String
    var grokPerRequest: String
}

struct CompareRootView: View {
    @ObservedObject var store: CompareStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Button("同步") { Task { await store.sync() } }
                    .disabled(store.syncing)
                Button("导出 CSV") { store.exportCSV() }
                    .disabled(store.report.rows.isEmpty)
                Spacer()
            }
            Text(store.status)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("窗口按各账号自己的最新周期或有效期。日均持有 = 折合月费÷30。窗口实付把月费按窗口天数折算后再摊到套餐内请求；按需仍按费用×汇率。表内同时给出 First-party / API / Grok Bot 的次数、Token 与单位成本。")
                .font(.caption)
                .foregroundStyle(.secondary)
            table
        }
        .padding(16)
        .frame(minWidth: 1120, minHeight: 560)
        .onAppear { store.loadCache() }
    }

    var table: some View {
        Table(displayRows) {
            TableColumn("账号") { row in cell(row.name, bold: row.isGroup) }
            TableColumn("渠道") { row in cell(row.channel, bold: row.isGroup) }
            TableColumn("套餐") { row in cell(row.membership) }
            TableColumn("窗口") { row in cell(row.window) }
            TableColumn("天数") { row in cell(row.days) }
            TableColumn("日均持有") { row in cell(row.dailyHolding, bold: row.isGroup) }
            TableColumn("窗口实付") { row in cell(row.totalCny, bold: row.isGroup) }
            TableColumn("请求") { row in cell(row.requests) }
            TableColumn("Token") { row in cell(row.tokens) }
            TableColumn("¥/百万") { row in cell(row.perMillion) }
            TableColumn("¥/次") { row in cell(row.perRequest) }
            TableColumn("FP次数") { row in cell(row.fpCount) }
            TableColumn("FP Token") { row in cell(row.fpTokens) }
            TableColumn("FP实付") { row in cell(row.fpCny) }
            TableColumn("FP ¥/百万") { row in cell(row.fpPerMillion) }
            TableColumn("FP ¥/次") { row in cell(row.fpPerRequest) }
            TableColumn("API次数") { row in cell(row.apiCount) }
            TableColumn("API Token") { row in cell(row.apiTokens) }
            TableColumn("API实付") { row in cell(row.apiCny) }
            TableColumn("API ¥/百万") { row in cell(row.apiPerMillion) }
            TableColumn("API ¥/次") { row in cell(row.apiPerRequest) }
            TableColumn("Grok次数") { row in cell(row.grokCount) }
            TableColumn("Grok Token") { row in cell(row.grokTokens) }
            TableColumn("Grok实付") { row in cell(row.grokCny) }
            TableColumn("Grok ¥/百万") { row in cell(row.grokPerMillion) }
            TableColumn("Grok ¥/次") { row in cell(row.grokPerRequest) }
        }
    }

    func cell(_ text: String, bold: Bool = false) -> some View {
        Text(text)
            .font(bold ? .body.weight(.semibold) : .body)
            .lineLimit(1)
    }

    var displayRows: [CompareDisplayRow] {
        var rows: [CompareDisplayRow] = []
        for group in store.report.groups {
            for row in group.rows {
                rows.append(displayRow(
                    id: row.accountId,
                    isGroup: false,
                    name: row.label,
                    channel: row.channelLabel,
                    membership: UsageParser.formatMembershipType(row.membershipType),
                    window: row.windowLabel,
                    days: formatDays(row.windowDays),
                    dailyHolding: row.dailyHoldingCny,
                    totalCny: row.totalCny,
                    requests: row.eventCount,
                    tokens: row.totalTokens,
                    perMillion: row.cnyPerMillion,
                    perRequest: row.cnyPerRequest,
                    firstParty: row.firstParty,
                    api: row.api,
                    grok: row.grokBot
                ))
            }
            rows.append(displayRow(
                id: "group:\(group.channel)",
                isGroup: true,
                name: "\(group.channelLabel)合计",
                channel: group.channelLabel,
                membership: "",
                window: "",
                days: "",
                dailyHolding: group.dailyHoldingCny,
                totalCny: group.totalCny,
                requests: group.eventCount,
                tokens: group.totalTokens,
                perMillion: group.cnyPerMillion,
                perRequest: group.cnyPerRequest,
                firstParty: group.firstParty,
                api: group.api,
                grok: group.grokBot
            ))
        }
        return rows
    }

    func displayRow(
        id: String,
        isGroup: Bool,
        name: String,
        channel: String,
        membership: String,
        window: String,
        days: String,
        dailyHolding: Double,
        totalCny: Double,
        requests: Int,
        tokens: Int,
        perMillion: Double?,
        perRequest: Double?,
        firstParty: AccountCompareCategory,
        api: AccountCompareCategory,
        grok: AccountCompareCategory
    ) -> CompareDisplayRow {
        CompareDisplayRow(
            id: id,
            isGroup: isGroup,
            name: name,
            channel: channel,
            membership: membership,
            window: window,
            days: days,
            dailyHolding: UsageEvents.formatCNY(dailyHolding),
            totalCny: UsageEvents.formatCNY(totalCny),
            requests: String(requests),
            tokens: UsageParser.formatTokenCount(Double(tokens)),
            perMillion: UsageEvents.formatCnyUnit(perMillion, suffix: "/百万"),
            perRequest: UsageEvents.formatCnyUnit(perRequest, suffix: "/次"),
            fpCount: String(firstParty.count),
            fpTokens: UsageParser.formatTokenCount(Double(firstParty.tokens)),
            fpCny: UsageEvents.formatCNY(firstParty.cny),
            fpPerMillion: UsageEvents.formatCnyUnit(firstParty.cnyPerMillion, suffix: "/百万"),
            fpPerRequest: UsageEvents.formatCnyUnit(firstParty.cnyPerRequest, suffix: "/次"),
            apiCount: String(api.count),
            apiTokens: UsageParser.formatTokenCount(Double(api.tokens)),
            apiCny: UsageEvents.formatCNY(api.cny),
            apiPerMillion: UsageEvents.formatCnyUnit(api.cnyPerMillion, suffix: "/百万"),
            apiPerRequest: UsageEvents.formatCnyUnit(api.cnyPerRequest, suffix: "/次"),
            grokCount: String(grok.count),
            grokTokens: UsageParser.formatTokenCount(Double(grok.tokens)),
            grokCny: UsageEvents.formatCNY(grok.cny),
            grokPerMillion: UsageEvents.formatCnyUnit(grok.cnyPerMillion, suffix: "/百万"),
            grokPerRequest: UsageEvents.formatCnyUnit(grok.cnyPerRequest, suffix: "/次")
        )
    }

    func formatDays(_ days: Double) -> String {
        if abs(days - days.rounded()) < 0.05 {
            return String(format: "%.0f", days.rounded())
        }
        return String(format: "%.2f", days)
    }
}

@MainActor
final class CompareWindowController: NSObject, NSWindowDelegate {
    static let shared = CompareWindowController()
    private var window: NSWindow?
    private var store: CompareStore?

    func show(app: AppStore) {
        FlyoutWindowController.shared.close()
        MenubarActivation.promoteForWindow()
        AppDelegate.ensureStatusItemVisible()
        if window == nil {
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 1180, height: 640),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false
            )
            win.title = "账号对比"
            win.minSize = NSSize(width: 1040, height: 520)
            win.isReleasedWhenClosed = false
            win.delegate = self
            window = win
        }
        let compareStore = CompareStore(app: app)
        store = compareStore
        window?.contentView = NSHostingView(rootView: CompareRootView(store: compareStore))
        window?.center()
        window?.makeKeyAndOrderFront(nil)
    }

    func close() {
        dismiss()
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        dismiss()
        return false
    }

    func windowWillClose(_ notification: Notification) {
        MenubarActivation.restoreAfterClosing(notification.object as? NSWindow)
    }

    private func dismiss() {
        window?.orderOut(nil)
        MenubarActivation.restoreNow(excluding: window)
    }
}
