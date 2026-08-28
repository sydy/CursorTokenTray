import AppKit
import CursorTokenCore
import SwiftUI

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private(set) var store: AppStore!
    var statusItem: StatusItemController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppLog.log("swift menubar start pid=\(ProcessInfo.processInfo.processIdentifier)")
        if !InstanceLock.acquireReplacingStale() {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            let alert = NSAlert()
            alert.messageText = "已在后台运行"
            alert.informativeText = "Cursor Token 剩余进度已经在菜单栏运行。若看不到图标，请打开「活动监视器」结束 CursorTokenTray 后再打开本程序。也可点菜单栏「•••」展开隐藏项。"
            alert.runModal()
            NSApp.terminate(nil)
            return
        }
        NSApp.setActivationPolicy(.accessory)
        let store = AppStore()
        self.store = store
        statusItem = StatusItemController(store: store)
        store.start()
        AppLog.log("swift menubar status item installed")
        Task { @MainActor in
            self.statusItem?.ensureVisible()
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        statusItem?.ensureVisible()
    }

    func applicationDidChangeScreenParameters(_ notification: Notification) {
        statusItem?.ensureVisible()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        statusItem?.ensureVisible()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        store?.stop()
        InstanceLock.release()
    }

    static func ensureStatusItemVisible() {
        (NSApp.delegate as? AppDelegate)?.statusItem?.ensureVisible()
    }
}
