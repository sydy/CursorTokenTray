import AppKit
import CursorTokenCore
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class ReportStore: ObservableObject {
    let app: AppStore
    @Published var teamScope = false
    @Published var kind = ""
    @Published var model = ""
    @Published var cloud = ""
    @Published var status = "正在同步本周期明细…"
    @Published var syncing = false
    @Published var events: [UsageEvent] = []
    @Published var modelNames: [String] = []

    init(app: AppStore) {
        self.app = app
    }

    var isTeam: Bool { app.usage?.isTeamAccount == true }

    var filter: UsageReportFilter {
        UsageReportFilter(
            kind: kind,
            model: model,
            headless: cloud == "local" ? false : cloud == "cloud" ? true : nil,
            owningUser: ""
        )
    }

    var report: UsageReport {
        UsageEvents.buildReport(events, filter: filter)
    }

    func loadCache() {
        let accountId = app.config.activeAccountId
        events = UsageEvents.load(accountId: accountId, teamScope: teamScope, directory: app.settingsDirectory)
        refreshModelNames()
    }

    func sync() async {
        if syncing { return }
        let token = app.config.activeAccount?.token ?? app.config.sessionToken
        let accountId = app.config.activeAccountId
        if token.trimmingCharacters(in: .whitespaces).isEmpty {
            status = "未配置 Token，请先在设置里导入账号"
            return
        }
        syncing = true
        loadCache()
        status = "正在同步本周期明细…"
        defer { syncing = false }
        do {
            let result = try await UsageEvents.sync(
                client: app.client,
                token: token,
                accountId: accountId,
                usage: app.usage,
                teamScope: teamScope,
                directory: app.settingsDirectory
            )
            events = result.events
            refreshModelNames()
            var extra = ""
            if result.truncated {
                extra = "（服务端约 \(result.totalAvailable) 条，已截到最近 \(result.events.count) 条）"
            }
            let stamp: String = {
                let f = DateFormatter()
                f.dateFormat = "HH:mm:ss"
                return f.string(from: Date())
            }()
            status = "已同步 \(events.count) 条\(extra)  ·  \(stamp)"
        } catch let err as CursorAPIError {
            refreshModelNames()
            status = "同步失败：\(err.message)"
        } catch {
            refreshModelNames()
            status = "同步失败：\(error.localizedDescription)"
        }
    }

    func exportCSV() {
        let rows = report.events
        guard !rows.isEmpty else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.commaSeparatedText]
        panel.nameFieldStringValue = {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = TimeZone(secondsFromGMT: 0)
            f.dateFormat = "yyyyMMdd"
            return "cursor-usage-\(f.string(from: Date())).csv"
        }()
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try UsageEvents.toCSV(rows).write(to: url, atomically: true, encoding: .utf8)
            status = "已导出 \(url.path)"
        } catch {
            status = "导出失败：\(error.localizedDescription)"
        }
    }

    func refreshModelNames() {
        let names = Array(Set(events.map(\.model).filter { !$0.isEmpty })).sorted()
        modelNames = names
        if !model.isEmpty && !names.contains(model) {
            model = ""
        }
    }
}

struct ReportRootView: View {
    @ObservedObject var store: ReportStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            filters
            Text(store.status)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(kpiText)
                .font(.subheadline)
            dailyChart
            models
            details
        }
        .padding(16)
        .frame(minWidth: 860, minHeight: 560)
        .task { await store.sync() }
        .onChange(of: store.teamScope) { _ in
            Task { await store.sync() }
        }
    }

    var filters: some View {
        HStack(spacing: 10) {
            if store.isTeam {
                Picker("范围", selection: $store.teamScope) {
                    Text("仅自己").tag(false)
                    Text("全员").tag(true)
                }
                .frame(width: 140)
            }
            Picker("类型", selection: $store.kind) {
                Text("全部类型").tag("")
                Text("套餐内").tag(UsageEvents.kindIncluded)
                Text("免费").tag(UsageEvents.kindFree)
                Text("按需").tag(UsageEvents.kindOnDemand)
            }
            .frame(width: 140)
            Picker("模型", selection: $store.model) {
                Text("全部模型").tag("")
                ForEach(store.modelNames, id: \.self) { name in
                    Text(name).tag(name)
                }
            }
            .frame(minWidth: 180)
            Picker("来源", selection: $store.cloud) {
                Text("全部来源").tag("")
                Text("本机").tag("local")
                Text("云端 Agent").tag("cloud")
            }
            .frame(width: 150)
            Button("同步") { Task { await store.sync() } }
                .disabled(store.syncing)
            Button("导出 CSV") { store.exportCSV() }
                .disabled(store.report.events.isEmpty)
            Spacer()
        }
    }

    var kpiText: String {
        let report = store.report
        var mix = "套餐内 \(report.includedCount) · 免费 \(report.freeCount) · 按需 \(report.onDemandCount)"
        if report.headlessCount > 0 { mix += " · 云端 \(report.headlessCount)" }
        let cost = report.hasCost ? "    费用 \(UsageParser.formatUSDCents(report.totalCents))" : ""
        return "请求 \(report.eventCount)    Token \(UsageParser.formatTokenCount(Double(report.totalTokens)))    \(mix)\(cost)"
    }

    var dailyChart: some View {
        let daily = store.report.daily
        return VStack(alignment: .leading, spacing: 4) {
            Text(daily.isEmpty ? "按日 Token" : "按日 Token（\(daily.first!.date) 至 \(daily.last!.date)）")
                .font(.caption)
                .foregroundStyle(.secondary)
            if daily.count >= 2 {
                Sparkline(values: daily.map { Double($0.tokens) })
                    .frame(height: 48)
            } else {
                Rectangle().fill(Color.secondary.opacity(0.08)).frame(height: 48)
            }
        }
    }

    var models: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("按模型").font(.caption).foregroundStyle(.secondary)
            Table(store.report.models) {
                TableColumn("模型") { row in Text(row.name) }
                TableColumn("Token") { row in Text(UsageParser.formatTokenCount(Double(row.tokens))) }
                TableColumn("费用") { row in Text(row.cents > 0 ? UsageParser.formatUSDCents(row.cents) : "—") }
                TableColumn("次数") { row in Text(String(row.count)) }
                TableColumn("云端") { row in Text(row.headlessCount > 0 ? String(row.headlessCount) : "—") }
            }
            .frame(minHeight: 120, maxHeight: 160)
        }
    }

    var details: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("明细").font(.caption).foregroundStyle(.secondary)
            Table(store.report.events) {
                TableColumn("日期 (UTC)") { ev in Text(UsageEvents.formatTime(ev.timestampMs)) }
                TableColumn("用户") { ev in Text(ev.userEmail) }
                TableColumn("类型") { ev in Text(UsageEvents.kindLabel(ev.kind)) }
                TableColumn("模型") { ev in Text(ev.model) }
                TableColumn("Token") { ev in Text(UsageParser.formatTokenCount(Double(ev.tokens))) }
                TableColumn("费用") { ev in Text(UsageEvents.formatCost(ev)) }
                TableColumn("云端") { ev in Text(ev.isHeadless ? "是" : "否") }
            }
        }
    }
}

extension DailyUsageRow: Identifiable {
    public var id: String { date }
}

extension ModelUsageRow: Identifiable {
    public var id: String { name }
}

extension UsageEvent: Identifiable {}

@MainActor
final class ReportWindowController: NSObject, NSWindowDelegate {
    static let shared = ReportWindowController()
    private var window: NSWindow?
    private var store: ReportStore?

    var isOpen: Bool { window?.isVisible == true }

    func show(app: AppStore) {
        FlyoutWindowController.shared.close()
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        if window == nil {
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 960, height: 680),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false
            )
            win.title = "用量报表"
            win.minSize = NSSize(width: 820, height: 520)
            win.isReleasedWhenClosed = false
            win.delegate = self
            window = win
        }
        let reportStore = ReportStore(app: app)
        store = reportStore
        window?.contentView = NSHostingView(rootView: ReportRootView(store: reportStore))
        window?.center()
        window?.makeKeyAndOrderFront(nil)
    }

    func close() {
        window?.orderOut(nil)
        if !SettingsWindowController.shared.isOpen {
            NSApp.setActivationPolicy(.accessory)
        }
    }

    func windowWillClose(_ notification: Notification) {
        if !SettingsWindowController.shared.isOpen {
            NSApp.setActivationPolicy(.accessory)
        }
    }
}
