import Foundation

public enum CloudSyncApi {
    public static let baseUrl = "https://sync.harker.cn"
}

public enum CloudSync {
    public static func applySession(_ cfg: inout AppConfig, email: String, password: String, access: String, refresh: String) {
        cfg.cloudEmail = email.trimmingCharacters(in: .whitespaces).lowercased()
        cfg.cloudAccessToken = access
        cfg.cloudRefreshToken = refresh
        cfg.syncSecret = password
        cfg.syncEnabled = cfg.cloudLoggedIn
        cfg.syncLastError = ""
        cfg.syncSecretDecryptFailed = false
    }

    public static func clearSession(_ cfg: inout AppConfig, keepEmail: Bool = true) {
        if !keepEmail { cfg.cloudEmail = "" }
        cfg.cloudAccessToken = ""
        cfg.cloudRefreshToken = ""
        cfg.syncSecret = ""
        cfg.cloudRevision = 0
        cfg.syncEnabled = false
    }

    public static func register(email: String, password: String) throws -> (email: String, access: String, refresh: String) {
        let payload = try send(method: "POST", path: "/v1/auth/register", access: nil, body: ["email": email, "password": password])
        return try readAuth(payload)
    }

    public static func login(email: String, password: String) throws -> (email: String, access: String, refresh: String) {
        let payload = try send(method: "POST", path: "/v1/auth/login", access: nil, body: ["email": email, "password": password])
        return try readAuth(payload)
    }

    public static func logout(_ cfg: inout AppConfig) {
        let refresh = cfg.cloudRefreshToken
        if !refresh.isEmpty {
            _ = try? send(method: "POST", path: "/v1/auth/logout", access: nil, body: ["refresh_token": refresh])
        }
        clearSession(&cfg)
    }

    public static func reconcile(_ cfg: inout AppConfig, now: Date? = nil, write: Bool = true) -> SyncStatus {
        var status = SyncStatus(path: CloudSyncApi.baseUrl)
        let reason = AccountSync.syncReady(cfg)
        if !reason.isEmpty {
            status.message = reason
            cfg.syncLastError = reason
            return status
        }
        _ = AccountSync.ensureDeviceId(&cfg)
        let stamp = AccountSync.nowIso(now)
        let passphrase = cfg.syncSecret
        var local = AccountSync.snapshotFromConfig(cfg)
        local.deviceId = cfg.syncDeviceId
        do {
            let got = try authed(&cfg, method: "GET", path: "/v1/sync", body: nil)
            let revision = intValue(got["revision"]) ?? 0
            let remote = try parseRemote(got, passphrase: passphrase)
            let merged = AccountSync.mergeSnapshots(local, remote)
            let changed = AccountSync.applySnapshotToConfig(&cfg, merged)
            if write && AccountSync.snapshotIdentity(merged) != AccountSync.snapshotIdentity(remote) {
                var toWrite = merged
                toWrite.updatedAt = stamp
                toWrite.deviceId = cfg.syncDeviceId
                let envelope = try AccountSync.encryptEnvelope(toWrite, passphrase: passphrase)
                let put = try authed(&cfg, method: "PUT", path: "/v1/sync", body: ["revision": revision, "envelope": envelope])
                cfg.cloudRevision = intValue(put["revision"]) ?? (revision + 1)
                status.pushed = true
            } else {
                cfg.cloudRevision = revision
            }
            cfg.syncLastAt = stamp
            cfg.syncLastError = ""
            status.ok = true
            status.changed = changed
            if changed && status.pushed { status.message = "已合并并对齐云端" }
            else if changed { status.message = "已从云端导入账号和设置" }
            else if status.pushed { status.message = "已上传到云端" }
            else { status.message = "账号和设置已与云端一致" }
            return status
        } catch let err as CursorAPIError where err.statusCode == 401 {
            clearSession(&cfg)
            status.message = "登录已过期，请重新登录"
            cfg.syncLastError = status.message
            return status
        } catch {
            let message = (error as? CursorAPIError)?.message ?? error.localizedDescription
            cfg.syncLastError = message.isEmpty ? "同步失败" : message
            status.message = cfg.syncLastError
            return status
        }
    }

    static func parseRemote(_ payload: [String: Any], passphrase: String) throws -> SyncSnapshot {
        guard let envelope = payload["envelope"] as? [String: Any] else { return SyncSnapshot() }
        return try AccountSync.decryptEnvelope(envelope, passphrase: passphrase)
    }

    static func readAuth(_ payload: [String: Any]) throws -> (email: String, access: String, refresh: String) {
        let access = str(payload["access_token"])
        let refresh = str(payload["refresh_token"])
        let email = str(payload["email"])
        if access.isEmpty { throw CursorAPIError("登录失败") }
        return (email, access, refresh)
    }

    static func authed(_ cfg: inout AppConfig, method: String, path: String, body: [String: Any]?) throws -> [String: Any] {
        do {
            return try send(method: method, path: path, access: cfg.cloudAccessToken, body: body)
        } catch let err as CursorAPIError where err.statusCode == 401 {
            if !refresh(&cfg) { throw err }
            return try send(method: method, path: path, access: cfg.cloudAccessToken, body: body)
        }
    }

    static func refresh(_ cfg: inout AppConfig) -> Bool {
        let token = cfg.cloudRefreshToken.trimmingCharacters(in: .whitespaces)
        if token.isEmpty { return false }
        do {
            let payload = try send(method: "POST", path: "/v1/auth/refresh", access: nil, body: ["refresh_token": token])
            cfg.cloudAccessToken = str(payload["access_token"])
            if let next = payload["refresh_token"] as? String, !next.isEmpty {
                cfg.cloudRefreshToken = next
            }
            return !cfg.cloudAccessToken.isEmpty
        } catch {
            clearSession(&cfg)
            return false
        }
    }

    static func send(method: String, path: String, access: String?, body: [String: Any]?) throws -> [String: Any] {
        guard let url = URL(string: CloudSyncApi.baseUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path) else {
            throw CursorAPIError("无法连接同步服务器")
        }
        var req = URLRequest(url: url, timeoutInterval: 20)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let access, !access.isEmpty {
            req.setValue("Bearer \(access)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let box = RequestBox()
        let sem = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { data, response, error in
            box.data = data
            box.response = response
            box.error = error
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 25)
        if box.error != nil { throw CursorAPIError("无法连接同步服务器") }
        let status = (box.response as? HTTPURLResponse)?.statusCode ?? 0
        let obj = (try? JSONSerialization.jsonObject(with: box.data ?? Data())) as? [String: Any] ?? [:]
        if status >= 400 {
            let detail = str(obj["detail"])
            throw CursorAPIError(detail.isEmpty ? "同步失败" : detail, statusCode: status)
        }
        return obj
    }

    static func str(_ value: Any?) -> String {
        (value as? String) ?? ""
    }

    static func intValue(_ value: Any?) -> Int? {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        return nil
    }
}

private final class RequestBox: @unchecked Sendable {
    var data: Data?
    var response: URLResponse?
    var error: Error?
}
