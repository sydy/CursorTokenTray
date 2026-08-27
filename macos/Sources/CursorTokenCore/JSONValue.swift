import Foundation

/// Loose JSON bag matching Python's dict-based Dashboard payloads.
public struct JSONValue {
    public let raw: Any

    public init(_ raw: Any) {
        self.raw = raw
    }

    public static let null = JSONValue(NSNull())

    public static func parse(_ data: Data) throws -> JSONValue {
        JSONValue(try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]))
    }

    public static func parseObject(_ data: Data) throws -> JSONValue {
        let value = try parse(data)
        guard value.isObject else {
            throw CursorAPIError("接口返回格式异常")
        }
        return value
    }

    public var isNull: Bool { raw is NSNull }
    public var isObject: Bool { raw is [String: Any] }
    public var isEmpty: Bool {
        if isNull { return true }
        if let dict = raw as? [String: Any] { return dict.isEmpty }
        if let arr = raw as? [Any] { return arr.isEmpty }
        if let s = raw as? String { return s.isEmpty }
        return false
    }

    public subscript(_ key: String) -> JSONValue {
        guard let dict = raw as? [String: Any], let value = dict[key] else {
            return .null
        }
        return JSONValue(value)
    }

    public var object: [String: Any] {
        raw as? [String: Any] ?? [:]
    }

    public var array: [JSONValue] {
        (raw as? [Any] ?? []).map(JSONValue.init)
    }

    public func asString() -> String? {
        if isNull { return nil }
        if let s = raw as? String { return s }
        if let n = raw as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() {
            return n.stringValue
        }
        return nil
    }

    public func asDouble() -> Double? {
        if isNull { return nil }
        if let s = raw as? String {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if t.isEmpty { return nil }
            return Double(t)
        }
        if let n = raw as? NSNumber {
            if CFGetTypeID(n) == CFBooleanGetTypeID() { return nil }
            return n.doubleValue
        }
        return nil
    }

    public func asInt() -> Int? {
        guard let n = asDouble() else { return nil }
        return Int((n).rounded())
    }

    public func asBool() -> Bool {
        if let b = raw as? Bool { return b }
        if let n = raw as? NSNumber { return n.boolValue }
        if let s = raw as? String {
            return ["1", "true", "yes"].contains(s.lowercased())
        }
        return false
    }

    public var jsonData: Data {
        (try? JSONSerialization.data(withJSONObject: raw, options: [.sortedKeys])) ?? Data()
    }
}

func round1(_ value: Double) -> Double {
    (value * 10.0).rounded() / 10.0
}

func round2(_ value: Double) -> Double {
    (value * 100.0).rounded() / 100.0
}

func clampPercent(_ value: Double) -> Double {
    min(100.0, max(0.0, value))
}
