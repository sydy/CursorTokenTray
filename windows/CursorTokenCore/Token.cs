using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CursorTokenCore;

public static class Token
{
    public const string CookieName = "WorkosCursorSessionToken";
    static readonly char[] Junk = ['\u2026', '\u2022', '\uFEFF', '\u200B', '\u200C', '\u200D', '\u00A0'];

    public static string Normalize(string raw)
    {
        var value = raw.Trim().Trim('"', '\'');
        if (value.Length == 0) return "";
        foreach (var ch in Junk) value = value.Replace(ch.ToString(), "");
        var m = Regex.Match(value, @"(?:^|[;\s])WorkosCursorSessionToken=([^;\s]+)", RegexOptions.IgnoreCase);
        if (m.Success) value = m.Groups[1].Value.Trim();
        else if (value.StartsWith("workoscursorsessiontoken=", StringComparison.OrdinalIgnoreCase))
            value = value.Split('=', 2)[1].Trim();
        value = string.Concat(value.Where(c => !char.IsWhiteSpace(c)));
        if (value.Contains("%3A%3A") || value.Contains("%3a%3a")) { }
        else if (value.Contains("::"))
            value = ReplaceFirst(value, "::", "%3A%3A");
        else if (LooksLikeJwt(value))
        {
            var uid = ExtractUserId(value);
            if (uid.Length > 0) value = uid + "%3A%3A" + value;
        }
        if (value.Any(c => c > 255) || value.Contains('\uFFFD'))
            throw new CursorApiException(
                "读到的 Token 已损坏（常见于 Chrome Cookie 解密失败，不是复制漏了）。请再点一次「导入」，或改用 Firefox，或在开发者工具里完整复制 WorkosCursorSessionToken。",
                401);
        return value;
    }

    public static List<string> Variants(string token)
    {
        var list = new List<string>();
        void Add(string? v)
        {
            var t = (v ?? "").Trim();
            if (t.Length > 0 && !list.Contains(t)) list.Add(t);
        }
        var raw = token.Trim();
        try { Add(Normalize(raw)); } catch { }
        Add(raw);
        var jwt = raw;
        if (raw.Contains("%3A%3A"))
        {
            jwt = raw.Split(["%3A%3A"], 2, StringSplitOptions.None)[^1];
            Add(ReplaceFirst(raw, "%3A%3A", "::"));
        }
        else if (raw.Contains("%3a%3a"))
        {
            jwt = raw.Split(["%3a%3a"], 2, StringSplitOptions.None)[^1];
            Add(ReplaceFirst(raw, "%3a%3a", "::"));
        }
        else if (raw.Contains("::"))
        {
            jwt = raw.Split(["::"], 2, StringSplitOptions.None)[^1];
            Add(ReplaceFirst(raw, "::", "%3A%3A"));
        }
        if (LooksLikeJwt(jwt))
        {
            Add(jwt);
            var payload = JwtPayload(jwt);
            if (payload is not null && payload.TryGetValue("sub", out var subObj) && subObj is not null)
            {
                var sub = subObj is JsonElement je
                    ? (je.ValueKind == JsonValueKind.String ? je.GetString() ?? "" : je.ToString())
                    : subObj.ToString() ?? "";
                if (sub.Length > 0)
                {
                    var uid = sub.Split('|')[^1];
                    Add($"{uid}%3A%3A{jwt}");
                    Add($"{uid}::{jwt}");
                    if (sub != uid)
                    {
                        Add($"{sub}%3A%3A{jwt}");
                        Add($"{sub}::{jwt}");
                    }
                }
            }
        }
        return list.Count > 4 ? list.Take(4).ToList() : list;
    }

    public static string AccountId(string token)
    {
        string value;
        try { value = Normalize(token); }
        catch { value = token.Trim(); }
        if (value.Length == 0) return "";
        var jwt = value;
        var prefix = "";
        foreach (var sep in new[] { "%3A%3A", "%3a%3a", "::" })
        {
            var i = value.IndexOf(sep, StringComparison.Ordinal);
            if (i >= 0)
            {
                prefix = value[..i];
                jwt = value[(i + sep.Length)..];
                break;
            }
        }
        if (LooksLikeJwt(jwt))
        {
            var uid = ExtractUserId(jwt);
            if (uid.Length > 0) return SafeAccountId(uid);
        }
        if (prefix.Trim().Length > 0) return SafeAccountId(prefix.Split('|')[^1]);
        if (LooksLikeJwt(value))
        {
            var uid = ExtractUserId(value);
            if (uid.Length > 0) return SafeAccountId(uid);
        }
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
        return "tok_" + digest[..16];
    }

    public static string SafeAccountId(string value)
    {
        var cleaned = Regex.Replace(value ?? "", @"[^A-Za-z0-9._-]+", "_").Trim('.', '_', '-');
        if (cleaned.Length == 0) cleaned = "account";
        return cleaned.Length > 80 ? cleaned[..80] : cleaned;
    }

    public static bool IsAuthErrorMessage(string? message)
    {
        if (string.IsNullOrEmpty(message)) return false;
        var text = message.ToLowerInvariant();
        string[] keys = ["token 已过期", "token 无效", "未配置 token", "未配置 session", "workoscursorsessiontoken", "unauthorized", "forbidden"];
        if (keys.Any(text.Contains)) return true;
        return (message.Contains("过期") || message.Contains("无效")) && (text.Contains("token") || message.Contains("Token"));
    }

    public static bool LooksLikeJwt(string value)
    {
        var parts = value.Split('.');
        return parts.Length == 3 && parts.All(p => p.Length > 0);
    }

    public static Dictionary<string, object?>? JwtPayload(string jwt)
    {
        try
        {
            var parts = jwt.Split('.');
            if (parts.Length != 3) return null;
            var payload = parts[1].Replace('-', '+').Replace('_', '/');
            payload += new string('=', (4 - payload.Length % 4) % 4);
            var json = Encoding.UTF8.GetString(Convert.FromBase64String(payload));
            return JsonSerializer.Deserialize<Dictionary<string, object?>>(json);
        }
        catch { return null; }
    }

    public static string ExtractUserId(string jwt)
    {
        var payload = JwtPayload(jwt);
        if (payload is null || !payload.TryGetValue("sub", out var subObj) || subObj is null) return "";
        var sub = subObj is JsonElement je
            ? (je.ValueKind == JsonValueKind.String ? je.GetString() ?? "" : je.ToString())
            : subObj.ToString() ?? "";
        return sub.Contains('|') ? sub.Split('|')[^1] : sub;
    }

    static string ReplaceFirst(string text, string old, string neu)
    {
        var i = text.IndexOf(old, StringComparison.Ordinal);
        return i < 0 ? text : text[..i] + neu + text[(i + old.Length)..];
    }
}
