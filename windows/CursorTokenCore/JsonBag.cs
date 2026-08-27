using System.Text.Json;

namespace CursorTokenCore;

public sealed class CursorApiException : Exception
{
    public int? StatusCode { get; }
    public CursorApiException(string message, int? statusCode = null) : base(message) => StatusCode = statusCode;
    public bool IsAuthError => StatusCode is 401 or 403 || Token.IsAuthErrorMessage(Message);
    public const string AuthMessage = "Token 已过期或无效，请重新粘贴 WorkosCursorSessionToken";
}

public readonly struct JsonBag
{
    readonly JsonElement? _el;
    public JsonBag(JsonElement el) => _el = el;
    public static JsonBag Null => default;
    public static JsonBag Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return new JsonBag(doc.RootElement.Clone());
    }

    public bool Has(string key) =>
        _el is { ValueKind: JsonValueKind.Object } obj && obj.TryGetProperty(key, out _);
    public static JsonBag Parse(JsonElement el) => new(el.Clone());
    public bool IsObject => _el is { ValueKind: JsonValueKind.Object };
    public bool IsEmpty =>
        _el is null or { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined }
        || (_el is { ValueKind: JsonValueKind.Object } e && !e.EnumerateObject().Any());

    public JsonBag this[string key]
    {
        get
        {
            if (_el is { ValueKind: JsonValueKind.Object } obj && obj.TryGetProperty(key, out var v))
                return new JsonBag(v.Clone());
            return Null;
        }
    }

    public IEnumerable<JsonBag> Array =>
        _el is { ValueKind: JsonValueKind.Array } a ? a.EnumerateArray().Select(x => new JsonBag(x.Clone())) : [];

    public string? AsString()
    {
        if (_el is null) return null;
        return _el.Value.ValueKind switch
        {
            JsonValueKind.String => _el.Value.GetString(),
            JsonValueKind.Number => _el.Value.ToString(),
            _ => null
        };
    }

    public double? AsDouble()
    {
        if (_el is null) return null;
        switch (_el.Value.ValueKind)
        {
            case JsonValueKind.Number:
                return _el.Value.GetDouble();
            case JsonValueKind.String:
                var s = _el.Value.GetString()?.Trim();
                return double.TryParse(s, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d) ? d : null;
            default:
                return null;
        }
    }

    public int? AsInt()
    {
        var n = AsDouble();
        return n is null ? null : (int)Math.Round(n.Value);
    }

    public bool AsBool()
    {
        if (_el is null) return false;
        return _el.Value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number => _el.Value.GetDouble() != 0,
            JsonValueKind.String => _el.Value.GetString() is "1" or "true" or "yes",
            _ => false
        };
    }
}

public static class Numbers
{
    public static double Round1(double v) => Math.Round(v, 1, MidpointRounding.ToEven);
    public static double Round2(double v) => Math.Round(v, 2, MidpointRounding.ToEven);
    public static double ClampPercent(double v) => Math.Min(100, Math.Max(0, v));
}
