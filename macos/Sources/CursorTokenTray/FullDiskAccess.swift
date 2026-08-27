import AppKit
import Foundation

enum FullDiskAccess {
    static func safariCookiesReadable() -> Bool {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let candidates = [
            home.appendingPathComponent("Library/Cookies/Cookies.binarycookies"),
            home.appendingPathComponent("Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"),
            home.appendingPathComponent("Library/Safari"),
        ]
        var sawExisting = false
        for url in candidates {
            var isDir: ObjCBool = false
            guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir) else { continue }
            sawExisting = true
            if FileManager.default.isReadableFile(atPath: url.path) { return true }
            if isDir.boolValue,
               (try? FileManager.default.contentsOfDirectory(atPath: url.path)) != nil
            {
                return true
            }
        }
        if !sawExisting {
            let safari = home.appendingPathComponent("Library/Safari")
            return (try? FileManager.default.contentsOfDirectory(atPath: safari.path)) != nil
                || !FileManager.default.fileExists(atPath: safari.path)
        }
        return false
    }

    static func openPrivacySettings() {
        let urls = [
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
        ]
        for raw in urls {
            if let url = URL(string: raw), NSWorkspace.shared.open(url) { return }
        }
    }
}
