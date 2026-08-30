import AppKit
import CursorTokenCore
import SwiftUI

struct SettingsRootView: View {
    @ObservedObject var store: AppStore
    @State private var extraOpen = false
    @State private var importing = false
    @State private var tokenText = ""
    @State private var intervalText = "10"
    @State private var thresholdText = "50,20,5"
    @State private var hint = ""
    @FocusState private var tokenFocused: Bool
    var startImport: Bool = false
    var focusToken: Bool = false

    var body: some View {
        TabView {
            accountPage.tabItem { Label("账户", systemImage: "person.circle") }
            notifyPage.tabItem { Label("通知", systemImage: "bell") }
            menuPage.tabItem { Label("菜单栏", systemImage: "menubar.rectangle") }
        }
        .padding(20)
        .frame(width: 520, height: 420)
        .onAppear {
            tokenText = ""
            intervalText = String(store.config.refreshIntervalMinutes)
            thresholdText = store.config.alertThresholds.map(String.init).joined(separator: ",")
            if focusToken || store.focusToken {
                tokenFocused = true
            }
            if startImport {
                Task { await importFrom(prefer: "cursor-app") }
            }
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
            }
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
            Text(store.importStatus.isEmpty ? "已登录 Cursor 时可直接导入。浏览器 Cookie 仅作备选。" : store.importStatus)
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
            set: { store.switchAccount($0) }
        )
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

    func save(close: Bool) {
        var cfg = store.config
        if let n = Int(intervalText.trimmingCharacters(in: .whitespaces)), n >= 1 {
            cfg.refreshIntervalMinutes = n
        }
        cfg.alertThresholds = ConfigStore.parseThresholds(thresholdText)
        if !tokenText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            _ = try? cfg.upsertAccount(token: tokenText, activate: true)
        }
        store.applyConfig(cfg, refresh: true)
        hint = close ? "" : "已应用"
        if close { SettingsWindowController.shared.close() }
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
                contentRect: NSRect(x: 0, y: 0, width: 520, height: 460),
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
