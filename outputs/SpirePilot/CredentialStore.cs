using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace SpirePilot;

static class CredentialStore
{
    const uint Generic = 1;
    const uint PersistLocalMachine = 2;
    const int NotFound = 1168;
    const int MaxBlobBytes = 2560;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct NativeCredential
    {
        public uint Flags;
        public uint Type;
        public string TargetName;
        public string? Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist;
        public uint AttributeCount;
        public IntPtr Attributes;
        public string? TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CredWrite(ref NativeCredential credential, uint flags);

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CredRead(string target, uint type, uint flags, out IntPtr credential);

    [DllImport("advapi32.dll", EntryPoint = "CredDeleteW", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CredDelete(string target, uint type, uint flags);

    [DllImport("advapi32.dll")]
    static extern void CredFree(IntPtr buffer);

    public static string Target(string role, string provider, string url)
    {
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Endpoint(url))))[..32];
        return $"SpirePilot:{role}:v2:{hash}";
    }

    static string Endpoint(string url) => Uri.TryCreate(url.Trim(), UriKind.Absolute, out var uri)
        ? uri.GetLeftPart(UriPartial.Authority).TrimEnd('/').ToLowerInvariant()
        : url.Trim().TrimEnd('/').ToLowerInvariant();

    static string LegacyTarget(string role, string provider, string url)
    {
        var identity = provider.Trim().ToLowerInvariant() + "\n" + Endpoint(url);
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(identity)))[..32];
        return $"SpirePilot:{role}:{hash}";
    }

    static IEnumerable<string> LegacyTargets(string role, string provider, string url) =>
        new[] { provider, "OpenRouter", "DeepSeek", "自定义" }
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(name => LegacyTarget(role, name, url));

    public static void SaveFor(string role, string provider, string url, string secret) =>
        Save(Target(role, provider, url), role, secret);

    public static string? ReadFor(string role, string provider, string url)
    {
        var target = Target(role, provider, url);
        var current = Read(target);
        if (current is not null) return current;
        foreach (var legacy in LegacyTargets(role, provider, url)) {
            var saved = Read(legacy);
            if (saved is null) continue;
            Save(target, role, saved);
            Delete(legacy);
            return saved;
        }
        return null;
    }

    public static void DeleteFor(string role, string provider, string url)
    {
        Delete(Target(role, provider, url));
        foreach (var legacy in LegacyTargets(role, provider, url)) Delete(legacy);
    }

    public static void Save(string target, string userName, string secret)
    {
        var bytes = Encoding.Unicode.GetByteCount(secret);
        if (bytes == 0) return;
        if (bytes > MaxBlobBytes) throw new InvalidOperationException("API 密钥过长，无法保存到 Windows 凭据管理器。");
        var blob = Marshal.StringToCoTaskMemUni(secret);
        try {
            var credential = new NativeCredential {
                Type = Generic,
                TargetName = target,
                UserName = userName,
                CredentialBlob = blob,
                CredentialBlobSize = (uint)bytes,
                Persist = PersistLocalMachine
            };
            if (!CredWrite(ref credential, 0))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "无法保存 API 密钥到 Windows 凭据管理器。");
        } finally {
            Marshal.ZeroFreeCoTaskMemUnicode(blob);
        }
    }

    public static string? Read(string target)
    {
        if (!CredRead(target, Generic, 0, out var pointer)) {
            var error = Marshal.GetLastWin32Error();
            if (error == NotFound) return null;
            throw new Win32Exception(error, "无法读取 Windows 凭据管理器中的 API 密钥。");
        }
        try {
            var credential = Marshal.PtrToStructure<NativeCredential>(pointer);
            return credential.CredentialBlobSize == 0 ? "" :
                Marshal.PtrToStringUni(credential.CredentialBlob, checked((int)credential.CredentialBlobSize / 2));
        } finally {
            CredFree(pointer);
        }
    }

    public static void Delete(string target)
    {
        if (CredDelete(target, Generic, 0)) return;
        var error = Marshal.GetLastWin32Error();
        if (error != NotFound)
            throw new Win32Exception(error, "无法删除 Windows 凭据管理器中的 API 密钥。");
    }

    public static void VerifyRoundTrip()
    {
        var target = "SpirePilot:self-test:" + Guid.NewGuid().ToString("N");
        const string secret = "temporary-credential-test";
        try {
            Save(target, "self-test", secret);
            if (Read(target) != secret)
                throw new InvalidOperationException("Windows 凭据管理器往返校验失败。");
        } finally {
            Delete(target);
        }
        if (Read(target) is not null)
            throw new InvalidOperationException("Windows 凭据管理器测试凭据未被删除。");
    }
}
