import Foundation

#if canImport(SQLite3)
import SQLite3
#endif

public struct CursorInstall: Equatable, Sendable {
    public var name: String
    public var stateDb: URL
    public var launchPath: URL?

    public init(name: String, stateDb: URL, launchPath: URL? = nil) {
        self.name = name
        self.stateDb = stateDb
        self.launchPath = launchPath
    }
}

public struct CursorAuthApplyResult: Equatable, Sendable {
    public var ok: Bool
    public var message: String
    public var backupPath: String?
    public var keysWritten: Int
    public var installName: String?
    public var relaunched: Bool

    public init(
        ok: Bool,
        message: String,
        backupPath: String? = nil,
        keysWritten: Int = 0,
        installName: String? = nil,
        relaunched: Bool = false
    ) {
        self.ok = ok
        self.message = message
        self.backupPath = backupPath
        self.keysWritten = keysWritten
        self.installName = installName
        self.relaunched = relaunched
    }
}

public enum CursorAuth {
    public static let backupSuffix = ".tray-backup"
    public static let webTokenMessage =
        "浏览器 Cookie（JWT type=web）不能登录 Cursor 应用，写回去会把客户端登出。"
        + "请先在 Cursor 里登录该账号，再点「从 Cursor 导入」，之后才能写回切换。"
    public static let notJwtMessage = "当前 Token 不是 Cursor 会话，无法写入客户端。请先从 Cursor 应用导入。"
    public static let confirmCloseMessage =
        "会先关闭 Cursor，再把当前账号写入客户端。请先保存未提交的改动。未保存的文件不会被强制结束。"

    public static let ownedKeys = [
        "cursorAuth/accessToken",
        "cursorAuth/refreshToken",
        "cursorAuth/cachedEmail",
        "cursorAuth/cachedSignUpType",
        "cursorAuth/cachedScopedProfile",
        "cursorAuth/stripeMembershipType",
        "cursorAuth/stripeSubscriptionStatus",
        "glass.lastSignedInAuthId",
    ]
    public static let optionalUpdateKeys = ["cursorAuth/cachedAccessToken"]

    public static func canWrite(_ token: String) -> Bool { Token.canWriteToCursor(token) }

    public static func buildValues(
        token: String,
        email: String? = nil,
        membershipType: String? = nil,
        displayName: String? = nil
    ) -> (values: [String: String]?, error: String) {
        let jwt = Token.extractJWT(token)
        if !Token.looksLikeJWT(jwt) {
            return (nil, notJwtMessage)
        }
        if Token.jwtType(jwt) == "web" {
            return (nil, webTokenMessage)
        }
        var values: [String: String] = [
            "cursorAuth/accessToken": jwt,
            "cursorAuth/refreshToken": jwt,
            "cursorAuth/cachedSignUpType": "Auth_0",
        ]
        var sub = Token.jwtSubject(jwt).trimmingCharacters(in: .whitespaces)
        if sub.isEmpty {
            let uid = Token.accountId(from: token)
            if !uid.isEmpty && !uid.hasPrefix("tok_") {
                sub = "auth0|\(uid)"
            }
        }
        if !sub.isEmpty { values["glass.lastSignedInAuthId"] = sub }

        let mail = firstNonEmpty(Token.jwtClaim(jwt, "email"), email)
        if looksLikeEmail(mail) { values["cursorAuth/cachedEmail"] = mail.trimmingCharacters(in: .whitespaces) }

        let name = firstNonEmpty(displayName, mail)
        if !name.trimmingCharacters(in: .whitespaces).isEmpty {
            let profile = ["displayName": name.trimmingCharacters(in: .whitespaces)]
            if let data = try? JSONSerialization.data(withJSONObject: profile),
               let json = String(data: data, encoding: .utf8)
            {
                values["cursorAuth/cachedScopedProfile"] = json
            }
        }

        let plan = stripePlan(membershipType)
        if !plan.membership.isEmpty {
            values["cursorAuth/stripeMembershipType"] = plan.membership
            values["cursorAuth/stripeSubscriptionStatus"] = plan.status
        }
        return (values, "")
    }

    public static func stripePlan(_ membershipType: String?) -> (membership: String, status: String) {
        let raw = (membershipType ?? "").trimmingCharacters(in: .whitespaces)
        if raw.isEmpty || raw == "未知" { return ("", "") }
        let lower = raw.lowercased()
        var key = ""
        switch lower {
        case "pro": key = "pro"
        case "pro+", "pro_plus": key = "pro_plus"
        case "ultra": key = "ultra"
        case "free", "hobby", "unpaid": key = "free"
        case "enterprise", "enterprise_trial": key = lower
        case "team", "teams": key = "team"
        case "business": key = "business"
        default:
            switch raw.lowercased() {
            case "pro": key = "pro"
            case "pro+": key = "pro_plus"
            case "ultra": key = "ultra"
            case "free", "hobby": key = "free"
            case "enterprise": key = "enterprise"
            case "team": key = "team"
            case "business": key = "business"
            default: key = lower
            }
        }
        let unpaid = ["free", "hobby", "unpaid"].contains(key)
        return (unpaid ? "free" : key, unpaid ? "unpaid" : "active")
    }

    public static func readValues(dbPath: URL, keys: [String]? = nil) -> [String: String] {
        var found: [String: String] = [:]
        guard FileManager.default.fileExists(atPath: dbPath.path) else { return found }
        let want = Set(keys ?? ownedKeys + optionalUpdateKeys)
        #if canImport(SQLite3)
        var db: OpaquePointer?
        guard sqlite3_open_v2(dbPath.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK, let db else { return found }
        defer { sqlite3_close(db) }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT key, value FROM ItemTable", -1, &stmt, nil) == SQLITE_OK, let stmt else {
            return found
        }
        defer { sqlite3_finalize(stmt) }
        while sqlite3_step(stmt) == SQLITE_ROW {
            let key = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            guard want.contains(key) else { continue }
            let value = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            if !key.isEmpty { found[key] = value }
        }
        #endif
        return found
    }

    public static func writeValues(dbPath: URL, values: [String: String], backup: Bool = true) -> CursorAuthApplyResult {
        guard FileManager.default.fileExists(atPath: dbPath.path) else {
            return CursorAuthApplyResult(ok: false, message: "未找到 Cursor 状态库，请先至少启动并登录过一次 Cursor。")
        }
        guard !values.isEmpty else {
            return CursorAuthApplyResult(ok: false, message: "没有可写入的登录态。")
        }
        var backupPath: String?
        if backup {
            do { backupPath = try Self.backup(dbPath: dbPath) }
            catch {
                return CursorAuthApplyResult(ok: false, message: "备份 Cursor 状态库失败，已中止写入：\(error.localizedDescription)")
            }
        }
        #if canImport(SQLite3)
        var db: OpaquePointer?
        guard sqlite3_open_v2(dbPath.path, &db, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK, let db else {
            return CursorAuthApplyResult(ok: false, message: "无法打开 Cursor 状态库。", backupPath: backupPath)
        }
        defer { sqlite3_close(db) }
        sqlite3_busy_timeout(db, 5000)
        guard sqlite3_exec(db, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK else {
            return CursorAuthApplyResult(ok: false, message: "无法开始写入 Cursor 状态库。", backupPath: backupPath)
        }
        var existing = Set<String>()
        var list: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT key FROM ItemTable", -1, &list, nil) == SQLITE_OK, let list {
            defer { sqlite3_finalize(list) }
            while sqlite3_step(list) == SQLITE_ROW {
                if let c = sqlite3_column_text(list, 0) { existing.insert(String(cString: c)) }
            }
        }
        let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "INSERT OR REPLACE INTO ItemTable(key, value) VALUES (?, ?)", -1, &stmt, nil) == SQLITE_OK, let stmt else {
            sqlite3_exec(db, "ROLLBACK", nil, nil, nil)
            return CursorAuthApplyResult(ok: false, message: "无法准备写入 Cursor 状态库。", backupPath: backupPath)
        }
        defer { sqlite3_finalize(stmt) }
        var written = 0
        func bind(_ key: String, _ value: String) -> Bool {
            sqlite3_reset(stmt)
            sqlite3_clear_bindings(stmt)
            key.withCString { kptr in
                _ = sqlite3_bind_text(stmt, 1, kptr, -1, sqliteTransient)
            }
            value.withCString { vptr in
                _ = sqlite3_bind_text(stmt, 2, vptr, -1, sqliteTransient)
            }
            return sqlite3_step(stmt) == SQLITE_DONE
        }
        for key in ownedKeys {
            guard let value = values[key], !value.isEmpty else { continue }
            if !bind(key, value) {
                sqlite3_exec(db, "ROLLBACK", nil, nil, nil)
                return CursorAuthApplyResult(ok: false, message: "写入 Cursor 状态库失败。", backupPath: backupPath)
            }
            written += 1
        }
        if let jwt = values["cursorAuth/accessToken"], !jwt.isEmpty {
            for key in optionalUpdateKeys where existing.contains(key) {
                if bind(key, jwt) { written += 1 }
            }
        }
        if sqlite3_exec(db, "COMMIT", nil, nil, nil) != SQLITE_OK {
            sqlite3_exec(db, "ROLLBACK", nil, nil, nil)
            return CursorAuthApplyResult(ok: false, message: "提交 Cursor 状态库失败。", backupPath: backupPath)
        }
        return CursorAuthApplyResult(ok: true, message: "已写入 Cursor（\(written) 项）", backupPath: backupPath, keysWritten: written)
        #else
        return CursorAuthApplyResult(ok: false, message: "当前环境无法写入 SQLite。", backupPath: backupPath)
        #endif
    }

    public static func backup(dbPath: URL) throws -> String {
        let dest = URL(fileURLWithPath: dbPath.path + backupSuffix)
        let fm = FileManager.default
        if fm.fileExists(atPath: dest.path) { try fm.removeItem(at: dest) }
        try fm.copyItem(at: dbPath, to: dest)
        for suffix in ["-wal", "-shm"] {
            let side = URL(fileURLWithPath: dbPath.path + suffix)
            if fm.fileExists(atPath: side.path) {
                let sideDest = URL(fileURLWithPath: dest.path + suffix)
                try? fm.removeItem(at: sideDest)
                try? fm.copyItem(at: side, to: sideDest)
            }
        }
        return dest.path
    }

    public static func findInstalls(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [CursorInstall] {
        #if os(macOS)
        let support = home.appendingPathComponent("Library/Application Support")
        let apps = [
            ("Cursor", "Cursor", "/Applications/Cursor.app"),
            ("Cursor Nightly", "Cursor Nightly", "/Applications/Cursor Nightly.app"),
            ("Cursor Insiders", "Cursor - Insiders", "/Applications/Cursor - Insiders.app"),
        ]
        var found: [CursorInstall] = []
        for (name, folder, launch) in apps {
            let db = support.appendingPathComponent("\(folder)/User/globalStorage/state.vscdb")
            guard FileManager.default.fileExists(atPath: db.path) else { continue }
            let app = URL(fileURLWithPath: launch)
            found.append(CursorInstall(
                name: name,
                stateDb: db,
                launchPath: FileManager.default.fileExists(atPath: app.path) ? app : nil
            ))
        }
        return found
        #else
        _ = home
        return []
        #endif
    }

    public static func resolveTarget(_ installs: [CursorInstall]? = nil) -> CursorInstall? {
        let list = installs ?? findInstalls()
        if list.isEmpty { return nil }
        for inst in list where isRunning(inst) { return inst }
        return list[0]
    }

    public static func isRunning(_ install: CursorInstall) -> Bool {
        !runningPids(install).isEmpty
    }

    public static func requestClose(_ install: CursorInstall) -> Bool {
        let appName = install.name
        _ = run("/usr/bin/osascript", arguments: ["-e", "tell application \"\(appName)\" to quit"])
        let pids = runningPids(install)
        if pids.isEmpty { return true }
        for pid in pids {
            _ = run("/bin/kill", arguments: ["-TERM", String(pid)])
        }
        return true
    }

    public static func waitUntilGone(_ install: CursorInstall, timeout: TimeInterval = 10) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !isRunning(install) { return true }
            Thread.sleep(forTimeInterval: 0.25)
        }
        return !isRunning(install)
    }

    public static func launch(_ install: CursorInstall) -> Bool {
        if let url = install.launchPath, FileManager.default.fileExists(atPath: url.path) {
            return run("/usr/bin/open", arguments: [url.path]).0 == 0
        }
        return run("/usr/bin/open", arguments: ["-a", install.name]).0 == 0
    }

    public static func apply(
        token: String,
        email: String? = nil,
        membershipType: String? = nil,
        displayName: String? = nil,
        closeIfRunning: Bool = true,
        relaunch: Bool = true,
        wait: TimeInterval = 10,
        installs: [CursorInstall]? = nil,
        isRunning: ((CursorInstall) -> Bool)? = nil,
        requestClose: ((CursorInstall) -> Bool)? = nil,
        waitGone: ((CursorInstall) -> Bool)? = nil,
        launch: ((CursorInstall) -> Bool)? = nil,
        write: ((URL, [String: String], Bool) -> CursorAuthApplyResult)? = nil
    ) -> CursorAuthApplyResult {
        let built = buildValues(token: token, email: email, membershipType: membershipType, displayName: displayName)
        guard let values = built.values else {
            return CursorAuthApplyResult(ok: false, message: built.error)
        }
        guard let target = resolveTarget(installs) else {
            return CursorAuthApplyResult(ok: false, message: "未找到 Cursor 状态库，请先至少启动并登录过一次 Cursor。")
        }
        let runningFn = isRunning ?? Self.isRunning
        let closeFn = requestClose ?? Self.requestClose
        let goneFn = waitGone ?? { Self.waitUntilGone($0, timeout: wait) }
        let launchFn = launch ?? Self.launch
        let writeFn = write ?? { Self.writeValues(dbPath: $0, values: $1, backup: $2) }

        if runningFn(target) {
            if !closeIfRunning {
                return CursorAuthApplyResult(ok: false, message: "Cursor 正在运行。请先关闭后再写入，以免冲掉未保存的文件。", installName: target.name)
            }
            _ = closeFn(target)
            if !goneFn(target) {
                return CursorAuthApplyResult(
                    ok: false,
                    message: "Cursor 没有退出（可能有未保存的改动）。请先手动关闭后再试，不会强制结束。",
                    installName: target.name
                )
            }
        }
        var written = writeFn(target.stateDb, values, true)
        if !written.ok {
            written.installName = target.name
            return written
        }
        var started = false
        if relaunch { started = launchFn(target) }
        var msg = written.message + " · " + target.name
        if relaunch {
            msg += started ? "，已重新打开。" : "。请手动打开 Cursor。"
        } else {
            msg += "。请重新打开 Cursor 后生效。"
        }
        written.message = msg
        written.installName = target.name
        written.relaunched = started
        return written
    }

    public static func looksLikeEmail(_ value: String?) -> Bool {
        let text = (value ?? "").trimmingCharacters(in: .whitespaces)
        guard let at = text.firstIndex(of: "@") else { return false }
        return at > text.startIndex && text.distance(from: at, to: text.endIndex) > 1 && !text.contains(" ")
    }

    static func runningPids(_ install: CursorInstall) -> [Int32] {
        let needle: String
        if install.name.contains("Nightly") {
            needle = "Cursor Nightly.app/Contents/MacOS"
        } else if install.name.contains("Insiders") {
            needle = "Cursor - Insiders.app/Contents/MacOS"
        } else {
            needle = "Cursor.app/Contents/MacOS"
        }
        let (status, output) = run("/usr/bin/pgrep", arguments: ["-f", needle])
        if status != 0 { return [] }
        return output.split(whereSeparator: \.isNewline).compactMap { Int32($0.trimmingCharacters(in: .whitespaces)) }
    }

    static func run(_ launchPath: String, arguments: [String]) -> (Int32, String) {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: launchPath)
        proc.arguments = arguments
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()
        do {
            try proc.run()
            proc.waitUntilExit()
        } catch {
            return (1, "")
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let text = String(data: data, encoding: .utf8) ?? ""
        return (proc.terminationStatus, text)
    }

    static func firstNonEmpty(_ values: String?...) -> String {
        for value in values {
            if let value, !value.trimmingCharacters(in: .whitespaces).isEmpty { return value }
        }
        return ""
    }
}
