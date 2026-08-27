import Foundation

public struct CursorClient: Sendable {
    public var session: URLSession
    public var timeout: TimeInterval

    public init(session: URLSession = .shared, timeout: TimeInterval = 30) {
        self.session = session
        self.timeout = timeout
    }

    public func fetchUsageSummary(sessionToken: String, timeout: TimeInterval? = nil) async throws -> UsageSnapshot {
        let token = try Token.normalize(sessionToken)
        if token.isEmpty { throw CursorAPIError("未配置 Session Token", statusCode: 401) }
        let limit = timeout ?? self.timeout
        var lastError: CursorAPIError?
        var snapshot: UsageSnapshot?
        for endpoint in usageEndpoints {
            do {
                let payload = try await requestJSON(method: "GET", endpoint: endpoint, token: token, timeout: limit)
                snapshot = UsageParser.parseUsageSummary(payload)
                break
            } catch let err as CursorAPIError {
                lastError = err
                if err.statusCode != 404 && err.statusCode != 405 { throw err }
            }
        }
        guard var snapshot else {
            throw lastError ?? CursorAPIError("接口返回格式异常")
        }
        do {
            try await attachAggregatedTokens(&snapshot, token: token, timeout: limit)
        } catch {
            // 明细失败不影响套餐剩余
        }
        return snapshot
    }

    func attachAggregatedTokens(_ snapshot: inout UsageSnapshot, token: String, timeout: TimeInterval) async throws {
        guard let startMs = UsageParser.isoToMs(snapshot.billingCycleStart) else { return }
        var endMs = UsageParser.isoToMs(snapshot.billingCycleEnd) ?? Int(Date().timeIntervalSince1970 * 1000)
        let nowMs = Int(Date().timeIntervalSince1970 * 1000)
        if endMs > nowMs { endMs = nowMs }
        if endMs < startMs { endMs = startMs }
        let teamId = UsageParser.teamId(from: snapshot.raw)
        let payload = try await requestJSON(
            method: "POST",
            endpoint: aggregatedUsageEndpoint,
            token: token,
            body: ["teamId": teamId, "startDate": startMs, "endDate": endMs],
            timeout: timeout
        )
        let parsed = UsageParser.parseAggregatedUsage(
            payload,
            autoPercent: snapshot.autoPercentUsed,
            apiPercent: snapshot.apiPercentUsed
        )
        snapshot.modelUsages = parsed.models
        snapshot.totalTokens = parsed.total
    }

    func requestJSON(
        method: String,
        endpoint: String,
        token: String,
        body: [String: Any]? = nil,
        timeout: TimeInterval
    ) async throws -> JSONValue {
        guard let url = URL(string: cursorBaseURL + endpoint) else {
            throw CursorAPIError("接口返回格式异常")
        }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("WorkosCursorSessionToken=\(token)", forHTTPHeaderField: "Cookie")
        request.setValue("https://cursor.com", forHTTPHeaderField: "Origin")
        request.setValue("https://cursor.com/dashboard", forHTTPHeaderField: "Referer")
        request.setValue("Mozilla/5.0 CursorTokenTray/1.0", forHTTPHeaderField: "User-Agent")
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw CursorAPIError("网络错误: \(error.localizedDescription)")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 || status == 403 {
            throw CursorAPIError(CursorAPIError.authMessage, statusCode: status)
        }
        if status >= 400 {
            let detail = String(data: data, encoding: .utf8)?.prefix(200) ?? ""
            let safe = detail.unicodeScalars.map { $0.isASCII ? Character($0) : "?" }.map(String.init).joined()
            throw CursorAPIError(safe.isEmpty ? "HTTP \(status)" : "HTTP \(status): \(safe)", statusCode: status)
        }
        if data.isEmpty { return JSONValue([:]) }
        do {
            return try JSONValue.parseObject(data)
        } catch let err as CursorAPIError {
            throw err
        } catch {
            throw CursorAPIError("接口返回非 JSON")
        }
    }
}
