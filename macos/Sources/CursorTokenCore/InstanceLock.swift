import Darwin
import Foundation

public enum InstanceLock {
    public static func acquire(directory: URL? = nil) -> Bool {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        let lockURL = dir.appendingPathComponent("instance.lock")
        let pidURL = dir.appendingPathComponent("instance.pid")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o644)
        if fd < 0 { return true }
        if flock(fd, LOCK_EX | LOCK_NB) != 0 {
            close(fd)
            return false
        }
        acquiredFD = fd
        try? "\(ProcessInfo.processInfo.processIdentifier)".write(to: pidURL, atomically: true, encoding: .utf8)
        return true
    }

    public static func release(directory: URL? = nil) {
        if let fd = acquiredFD {
            flock(fd, LOCK_UN)
            close(fd)
            acquiredFD = nil
        }
        let dir = directory ?? AppPaths.configDirectory()
        try? FileManager.default.removeItem(at: dir.appendingPathComponent("instance.pid"))
    }

    private static var acquiredFD: Int32?
}
