import Foundation

public enum AppLog {
    public static func log(_ message: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(stamp)] \(message)\n"
        let path = AppPaths.logPath()
        AppPaths.ensureDirectory(path.deletingLastPathComponent())
        if let handle = try? FileHandle(forWritingTo: path) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(line.utf8))
        } else {
            try? line.write(to: path, atomically: true, encoding: .utf8)
        }
        fputs(line, stderr)
    }
}
