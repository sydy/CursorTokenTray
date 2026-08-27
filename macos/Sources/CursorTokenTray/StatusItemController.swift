import AppKit
import Combine
import CursorTokenCore
import SwiftUI

@MainActor
final class StatusItemController: NSObject {
    private let store: AppStore
    private let item: NSStatusItem
    private var cancellable: AnyCancellable?

    init(store: AppStore) {
        self.store = store
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        super.init()
        item.button?.target = self
        item.button?.action = #selector(clicked(_:))
        item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
        item.button?.imagePosition = .imageOnly
        item.button?.toolTip = "Cursor Token 剩余进度"
        render()
        cancellable = store.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async { self?.render() }
        }
    }

    func render() {
        let mode = store.config.trayDisplayMode
        let remaining: Double?
        let error: Bool
        if let err = store.errorMessage, err.hasPrefix("未配置") {
            remaining = nil
            error = false
        } else if store.errorMessage != nil {
            remaining = nil
            error = true
        } else {
            remaining = store.usage?.remainingPercent
            error = false
        }
        item.button?.image = MenubarIcon.image(remaining: remaining, error: error, mode: mode)
        if let usage = store.usage {
            let label = store.config.activeAccount?.displayLabel ?? ""
            let pct = String(format: "%.0f%%", usage.remainingPercent)
            item.button?.toolTip = label.isEmpty ? pct : "\(label) · \(pct)"
        } else {
            item.button?.toolTip = "Token"
        }
        if store.flyoutVisible {
            FlyoutWindowController.shared.update(store: store)
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
    @objc private func importToken() { store.openSettings(focusToken: true, startImport: true) }
    @objc private func openSettings() { store.openSettings() }
    @objc private func switchAccount(_ sender: NSMenuItem) {
        if let id = sender.representedObject as? String { store.switchAccount(id) }
    }

    @objc private func quit() {
        FlyoutWindowController.shared.close()
        SettingsWindowController.shared.close()
        store.stop()
        NSApp.terminate(nil)
    }
}
