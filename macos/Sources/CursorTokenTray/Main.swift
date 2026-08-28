import AppKit
import CursorTokenCore

/// Swift `@main` on `NSApplicationDelegate` only calls `NSApplicationMain`.
/// Without a MainMenu nib, the delegate is never created, so the process
/// sits in the menu bar host with no extra. Keep a strong retain: `NSApplication.delegate` is weak.
@main
@MainActor
enum CursorTokenTrayMain {
    private static var retainedDelegate: AppDelegate?

    static func main() {
        AppLog.log("swift process main pid=\(ProcessInfo.processInfo.processIdentifier)")
        let app = NSApplication.shared
        let delegate = AppDelegate()
        retainedDelegate = delegate
        app.setActivationPolicy(.accessory)
        app.delegate = delegate
        app.run()
    }
}
