using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;

namespace SpirePilot;

public sealed class Backend
{
    public string Python { get; set; } = "python";
    public string Root { get; set; } = "";
    public async Task<JsonNode> Call(string command, object? data = null)
    {
        if (!File.Exists(Path.Combine(Root, "desktop_bridge.py")))
            throw new InvalidOperationException("找不到控制器，请在模型与设置中选择 hybrid 文件夹。");
        var info = new ProcessStartInfo(Python) {
            WorkingDirectory = Root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        };
        info.ArgumentList.Add(Path.Combine(Root, "desktop_bridge.py"));
        info.ArgumentList.Add(command);
        using var process = Process.Start(info) ?? throw new InvalidOperationException("无法启动 Python。");
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteAsync(System.Text.Json.JsonSerializer.Serialize(data ?? new {}));
        process.StandardInput.Close();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException) {
            if (!process.HasExited) process.Kill();
            throw new TimeoutException("本地控制器响应超时，请检查 Python 与控制器路径。");
        }
        var output = await stdout;
        var errors = await stderr;
        JsonNode? envelope;
        try { envelope = JsonNode.Parse(output); }
        catch { throw new InvalidOperationException("控制器响应无效：" + errors[..Math.Min(500, errors.Length)]); }
        if (envelope?["ok"]?.GetValue<bool>() != true)
            throw new InvalidOperationException(envelope?["error"]?.ToString() ?? "控制器调用失败。");
        return envelope["data"]!;
    }
}
