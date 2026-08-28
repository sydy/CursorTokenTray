namespace CursorTokenCore;

public static class CrashLog
{
    public static string PathFor(string? directory = null) => AppPaths.ErrorLogPath(directory);

    public static void Write(Exception? ex, string? directory = null)
    {
        if (ex is null) return;
        try
        {
            var dir = AppPaths.ConfigDirectory(directory);
            Directory.CreateDirectory(dir);
            var text = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + Environment.NewLine + ex + Environment.NewLine + Environment.NewLine;
            File.AppendAllText(PathFor(directory), text);
        }
        catch
        {
            // Never throw from a crash logger.
        }
    }
}
