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
    static readonly byte[] Entropy = "CursorTokenTray.v1"u8.ToArray();

    public static bool IsProtected(string? value) =>
        !string.IsNullOrEmpty(value) && value.StartsWith(Prefix, StringComparison.Ordinal);

    public static string Protect(string plaintext)
    {
        if (string.IsNullOrEmpty(plaintext) || IsProtected(plaintext)) return plaintext;
        if (!OperatingSystem.IsWindows()) return plaintext;
        try
        {
            var data = ProtectedData.Protect(Encoding.UTF8.GetBytes(plaintext), Entropy, DataProtectionScope.CurrentUser);
            return Prefix + Convert.ToBase64String(data);
        }
        catch
        {
            return plaintext;
        }
    }

    public static string Unprotect(string stored)
    {
        if (string.IsNullOrEmpty(stored) || !IsProtected(stored)) return stored;
        if (!OperatingSystem.IsWindows()) return stored;
        try
        {
            var data = ProtectedData.Unprotect(Convert.FromBase64String(stored[Prefix.Length..]), Entropy, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(data);
        }
        catch
        {
            return stored;
        }
    }
}
