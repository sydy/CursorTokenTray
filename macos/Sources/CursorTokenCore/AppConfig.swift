import Foundation
#if canImport(Darwin)
import Darwin
#endif

public enum AppPaths {
    public static let appSupportName = "CursorTokenTray"
    public static let launchLabel = "com.harker.cursortokentray"

    public static func configDirectory(home: URL? = nil) -> URL {
        #if os(macOS)
        let base = home ?? FileManager.default.homeDirectoryForCurrentUser
        return base.appendingPathComponent("Library/Application Support/\(appSupportName)", isDirectory: true)
        #elseif os(Windows)
        if let appdata = ProcessInfo.processInfo.environment["APPDATA"], !appdata.isEmpty {
            return URL(fileURLWithPath: appdata, isDirectory: true).appendingPathComponent(appSupportName, isDirectory: true)
        }
        let base = home ?? FileManager.default.homeDirectoryForCurrentUser
        return base.appendingPathComponent("AppData/Roaming/\(appSupportName)", isDirectory: true)
        #else
        let base = home ?? FileManager.default.homeDirectoryForCurrentUser
        return base.appendingPathComponent(".config/\(appSupportName)", isDirectory: true)
        #endif
    }

    public static func configPath(in directory: URL? = nil) -> URL {
        (directory ?? configDirectory()).appendingPathComponent("config.json")
    }

    public static func historyPath(accountId: String?, in directory: URL? = nil) -> URL {
        let root = directory ?? configDirectory()
        let aid = (accountId ?? "").trimmingCharacters(in: .whitespaces)
        if aid.isEmpty {
            return root.appendingPathComponent("usage_history.jsonl")
        }
        return root.appendingPathComponent("usage_history.\(Token.safeAccountId(aid)).jsonl")
    }

    public static func usageEventsPath(accountId: String?, teamScope: Bool, in directory: URL? = nil) -> URL {
        let root = directory ?? configDirectory()
        var aid = Token.safeAccountId((accountId ?? "").trimmingCharacters(in: .whitespaces))
        if aid.isEmpty { aid = "account" }
        let name = teamScope ? "usage_events.\(aid).team.jsonl" : "usage_events.\(aid).jsonl"
        return root.appendingPathComponent(name)
    }

    public static func logPath() -> URL {
        #if os(macOS)
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/CursorTokenTray.log")
        #else
        return configDirectory().appendingPathComponent("CursorTokenTray.log")
        #endif
    }

    public static func ensureDirectory(_ url: URL) {
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    }
}

public struct Account: Equatable, Sendable, Codable {
    public var id: String
    public var label: String
    public var token: String
    public var membershipType: String
    public var lastRemaining: Double?
    public var lastError: String
    public var updatedAt: String
    public var alertNotifiedLevels: [Int]
    public var authErrorNotified: Bool
    public var exhaustionNotified: Bool
    public var lowQuotaNotified: Bool
    public var tokenDecryptFailed: Bool
    public var storedToken: String

    public init(
        id: String = "",
        label: String = "",
        token: String = "",
        membershipType: String = "",
        lastRemaining: Double? = nil,
        lastError: String = "",
        updatedAt: String = "",
        alertNotifiedLevels: [Int] = [],
        authErrorNotified: Bool = false,
        exhaustionNotified: Bool = false,
        lowQuotaNotified: Bool = false,
        tokenDecryptFailed: Bool = false,
        storedToken: String = ""
    ) {
        self.id = id
        self.label = label
        self.token = token
        self.membershipType = membershipType
        self.lastRemaining = lastRemaining
        self.lastError = lastError
        self.updatedAt = updatedAt
        self.alertNotifiedLevels = alertNotifiedLevels
        self.authErrorNotified = authErrorNotified
        self.exhaustionNotified = exhaustionNotified
        self.lowQuotaNotified = lowQuotaNotified
        self.tokenDecryptFailed = tokenDecryptFailed
        self.storedToken = storedToken
    }

    public var displayLabel: String {
        let label = self.label.trimmingCharacters(in: .whitespaces)
        if !label.isEmpty { return label }
        let memb = membershipType.trimmingCharacters(in: .whitespaces)
        if !memb.isEmpty { return memb }
        let aid = id.trimmingCharacters(in: .whitespaces)
        if aid.hasPrefix("tok_") { return "未命名账号" }
        if aid.count > 14 { return String(aid.prefix(12)) + "…" }
        return aid.isEmpty ? "未命名账号" : aid
    }

    public func caption(isActive: Bool) -> String {
        var parts = [displayLabel]
        let memb = membershipType.trimmingCharacters(in: .whitespaces)
        if !memb.isEmpty, memb.lowercased() != displayLabel.lowercased() {
            parts.append(memb)
        }
        if let remaining = lastRemaining {
            parts.append(String(format: "剩余 %.0f%%", remaining))
        }
        let err = lastError.trimmingCharacters(in: .whitespaces)
        if !err.isEmpty, lastRemaining == nil {
            parts.append("已失效")
        }
        var text = parts.joined(separator: " · ")
        if isActive { text += "  (当前)" }
        return text
    }
}

public struct AppConfig: Equatable, Sendable {
    public var sessionToken: String
    public var accounts: [Account]
    public var activeAccountId: String
    public var refreshIntervalMinutes: Int
    public var lowQuotaThreshold: Int
    public var alertThresholds: [Int]
    public var notifyEnabled: Bool
    public var notifyExhaustionRisk: Bool
    public var autostartEnabled: Bool
    public var trayDisplayMode: String
    public var lowQuotaNotified: Bool
    public var authErrorNotified: Bool
    public var alertNotifiedLevels: [Int]
    public var exhaustionNotified: Bool
    /// True when config.json existed but could not be parsed. Save will not clobber it unless the user adds an account.
    public var loadError: Bool
    public var decryptError: Bool
    public var storedSessionToken: String

    public static let displayModes: Set<String> = ["ring", "number", "dot"]

    public static let `default` = AppConfig(
        sessionToken: "",
        accounts: [],
        activeAccountId: "",
        refreshIntervalMinutes: 10,
        lowQuotaThreshold: 20,
        alertThresholds: [50, 20, 5],
        notifyEnabled: true,
        notifyExhaustionRisk: true,
        autostartEnabled: true,
        trayDisplayMode: "ring",
        lowQuotaNotified: false,
        authErrorNotified: false,
        alertNotifiedLevels: [],
        exhaustionNotified: false,
        loadError: false,
        decryptError: false,
        storedSessionToken: ""
    )

    public var activeAccount: Account? {
        if let found = accounts.first(where: { $0.id == activeAccountId }) { return found }
        return accounts.first
    }

    public mutating func upsertAccount(
        token rawToken: String,
        label: String? = nil,
        membershipType: String? = nil,
        remaining: Double? = nil,
        error: String? = nil,
        activate: Bool = true
    ) throws -> (Account, Bool) {
        let token = (try? Token.normalize(rawToken)) ?? rawToken.trimmingCharacters(in: .whitespaces)
        if token.isEmpty { throw CursorAPIError("Token 为空") }
        let accountId = Token.accountId(from: token)
        if accountId.isEmpty { throw CursorAPIError("无法从 Token 识别账号") }
        if let idx = accounts.firstIndex(where: { $0.id == accountId }) {
            accounts[idx].token = token
            if let label { accounts[idx].label = label.trimmingCharacters(in: .whitespaces) }
            if let membershipType { accounts[idx].membershipType = membershipType.trimmingCharacters(in: .whitespaces) }
            if let remaining {
                accounts[idx].lastRemaining = round2(remaining)
                accounts[idx].lastError = ""
            }
            if let error { accounts[idx].lastError = error }
            if activate { activeAccountId = accountId }
            syncLegacyFields()
            return (accounts[idx], false)
        }
        var acc = Account(id: accountId, token: token)
        if accounts.isEmpty { copyLegacyFlags(into: &acc) }
        if let label { acc.label = label.trimmingCharacters(in: .whitespaces) }
        if let membershipType { acc.membershipType = membershipType.trimmingCharacters(in: .whitespaces) }
        if let remaining { acc.lastRemaining = round2(remaining) }
        if let error { acc.lastError = error }
        accounts.append(acc)
        if activate { activeAccountId = accountId }
        syncLegacyFields()
        return (acc, true)
    }

    public mutating func setActiveAccount(_ accountId: String) -> Bool {
        guard accounts.contains(where: { $0.id == accountId }) else { return false }
        activeAccountId = accountId
        syncLegacyFields()
        return true
    }

    public mutating func renameAccount(_ accountId: String, label: String) -> Bool {
        guard let idx = accounts.firstIndex(where: { $0.id == accountId }) else { return false }
        accounts[idx].label = label.trimmingCharacters(in: .whitespaces)
        return true
    }

    public mutating func removeAccount(_ accountId: String) -> Bool {
        let before = accounts.count
        accounts.removeAll { $0.id == accountId }
        if accounts.count == before { return false }
        if activeAccountId == accountId {
            activeAccountId = accounts.first?.id ?? ""
        }
        syncLegacyFields()
        return true
    }

    public func existingTokenVariants() -> Set<String> {
        var skip = Set<String>()
        for acc in accounts {
            for v in Token.variants(acc.token) { skip.insert(v) }
            let t = acc.token.trimmingCharacters(in: .whitespaces)
            if !t.isEmpty { skip.insert(t) }
        }
        return skip
    }

    public mutating func applySnapshot(
        to accountId: String,
        membershipType: String? = nil,
        remaining: Double? = nil,
        error: String? = nil,
        updatedAt: String? = nil
    ) {
        guard let idx = accounts.firstIndex(where: { $0.id == accountId }) else { return }
        if let membershipType { accounts[idx].membershipType = membershipType.trimmingCharacters(in: .whitespaces) }
        if let remaining { accounts[idx].lastRemaining = round2(remaining) }
        if let error {
            accounts[idx].lastError = error
        } else if remaining != nil {
            accounts[idx].lastError = ""
        }
        if let updatedAt { accounts[idx].updatedAt = updatedAt }
    }

    public mutating func syncLegacyFields() {
        guard let acc = activeAccount else {
            sessionToken = ""
            activeAccountId = ""
            accounts = []
            alertNotifiedLevels = []
            authErrorNotified = false
            exhaustionNotified = false
            lowQuotaNotified = false
            return
        }
        activeAccountId = acc.id
        sessionToken = acc.token
        alertNotifiedLevels = acc.alertNotifiedLevels
        authErrorNotified = acc.authErrorNotified
        exhaustionNotified = acc.exhaustionNotified
        lowQuotaNotified = acc.lowQuotaNotified
    }

    mutating func copyLegacyFlags(into account: inout Account) {
        account.alertNotifiedLevels = alertNotifiedLevels.filter { (1...100).contains($0) }.sorted()
        account.authErrorNotified = authErrorNotified
        account.exhaustionNotified = exhaustionNotified
        account.lowQuotaNotified = lowQuotaNotified
    }
}

public enum ConfigStore {
    public static func load(from directory: URL? = nil) -> AppConfig {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        return withLock(dir) { loadUnlocked(from: dir) }
    }

    @discardableResult
    public static func save(_ cfg: AppConfig, to directory: URL? = nil) -> Bool {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        return withLock(dir) { saveUnlocked(cfg, to: dir) }
    }

    /// Reload from disk, apply `mutate`, and save under the same lock so a
    /// long-running refresh cannot clobber settings saved in the meantime.
    @discardableResult
    public static func update(from directory: URL? = nil, mutate: (inout AppConfig) -> Void) -> AppConfig {
        let dir = directory ?? AppPaths.configDirectory()
        AppPaths.ensureDirectory(dir)
        return withLock(dir) {
            var cfg = loadUnlocked(from: dir)
            if cfg.loadError && cfg.accounts.isEmpty { return cfg }
            mutate(&cfg)
            saveUnlocked(cfg, to: dir)
            return cfg
        }
    }

    static func loadUnlocked(from dir: URL) -> AppConfig {
        let path = AppPaths.configPath(in: dir)
        guard FileManager.default.fileExists(atPath: path.path) else {
            let cfg = AppConfig.default
            saveUnlocked(cfg, to: dir)
            return cfg
        }
        guard let data = try? Data(contentsOf: path),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            quarantine(path)
            var cfg = AppConfig.default
            cfg.loadError = true
            return cfg
        }
        return normalize(obj)
    }

    @discardableResult
    static func saveUnlocked(_ cfg: AppConfig, to dir: URL) -> Bool {
        if cfg.loadError && cfg.accounts.isEmpty { return true }
        var normalized = cfg
        normalized.loadError = false
        guard let first = try? toDictionary(normalized) else { return false }
        normalized = normalize(first)
        guard let dict = try? toDictionary(normalized),
              let data = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys])
        else { return false }
        let path = AppPaths.configPath(in: dir)
        atomicWrite(data, to: path)
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path.path)
        return true
    }

    @discardableResult
    static func withLock<T>(_ directory: URL, _ body: () -> T) -> T {
        AppPaths.ensureDirectory(directory)
        #if canImport(Darwin)
        let lockURL = directory.appendingPathComponent("config.lock")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        if fd >= 0 {
            flock(fd, LOCK_EX)
            defer {
                flock(fd, LOCK_UN)
                close(fd)
            }
            return body()
        }
        #endif
        return body()
    }

    static func atomicWrite(_ data: Data, to path: URL) {
        let tmp = path.appendingPathExtension("tmp")
        do {
            try data.write(to: tmp, options: [.atomic])
            if FileManager.default.fileExists(atPath: path.path) {
                _ = try FileManager.default.replaceItemAt(path, withItemAt: tmp)
            } else {
                try FileManager.default.moveItem(at: tmp, to: path)
            }
        } catch {
            try? data.write(to: path, options: [.atomic])
        }
    }

    static func quarantine(_ path: URL) {
        let dest = path.appendingPathExtension("corrupt")
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.copyItem(at: path, to: dest)
    }

    public static func normalize(_ raw: [String: Any]) -> AppConfig {
        var cfg = AppConfig.default
        if let v = raw["session_token"] as? String {
            let result = TokenProtector.tryUnprotect(v)
            if result.ok {
                cfg.sessionToken = result.value
            } else {
                cfg.sessionToken = ""
                cfg.decryptError = true
                cfg.storedSessionToken = v
            }
        }
        if let v = raw["active_account_id"] as? String { cfg.activeAccountId = v }
        if let v = intValue(raw["refresh_interval_minutes"]) { cfg.refreshIntervalMinutes = max(1, v) }
        if let v = intValue(raw["low_quota_threshold"]) { cfg.lowQuotaThreshold = min(100, max(1, v)) }
        if let v = raw["notify_enabled"] as? Bool { cfg.notifyEnabled = v }
        if let v = raw["notify_exhaustion_risk"] as? Bool { cfg.notifyExhaustionRisk = v }
        if let v = raw["autostart_enabled"] as? Bool { cfg.autostartEnabled = v }
        if let v = raw["low_quota_notified"] as? Bool { cfg.lowQuotaNotified = v }
        if let v = raw["auth_error_notified"] as? Bool { cfg.authErrorNotified = v }
        if let v = raw["exhaustion_notified"] as? Bool { cfg.exhaustionNotified = v }
        let rawToken = (cfg.sessionToken).trimmingCharacters(in: .whitespaces)
        if !rawToken.isEmpty {
            cfg.sessionToken = (try? Token.normalize(rawToken)) ?? rawToken
        }
        let mode = ((raw["tray_display_mode"] as? String) ?? "ring").trimmingCharacters(in: .whitespaces).lowercased()
        cfg.trayDisplayMode = AppConfig.displayModes.contains(mode) ? mode : "ring"
        if raw["alert_thresholds"] == nil, raw["low_quota_threshold"] != nil {
            cfg.alertThresholds = [cfg.lowQuotaThreshold]
        } else {
            cfg.alertThresholds = parseThresholds(raw["alert_thresholds"])
        }
        cfg.alertNotifiedLevels = parseIntList(raw["alert_notified_levels"])
        cfg.accounts = parseAccounts(raw["accounts"])
        if cfg.accounts.contains(where: \.tokenDecryptFailed) { cfg.decryptError = true }
        cfg = normalizeAccounts(cfg, raw: raw)
        return cfg
    }

    static func normalizeAccounts(_ input: AppConfig, raw: [String: Any]) -> AppConfig {
        var cfg = input
        var accounts = cfg.accounts
        var seen = Set<String>()
        accounts = accounts.filter { acc in
            if seen.contains(acc.id) { return false }
            seen.insert(acc.id)
            return true
        }
        cfg.accounts = accounts
        let token = (try? Token.normalize(cfg.sessionToken)) ?? cfg.sessionToken.trimmingCharacters(in: .whitespaces)
        var activeId = cfg.activeAccountId.trimmingCharacters(in: .whitespaces)
        if !token.isEmpty {
            let active = accounts.first(where: { $0.id == activeId })
            if active == nil || active?.token != token {
                let createdEmpty = accounts.isEmpty
                if let result = try? cfg.upsertAccount(token: token, activate: true) {
                    if createdEmpty {
                        // flags already copied inside upsert when accounts was empty
                        _ = result
                    }
                    activeId = result.0.id
                }
            }
        }
        accounts = cfg.accounts
        if !accounts.isEmpty {
            let ids = Set(accounts.map(\.id))
            if !ids.contains(activeId) { activeId = accounts[0].id }
            cfg.activeAccountId = activeId
        } else {
            cfg.activeAccountId = ""
        }
        cfg.syncLegacyFields()
        return cfg
    }

    static func parseAccounts(_ raw: Any?) -> [Account] {
        guard let rows = raw as? [[String: Any]] else { return [] }
        return rows.compactMap(sanitizeAccount)
    }

    static func sanitizeAccount(_ raw: [String: Any]) -> Account? {
        let stored = (raw["token"] as? String ?? "").trimmingCharacters(in: .whitespaces)
        let unpacked = TokenProtector.tryUnprotect(stored)
        let decryptFailed = !unpacked.ok
        let tokenRaw = unpacked.value
        let token = decryptFailed ? "" : ((try? Token.normalize(tokenRaw)) ?? tokenRaw)
        var accountId = (raw["id"] as? String ?? "").trimmingCharacters(in: .whitespaces)
        if accountId.isEmpty, !token.isEmpty { accountId = Token.accountId(from: token) }
        if accountId.isEmpty { return nil }
        if token.isEmpty && !decryptFailed { return nil }
        var acc = Account(id: accountId, token: token)
        if decryptFailed {
            acc.tokenDecryptFailed = true
            acc.storedToken = stored
            acc.lastError = TokenProtector.decryptFailedMessage
        }
        acc.label = (raw["label"] as? String ?? "").trimmingCharacters(in: .whitespaces)
        acc.membershipType = (raw["membershipType"] as? String ?? raw["membership_type"] as? String ?? "")
            .trimmingCharacters(in: .whitespaces)
        if !decryptFailed { acc.lastError = raw["last_error"] as? String ?? "" }
        acc.updatedAt = raw["updated_at"] as? String ?? ""
        if let remaining = raw["last_remaining"] {
            if remaining is NSNull {
                acc.lastRemaining = nil
            } else if let n = remaining as? NSNumber {
                acc.lastRemaining = round2(n.doubleValue)
            } else if let s = remaining as? String, let d = Double(s) {
                acc.lastRemaining = round2(d)
            }
        }
        acc.alertNotifiedLevels = parseIntList(raw["alert_notified_levels"])
        acc.authErrorNotified = boolValue(raw["auth_error_notified"])
        acc.exhaustionNotified = boolValue(raw["exhaustion_notified"])
        acc.lowQuotaNotified = boolValue(raw["low_quota_notified"])
        return acc
    }

    public static func parseThresholds(_ value: Any?) -> [Int] {
        var nums: [Int] = []
        if let s = value as? String {
            let parts = s.replacingOccurrences(of: "，", with: ",").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            nums = parts.compactMap { Int(Double($0) ?? -1) }
        } else if let arr = value as? [Any] {
            nums = arr.compactMap { intValue($0) }
        } else {
            nums = AppConfig.default.alertThresholds
        }
        let cleaned = Set(nums.filter { (1...100).contains($0) }).sorted(by: >)
        return cleaned.isEmpty ? AppConfig.default.alertThresholds : cleaned
    }

    static func parseIntList(_ value: Any?) -> [Int] {
        guard let arr = value as? [Any] else { return [] }
        return Set(arr.compactMap { intValue($0) }.filter { (1...100).contains($0) }).sorted()
    }

    static func intValue(_ value: Any?) -> Int? {
        if let n = value as? NSNumber { return n.intValue }
        if let s = value as? String, let d = Double(s) { return Int(d) }
        if let i = value as? Int { return i }
        return nil
    }

    static func boolValue(_ value: Any?) -> Bool {
        if let b = value as? Bool { return b }
        if let n = value as? NSNumber { return n.boolValue }
        return false
    }

    public static func toDictionary(_ cfg: AppConfig) throws -> [String: Any] {
        [
            "session_token": try TokenProtector.diskToken(
                plaintext: cfg.sessionToken,
                storedRaw: cfg.storedSessionToken,
                decryptFailed: cfg.decryptError && cfg.sessionToken.isEmpty
            ),
            "accounts": try cfg.accounts.map { acc -> [String: Any] in
                var d: [String: Any] = [
                    "id": acc.id,
                    "label": acc.label,
                    "token": try TokenProtector.diskToken(
                        plaintext: acc.token,
                        storedRaw: acc.storedToken,
                        decryptFailed: acc.tokenDecryptFailed
                    ),
                    "membership_type": acc.membershipType,
                    "last_error": acc.lastError,
                    "updated_at": acc.updatedAt,
                    "alert_notified_levels": acc.alertNotifiedLevels,
                    "auth_error_notified": acc.authErrorNotified,
                    "exhaustion_notified": acc.exhaustionNotified,
                    "low_quota_notified": acc.lowQuotaNotified,
                ]
                if let r = acc.lastRemaining { d["last_remaining"] = r } else { d["last_remaining"] = NSNull() }
                return d
            },
            "active_account_id": cfg.activeAccountId,
            "refresh_interval_minutes": cfg.refreshIntervalMinutes,
            "low_quota_threshold": cfg.lowQuotaThreshold,
            "alert_thresholds": cfg.alertThresholds,
            "notify_enabled": cfg.notifyEnabled,
            "notify_exhaustion_risk": cfg.notifyExhaustionRisk,
            "autostart_enabled": cfg.autostartEnabled,
            "tray_display_mode": cfg.trayDisplayMode,
            "low_quota_notified": cfg.lowQuotaNotified,
            "auth_error_notified": cfg.authErrorNotified,
            "alert_notified_levels": cfg.alertNotifiedLevels,
            "exhaustion_notified": cfg.exhaustionNotified,
        ]
    }
}
