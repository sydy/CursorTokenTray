import CursorTokenCore
import Foundation
import ServiceManagement

enum LoginItem {
    static func apply(_ enabled: Bool) {
        if #available(macOS 13.0, *) {
            do {
                if enabled {
                    try SMAppService.mainApp.register()
                } else {
                    try SMAppService.mainApp.unregister()
                }
                writeLegacyAgent(false)
                return
            } catch {
                AppLog.log("SMAppService failed: \(error.localizedDescription), fallback LaunchAgent")
            }
        }
        writeLegacyAgent(enabled)
    }

    static func writeLegacyAgent(_ enabled: Bool) {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/\(AppPaths.launchLabel).plist")
        if !enabled {
            try? FileManager.default.removeItem(at: plist)
            return
        }
        let exe = Bundle.main.executableURL?.path
            ?? CommandLine.arguments.first
            ?? "/usr/bin/true"
        let cwd = (Bundle.main.bundleURL.path.hasSuffix(".app")
            ? Bundle.main.bundleURL.deletingLastPathComponent().path
            : URL(fileURLWithPath: exe).deletingLastPathComponent().path)
        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>\(AppPaths.launchLabel)</string>
            <key>ProgramArguments</key>
            <array>
                <string>\(xmlEscape(exe))</string>
            </array>
            <key>WorkingDirectory</key>
            <string>\(xmlEscape(cwd))</string>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <false/>
            <key>ProcessType</key>
            <string>Interactive</string>
            <key>LimitLoadToSessionType</key>
            <string>Aqua</string>
        </dict>
        </plist>
        """
        try? FileManager.default.createDirectory(at: plist.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? xml.write(to: plist, atomically: true, encoding: .utf8)
    }

    static func xmlEscape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }
}
