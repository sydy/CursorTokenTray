import AppKit
import CursorTokenCore
import SwiftUI

struct SettingsRootView: View {
    @ObservedObject var store: AppStore
    @State private var extraOpen = false
    @State private var importing = false
    @State private var tokenText = ""
    @State private var intervalText = "10"
    @State private var planUsdText = "0"
    @State private var actualCnyText = "0"
    @State private var cnyRateText = "7.5"
    @State private var thresholdText = "50,20,5"
    @State private var syncPath = ""
    @State private var syncSecret = ""
    @State private var syncStatus = ""
    @State private var hint = ""
    @FocusState private var tokenFocused: Bool
    var startImport: Bool = false
    var focusToken: Bool = false

    var body: some View {
        TabView {
            accountPage.tabItem { Label("账户", systemImage: "person.circle") }
            notifyPage.tabItem { Label("通知", systemImage: "bell") }
            menuPage.tabItem { Label("菜单栏", systemImage: "menubar.rectangle") }
            syncPage.tabItem { Label("同步", systemImage: "arrow.triangle.2.circlepath") }
        }
        .padding(20)
        .frame(width: 540, height: 600)
        .onAppear {
            tokenText = ""
            intervalText = String(store.config.refreshIntervalMinutes)
            let membership = store.config.activeAccount?.membershipType ?? ""
            let plan = store.config.monthlyPlanUsd > 0
                ? store.config.monthlyPlanUsd
                : UsageEvents.defaultMonthlyPlanUsd(membership)
            planUsdText = formatDecimal(plan)
            actualCnyText = formatDecimal(store.config.activeAccount?.actualCny ?? 0)
            cnyRateText = formatDecimal(store.config.usdCnyRate)
            thresholdText = store.config.alertThresholds.map(String.init).joined(separator: ",")
            syncPath = store.config.syncPath
            syncSecret = ""
            syncStatus = store.config.syncLastError.isEmpty
                ? (store.config.syncLastAt.isEmpty ? "" : "上次同步 " + store.config.syncLastAt)
                : store.config.syncLastError
            if focusToken || store.focusToken {
                tokenFocused = true
            }
            if startImport {
                Task { await importFrom(prefer: "cursor-app") }
            }
        }
        .onChange(of: store.config.activeAccountId) { _ in
            actualCnyText = formatDecimal(store.config.activeAccount?.actualCny ?? 0)
        }
    }

    var accountPage: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("当前账号").font(.headline)
            Picker("账号", selection: activeBinding) {
                ForEach(store.config.accounts, id: \.id) { acc in
                    Text(acc.caption(isActive: acc.id == store.config.activeAccountId)).tag(acc.id)
                }
            }
            .labelsHidden()
            HStack {
                Button("重命名") { rename() }
                Button("删除") { deleteAccount() }
                Button("登录到 Cursor") { Task { await loginToCursor() } }
                    .disabled(importing)
            }
            Picker("账号类型", selection: kindBinding) {
                Text("长期账号").tag(AccountValidity.longTerm)
                Text("临时账号").tag(AccountValidity.temporary)
            }
            .disabled(store.config.activeAccount == nil)
            if AccountValidity.isTemporary(store.config.activeAccount) {
                DatePicker("开始时间", selection: startBinding, displayedComponents: [.date, .hourAndMinute])
                HStack {
                    Text("有效时间")
                    Stepper(value: daysBinding, in: 0...AccountValidity.maxDays) {
                        Text("\(store.config.activeAccount?.tempValidDays ?? 0) 天")
                    }
                    Stepper(value: hoursBinding, in: 0...AccountValidity.maxHours) {
                        Text("\(store.config.activeAccount?.tempValidHours ?? 0) 小时")
                    }
                }
                Text(endCaption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Text("实际成本（人民币）")
                TextField("0", text: $actualCnyText).frame(width: 72)
            }
            .disabled(store.config.activeAccount == nil)
            Text("仅当前账号。企业 / 团队额度不是真实支出；填了则按套餐内费用分摊，优先于月费。按需仍按费用×汇率。")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("添加账号（粘贴 Token，请勿分享；已保存的不会显示）").font(.headline).padding(.top, 8)
            TextEditor(text: $tokenText)
                .font(.system(.body, design: .monospaced))
                .frame(height: 56)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.3)))
                .focused($tokenFocused)
            HStack {
                Button("从 Cursor 导入") { Task { await importFrom(prefer: "cursor-app") } }
                    .disabled(importing)
                Button("添加此 Token") { addToken() }
            }
            DisclosureGroup("其他导入方式", isExpanded: $extraOpen) {
                HStack {
                    Button("Safari 登录") { Task { await loginAndImport(prefer: "safari") } }
                        .disabled(importing)
                    Button("Firefox 登录") { Task { await loginAndImport(prefer: "firefox") } }
                        .disabled(importing)
                    Button("仅扫描 Cookie") { Task { await importFrom(prefer: nil) } }
                        .disabled(importing)
                }
            }
            if !FullDiskAccess.safariCookiesReadable() {
                HStack(alignment: .top, spacing: 8) {
                    Text("Safari 导入需要「完全磁盘访问权限」。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("打开系统设置") { FullDiskAccess.openPrivacySettings() }
                        .font(.caption)
                }
            }
            Text(store.importStatus.isEmpty ? "已登录 Cursor 时可直接导入。浏览器 Cookie 仅作备选，不能写回客户端切号。" : store.importStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            Spacer()
            footer
        }
    }

    var notifyPage: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("刷新与通知").font(.title3.bold())
            HStack {
                Text("刷新间隔（分钟）")
                TextField("10", text: $intervalText).frame(width: 72)
            }
            HStack {
                Text("月费（美元）")
                TextField("20", text: $planUsdText).frame(width: 72)
            }
            HStack {
                Text("美元兑人民币")
                TextField("7.5", text: $cnyRateText).frame(width: 72)
            }
            Text("月费填 0 则按套餐预填：Pro $20 / Pro+ $60 / Ultra $200。年付请填折合月费。实际成本在「账户」里按账号填写。")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack {
                Text("告警阈值，例如 50,20,5")
                TextField("50,20,5", text: $thresholdText).frame(width: 160)
            }
            Toggle("启用用量通知", isOn: notifyBinding)
            Toggle("启用耗尽风险通知", isOn: exhaustBinding)
            Spacer()
            footer
        }
    }

    var menuPage: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("菜单栏与启动").font(.title3.bold())
            Picker("菜单栏图标", selection: modeBinding) {
                Text("圆环百分比").tag("ring")
                Text("纯数字").tag("number")
                Text("仅色点").tag("dot")
            }
            Toggle("开机自启（下次登录生效）", isOn: autostartBinding)
            Spacer()
            footer
        }
    }

    var syncPage: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("多端同步").font(.title3.bold())
            Toggle("启用账号同步", isOn: syncEnabledBinding)
            HStack {
                TextField("同步文件夹（iCloud / 坚果云 / NAS）", text: $syncPath)
                Button("选择…") { pickFolder() }
            }
            SecureField(store.config.syncSecret.isEmpty ? "同步口令，两端必须相同" : "已保存，留空则不修改", text: $syncSecret)
            Text("把文件夹放到云盘即可多电脑共用。文件用口令 AES-GCM 加密，请勿分享口令。")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack {
                Button("立即同步") { syncNow() }
                Button("导出…") { exportFile() }
                Button("导入…") { importFile() }
            }
            Text(syncStatus.isEmpty ? " " : syncStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            footer
        }
    }

    var footer: some View {
        HStack {
            Text(store.saveError.isEmpty ? hint : store.saveError)
                .foregroundStyle(store.saveError.isEmpty ? Color.secondary : Color.red)
                .font(.caption)
            Spacer()
            Button("取消") { SettingsWindowController.shared.close() }
            Button("应用") { save(close: false) }
            Button("保存") { save(close: true) }.keyboardShortcut(.defaultAction)
        }
    }

    var activeBinding: Binding<String> {
        Binding(
            get: { store.config.activeAccountId },
            set: { newId in
                persistActualCny()
                store.switchAccount(newId)
                actualCnyText = formatDecimal(store.config.activeAccount?.actualCny ?? 0)
            }
        )
    }

    var kindBinding: Binding<String> {
        Binding(
            get: { store.config.activeAccount?.accountKind ?? AccountValidity.longTerm },
            set: { setValidity(kind: $0, refresh: true) }
        )
    }

    var startBinding: Binding<Date> {
        Binding(
            get: { AccountSync.parseIso(store.config.activeAccount?.tempStartAt) ?? Date() },
            set: { setValidity(start: $0) }
        )
    }

    var daysBinding: Binding<Int> {
        Binding(
            get: { store.config.activeAccount?.tempValidDays ?? 0 },
            set: { setValidity(days: $0) }
        )
    }

    var hoursBinding: Binding<Int> {
        Binding(
            get: { store.config.activeAccount?.tempValidHours ?? 0 },
            set: { setValidity(hours: $0) }
        )
    }

    var endCaption: String {
        guard let acc = store.config.activeAccount,
              let end = AccountValidity.accountEndIso(acc)
        else { return "请设置有效时间（天和小时可组合）" }
        return "结束时间 \(StatusText.formatResetDate(end, includeTime: true))（按开始时间计算，覆盖管理端重置日）"
    }

    func setValidity(kind: String? = nil, start: Date? = nil, days: Int? = nil, hours: Int? = nil, refresh: Bool = false) {
        guard let acc = store.config.activeAccount else { return }
        var c = store.config
        var newKind = kind ?? acc.accountKind
        var newStart = acc.tempStartAt
        if let start { newStart = AccountSync.nowIso(start) }
        var newDays = days ?? acc.tempValidDays
        var newHours = hours ?? acc.tempValidHours
        if AccountValidity.sanitizeKind(newKind) == AccountValidity.temporary {
            if newStart.trimmingCharacters(in: .whitespaces).isEmpty {
                newStart = AccountSync.nowIso()
            }
            if newDays == 0 && newHours == 0 { newDays = 1 }
        }
        _ = c.updateAccountValidity(acc.id, kind: newKind, startAt: newStart, days: newDays, hours: newHours)
        store.applyConfig(c, refresh: refresh)
    }

    var notifyBinding: Binding<Bool> {
        Binding(
            get: { store.config.notifyEnabled },
            set: { v in var c = store.config; c.notifyEnabled = v; store.applyConfig(c, refresh: false) }
        )
    }

    var exhaustBinding: Binding<Bool> {
        Binding(
            get: { store.config.notifyExhaustionRisk },
            set: { v in var c = store.config; c.notifyExhaustionRisk = v; store.applyConfig(c, refresh: false) }
        )
    }

    var modeBinding: Binding<String> {
        Binding(
            get: { store.config.trayDisplayMode },
            set: { v in var c = store.config; c.trayDisplayMode = v; store.applyConfig(c, refresh: false) }
        )
    }

    var autostartBinding: Binding<Bool> {
        Binding(
            get: { store.config.autostartEnabled },
            set: { v in var c = store.config; c.autostartEnabled = v; store.applyConfig(c, refresh: false) }
        )
    }

    var syncEnabledBinding: Binding<Bool> {
        Binding(
            get: { store.config.syncEnabled },
            set: { v in
                var c = store.config
                c.syncEnabled = v
                c.syncPath = syncPath.trimmingCharacters(in: .whitespaces)
                if !syncSecret.trimmingCharacters(in: .whitespaces).isEmpty {
                    c.syncSecret = syncSecret.trimmingCharacters(in: .whitespaces)
                }
                store.applyConfig(c, refresh: false)
            }
        )
    }

    func addToken() {
        do {
            var cfg = store.config
            _ = try cfg.upsertAccount(token: tokenText, activate: true)
            store.applyConfig(cfg, refresh: true)
            hint = "已添加"
            store.importStatus = "已写入当前账号"
            tokenText = ""
        } catch {
            hint = error.localizedDescription
        }
    }

    func rename() {
        guard let acc = store.config.activeAccount else { return }
        let alert = NSAlert()
        alert.messageText = "重命名账号"
        alert.informativeText = acc.displayLabel
        let field = NSTextField(string: acc.label)
        field.frame = NSRect(x: 0, y: 0, width: 240, height: 24)
        alert.accessoryView = field
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        if alert.runModal() == .alertFirstButtonReturn {
            var cfg = store.config
            _ = cfg.renameAccount(acc.id, label: field.stringValue)
            store.applyConfig(cfg, refresh: false)
        }
    }

    func deleteAccount() {
        guard let acc = store.config.activeAccount else { return }
        let alert = NSAlert()
        alert.messageText = "删除账号"
        alert.informativeText = "确定删除「\(acc.displayLabel)」？"
        alert.addButton(withTitle: "删除")
        alert.addButton(withTitle: "取消")
        if alert.runModal() == .alertFirstButtonReturn {
            var cfg = store.config
            _ = cfg.removeAccount(acc.id)
            store.applyConfig(cfg, refresh: true)
        }
    }

    func loginToCursor() async {
        importing = true
        store.importStatus = "正在写入 Cursor…"
        let result = await store.loginToCursor(confirmClose: { running in
            if !running { return true }
            let alert = NSAlert()
            alert.messageText = "登录到 Cursor"
            alert.informativeText = CursorAuth.confirmCloseMessage
            alert.addButton(withTitle: "关闭并写入")
            alert.addButton(withTitle: "取消")
            return alert.runModal() == .alertFirstButtonReturn
        })
        importing = false
        store.importStatus = result.message
        hint = result.ok ? "已写入 Cursor" : result.message
    }

    func save(close: Bool) {
        var cfg = store.config
        if let n = Int(intervalText.trimmingCharacters(in: .whitespaces)), n >= 1 {
            cfg.refreshIntervalMinutes = n
        }
        if let plan = parseDecimal(planUsdText) {
            cfg.monthlyPlanUsd = UsageEvents.clampMonthlyPlanUsd(plan)
        }
        if let actual = parseDecimal(actualCnyText), let acc = cfg.activeAccount {
            _ = cfg.setActualCny(acc.id, actual)
        }
        if let rate = parseDecimal(cnyRateText) {
            cfg.usdCnyRate = UsageEvents.clampUsdCnyRate(rate)
        }
        cfg.alertThresholds = ConfigStore.parseThresholds(thresholdText)
        cfg.syncPath = syncPath.trimmingCharacters(in: .whitespaces)
        if !syncSecret.trimmingCharacters(in: .whitespaces).isEmpty {
            cfg.syncSecret = syncSecret.trimmingCharacters(in: .whitespaces)
        }
        if !tokenText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            _ = try? cfg.upsertAccount(token: tokenText, activate: true)
        }
        store.applyConfig(cfg, refresh: true)
        hint = close ? "" : "已应用"
        if close { SettingsWindowController.shared.close() }
    }

    func persistActualCny() {
        guard let acc = store.config.activeAccount, let actual = parseDecimal(actualCnyText) else { return }
        var cfg = store.config
        _ = cfg.setActualCny(acc.id, actual)
        store.applyConfig(cfg, refresh: false)
    }

    func applySyncFields(_ cfg: inout AppConfig) {
        cfg.syncPath = syncPath.trimmingCharacters(in: .whitespaces)
        if !syncSecret.trimmingCharacters(in: .whitespaces).isEmpty {
            cfg.syncSecret = syncSecret.trimmingCharacters(in: .whitespaces)
        }
    }

    func syncNow() {
        var cfg = store.config
        applySyncFields(&cfg)
        let status = AccountSync.reconcile(&cfg)
        store.applyConfig(cfg, refresh: status.changed)
        syncStatus = status.message
        hint = status.ok ? status.message : status.message
    }

    func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "选择"
        panel.message = "选择同步文件夹（建议放到 iCloud Drive）"
        if panel.runModal() == .OK, let url = panel.url {
            syncPath = url.path
            var cfg = store.config
            applySyncFields(&cfg)
            store.applyConfig(cfg, refresh: false)
        }
    }

    func exportFile() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = AccountSync.filename
        panel.title = "导出加密账号包"
        panel.allowedFileTypes = ["sync", "json"]
        if panel.runModal() != .OK { return }
        guard let url = panel.url else { return }
        var cfg = store.config
        applySyncFields(&cfg)
        do {
            let dest = try AccountSync.exportToFile(&cfg, path: url.path)
            store.applyConfig(cfg, refresh: false)
            syncStatus = "已导出到 " + dest
        } catch {
            syncStatus = (error as? CursorAPIError)?.message ?? error.localizedDescription
        }
    }

    func importFile() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.title = "导入加密账号包"
        if panel.runModal() != .OK { return }
        guard let url = panel.url else { return }
        var cfg = store.config
        applySyncFields(&cfg)
        do {
            try AccountSync.importFromFile(&cfg, path: url.path)
            store.applyConfig(cfg, refresh: true)
            syncStatus = "已从文件合并账号"
            hint = "已导入"
        } catch {
            syncStatus = (error as? CursorAPIError)?.message ?? error.localizedDescription
        }
    }

    func importFrom(prefer: String?) async {
        importing = true
        store.importStatus = "正在导入…"
        let result = await SessionImporter.importAndValidate(
            preferBrowsers: SessionImporter.defaultPreferBrowsers(prefer),
            onlyBrowsers: SessionImporter.onlyBrowsers(for: prefer),
            skipTokens: store.config.existingTokenVariants()
        )
        await MainActor.run {
            importing = false
            store.importStatus = result.message
            if result.ok {
                var cfg = store.config
                _ = try? cfg.upsertAccount(
                    token: result.token,
                    membershipType: result.membershipType,
                    remaining: result.remainingPercent,
                    activate: true
                )
                store.applyConfig(cfg, refresh: true)
                tokenText = ""
                hint = "已导入"
            }
        }
    }

    func loginAndImport(prefer: String) async {
        if importing { return }
        importing = true
        defer { importing = false }
        let apps = SessionImporter.preferredMacAppNames(prefer)
        if let app = apps.first {
            let url = URL(string: "https://cursor.com/dashboard")!
            let config = NSWorkspace.OpenConfiguration()
            if let appURL = applicationURL(named: app) {
                _ = try? await NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: config)
            } else {
                NSWorkspace.shared.open(url)
            }
        }
        store.importStatus = "请在浏览器登录，正在等待 Cookie…"
        let deadline = Date().addingTimeInterval(180)
        while Date() < deadline {
            let result = await SessionImporter.importAndValidate(
                preferBrowsers: SessionImporter.defaultPreferBrowsers(prefer),
                onlyBrowsers: SessionImporter.onlyBrowsers(for: prefer),
                skipTokens: store.config.existingTokenVariants()
            )
            if result.ok {
                await MainActor.run {
                    var cfg = store.config
                    _ = try? cfg.upsertAccount(token: result.token, membershipType: result.membershipType, remaining: result.remainingPercent, activate: true)
                    store.applyConfig(cfg, refresh: true)
                    tokenText = ""
                    store.importStatus = result.message
                    hint = "已导入"
                }
                return
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
        await MainActor.run { store.importStatus = "等待登录超时，请手动粘贴 Token。" }
    }

    func formatDecimal(_ value: Double) -> String {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.minimumFractionDigits = 0
        f.maximumFractionDigits = 4
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: value)) ?? String(value)
    }

    func parseDecimal(_ text: String) -> Double? {
        let cleaned = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "，", with: ".")
        return Double(cleaned)
    }

    func bundleId(for app: String) -> String {
        switch app {
        case "Safari": return "com.apple.Safari"
        case "Firefox": return "org.mozilla.firefox"
        default: return ""
        }
    }

    func applicationURL(named app: String) -> URL? {
        let id = bundleId(for: app)
        if !id.isEmpty, let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id) {
            return url
        }
        let candidates = [
            "/Applications/\(app).app",
            "/System/Cryptexes/App/System/Applications/\(app).app",
            "/System/Applications/\(app).app",
            NSHomeDirectory() + "/Applications/\(app).app",
        ]
        return candidates.map { URL(fileURLWithPath: $0) }.first { FileManager.default.fileExists(atPath: $0.path) }
    }
}

@MainActor
final class SettingsWindowController: NSObject, NSWindowDelegate {
    static let shared = SettingsWindowController()
    private var window: NSWindow?
    private weak var store: AppStore?

    func show(store: AppStore, focusToken: Bool, startImport: Bool) {
        self.store = store
        MenubarActivation.promoteForWindow()
        AppDelegate.ensureStatusItemVisible()
        if window == nil {
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 540, height: 600),
                styleMask: [.titled, .closable, .miniaturizable],
                backing: .buffered,
                defer: false
            )
            win.title = "Cursor Token 设置"
            win.isReleasedWhenClosed = false
            win.delegate = self
            window = win
        }
        window?.contentView = NSHostingView(rootView: SettingsRootView(store: store, startImport: startImport, focusToken: focusToken))
        window?.center()
        window?.makeKeyAndOrderFront(nil)
        if focusToken {
            DispatchQueue.main.async {
                store.focusToken = true
            }
        }
    }

    func close() {
        dismiss()
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        dismiss()
        return false
    }

    func windowWillClose(_ notification: Notification) {
        store?.settingsVisible = false
        MenubarActivation.restoreAfterClosing(notification.object as? NSWindow)
    }

    private func dismiss() {
        window?.orderOut(nil)
        store?.settingsVisible = false
        MenubarActivation.restoreNow(excluding: window)
    }
}
