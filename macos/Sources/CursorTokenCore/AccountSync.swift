import Foundation
#if canImport(CryptoKit)
import CryptoKit
#endif
#if canImport(CommonCrypto)
import CommonCrypto
#endif

public struct DeletedAccount: Equatable, Sendable {
    public var id: String
    public var deletedAt: String
    public init(id: String = "", deletedAt: String = "") {
        self.id = id
        self.deletedAt = deletedAt
    }
}

public struct SyncAccount: Equatable, Sendable {
    public var id: String
    public var label: String
    public var token: String
    public var membershipType: String
    public var accountKind: String
    public var tempStartAt: String
    public var tempValidDays: Int
    public var tempValidHours: Int
    public var actualCny: Double
    public var channel: String
    public var syncUpdatedAt: String
    public init(
        id: String = "",
        label: String = "",
        token: String = "",
        membershipType: String = "",
        accountKind: String = AccountValidity.longTerm,
        tempStartAt: String = "",
        tempValidDays: Int = 0,
        tempValidHours: Int = 0,
        actualCny: Double = 0,
        channel: String = "",
        syncUpdatedAt: String = ""
    ) {
        self.id = id
        self.label = label
        self.token = token
        self.membershipType = membershipType
        self.accountKind = AccountValidity.sanitizeKind(accountKind)
        self.tempStartAt = tempStartAt
        self.tempValidDays = AccountValidity.clampDays(tempValidDays)
        self.tempValidHours = AccountValidity.clampHours(tempValidHours)
        self.actualCny = UsageEvents.clampActualCny(actualCny)
        self.channel = UsageEvents.sanitizeChannel(channel)
        self.syncUpdatedAt = syncUpdatedAt
    }
}

public struct SyncSnapshot: Equatable, Sendable {
    public var version: Int
    public var updatedAt: String
    public var deviceId: String
    public var activeAccountId: String
    public var accounts: [SyncAccount]
    public var deleted: [DeletedAccount]
    public init(
        version: Int = 1,
        updatedAt: String = "",
        deviceId: String = "",
        activeAccountId: String = "",
        accounts: [SyncAccount] = [],
        deleted: [DeletedAccount] = []
    ) {
        self.version = version
        self.updatedAt = updatedAt
        self.deviceId = deviceId
        self.activeAccountId = activeAccountId
        self.accounts = accounts
        self.deleted = deleted
    }
}

public struct SyncStatus: Sendable {
    public var ok: Bool
    public var changed: Bool
    public var pushed: Bool
    public var message: String
    public var path: String
    public init(ok: Bool = false, changed: Bool = false, pushed: Bool = false, message: String = "", path: String = "") {
        self.ok = ok
        self.changed = changed
        self.pushed = pushed
        self.message = message
        self.path = path
    }
}

public enum AccountSync {
    public static let format = "cursortokentray.accounts.v1"
    public static let filename = "CursorTokenTray.accounts.sync"
    public static let kdf = "pbkdf2-sha256"
    public static let defaultIterations = 210_000
    public static let keyLen = 32
    public static let saltLen = 16
    public static let nonceLen = 12
    public static let tagLen = 16
    static let fileSuffixes: Set<String> = [".sync", ".json"]

    public static func nowIso(_ now: Date? = nil) -> String {
        let stamp = now ?? Date()
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone(secondsFromGMT: 0)
        fmt.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
        return fmt.string(from: stamp)
    }

    public static func parseIso(_ value: String?) -> Date? {
        let text = (value ?? "").trimmingCharacters(in: .whitespaces)
        if text.isEmpty { return nil }
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone(secondsFromGMT: 0)
        for pattern in ["yyyy-MM-dd'T'HH:mm:ss.SSSXXXXX", "yyyy-MM-dd'T'HH:mm:ssXXXXX", "yyyy-MM-dd'T'HH:mm:ss.SSSZ", "yyyy-MM-dd'T'HH:mm:ssZ"] {
            fmt.dateFormat = pattern
            if let date = fmt.date(from: text) { return date }
        }
        return ISO8601DateFormatter().date(from: text)
    }

    public static func compareIso(_ left: String?, _ right: String?) -> Int {
        let a = parseIso(left)
        let b = parseIso(right)
        if a == nil && b == nil { return 0 }
        if a == nil { return -1 }
        if b == nil { return 1 }
        if a! < b! { return -1 }
        if a! > b! { return 1 }
        return 0
    }

    public static func newerIso(_ left: String?, _ right: String?) -> String {
        compareIso(left, right) >= 0 ? (left ?? "") : (right ?? "")
    }

    public static func resolveSyncPath(_ path: String) -> String {
        var raw = path.trimmingCharacters(in: .whitespaces)
        if raw.isEmpty { return "" }
        if raw.hasPrefix("~") {
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            let rest = String(raw.dropFirst()).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            raw = rest.isEmpty ? home : (home as NSString).appendingPathComponent(rest)
        }
        let url = URL(fileURLWithPath: raw)
        let suffix = url.pathExtension.lowercased()
        if raw.hasSuffix("/") || raw.hasSuffix("\\") || url.hasDirectoryPath || !fileSuffixes.contains("." + suffix) {
            return url.appendingPathComponent(filename).path
        }
        if (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true {
            return url.appendingPathComponent(filename).path
        }
        return url.path
    }

    public static func ensureDeviceId(_ cfg: inout AppConfig) -> String {
        let current = cfg.syncDeviceId.trimmingCharacters(in: .whitespaces)
        if !current.isEmpty { return current }
        cfg.syncDeviceId = UUID().uuidString
        return cfg.syncDeviceId
    }

    public static func sanitizeDeleted(_ raw: [DeletedAccount]) -> [DeletedAccount] {
        var best: [String: String] = [:]
        for item in raw {
            let id = item.id.trimmingCharacters(in: .whitespaces)
            let deletedAt = item.deletedAt.trimmingCharacters(in: .whitespaces)
            if id.isEmpty || deletedAt.isEmpty { continue }
            if let prev = best[id], compareIso(deletedAt, prev) < 0 { continue }
            best[id] = deletedAt
        }
        return best.keys.sorted().map { DeletedAccount(id: $0, deletedAt: best[$0]!) }
    }

    public static func rememberDeleted(_ cfg: inout AppConfig, accountId: String, deletedAt: String? = nil) {
        let id = accountId.trimmingCharacters(in: .whitespaces)
        if id.isEmpty { return }
        var rows = sanitizeDeleted(cfg.deletedAccounts).filter { $0.id != id }
        rows.append(DeletedAccount(id: id, deletedAt: deletedAt ?? nowIso()))
        cfg.deletedAccounts = sanitizeDeleted(rows)
    }

    public static func forgetDeleted(_ cfg: inout AppConfig, accountId: String) {
        let id = accountId.trimmingCharacters(in: .whitespaces)
        cfg.deletedAccounts = sanitizeDeleted(cfg.deletedAccounts).filter { $0.id != id }
    }

    public static func touchAccount(_ account: inout Account, stamp: String? = nil) {
        account.syncUpdatedAt = stamp ?? nowIso()
    }

    public static func snapshotAccount(_ account: Account) -> SyncAccount {
        SyncAccount(
            id: account.id.trimmingCharacters(in: .whitespaces),
            label: account.label.trimmingCharacters(in: .whitespaces),
            token: account.token.trimmingCharacters(in: .whitespaces),
            membershipType: account.membershipType.trimmingCharacters(in: .whitespaces),
            accountKind: account.accountKind,
            tempStartAt: account.tempStartAt.trimmingCharacters(in: .whitespaces),
            tempValidDays: account.tempValidDays,
            tempValidHours: account.tempValidHours,
            actualCny: account.actualCny,
            channel: account.channel,
            syncUpdatedAt: account.syncUpdatedAt.trimmingCharacters(in: .whitespaces)
        )
    }

    public static func snapshotAccount(_ account: SyncAccount) -> SyncAccount {
        SyncAccount(
            id: account.id.trimmingCharacters(in: .whitespaces),
            label: account.label.trimmingCharacters(in: .whitespaces),
            token: account.token.trimmingCharacters(in: .whitespaces),
            membershipType: account.membershipType.trimmingCharacters(in: .whitespaces),
            accountKind: account.accountKind,
            tempStartAt: account.tempStartAt.trimmingCharacters(in: .whitespaces),
            tempValidDays: account.tempValidDays,
            tempValidHours: account.tempValidHours,
            actualCny: account.actualCny,
            channel: account.channel,
            syncUpdatedAt: account.syncUpdatedAt.trimmingCharacters(in: .whitespaces)
        )
    }

    public static func snapshotFromConfig(_ cfg: AppConfig) -> SyncSnapshot {
        var accounts: [SyncAccount] = []
        for acc in cfg.accounts {
            let row = snapshotAccount(acc)
            if row.id.isEmpty || row.token.isEmpty { continue }
            accounts.append(row)
        }
        return SyncSnapshot(
            updatedAt: cfg.syncLastAt,
            deviceId: cfg.syncDeviceId,
            activeAccountId: cfg.activeAccountId,
            accounts: accounts,
            deleted: sanitizeDeleted(cfg.deletedAccounts)
        )
    }

    public static func snapshotIdentity(_ snap: SyncSnapshot) -> String {
        let accounts = snap.accounts.sorted { $0.id < $1.id }.map {
            "\($0.id)\n\($0.label)\n\($0.token)\n\($0.membershipType)\n\($0.accountKind)\n\($0.tempStartAt)\n\($0.tempValidDays)\n\($0.tempValidHours)\n\($0.actualCny)\n\($0.channel)\n\($0.syncUpdatedAt)"
        }.joined(separator: "|")
        let deleted = snap.deleted.sorted { $0.id < $1.id }.map { "\($0.id)\n\($0.deletedAt)" }.joined(separator: "|")
        return "\(snap.activeAccountId)\n\(accounts)\n\(deleted)"
    }

    public static func mergeSnapshots(_ local: SyncSnapshot, _ remote: SyncSnapshot) -> SyncSnapshot {
        var tombstones: [String: String] = [:]
        for row in sanitizeDeleted(local.deleted) + sanitizeDeleted(remote.deleted) {
            if let prev = tombstones[row.id], compareIso(row.deletedAt, prev) < 0 { continue }
            tombstones[row.id] = row.deletedAt
        }
        var chosen: [String: SyncAccount] = [:]
        for src in local.accounts + remote.accounts {
            let acc = snapshotAccount(src)
            if acc.id.isEmpty || acc.token.isEmpty { continue }
            if let tomb = tombstones[acc.id], compareIso(tomb, acc.syncUpdatedAt) >= 0 { continue }
            if let prev = chosen[acc.id] {
                let cmp = compareIso(acc.syncUpdatedAt, prev.syncUpdatedAt)
                if cmp > 0 { chosen[acc.id] = acc }
                else if cmp == 0 && prev.token.isEmpty && !acc.token.isEmpty { chosen[acc.id] = acc }
            } else {
                chosen[acc.id] = acc
            }
        }
        for id in tombstones.keys where chosen[id] != nil { tombstones.removeValue(forKey: id) }
        var active = compareIso(remote.updatedAt, local.updatedAt) > 0 ? remote.activeAccountId : local.activeAccountId
        if chosen[active] == nil {
            active = chosen.keys.sorted().first ?? ""
        }
        return SyncSnapshot(
            updatedAt: newerIso(local.updatedAt, remote.updatedAt),
            deviceId: local.deviceId.isEmpty ? remote.deviceId : local.deviceId,
            activeAccountId: active,
            accounts: chosen.keys.sorted().compactMap { chosen[$0] },
            deleted: tombstones.keys.sorted().map { DeletedAccount(id: $0, deletedAt: tombstones[$0]!) }
        )
    }

    @discardableResult
    public static func applySnapshotToConfig(_ cfg: inout AppConfig, _ snap: SyncSnapshot) -> Bool {
        let before = cfg.accounts.map { "\($0.id)\n\($0.token)\n\($0.label)\n\($0.membershipType)\n\($0.accountKind)\n\($0.tempStartAt)\n\($0.tempValidDays)\n\($0.tempValidHours)\n\($0.actualCny)\n\($0.channel)\n\($0.syncUpdatedAt)" }.joined(separator: "|")
        var existing: [String: Account] = [:]
        for acc in cfg.accounts { existing[acc.id] = acc }
        var merged: [Account] = []
        for row in snap.accounts {
            let ident = snapshotAccount(row)
            if ident.id.isEmpty || ident.token.isEmpty { continue }
            if var old = existing[ident.id] {
                old.token = ident.token
                old.label = ident.label
                if !ident.membershipType.isEmpty { old.membershipType = ident.membershipType }
                old.accountKind = ident.accountKind
                old.tempStartAt = ident.tempStartAt
                old.tempValidDays = ident.tempValidDays
                old.tempValidHours = ident.tempValidHours
                old.actualCny = ident.actualCny
                old.channel = ident.channel
                old.syncUpdatedAt = ident.syncUpdatedAt
                merged.append(old)
            } else {
                var acc = Account(
                    id: ident.id,
                    label: ident.label,
                    token: ident.token,
                    membershipType: ident.membershipType,
                    accountKind: ident.accountKind,
                    tempStartAt: ident.tempStartAt,
                    tempValidDays: ident.tempValidDays,
                    tempValidHours: ident.tempValidHours,
                    actualCny: ident.actualCny,
                    channel: ident.channel
                )
                acc.syncUpdatedAt = ident.syncUpdatedAt
                merged.append(acc)
            }
        }
        cfg.accounts = merged
        cfg.deletedAccounts = sanitizeDeleted(snap.deleted)
        let ids = Set(merged.map(\.id))
        if ids.contains(snap.activeAccountId) { cfg.activeAccountId = snap.activeAccountId }
        else { cfg.activeAccountId = merged.first?.id ?? "" }
        cfg.syncLegacyFields()
        let after = cfg.accounts.map { "\($0.id)\n\($0.token)\n\($0.label)\n\($0.membershipType)\n\($0.accountKind)\n\($0.tempStartAt)\n\($0.tempValidDays)\n\($0.tempValidHours)\n\($0.actualCny)\n\($0.channel)\n\($0.syncUpdatedAt)" }.joined(separator: "|")
        return before != after
    }

    public static func deriveKey(passphrase: String, salt: Data, iterations: Int = defaultIterations) throws -> Data {
        if passphrase.isEmpty { throw CursorAPIError("同步口令不能为空") }
        if iterations < 1000 { throw CursorAPIError("KDF 迭代次数过低") }
        #if canImport(CommonCrypto)
        var derived = Data(count: keyLen)
        let status = derived.withUnsafeMutableBytes { derivedPtr in
            salt.withUnsafeBytes { saltPtr in
                passphrase.withCString { passPtr in
                    CCKeyDerivationPBKDF(
                        CCPBKDFAlgorithm(kCCPBKDF2),
                        passPtr,
                        passphrase.lengthOfBytes(using: .utf8),
                        saltPtr.bindMemory(to: UInt8.self).baseAddress,
                        salt.count,
                        CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256),
                        UInt32(iterations),
                        derivedPtr.bindMemory(to: UInt8.self).baseAddress,
                        keyLen
                    )
                }
            }
        }
        if status != kCCSuccess { throw CursorAPIError("无法派生同步密钥") }
        return derived
        #else
        throw CursorAPIError("当前平台无法加密同步文件")
        #endif
    }

    public static func canonicalJSON(_ snap: SyncSnapshot) -> String {
        func q(_ value: String) -> String {
            let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed])
            return String(data: data ?? Data("\"\"".utf8), encoding: .utf8) ?? "\"\""
        }
        let accounts = snap.accounts.map { acc in
            var extra = ""
            if AccountValidity.sanitizeKind(acc.accountKind) != AccountValidity.longTerm
                || !acc.tempStartAt.isEmpty
                || acc.tempValidDays != 0
                || acc.tempValidHours != 0
            {
                extra += ",\"account_kind\":\(q(AccountValidity.sanitizeKind(acc.accountKind))),\"temp_start_at\":\(q(acc.tempStartAt)),\"temp_valid_days\":\(acc.tempValidDays),\"temp_valid_hours\":\(acc.tempValidHours)"
            }
            if acc.actualCny != 0 {
                extra += ",\"actual_cny\":\(canonicalNumber(acc.actualCny))"
            }
            if !acc.channel.isEmpty {
                extra += ",\"channel\":\(q(acc.channel))"
            }
            return "{\"id\":\(q(acc.id)),\"label\":\(q(acc.label)),\"membership_type\":\(q(acc.membershipType)),\"sync_updated_at\":\(q(acc.syncUpdatedAt)),\"token\":\(q(acc.token))\(extra)}"
        }.joined(separator: ",")
        let deleted = snap.deleted.map { d in
            "{\"deleted_at\":\(q(d.deletedAt)),\"id\":\(q(d.id))}"
        }.joined(separator: ",")
        return "{\"accounts\":[\(accounts)],\"active_account_id\":\(q(snap.activeAccountId)),\"deleted\":[\(deleted)],\"device_id\":\(q(snap.deviceId)),\"updated_at\":\(q(snap.updatedAt)),\"version\":\(snap.version)}"
    }

    public static func encryptEnvelope(
        _ payload: SyncSnapshot,
        passphrase: String,
        salt: Data? = nil,
        nonce: Data? = nil,
        iterations: Int = defaultIterations
    ) throws -> [String: Any] {
        #if canImport(CryptoKit)
        let saltB = salt ?? Data((0..<saltLen).map { _ in UInt8.random(in: 0...255) })
        let nonceB = nonce ?? Data((0..<nonceLen).map { _ in UInt8.random(in: 0...255) })
        if saltB.count != saltLen || nonceB.count != nonceLen { throw CursorAPIError("salt/nonce 长度不正确") }
        let raw = Data(canonicalJSON(payload).utf8)
        let key = SymmetricKey(data: try deriveKey(passphrase: passphrase, salt: saltB, iterations: iterations))
        let sealed = try AES.GCM.seal(raw, using: key, nonce: AES.GCM.Nonce(data: nonceB))
        let blob = sealed.ciphertext + sealed.tag
        return [
            "format": format,
            "kdf": kdf,
            "iterations": iterations,
            "salt": saltB.base64EncodedString(),
            "nonce": nonceB.base64EncodedString(),
            "ciphertext": blob.base64EncodedString(),
        ]
        #else
        throw CursorAPIError("当前平台无法加密同步文件")
        #endif
    }

    public static func decryptEnvelope(_ envelope: [String: Any], passphrase: String) throws -> SyncSnapshot {
        if str(envelope["format"]) != format { throw CursorAPIError("不是 CursorTokenTray 账号同步文件") }
        if str(envelope["kdf"]) != kdf { throw CursorAPIError("不支持的同步文件密钥算法") }
        guard let salt = Data(base64Encoded: str(envelope["salt"])),
              let nonce = Data(base64Encoded: str(envelope["nonce"])),
              let blob = Data(base64Encoded: str(envelope["ciphertext"]))
        else { throw CursorAPIError("同步文件损坏") }
        let iterations = intValue(envelope["iterations"]) ?? 0
        if salt.count != saltLen || nonce.count != nonceLen || blob.count < tagLen {
            throw CursorAPIError("同步文件损坏")
        }
        #if canImport(CryptoKit)
        let key = SymmetricKey(data: try deriveKey(passphrase: passphrase, salt: salt, iterations: iterations))
        let cipher = blob.prefix(blob.count - tagLen)
        let tag = blob.suffix(tagLen)
        do {
            let box = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: nonce), ciphertext: cipher, tag: tag)
            let opened = try AES.GCM.open(box, using: key)
            let obj = try JSONSerialization.jsonObject(with: opened)
            guard let dict = obj as? [String: Any] else { throw CursorAPIError("同步文件内容无法解析") }
            return parseSnapshot(dict)
        } catch let err as CursorAPIError {
            throw err
        } catch {
            throw CursorAPIError("同步口令不正确或文件已损坏")
        }
        #else
        throw CursorAPIError("当前平台无法解密同步文件")
        #endif
    }

    public static func parseSnapshot(_ raw: [String: Any]) -> SyncSnapshot {
        var snap = SyncSnapshot(
            updatedAt: str(raw["updated_at"]),
            deviceId: str(raw["device_id"]),
            activeAccountId: str(raw["active_account_id"])
        )
        if let arr = raw["accounts"] as? [[String: Any]] {
            snap.accounts = arr.map {
                SyncAccount(
                    id: str($0["id"]).trimmingCharacters(in: .whitespaces),
                    label: str($0["label"]).trimmingCharacters(in: .whitespaces),
                    token: str($0["token"]).trimmingCharacters(in: .whitespaces),
                    membershipType: str($0["membership_type"]).trimmingCharacters(in: .whitespaces),
                    accountKind: str($0["account_kind"]),
                    tempStartAt: str($0["temp_start_at"]).trimmingCharacters(in: .whitespaces),
                    tempValidDays: AccountValidity.clampDays($0["temp_valid_days"]),
                    tempValidHours: AccountValidity.clampHours($0["temp_valid_hours"]),
                    actualCny: UsageEvents.clampActualCny(num($0["actual_cny"]) ?? num($0["actualCny"]) ?? 0),
                    channel: UsageEvents.sanitizeChannel($0["channel"] as? String),
                    syncUpdatedAt: str($0["sync_updated_at"]).trimmingCharacters(in: .whitespaces)
                )
            }.filter { !$0.id.isEmpty }
        }
        if let arr = raw["deleted"] as? [[String: Any]] {
            snap.deleted = sanitizeDeleted(arr.map {
                DeletedAccount(id: str($0["id"]).trimmingCharacters(in: .whitespaces), deletedAt: str($0["deleted_at"]).trimmingCharacters(in: .whitespaces))
            })
        }
        return snap
    }

    public static func readEnvelope(_ path: String) throws -> [String: Any]? {
        let url = URL(fileURLWithPath: path)
        if !FileManager.default.fileExists(atPath: url.path) { return nil }
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { throw CursorAPIError("无法读取同步文件") }
        return obj
    }

    public static func writeEnvelope(_ path: String, _ envelope: [String: Any]) throws {
        let url = URL(fileURLWithPath: path)
        AppPaths.ensureDirectory(url.deletingLastPathComponent())
        let data = try JSONSerialization.data(withJSONObject: envelope, options: [.prettyPrinted, .sortedKeys])
        ConfigStore.atomicWrite(data, to: url)
    }

    public static func syncReady(_ cfg: AppConfig) -> String {
        if !cfg.syncEnabled { return "未启用多端同步" }
        if cfg.syncPath.trimmingCharacters(in: .whitespaces).isEmpty { return "请选择同步文件夹" }
        if cfg.syncSecret.trimmingCharacters(in: .whitespaces).isEmpty { return "请设置同步口令" }
        return ""
    }

    public static func reconcile(_ cfg: inout AppConfig, now: Date? = nil, write: Bool = true) -> SyncStatus {
        var status = SyncStatus()
        let reason = syncReady(cfg)
        if !reason.isEmpty {
            status.message = reason
            cfg.syncLastError = reason
            return status
        }
        let path = resolveSyncPath(cfg.syncPath)
        status.path = path
        _ = ensureDeviceId(&cfg)
        let stamp = nowIso(now)
        var local = snapshotFromConfig(cfg)
        local.deviceId = cfg.syncDeviceId
        do {
            let envelope = try readEnvelope(path)
            let remote = envelope == nil ? SyncSnapshot() : try decryptEnvelope(envelope!, passphrase: cfg.syncSecret)
            let merged = mergeSnapshots(local, remote)
            let changed = applySnapshotToConfig(&cfg, merged)
            if write && snapshotIdentity(merged) != snapshotIdentity(remote) {
                var toWrite = merged
                toWrite.updatedAt = stamp
                toWrite.deviceId = cfg.syncDeviceId
                try writeEnvelope(path, try encryptEnvelope(toWrite, passphrase: cfg.syncSecret))
                status.pushed = true
            }
            cfg.syncLastAt = stamp
            cfg.syncLastError = ""
            status.ok = true
            status.changed = changed
            if changed && status.pushed { status.message = "已合并并对齐同步文件" }
            else if changed { status.message = "已从同步文件导入账号" }
            else if status.pushed { status.message = "已写入同步文件" }
            else { status.message = "账号已与同步文件一致" }
            return status
        } catch {
            let message = (error as? CursorAPIError)?.message ?? error.localizedDescription
            cfg.syncLastError = message
            status.message = message.isEmpty ? "同步失败" : message
            return status
        }
    }

    public static func exportToFile(_ cfg: inout AppConfig, path: String, passphrase: String? = nil) throws -> String {
        let secret = (passphrase ?? cfg.syncSecret).trimmingCharacters(in: .whitespaces)
        if secret.isEmpty { throw CursorAPIError("请设置同步口令") }
        let ext = URL(fileURLWithPath: path).pathExtension.lowercased()
        let dest = fileSuffixes.contains("." + ext) ? path : resolveSyncPath(path)
        var snap = snapshotFromConfig(cfg)
        snap.updatedAt = nowIso()
        snap.deviceId = ensureDeviceId(&cfg)
        try writeEnvelope(dest, try encryptEnvelope(snap, passphrase: secret))
        return dest
    }

    public static func importFromFile(_ cfg: inout AppConfig, path: String, passphrase: String? = nil) throws {
        let secret = (passphrase ?? cfg.syncSecret).trimmingCharacters(in: .whitespaces)
        if secret.isEmpty { throw CursorAPIError("请设置同步口令") }
        guard let envelope = try readEnvelope(path) else { throw CursorAPIError("找不到同步文件") }
        let remote = try decryptEnvelope(envelope, passphrase: secret)
        applySnapshotToConfig(&cfg, mergeSnapshots(snapshotFromConfig(cfg), remote))
        cfg.syncLastAt = nowIso()
        cfg.syncLastError = ""
    }

    static func str(_ value: Any?) -> String {
        if let s = value as? String { return s }
        return ""
    }

    static func intValue(_ value: Any?) -> Int? {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        return nil
    }

    static func num(_ value: Any?) -> Double? {
        if let n = value as? NSNumber { return n.doubleValue }
        if let d = value as? Double { return d }
        if let s = value as? String {
            let cleaned = s.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "，", with: ".")
            return Double(cleaned)
        }
        return nil
    }

    static func canonicalNumber(_ value: Double) -> String {
        var text = String(format: "%.6f", value)
        while text.contains("."), text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(".") { text.removeLast() }
        return text.isEmpty ? "0" : text
    }
}
