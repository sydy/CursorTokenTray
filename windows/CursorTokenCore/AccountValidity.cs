using System.Globalization;

namespace CursorTokenCore;

public static class AccountValidity
{
    public const string LongTerm = "long_term";
    public const string Temporary = "temporary";
    public const int MaxDays = 999;
    public const int MaxHours = 23;

    public static string SanitizeKind(string? raw)
    {
        var key = (raw ?? "").Trim().ToLowerInvariant().Replace('-', '_');
        return key is "temporary" or "temp" or "short" ? Temporary : LongTerm;
    }

    public static int ClampDays(object? raw) => ClampInt(raw, 0, MaxDays);
    public static int ClampHours(object? raw) => ClampInt(raw, 0, MaxHours);

    public static bool IsTemporary(Account? account) =>
        account is not null && SanitizeKind(account.AccountKind) == Temporary;

    public static string? ComputeEndIso(string? startAt, int days, int hours)
    {
        var start = AccountSync.ParseIso(startAt);
        if (start is null) return null;
        var d = ClampDays(days);
        var h = ClampHours(hours);
        if (d == 0 && h == 0) return null;
        return AccountSync.NowIso(start.Value.AddDays(d).AddHours(h));
    }

    public static string? AccountEndIso(Account? account)
    {
        if (!IsTemporary(account) || account is null) return null;
        return ComputeEndIso(account.TempStartAt, account.TempValidDays, account.TempValidHours);
    }

    public static void ApplyEndOverride(UsageSnapshot snap, Account? account, DateTimeOffset? now = null)
    {
        var end = AccountEndIso(account);
        if (string.IsNullOrEmpty(end)) return;
        snap.BillingCycleEnd = end;
        snap.DaysRemaining = UsageParser.DaysUntil(end, now ?? DateTimeOffset.UtcNow);
        snap.BillingCycleEndOverridden = true;
    }

    public static bool ValidityEquals(Account a, string kind, string startAt, int days, int hours) =>
        SanitizeKind(a.AccountKind) == SanitizeKind(kind)
        && (a.TempStartAt ?? "").Trim() == (startAt ?? "").Trim()
        && ClampDays(a.TempValidDays) == ClampDays(days)
        && ClampHours(a.TempValidHours) == ClampHours(hours);

    static int ClampInt(object? raw, int lo, int hi)
    {
        int n;
        switch (raw)
        {
            case int i: n = i; break;
            case long l: n = (int)l; break;
            case double d: n = (int)d; break;
            case string s when int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out var p): n = p; break;
            default: return 0;
        }
        return Math.Clamp(n, lo, hi);
    }
}
