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
        let targets = config.accounts.map { (id: $0.id, token: $0.token, decryptFailed: $0.tokenDecryptFailed) }
        if targets.isEmpty {
            usage = nil
            errorMessage = "未配置 Token，请打开设置粘贴"
            updatedAt = nil
            return
        }
        let activeId = config.activeAccountId
        struct Outcome {
            var id: String
            var snap: UsageSnapshot?
            var error: String?
            var authError: Bool
            var stamp: String
        }
        var outcomes: [Outcome] = []
        let ordered = targets.sorted { a, b in
            (a.id == activeId ? 0 : 1) < (b.id == activeId ? 0 : 1)
        }
        for acc in ordered {
            if Task.isCancelled { break }
            let stamp: String = {
                let f = DateFormatter()
                f.dateFormat = "HH:mm:ss"
                return f.string(from: Date())
            }()
            if acc.decryptFailed || acc.token.trimmingCharacters(in: .whitespaces).isEmpty {
                outcomes.append(Outcome(id: acc.id, snap: nil, error: TokenProtector.decryptFailedMessage, authError: false, stamp: stamp))
                continue
            }
            do {
                let snap = try await client.fetchUsageSummary(sessionToken: acc.token, timeout: 20)
                outcomes.append(Outcome(id: acc.id, snap: snap, error: nil, authError: false, stamp: stamp))
                UsageHistory.append(
                    remaining: snap.remainingPercent,
                    auto: snap.autoPercentUsed,
                    api: snap.apiPercentUsed,
                    accountId: acc.id,
                    directory: settingsDirectory
                )
            } catch let err as CursorAPIError {
                outcomes.append(Outcome(id: acc.id, snap: nil, error: err.message, authError: err.isAuthError, stamp: stamp))
            } catch {
                outcomes.append(Outcome(id: acc.id, snap: nil, error: "刷新失败: \(error.localizedDescription)", authError: false, stamp: stamp))
            }
        }

        var notices: [(String, String)] = []
        let cfg = ConfigStore.update(from: settingsDirectory) { live in
            for o in outcomes {
                guard let idx = live.accounts.firstIndex(where: { $0.id == o.id }) else { continue }
                if let snap = o.snap {
                    live.applySnapshot(to: o.id, membershipType: snap.membershipType, remaining: snap.remainingPercent, error: "", updatedAt: o.stamp)
                    live.accounts[idx].authErrorNotified = false
                    var account = live.accounts[idx]
                    let found = AlertLogic.evaluate(config: live, account: &account, snapshot: snap)
                    live.accounts[idx] = account
                    for n in found { notices.append((n.title, n.body)) }
                } else if let err = o.error {
                    live.applySnapshot(to: o.id, error: err, updatedAt: o.stamp)
                    if o.authError, !live.accounts[idx].authErrorNotified {
                        live.accounts[idx].authErrorNotified = true
                        if live.notifyEnabled {
                            let name = live.accounts[idx].displayLabel
                            notices.append(("Token 需要更新", name.isEmpty ? err : "账号「\(name)」：\(err)"))
                        }
                    }
                }
            }
            live.syncLegacyFields()
        }
        config = cfg
        if let active = outcomes.first(where: { $0.id == cfg.activeAccountId }) {
            if let snap = active.snap {
                usage = snap
                errorMessage = nil
                updatedAt = active.stamp
            } else if let err = active.error {
                usage = nil
                errorMessage = err
                updatedAt = active.stamp
            }
        } else if cfg.accounts.isEmpty {
            usage = nil
            errorMessage = "未配置 Token，请打开设置粘贴"
            updatedAt = nil
        }
        for n in notices { notify(n.0, n.1) }
    }

    func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }
}
