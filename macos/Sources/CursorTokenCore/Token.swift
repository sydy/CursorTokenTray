import CryptoKit
import Foundation

public enum Token {
    public static let cookieName = "WorkosCursorSessionToken"
    public static let junk: [Character] = ["\u{2026}", "\u{2022}", "\u{FEFF}", "\u{200B}", "\u{200C}", "\u{200D}", "\u{00A0}"]

    public static func normalize(_ raw: String) throws -> String {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        if value.isEmpty { return "" }
        for ch in junk {
            value.removeAll { $0 == ch }
        }

        let cookieRe = try? NSRegularExpression(
            pattern: #"(?:^|[;\s])WorkosCursorSessionToken=([^;\s]+)"#,
            options: .caseInsensitive
        )
        if let cookieRe,
           let match = cookieRe.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)),
           match.numberOfRanges > 1,
           let r = Range(match.range(at: 1), in: value)
        {
            value = String(value[r]).trimmingCharacters(in: .whitespaces)
        } else if value.lowercased().hasPrefix("workoscursorsessiontoken=") {
            value = String(value.split(separator: "=", maxSplits: 1).dropFirst().first ?? "")
                .trimmingCharacters(in: .whitespaces)
        }

        value = value.filter { !$0.isWhitespace }

        if value.contains("%3A%3A") || value.contains("%3a%3a") {
            // already encoded
        } else if value.contains("::") {
            if let r = value.range(of: "::") {
                value.replaceSubrange(r, with: "%3A%3A")
            }
        } else if looksLikeJWT(value) {
            let userId = extractUserId(fromJWT: value)
            if !userId.isEmpty {
                value = "\(userId)%3A%3A\(value)"
            }
        }

        if value.unicodeScalars.contains(where: { $0.value > 255 }) || value.contains("\u{FFFD}") {
            throw CursorAPIError(
                "读到的 Token 已损坏（常见于 Chrome Cookie 解密失败，不是复制漏了）。"
                    + "请再点一次「导入」，钥匙串弹窗选「始终允许」；"
                    + "或改用 Safari / Firefox，或在开发者工具里完整复制 WorkosCursorSessionToken。",
                statusCode: 401
            )
        }
        return value
    }

    public static func variants(_ token: String) -> [String] {
        var list: [String] = []
        func add(_ value: String?) {
            let text = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty, !list.contains(text) { list.append(text) }
        }
        let raw = token.trimmingCharacters(in: .whitespacesAndNewlines)
        do { add(try normalize(raw)) } catch { /* skip */ }
        add(raw)
        var jwt = raw
        if raw.contains("%3A%3A") {
            jwt = raw.components(separatedBy: "%3A%3A").last ?? raw
            add(raw.replacingOccurrences(of: "%3A%3A", with: "::", options: [], range: raw.range(of: "%3A%3A")))
        } else if raw.contains("%3a%3a") {
            jwt = raw.components(separatedBy: "%3a%3a").last ?? raw
            add(raw.replacingOccurrences(of: "%3a%3a", with: "::", options: [], range: raw.range(of: "%3a%3a")))
        } else if raw.contains("::") {
            jwt = raw.components(separatedBy: "::").last ?? raw
            add(raw.replacingOccurrences(of: "::", with: "%3A%3A", options: [], range: raw.range(of: "::")))
        }
        if looksLikeJWT(jwt) {
            add(jwt)
            if let payload = jwtPayload(jwt) {
                let sub = payload["sub"] as? String ?? ""
                if !sub.isEmpty {
                    let userId = sub.split(separator: "|").last.map(String.init) ?? sub
                    add("\(userId)%3A%3A\(jwt)")
                    add("\(userId)::\(jwt)")
                    if sub != userId {
                        add("\(sub)%3A%3A\(jwt)")
                        add("\(sub)::\(jwt)")
                    }
                }
            }
        }
        if list.count > 4 { return Array(list.prefix(4)) }
        return list
    }

    public static func accountId(from token: String) -> String {
        let value: String
        do { value = try normalize(token) } catch {
            value = token.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if value.isEmpty { return "" }

        var jwt = value
        var prefix = ""
        for sep in ["%3A%3A", "%3a%3a", "::"] {
            if let r = value.range(of: sep) {
                prefix = String(value[..<r.lowerBound])
                jwt = String(value[r.upperBound...])
                break
            }
        }
        if looksLikeJWT(jwt) {
            let uid = extractUserId(fromJWT: jwt)
            if !uid.isEmpty { return safeAccountId(uid) }
        }
        let trimmedPrefix = prefix.trimmingCharacters(in: .whitespaces)
        if !trimmedPrefix.isEmpty {
            let last = trimmedPrefix.split(separator: "|").last.map(String.init) ?? trimmedPrefix
            return safeAccountId(last)
        }
        if looksLikeJWT(value) {
            let uid = extractUserId(fromJWT: value)
            if !uid.isEmpty { return safeAccountId(uid) }
        }
        let digest = SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
        return "tok_" + digest.prefix(16)
    }

    public static func safeAccountId(_ value: String) -> String {
        let pattern = try! NSRegularExpression(pattern: "[^A-Za-z0-9._-]+")
        let range = NSRange(value.startIndex..., in: value)
        var cleaned = pattern.stringByReplacingMatches(in: value, range: range, withTemplate: "_")
        cleaned = cleaned.trimmingCharacters(in: CharacterSet(charactersIn: "._-"))
        if cleaned.isEmpty { cleaned = "account" }
        return String(cleaned.prefix(80))
    }

    public static func isAuthErrorMessage(_ message: String?) -> Bool {
        guard let message, !message.isEmpty else { return false }
        let text = message.lowercased()
        let keys = [
            "token 已过期", "token 无效", "未配置 token", "未配置 session",
            "workoscursorsessiontoken", "unauthorized", "forbidden",
        ]
        if keys.contains(where: { text.contains($0) }) { return true }
        return (message.contains("过期") || message.contains("无效"))
            && (text.contains("token") || message.contains("Token"))
    }

    public static func looksLikeJWT(_ value: String) -> Bool {
        let parts = value.split(separator: ".", omittingEmptySubsequences: false)
        return parts.count == 3 && parts.allSatisfy { !$0.isEmpty }
    }

    public static func jwtPayload(_ jwt: String) -> [String: Any]? {
        let parts = jwt.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3 else { return nil }
        var payload = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        let pad = (4 - payload.count % 4) % 4
        payload += String(repeating: "=", count: pad)
        guard let data = Data(base64Encoded: payload),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return obj
    }

    public static func extractUserId(fromJWT jwt: String) -> String {
        guard let payload = jwtPayload(jwt) else { return "" }
        let sub = payload["sub"] as? String ?? ""
        return sub.split(separator: "|").last.map(String.init) ?? ""
    }
}
