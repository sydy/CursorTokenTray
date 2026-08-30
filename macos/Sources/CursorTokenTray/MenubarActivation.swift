import AppKit
import CursorTokenCore

/// Menu-bar agent: Dock tile only while Settings / Report is on screen.
///
/// Switching `.regular` → `.accessory` from `windowWillClose` often no-ops on
/// macOS 14+: the closing window is still visible, `setActivationPolicy`
/// returns false, and a zombie Dock icon remains. Restore only after the
/// window is gone, and yield frontmost so Dock actually drops the tile.
@MainActor
enum MenubarActivation {
    static func promoteForWindow() {
        _ = NSApp.setActivationPolicy(.regular)
        NSApp.unhide(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Call from Cancel / 保存 / `windowShouldClose` after `orderOut`.
    static func restoreNow(excluding closing: NSWindow? = nil) {
        if hasDockKeepingWindow(excluding: closing) { return }
        hideDockIcon()
    }

    /// `windowWillClose` fires while the window is still visible; wait a turn.
    static func restoreAfterClosing(_ closing: NSWindow? = nil) {
        Task { @MainActor in
            restoreNow(excluding: closing)
        }
    }

    private static func hasDockKeepingWindow(excluding closing: NSWindow? = nil) -> Bool {
        NSApp.windows.contains { window in
            isDockKeepingWindow(window, excluding: closing)
        }
    }

    private static func isDockKeepingWindow(_ window: NSWindow, excluding closing: NSWindow? = nil) -> Bool {
        if let closing, window === closing { return false }
        if window is NSPanel { return false }
        if !window.styleMask.contains(.titled) { return false }
        if window.level != .normal { return false }
        return window.isVisible || window.isMiniaturized
    }

    private static func hideDockIcon() {
        if NSApp.activationPolicy() == .accessory {
            AppDelegate.ensureStatusItemVisible()
            return
        }
        // Hide yields to the previous app so Dock drops the tile, then
        // unhideWithoutActivation clears NSApp.isHidden so the flyout still
        // opens. Stay accessory the whole time or the tile comes back.
        applyAccessory()
        NSApp.hide(nil)
        NSApp.unhideWithoutActivation()
        NSApp.deactivate()
        AppDelegate.ensureStatusItemVisible()
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 200_000_000)
            if NSApp.activationPolicy() != .accessory {
                applyAccessory()
                NSApp.deactivate()
            }
            AppDelegate.ensureStatusItemVisible()
        }
    }

    @discardableResult
    private static func applyAccessory() -> Bool {
        let applied = NSApp.setActivationPolicy(.accessory)
        AppLog.log("activation policy -> accessory applied=\(applied)")
        if applied { return true }
        Task { @MainActor in
            let retry = NSApp.setActivationPolicy(.accessory)
            AppLog.log("activation policy accessory retry applied=\(retry)")
        }
        return false
    }
}
