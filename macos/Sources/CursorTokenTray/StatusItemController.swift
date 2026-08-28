import AppKit
import Combine
import CursorTokenCore
import SwiftUI

@MainActor
final class StatusItemController: NSObject {
    private let store: AppStore
    private var item: NSStatusItem
    private var cancellable: AnyCancellable?
    private var retryTask: Task<Void, Never>?
    private var lastIconLog: String?

    init(store: AppStore) {
        self.store = store
        item = StatusItemController.makeStatusItem()
        super.init()
        configureButton()
        render()
        cancellable = store.objectWillChange.sink { [weak self] _ in
            Task { @MainActor in self?.render() }
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(systemDidWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
        scheduleAppearRetries()
    }

    @objc private func systemDidWake() {
        recreateItem()
    }

    func ensureVisible() {
        item.isVisible = true
        item.length = NSStatusItem.squareLength
        if item.button == nil {
            recreateItem()
            return
        }
        configureButton()
        render()
    }

    func render() {
        item.isVisible = true
        item.length = NSStatusItem.squareLength
        guard let button = item.button else {
            if lastIconLog != "nil-button" {
                lastIconLog = "nil-button"
                AppLog.log("menubar status button is nil")
            }
            return
        }
        let mode = store.config.trayDisplayMode
        let (remaining, error) = StatusText.trayTemplateState(
            errorMessage: store.errorMessage,
            remainingPercent: store.usage?.remainingPercent
        )
        let image = MenubarIcon.image(remaining: remaining, error: error, mode: mode)
        button.title = ""
        button.imagePosition = .imageOnly
        button.imageScaling = .scaleNone
        button.image = image
        if let usage = store.usage {
            let label = store.config.activeAccount?.displayLabel ?? ""
            let pct = String(format: "%.0f%%", usage.remainingPercent)
            button.toolTip = label.isEmpty ? pct : "\(label) · \(pct)"
        } else {
            button.toolTip = "Token"
        }
        let key = "\(mode)|\(remaining.map { String(Int($0.rounded())) } ?? "nil")|\(error)"
        if key != lastIconLog {
            lastIconLog = key
            AppLog.log("menubar icon applied \(key) pt=\(MenubarIcon.pointSize())")
        }
        if store.flyoutVisible {
            FlyoutWindowController.shared.update(store: store)
        }
    }

    private static func makeStatusItem() -> NSStatusItem {
        // A previous build autosaved this extra as hidden; force it visible.
        UserDefaults.standard.set(true, forKey: "NSStatusItem Visible com.harker.cursortokentray.status")
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.isVisible = true
        return item
    }

    private func configureButton() {
        item.isVisible = true
        item.length = NSStatusItem.squareLength
        guard let button = item.button else { return }
        button.target = self
        button.action = #selector(clicked(_:))
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        button.imagePosition = .imageOnly
        button.imageScaling = .scaleNone
        button.title = ""
        if button.toolTip == nil {
            button.toolTip = "Cursor Token 剩余进度"
        }
    }

    private func recreateItem() {
        NSStatusBar.system.removeStatusItem(item)
        item = StatusItemController.makeStatusItem()
        configureButton()
        render()
        AppLog.log("menubar status item recreated")
    }

    private func scheduleAppearRetries() {
        retryTask?.cancel()
        retryTask = Task { [weak self] in
            // Sequoia/Tahoe often keep a "live" button that never attaches to
            // Control Center. Recreate the extra instead of only toggling isVisible.
            for delayNs: UInt64 in [250_000_000, 800_000_000, 2_000_000_000] {
                try? await Task.sleep(nanoseconds: delayNs)
                guard let self, !Task.isCancelled else { return }
                if self.item.button?.window == nil {
                    self.recreateItem()
                } else {
                    self.ensureVisible()
                }
            }
        }
    }

    @objc private func clicked(_ sender: Any?) {
        guard let event = NSApp.currentEvent else { return }
        if event.type == .rightMouseUp || event.modifierFlags.contains(.control) {
            showMenu()
            return
        }
        FlyoutWindowController.shared.toggle(store: store, statusButton: item.button)
    }

    private func showMenu() {
        FlyoutWindowController.shared.close()
        let menu = NSMenu()
        menu.addItem(withTitle: "显示状态", action: #selector(openStatus), keyEquivalent: "").target = self
        menu.addItem(withTitle: "立即刷新", action: #selector(refresh), keyEquivalent: "").target = self
        let web = NSMenuItem(title: UsageParser.dashboardMenuLabel(store.usage), action: #selector(openWeb), keyEquivalent: "")
        web.target = self
        menu.addItem(web)
        menu.addItem(withTitle: "用量报表…", action: #selector(openReport), keyEquivalent: "").target = self
        let switcher = NSMenuItem(title: "切换账号", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        let accounts = store.config.accounts
        if accounts.isEmpty {
            let empty = NSMenuItem(title: "暂无账号", action: nil, keyEquivalent: "")
            empty.isEnabled = false
            sub.addItem(empty)
        } else {
            for acc in accounts {
                var title = acc.displayLabel
                if let r = acc.lastRemaining { title += String(format: "  %.0f%%", r) }
                let item = NSMenuItem(title: title, action: #selector(switchAccount(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = acc.id
                item.state = acc.id == store.config.activeAccountId ? .on : .off
                sub.addItem(item)
            }
        }
        switcher.submenu = sub
        menu.addItem(switcher)
        menu.addItem(withTitle: "导入 Token…", action: #selector(importToken), keyEquivalent: "").target = self
        menu.addItem(withTitle: "设置…", action: #selector(openSettings), keyEquivalent: "").target = self
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(quit), keyEquivalent: "q").target = self
        guard let button = item.button else { return }
        menu.popUp(positioning: nil, at: NSPoint(x: 0, y: button.bounds.height + 2), in: button)
    }

    @objc private func openStatus() {
        FlyoutWindowController.shared.show(store: store, statusButton: item.button)
    }

    @objc private func refresh() { store.requestRefresh() }
    @objc private func openWeb() { store.openDashboard() }
    @objc private func openReport() { store.openReport() }
    @objc private func importToken() { store.openSettings(focusToken: true, startImport: true) }
    @objc private func openSettings() { store.openSettings() }
    @objc private func switchAccount(_ sender: NSMenuItem) {
        if let id = sender.representedObject as? String { store.switchAccount(id) }
    }

    @objc private func quit() {
        FlyoutWindowController.shared.close()
        SettingsWindowController.shared.close()
        ReportWindowController.shared.close()
        store.stop()
        NSApp.terminate(nil)
    }
}
