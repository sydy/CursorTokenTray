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
        statusItem = StatusItemController(store: store)
        store.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        store?.stop()
        InstanceLock.release()
    }
}
