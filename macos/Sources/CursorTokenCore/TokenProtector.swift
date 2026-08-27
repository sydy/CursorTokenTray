import Foundation

#if canImport(CryptoKit) && canImport(Security)
import CryptoKit
import Security

/// Encrypts session tokens at rest with AES-GCM. The wrap key lives in the
/// macOS keychain (service `com.harker.cursortokentray`). If the keychain is
/// unavailable Protect throws so a save never replaces ciphertext with plaintext.
public enum TokenProtector {
    public static let prefix = "enc:v1:"
    public static let decryptFailedMessage = "Token 解密失败，请重新导入"
    public static let service = "com.harker.cursortokentray"
    static let keyAccount = "wrap-key-v1"

    public static func isProtected(_ value: String) -> Bool {
        value.hasPrefix(prefix)
    }

    public static func protect(_ plaintext: String) throws -> String {
        let value = plaintext.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty || isProtected(value) { return plaintext }
        guard let key = wrapKey() else {
            throw CursorAPIError("无法使用钥匙串加密 Token，配置未写入")
        }
        let sealed = try AES.GCM.seal(Data(value.utf8), using: key)
        guard let combined = sealed.combined else {
            throw CursorAPIError("无法使用钥匙串加密 Token，配置未写入")
        }
        return prefix + combined.base64EncodedString()
    }

    /// Never returns an `enc:v1:` blob as if it were a session token.
    public static func unprotect(_ stored: String) -> String {
        tryUnprotect(stored).value
    }

    public static func tryUnprotect(_ stored: String) -> (value: String, ok: Bool) {
        if stored.isEmpty || !isProtected(stored) { return (stored, true) }
        let b64 = String(stored.dropFirst(prefix.count))
        guard let data = Data(base64Encoded: b64), let key = wrapKey() else {
            return ("", false)
        }
        do {
            let box = try AES.GCM.SealedBox(combined: data)
            let opened = try AES.GCM.open(box, using: key)
            return (String(data: opened, encoding: .utf8) ?? "", true)
        } catch {
            return ("", false)
        }
    }

    public static func diskToken(plaintext: String, storedRaw: String, decryptFailed: Bool) throws -> String {
        if decryptFailed && isProtected(storedRaw) { return storedRaw }
        return try protect(plaintext)
    }

    static func wrapKey() -> SymmetricKey? {
        if let existing = readKey() { return existing }
        let key = SymmetricKey(size: .bits256)
        if storeKey(key) { return key }
        return nil
    }

    static func readKey() -> SymmetricKey? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data, data.count == 32 else { return nil }
        return SymmetricKey(data: data)
    }

    static func storeKey(_ key: SymmetricKey) -> Bool {
        let data = key.withUnsafeBytes { Data($0) }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyAccount,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecValueData as String: data,
        ]
        SecItemDelete(query as CFDictionary)
        return SecItemAdd(query as CFDictionary, nil) == errSecSuccess
    }
}

#else

public enum TokenProtector {
    public static let prefix = "enc:v1:"
    public static let decryptFailedMessage = "Token 解密失败，请重新导入"

    public static func isProtected(_ value: String) -> Bool { value.hasPrefix(prefix) }
    public static func protect(_ plaintext: String) throws -> String { plaintext }
    public static func unprotect(_ stored: String) -> String { tryUnprotect(stored).value }
    public static func tryUnprotect(_ stored: String) -> (value: String, ok: Bool) {
        if isProtected(stored) { return ("", false) }
        return (stored, true)
    }
    public static func diskToken(plaintext: String, storedRaw: String, decryptFailed: Bool) throws -> String {
        if decryptFailed && isProtected(storedRaw) { return storedRaw }
        return try protect(plaintext)
    }
}

#endif
