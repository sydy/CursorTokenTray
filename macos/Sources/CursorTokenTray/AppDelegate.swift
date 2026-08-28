import AppKit
import CursorTokenCore
import SwiftUI

@main
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private(set) var store: AppStore!
    var statusItem: StatusItemController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppLog.log("swift menubar start")
        NSApp.setActivationPolicy(.accessory)
        if !InstanceLock.acquire() {
            let alert = NSAlert()
            alert.messageText = "已在后台运行"
            alert.informativeText = "Cursor Token 剩余进度已经在菜单栏运行。"
            alert.runModal()
            NSApp.terminate(nil)
            return
        }
        let store = AppStore()
        self.store = store
        // Next run-loop turn: the menu bar extra host is up. Creating the
        // status item in this method (especially as a login item) can yield
        // an extra that never appears.
        Task { @MainActor in
            await Task.yield()
            self.statusItem = StatusItemController(store: store)
            store.start()
            AppLog.log("swift menubar status item installed")
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        statusItem?.ensureVisible()
    }

    func applicationWillTerminate(_ notification: Notification) {
        store?.stop()
        InstanceLock.release()
    }

    static func ensureStatusItemVisible() {
        (NSApp.delegate as? AppDelegate)?.statusItem?.ensureVisible()
    }
}
