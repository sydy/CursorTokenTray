import Foundation

#if canImport(CryptoKit) && canImport(Security)
import CryptoKit
import Security

/// Encrypts session tokens at rest with AES-GCM. The wrap key lives in the
/// macOS keychain (service `com.harker.cursortokentray`). If the keychain is
/// unavailable the plaintext is left unchanged so a save never drops the token.
public enum TokenProtector {
    public static let prefix = "enc:v1:"
    public static let service = "com.harker.cursortokentray"
    static let keyAccount = "wrap-key-v1"

    public static func isProtected(_ value: String) -> Bool {
        value.hasPrefix(prefix)
    }

    public static func protect(_ plaintext: String) -> String {
        let value = plaintext.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty || isProtected(value) { return plaintext }
        guard let key = wrapKey() else { return plaintext }
        do {
            let sealed = try AES.GCM.seal(Data(value.utf8), using: key)
            guard let combined = sealed.combined else { return plaintext }
            return prefix + combined.base64EncodedString()
        } catch {
            return plaintext
        }
    }

    public static func unprotect(_ stored: String) -> String {
        guard isProtected(stored) else { return stored }
        let b64 = String(stored.dropFirst(prefix.count))
        guard let data = Data(base64Encoded: b64), let key = wrapKey() else { return stored }
        do {
            let box = try AES.GCM.SealedBox(combined: data)
            let opened = try AES.GCM.open(box, using: key)
            return String(data: opened, encoding: .utf8) ?? stored
        } catch {
            return stored
        }
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

    public static func isProtected(_ value: String) -> Bool { value.hasPrefix(prefix) }
    public static func protect(_ plaintext: String) -> String { plaintext }
    public static func unprotect(_ stored: String) -> String { stored }
}

#endif
