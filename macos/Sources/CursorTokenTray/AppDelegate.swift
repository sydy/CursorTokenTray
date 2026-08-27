import AppKit
import CursorTokenCore
import SwiftUI

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    let store = AppStore()
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
        statusItem = StatusItemController(store: store)
        store.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        store.stop()
        InstanceLock.release()
    }
}
