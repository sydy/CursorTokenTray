import AppKit
import Combine
import CursorTokenCore
import Foundation
import UserNotifications

@MainActor
final class AppStore: ObservableObject {
    @Published var config: AppConfig
    @Published var usage: UsageSnapshot?
    @Published var errorMessage: String?
    @Published var updatedAt: String?
    @Published var settingsVisible = false
    @Published var flyoutVisible = false
    @Published var importStatus = ""
    @Published var focusToken = false

    let client = CursorClient()
    var settingsDirectory: URL?

    private var refreshTask: Task<Void, Never>?
    private var refreshNow = false

    init(directory: URL? = nil) {
        settingsDirectory = directory
        config = ConfigStore.load(from: directory)
    }

    func start() {
        LoginItem.apply(config.autostartEnabled)
        if let acc = config.activeAccount {
            UsageHistory.adoptLegacyHistory(accountId: acc.id, directory: settingsDirectory ?? AppPaths.configDirectory())
        }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        loopRefresh()
        if config.sessionToken.isEmpty {
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 300_000_000)
                self.openSettings(focusToken: true)
            }
        }
    }

    func stop() {
        refreshTask?.cancel()
        refreshTask = nil
        InstanceLock.release(directory: settingsDirectory)
    }

    func requestRefresh() {
        refreshNow = true
    }

    func openDashboard() {
        if let url = URL(string: UsageParser.dashboardURL(for: usage)) {
            NSWorkspace.shared.open(url)
        }
    }

    func openSettings(focusToken: Bool = false, startImport: Bool = false) {
        self.focusToken = focusToken
        settingsVisible = true
        SettingsWindowController.shared.show(store: self, focusToken: focusToken, startImport: startImport)
    }

    func applyConfig(_ cfg: AppConfig, refresh: Bool) {
        let prevToken = config.sessionToken
        let prevActive = config.activeAccountId
        let prevAuto = config.autostartEnabled
        config = cfg
        ConfigStore.save(cfg, to: settingsDirectory)
        if prevAuto != cfg.autostartEnabled {
            LoginItem.apply(cfg.autostartEnabled)
        }
        if refresh || prevToken != cfg.sessionToken || prevActive != cfg.activeAccountId {
            requestRefresh()
        }
        objectWillChange.send()
    }

    func copySummary() {
        let text = StatusText.formatSummary(usage, errorMessage: errorMessage, updatedAt: updatedAt, accountLabel: config.activeAccount?.displayLabel)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    func historyValues() -> [Double] {
        let aid = config.activeAccount?.id
        return UsageHistory.loadRecent(days: 7, accountId: aid, directory: settingsDirectory).map(\.remaining)
    }

    func switchAccount(_ id: String) {
        var cfg = config
        guard cfg.setActiveAccount(id) else { return }
        applyConfig(cfg, refresh: true)
        flyoutVisible = false
        FlyoutWindowController.shared.close()
    }

    func loopRefresh() {
        refreshTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                await self.refreshAll()
                let minutes = max(1, self.config.refreshIntervalMinutes)
                let deadline = Date().addingTimeInterval(Double(max(60, minutes * 60)))
                while Date() < deadline, !Task.isCancelled {
                    if self.refreshNow {
                        self.refreshNow = false
                        break
                    }
                    try? await Task.sleep(nanoseconds: 250_000_000)
                }
            }
        }
    }

    func refreshAll() async {
        var cfg = config
        if cfg.accounts.isEmpty {
            usage = nil
            errorMessage = "未配置 Token，请打开设置粘贴"
            updatedAt = nil
            return
        }
        let activeId = cfg.activeAccountId
        let ordered = cfg.accounts.sorted { a, b in
            (a.id == activeId ? 0 : 1) < (b.id == activeId ? 0 : 1)
        }
        for acc in ordered {
            if Task.isCancelled { break }
            let token = acc.token.trimmingCharacters(in: .whitespaces)
            guard !token.isEmpty else { continue }
            let isActive = acc.id == activeId
            let stamp: String = {
                let f = DateFormatter()
                f.dateFormat = "HH:mm:ss"
                return f.string(from: Date())
            }()
            do {
                let snap = try await client.fetchUsageSummary(sessionToken: token, timeout: 20)
                cfg.applySnapshot(to: acc.id, membershipType: snap.membershipType, remaining: snap.remainingPercent, error: "", updatedAt: stamp)
                if let idx = cfg.accounts.firstIndex(where: { $0.id == acc.id }) {
                    cfg.accounts[idx].authErrorNotified = false
                    let notices = AlertLogic.evaluate(config: cfg, account: &cfg.accounts[idx], snapshot: snap)
                    for n in notices { notify(n.title, n.body) }
                }
                UsageHistory.append(
                    remaining: snap.remainingPercent,
                    auto: snap.autoPercentUsed,
                    api: snap.apiPercentUsed,
                    accountId: acc.id,
                    directory: settingsDirectory
                )
                if isActive {
                    usage = snap
                    errorMessage = nil
                    updatedAt = stamp
                }
            } catch let err as CursorAPIError {
                cfg.applySnapshot(to: acc.id, error: err.message, updatedAt: stamp)
                if err.isAuthError, let idx = cfg.accounts.firstIndex(where: { $0.id == acc.id }), !cfg.accounts[idx].authErrorNotified {
                    if cfg.notifyEnabled {
                        let name = cfg.accounts[idx].displayLabel
                        notify("Token 需要更新", name.isEmpty ? err.message : "账号「\(name)」：\(err.message)")
                    }
                    cfg.accounts[idx].authErrorNotified = true
                }
                if isActive {
                    usage = nil
                    errorMessage = err.message
                    updatedAt = stamp
                }
            } catch {
                let msg = "刷新失败: \(error.localizedDescription)"
                cfg.applySnapshot(to: acc.id, error: msg, updatedAt: stamp)
                if isActive {
                    usage = nil
                    errorMessage = msg
                    updatedAt = stamp
                }
            }
        }
        cfg.syncLegacyFields()
        config = cfg
        ConfigStore.save(cfg, to: settingsDirectory)
    }

    func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }
}
