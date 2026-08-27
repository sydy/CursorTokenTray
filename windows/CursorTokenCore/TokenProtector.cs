using System.Security.Cryptography;
using System.Text;

namespace CursorTokenCore;

/// <summary>
/// Encrypts session tokens at rest. Windows uses DPAPI (CurrentUser);
/// other OS (unit tests) leave plaintext so CI can round-trip config files.
/// </summary>
public static class TokenProtector
{
    public const string Prefix = "enc:v1:";
    public const string DecryptFailedMessage = "Token 解密失败，请重新导入";
    static readonly byte[] Entropy = "CursorTokenTray.v1"u8.ToArray();

    public static bool IsProtected(string? value) =>
        !string.IsNullOrEmpty(value) && value.StartsWith(Prefix, StringComparison.Ordinal);

    public static string Protect(string plaintext)
    {
        if (string.IsNullOrEmpty(plaintext) || IsProtected(plaintext)) return plaintext;
        if (!OperatingSystem.IsWindows()) return plaintext;
        var data = ProtectedData.Protect(Encoding.UTF8.GetBytes(plaintext), Entropy, DataProtectionScope.CurrentUser);
        return Prefix + Convert.ToBase64String(data);
    }

    /// <summary>
    /// Decrypts a stored value. Never returns an <c>enc:v1:</c> blob as if it were a session token.
    /// On failure the plaintext is empty.
    /// </summary>
    public static string Unprotect(string stored)
    {
        TryUnprotect(stored, out var plaintext);
        return plaintext;
    }

    public static bool TryUnprotect(string? stored, out string plaintext)
    {
        plaintext = stored ?? "";
        if (string.IsNullOrEmpty(stored) || !IsProtected(stored)) return true;
        if (!OperatingSystem.IsWindows())
        {
            plaintext = "";
            return false;
        }
        try
        {
            var data = ProtectedData.Unprotect(Convert.FromBase64String(stored[Prefix.Length..]), Entropy, DataProtectionScope.CurrentUser);
            plaintext = Encoding.UTF8.GetString(data);
            return true;
        }
        catch
        {
            plaintext = "";
            return false;
        }
    }

    public static string DiskToken(string plaintext, string storedRaw, bool decryptFailed) =>
        decryptFailed && IsProtected(storedRaw) ? storedRaw : Protect(plaintext);
}
