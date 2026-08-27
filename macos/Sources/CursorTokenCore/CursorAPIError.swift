import Foundation

public struct CursorAPIError: Error, LocalizedError, Equatable {
    public var message: String
    public var statusCode: Int?

    public init(_ message: String, statusCode: Int? = nil) {
        self.message = message
        self.statusCode = statusCode
    }

    public var errorDescription: String? { message }

    public var isAuthError: Bool {
        if statusCode == 401 || statusCode == 403 { return true }
        return Token.isAuthErrorMessage(message)
    }

    public static let authMessage = "Token 已过期或无效，请重新粘贴 WorkosCursorSessionToken"
}
