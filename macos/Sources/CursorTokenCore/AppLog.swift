import Foundation

public enum AppLog {
    static let maxBytes = 512 * 1024

    public static func log(_ message: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(stamp)] \(message)\n"
        let path = AppPaths.logPath()
        AppPaths.ensureDirectory(path.deletingLastPathComponent())
        if let handle = try? FileHandle(forWritingTo: path) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(line.utf8))
            if let size = try? handle.offset(), size > maxBytes {
                rotate(path)
            }
        } else {
            try? line.write(to: path, atomically: true, encoding: .utf8)
        }
        fputs(line, stderr)
    }

    static func rotate(_ path: URL) {
        guard let data = try? Data(contentsOf: path), data.count > maxBytes / 2 else { return }
        let kept = data.suffix(maxBytes / 2)
        try? kept.write(to: path, options: [.atomic])
    }
}
