import Foundation

#if canImport(SQLite3)
import SQLite3
#endif

public struct CookieCandidate: Equatable, Sendable {
    public var browser: String
    public var profile: String
    public var token: String
    public var lastUpdate: Int

    public init(browser: String, profile: String, token: String, lastUpdate: Int) {
        self.browser = browser
        self.profile = profile
        self.token = token
        self.lastUpdate = lastUpdate
    }
}

public struct ImportResult: Equatable, Sendable {
    public var ok: Bool
    public var token: String
    public var browser: String
    public var profile: String
    public var remainingPercent: Double?
    public var membershipType: String
    public var message: String

    public init(
        ok: Bool,
        token: String = "",
        browser: String = "",
        profile: String = "",
        remainingPercent: Double? = nil,
        membershipType: String = "",
        message: String = ""
    ) {
        self.ok = ok
        self.token = token
        self.browser = browser
        self.profile = profile
        self.remainingPercent = remainingPercent
        self.membershipType = membershipType
        self.message = message
    }
}

public enum SessionImporter {
    public static let cookieName = Token.cookieName
    public static let cookieHostHints = ["cursor.com", "cursor.sh"]

    public static func defaultPreferBrowsers(_ prefer: String? = nil) -> [String] {
        let firefoxFirst = ["firefox", "firefox-dev", "firefox-nightly", "librewolf", "waterfox", "zen"]
        let cursorFirst = ["cursor-app"]
        if prefer == "safari" { return cursorFirst + ["safari"] + firefoxFirst + ["edge", "chrome", "brave", "arc"] }
        if firefoxFirst.contains(prefer ?? "") {
            return cursorFirst + firefoxFirst + ["safari", "edge", "chrome", "brave", "arc"]
        }
        if prefer == "cursor-app" {
            return cursorFirst + ["safari"] + firefoxFirst + ["edge", "chrome", "brave", "arc"]
        }
        #if os(macOS)
        return cursorFirst + ["safari"] + firefoxFirst + ["edge", "chrome", "brave", "arc"]
        #else
        return cursorFirst + firefoxFirst + ["edge", "chrome"]
        #endif
    }

    public static func onlyBrowsers(for prefer: String?) -> [String]? {
        let firefox = ["firefox", "firefox-dev", "firefox-nightly", "librewolf", "waterfox", "zen"]
        if let prefer, firefox.contains(prefer) { return firefox }
        if prefer == "safari" { return ["safari"] }
        if prefer == "cursor-app" { return ["cursor-app"] }
        return nil
    }

    public static func preferredMacAppNames(_ prefer: String?) -> [String] {
        switch prefer {
        case "safari": return ["Safari"]
        case "firefox", "firefox-dev", "firefox-nightly": return ["Firefox"]
        default: return ["Safari", "Firefox"]
        }
    }

    public static func cursorStateDBPaths(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [URL] {
        #if os(macOS)
        let support = home.appendingPathComponent("Library/Application Support")
        return [
            support.appendingPathComponent("Cursor/User/globalStorage/state.vscdb"),
            support.appendingPathComponent("Cursor Nightly/User/globalStorage/state.vscdb"),
            support.appendingPathComponent("Cursor - Insiders/User/globalStorage/state.vscdb"),
        ]
        #else
        let appdata = ProcessInfo.processInfo.environment["APPDATA"].flatMap { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? home.appendingPathComponent("AppData/Roaming")
        return [
            appdata.appendingPathComponent("Cursor/User/globalStorage/state.vscdb"),
            appdata.appendingPathComponent("Cursor Nightly/User/globalStorage/state.vscdb"),
        ]
        #endif
    }

    public static func readCursorAccessToken(dbPath: URL) -> String? {
        guard FileManager.default.fileExists(atPath: dbPath.path) else { return nil }
        #if canImport(SQLite3)
        var db: OpaquePointer?
        guard sqlite3_open_v2(dbPath.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK, let db else {
            return nil
        }
        defer { sqlite3_close(db) }
        for key in ["cursorAuth/accessToken", "cursorAuth/cachedAccessToken"] {
            let sql = "SELECT value FROM ItemTable WHERE key = ? LIMIT 1"
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else { continue }
            defer { sqlite3_finalize(stmt) }
            sqlite3_bind_text(stmt, 1, (key as NSString).utf8String, -1, nil)
            if sqlite3_step(stmt) == SQLITE_ROW, let cstr = sqlite3_column_text(stmt, 0) {
                let value = String(cString: cstr).trimmingCharacters(in: .whitespacesAndNewlines)
                if !value.isEmpty { return value }
            }
        }
        #endif
        return nil
    }

    public static func safeNormalize(_ raw: String) -> String? {
        guard let token = try? Token.normalize(raw), isPlausible(token) else { return nil }
        return token
    }

    public static func isPlausible(_ value: String) -> Bool {
        let t = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.count < 20 { return false }
        return t.unicodeScalars.allSatisfy { $0.value >= 0x21 && $0.value <= 0x7E }
    }

    public static func findCursorAppCandidates(paths: [URL]? = nil) -> [CookieCandidate] {
        var found: [CookieCandidate] = []
        for path in paths ?? cursorStateDBPaths() {
            guard let jwt = readCursorAccessToken(dbPath: path), let token = safeNormalize(jwt) else { continue }
            let mtime = (try? path.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate?.timeIntervalSince1970) ?? 0
            found.append(CookieCandidate(
                browser: "cursor-app",
                profile: path.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().lastPathComponent,
                token: token,
                lastUpdate: Int(mtime * 1_000_000)
            ))
        }
        return found
    }

    public static func firefoxProductRoots(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [(String, URL)] {
        #if os(macOS)
        let support = home.appendingPathComponent("Library/Application Support")
        let roots: [(String, URL)] = [
            ("firefox", support.appendingPathComponent("Firefox")),
            ("firefox-dev", support.appendingPathComponent("Firefox Developer Edition")),
            ("firefox-nightly", support.appendingPathComponent("Firefox Nightly")),
            ("librewolf", support.appendingPathComponent("LibreWolf")),
            ("waterfox", support.appendingPathComponent("Waterfox")),
            ("zen", support.appendingPathComponent("zen")),
        ]
        #else
        let appdata = ProcessInfo.processInfo.environment["APPDATA"].flatMap { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? home.appendingPathComponent("AppData/Roaming")
        let roots: [(String, URL)] = [
            ("firefox", appdata.appendingPathComponent("Mozilla/Firefox")),
            ("firefox-dev", appdata.appendingPathComponent("Mozilla/Firefox Developer Edition")),
            ("firefox-nightly", appdata.appendingPathComponent("Mozilla/Firefox Nightly")),
            ("librewolf", appdata.appendingPathComponent("librewolf")),
            ("waterfox", appdata.appendingPathComponent("Waterfox")),
            ("zen", appdata.appendingPathComponent("zen")),
        ]
        #endif
        return roots.filter { FileManager.default.fileExists(atPath: $0.1.path) }
    }

    public static func iterFirefoxProfiles(support: URL) -> [URL] {
        var profiles: [URL] = []
        var seen = Set<String>()
        func add(_ path: URL) {
            let key = path.standardizedFileURL.path
            if seen.contains(key) { return }
            seen.insert(key)
            if FileManager.default.fileExists(atPath: path.appendingPathComponent("cookies.sqlite").path) {
                profiles.append(path)
            }
        }
        for iniName in ["profiles.ini", "installs.ini"] {
            let ini = support.appendingPathComponent(iniName)
            guard let text = try? String(contentsOf: ini, encoding: .utf8) else { continue }
            var current = ""
            var fields: [String: String] = [:]
            func flush() {
                let section = current.lowercased()
                guard section.hasPrefix("profile") || section.hasPrefix("install") else { return }
                let key = section.hasPrefix("profile") ? "Path" : "Default"
                let rel = (fields[key] ?? "").trimmingCharacters(in: .whitespaces)
                if rel.isEmpty { return }
                let isRel = (fields["IsRelative"] ?? "1").trimmingCharacters(in: .whitespaces) != "0"
                add(isRel ? support.appendingPathComponent(rel) : URL(fileURLWithPath: rel))
            }
            for line in text.split(whereSeparator: \.isNewline).map(String.init) {
                let t = line.trimmingCharacters(in: .whitespaces)
                if t.hasPrefix("[") && t.hasSuffix("]") {
                    flush()
                    current = String(t.dropFirst().dropLast())
                    fields = [:]
                    continue
                }
                if let eq = t.firstIndex(of: "=") {
                    fields[String(t[..<eq])] = String(t[t.index(after: eq)...])
                }
            }
            flush()
        }
        let root = support.appendingPathComponent("Profiles")
        if let children = try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
            for child in children.sorted(by: { $0.path < $1.path }) where child.hasDirectoryPath {
                add(child)
            }
        }
        return profiles
    }

    public static func readFirefoxCookieRows(dbPath: URL) -> [(String, String, Int)] {
        #if canImport(SQLite3)
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("cursor_tray_ffcookies_\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let dst = tmp.appendingPathComponent("cookies.sqlite")
        try? FileManager.default.copyItem(at: dbPath, to: dst)
        for suffix in ["-wal", "-shm"] {
            let side = URL(fileURLWithPath: dbPath.path + suffix)
            if FileManager.default.fileExists(atPath: side.path) {
                try? FileManager.default.copyItem(at: side, to: URL(fileURLWithPath: dst.path + suffix))
            }
        }
        var db: OpaquePointer?
        guard sqlite3_open(dst.path, &db) == SQLITE_OK, let db else { return [] }
        defer { sqlite3_close(db) }
        let sql = "SELECT host, value, lastAccessed FROM moz_cookies WHERE name = ?"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else { return [] }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, (cookieName as NSString).utf8String, -1, nil)
        var rows: [(String, String, Int)] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let host = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let value = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            let last = Int(sqlite3_column_int64(stmt, 2))
            rows.append((host, value, last))
        }
        return rows
        #else
        return []
        #endif
    }

    public static func parseSafariBinaryCookies(_ path: URL) throws -> [(String, String, String, Int)] {
        let data = try Data(contentsOf: path)
        return try parseSafariBinaryCookies(data: data)
    }

    public static func parseSafariBinaryCookies(data: Data) throws -> [(String, String, String, Int)] {
        guard data.count >= 8, String(data: data.prefix(4), encoding: .ascii) == "cook" else { return [] }
        let pageCount = Int(readUInt32BE(data, 4))
        var offset = 8
        var pageSizes: [Int] = []
        for _ in 0..<pageCount {
            guard offset + 4 <= data.count else { break }
            pageSizes.append(Int(readUInt32BE(data, offset)))
            offset += 4
        }
        var rows: [(String, String, String, Int)] = []
        for size in pageSizes {
            guard offset + size <= data.count else { break }
            let page = data.subdata(in: offset..<(offset + size))
            rows.append(contentsOf: parseSafariPage(page))
            offset += size
        }
        return rows
    }

    static func parseSafariPage(_ page: Data) -> [(String, String, String, Int)] {
        guard page.count >= 8 else { return [] }
        let count = Int(readUInt32LE(page, 4))
        var offsets: [Int] = []
        var pos = 8
        for _ in 0..<count {
            guard pos + 4 <= page.count else { break }
            offsets.append(Int(readUInt32LE(page, pos)))
            pos += 4
        }
        var rows: [(String, String, String, Int)] = []
        for off in offsets {
            guard off + 56 <= page.count else { continue }
            let recSize = Int(readInt32LE(page, off))
            guard recSize > 56, off + recSize <= page.count else { continue }
            let rec = page.subdata(in: off..<(off + recSize))
            let urlOff = Int(readInt32LE(rec, 16))
            let nameOff = Int(readInt32LE(rec, 20))
            let pathOff = Int(readInt32LE(rec, 24))
            let valueOff = Int(readInt32LE(rec, 28))
            let host = cString(rec, urlOff)
            let name = cString(rec, nameOff)
            let value = cString(rec, valueOff)
            _ = pathOff
            rows.append((host, name, value, 0))
        }
        return rows
    }

    public static func parseSafariSQLiteCookies(_ path: URL) -> [(String, String, String, Int)] {
        #if canImport(SQLite3)
        var db: OpaquePointer?
        guard sqlite3_open(path.path, &db) == SQLITE_OK, let db else { return [] }
        defer { sqlite3_close(db) }
        var tables: [String] = []
        var listStmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT name FROM sqlite_master WHERE type='table'", -1, &listStmt, nil) == SQLITE_OK, let listStmt {
            defer { sqlite3_finalize(listStmt) }
            while sqlite3_step(listStmt) == SQLITE_ROW {
                if let c = sqlite3_column_text(listStmt, 0) { tables.append(String(cString: c)) }
            }
        }
        var rows: [(String, String, String, Int)] = []
        for table in tables {
            var info: OpaquePointer?
            let pragma = "PRAGMA table_info(\"\(table)\")"
            var cols: [String: String] = [:]
            if sqlite3_prepare_v2(db, pragma, -1, &info, nil) == SQLITE_OK, let info {
                defer { sqlite3_finalize(info) }
                while sqlite3_step(info) == SQLITE_ROW {
                    if let c = sqlite3_column_text(info, 1) {
                        let name = String(cString: c)
                        cols[name.lowercased()] = name
                    }
                }
            }
            let nameCol = ["name", "cookie_name", "nshttpcookiename"].compactMap { cols[$0] }.first
            let valueCol = ["value", "cookie_value", "nshttpcookievalue"].compactMap { cols[$0] }.first
            let hostCol = ["host", "domain", "host_key", "origin", "nshttpcookiedomain"].compactMap { cols[$0] }.first
            let timeCol = ["last_access", "lastaccessed", "last_update", "creation"].compactMap { cols[$0] }.first
            guard let nameCol, let valueCol else { continue }
            let hostExpr = hostCol ?? "''"
            let timeExpr = timeCol ?? "0"
            let sql = "SELECT \(hostExpr), \(nameCol), \(valueCol), \(timeExpr) FROM \"\(table)\""
            var stmt: OpaquePointer?
            guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else { continue }
            defer { sqlite3_finalize(stmt) }
            while sqlite3_step(stmt) == SQLITE_ROW {
                let host = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
                let name = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
                let value = sqlite3_column_text(stmt, 2).map { String(cString: $0) } ?? ""
                let ts = Int(sqlite3_column_int64(stmt, 3))
                rows.append((host, name, value, ts))
            }
        }
        return rows
        #else
        return []
        #endif
    }

    public static func findSafariCandidates(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [CookieCandidate] {
        #if os(macOS)
        let roots = [
            home.appendingPathComponent("Library/Containers/com.apple.Safari/Data/Library/Cookies"),
            home.appendingPathComponent("Library/Cookies"),
            home.appendingPathComponent("Library/WebKit/com.apple.Safari/WebsiteData"),
        ]
        let names: Set<String> = ["Cookies.binarycookies", "Cookies.db", "Cookies.sqlite"]
        var files: [URL] = []
        for root in roots {
            files.append(contentsOf: namedFiles(root, names: names, depth: 5))
        }
        var found: [CookieCandidate] = []
        for path in files {
            let rows: [(String, String, String, Int)]
            if path.pathExtension.lowercased() == "db" || path.pathExtension.lowercased() == "sqlite" {
                rows = parseSafariSQLiteCookies(path)
            } else if let parsed = try? parseSafariBinaryCookies(path) {
                rows = parsed
            } else {
                continue
            }
            for (host, name, value, last) in rows where name == cookieName {
                if let token = safeNormalize(value) {
                    found.append(CookieCandidate(browser: "safari", profile: path.deletingLastPathComponent().lastPathComponent, token: token, lastUpdate: firefoxToUnixUs(last)))
                }
                _ = host
            }
        }
        return found
        #else
        return []
        #endif
    }

    static func namedFiles(_ root: URL, names: Set<String>, depth: Int) -> [URL] {
        if depth < 0 { return [] }
        var found: [URL] = []
        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: root.path, isDirectory: &isDir) {
            if !isDir.boolValue {
                if names.contains(root.lastPathComponent) { return [root] }
                return []
            }
        } else {
            return []
        }
        guard let children = try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: [.isDirectoryKey]) else {
            return []
        }
        for child in children {
            let dir = (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            if names.contains(child.lastPathComponent) {
                found.append(child)
            } else if dir {
                found.append(contentsOf: namedFiles(child, names: names, depth: depth - 1))
            }
        }
        return found
    }

    public static func findSessionCandidates(
        onlyBrowsers: [String]? = nil,
        cursorPaths: [URL]? = nil,
        firefoxRoots: [(String, URL)]? = nil
    ) -> [CookieCandidate] {
        var found: [CookieCandidate] = []
        let allow = onlyBrowsers.map { Set($0) }
        if allow == nil || allow!.contains("cursor-app") {
            found.append(contentsOf: findCursorAppCandidates(paths: cursorPaths))
        }
        if allow == nil || allow!.contains("safari") {
            found.append(contentsOf: findSafariCandidates())
        }
        if allow == nil || allow!.contains("firefox") || (allow?.contains(where: { $0.hasPrefix("firefox") }) == true) {
            for (browser, support) in firefoxRoots ?? firefoxProductRoots() {
                if let allow, !allow.contains(browser) { continue }
                for profile in iterFirefoxProfiles(support: support) {
                    for (_, value, last) in readFirefoxCookieRows(dbPath: profile.appendingPathComponent("cookies.sqlite")) {
                        if let token = safeNormalize(value) {
                            found.append(CookieCandidate(browser: browser, profile: profile.lastPathComponent, token: token, lastUpdate: firefoxToUnixUs(last)))
                        }
                    }
                }
            }
        }
        var seen = Set<String>()
        var uniq: [CookieCandidate] = []
        for c in found {
            if seen.contains(c.token) { continue }
            seen.insert(c.token)
            uniq.append(c)
        }
        return uniq
    }

    public static func importAndValidate(
        client: CursorClient = CursorClient(),
        preferBrowsers: [String]? = nil,
        onlyBrowsers: [String]? = nil,
        skipTokens: Set<String> = [],
        cursorPaths: [URL]? = nil,
        firefoxRoots: [(String, URL)]? = nil
    ) async -> ImportResult {
        let prefer = preferBrowsers ?? defaultPreferBrowsers()
        var candidates = findSessionCandidates(onlyBrowsers: onlyBrowsers, cursorPaths: cursorPaths, firefoxRoots: firefoxRoots)
        if candidates.isEmpty {
            return ImportResult(ok: false, message: "未找到可用 Cookie。请先登录 Cursor 应用，或在 Safari / Firefox 登录 cursor.com 后再导入。也可手动粘贴 WorkosCursorSessionToken。")
        }
        let order = Dictionary(uniqueKeysWithValues: prefer.enumerated().map { ($1, $0) })
        candidates.sort { a, b in
            if a.lastUpdate != b.lastUpdate { return a.lastUpdate > b.lastUpdate }
            return (order[a.browser] ?? 99) < (order[b.browser] ?? 99)
        }
        var skip = skipTokens
        var lastErr = "找到 Cookie，但校验均失败"
        var lastSource = candidates[0].browser
        var tried = 0
        for c in candidates {
            var variants = Token.variants(c.token)
            if variants.isEmpty { variants = [c.token] }
            if variants.allSatisfy({ skip.contains($0) }) { continue }
            for variant in variants where !skip.contains(variant) {
                tried += 1
                do {
                    let snap = try await client.fetchUsageSummary(sessionToken: variant, timeout: 12)
                    return ImportResult(
                        ok: true,
                        token: variant,
                        browser: c.browser,
                        profile: c.profile,
                        remainingPercent: snap.remainingPercent,
                        membershipType: snap.membershipType,
                        message: String(format: "已从 %@ (%@) 导入并校验成功：剩余 %.1f%% · %@", c.browser, c.profile, snap.remainingPercent, snap.membershipType)
                    )
                } catch let err as CursorAPIError {
                    lastErr = err.message
                    lastSource = c.browser
                    if err.isAuthError { skip.insert(variant) } else { break }
                } catch {
                    lastErr = "校验失败: \(error.localizedDescription)"
                    lastSource = c.browser
                    break
                }
            }
        }
        if tried == 0, !skip.isEmpty {
            return ImportResult(ok: false, message: "已读到 \(lastSource) 的 Cookie，但接口拒绝了这条登录态。请完整复制 WorkosCursorSessionToken 后粘贴。")
        }
        return ImportResult(ok: false, message: "已读到 \(lastSource) 的 Cookie，但校验失败：\(lastErr)\n请在当前已登录的浏览器里完整复制 WorkosCursorSessionToken 后粘贴。")
    }

    static func firefoxToUnixUs(_ lastAccessed: Int) -> Int {
        if lastAccessed <= 0 { return 0 }
        if lastAccessed < 10_000_000_000_000 { return lastAccessed * 1000 }
        return lastAccessed
    }

    static func readUInt32BE(_ data: Data, _ offset: Int) -> UInt32 {
        UInt32(data[offset]) << 24 | UInt32(data[offset + 1]) << 16 | UInt32(data[offset + 2]) << 8 | UInt32(data[offset + 3])
    }

    static func readUInt32LE(_ data: Data, _ offset: Int) -> UInt32 {
        UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 | UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
    }

    static func readInt32LE(_ data: Data, _ offset: Int) -> Int32 {
        Int32(bitPattern: readUInt32LE(data, offset))
    }

    static func cString(_ data: Data, _ offset: Int) -> String {
        guard offset >= 0, offset < data.count else { return "" }
        var end = offset
        while end < data.count, data[end] != 0 { end += 1 }
        return String(data: data.subdata(in: offset..<end), encoding: .utf8) ?? ""
    }
}
