using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace SpirePilot;

public sealed class ModelSettings
{
    public readonly ComboBox Provider = new() { Header = "提供商", HorizontalAlignment = HorizontalAlignment.Stretch };
    public readonly TextBox Model = new() { Header = "模型 ID", PlaceholderText = "填写该提供商支持的模型 ID" };
    public readonly PasswordBox Key = new() { Header = "API 密钥" };
    public readonly CheckBox RememberKey = new() { Content = "保存到 Windows 凭据管理器", IsChecked = true };
    public readonly TextBox Url = new() { Header = "完整 API 地址" };
    public readonly ComboBox Protocol = new() { Header = "接口类型", HorizontalAlignment = HorizontalAlignment.Stretch };
    public readonly ComboBox ReasoningEffort = new() { Header = "思考强度", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBlock credentialStatus = new() { FontSize = 12, Opacity = .72, TextWrapping = TextWrapping.Wrap };
    readonly Button forgetKey = new() { Content = "删除已保存密钥" };
    readonly bool combat;
    bool loading;
    string role = "";
    public string ProtocolId => ((ComboBoxItem)Protocol.SelectedItem).Tag.ToString()!;
    public string ProviderId => Provider.SelectedItem?.ToString() ?? "自定义";
    public string ReasoningEffortId => ((ComboBoxItem)ReasoningEffort.SelectedItem).Tag.ToString()!;
    public ModelSettings(bool isCombat)
    {
        combat = isCombat;
        Key.PlaceholderText = "留空读取 Windows 凭据或 " + (combat ? "SPIRE_COMBAT_KEY" : "SPIRE_PLANNER_KEY");
        foreach (var name in new[] { "OpenRouter", "DeepSeek", "自定义" }) Provider.Items.Add(name);
        Protocol.Items.Add(new ComboBoxItem { Content = "聊天 · JSON Schema", Tag = "chat_schema" });
        Protocol.Items.Add(new ComboBoxItem { Content = "聊天 · JSON Object", Tag = "chat_json" });
        if (combat) Protocol.Items.Add(new ComboBoxItem { Content = "Jev · Decisions", Tag = "decisions" });
        Protocol.SelectedIndex = combat ? 2 : 0;
        if (!combat) {
            ReasoningEffort.Items.Add(new ComboBoxItem { Content = "低（默认）", Tag = "low" });
            ReasoningEffort.Items.Add(new ComboBoxItem { Content = "中", Tag = "medium" });
            ReasoningEffort.Items.Add(new ComboBoxItem { Content = "高", Tag = "high" });
            ReasoningEffort.SelectedIndex = 0;
        }
        Provider.SelectionChanged += (_, _) => {
            if (loading) return;
            Key.Password = "";
            if (ProviderId == "OpenRouter") {
                Url.Text = combat ? "https://openrouter.ai/api/alpha/decisions" : "https://openrouter.ai/api/v1/chat/completions";
                Protocol.SelectedIndex = combat ? 2 : 0;
            } else if (ProviderId == "DeepSeek") {
                Url.Text = "https://api.deepseek.com/chat/completions";
                Protocol.SelectedIndex = 1;
                Model.Text = "";
            }
            RefreshCredentialState();
        };
        Protocol.SelectionChanged += (_, _) => {
            if (!loading && ProviderId == "OpenRouter")
                Url.Text = ProtocolId == "decisions" ? "https://openrouter.ai/api/alpha/decisions" : "https://openrouter.ai/api/v1/chat/completions";
        };
        Url.TextChanged += (_, _) => { if (!loading) { Key.Password = ""; RefreshCredentialState(); } };
        Key.PasswordChanged += (_, _) => {
            if (!loading && !string.IsNullOrEmpty(Key.Password))
                credentialStatus.Text = RememberKey.IsChecked == true ? "新密钥将在保存设置时安全保存。" : "密钥只用于当前窗口会话。";
        };
        RememberKey.Checked += (_, _) => RefreshCredentialState();
        RememberKey.Unchecked += (_, _) => credentialStatus.Text = "保存设置后将删除当前提供商地址对应的已保存密钥。";
        forgetKey.Click += (_, _) => {
            try { CredentialStore.DeleteFor(role, ProviderId, Url.Text); Key.Password = ""; RefreshCredentialState(); }
            catch (Exception e) { credentialStatus.Text = e.Message; }
        };
    }
    public void Load(JsonNode config, string role)
    {
        this.role = role;
        loading = true;
        Url.Text = config[role + "_url"]!.ToString();
        Provider.SelectedItem = config[role + "_provider"]?.ToString() ?? (Url.Text.Contains("openrouter.ai") ? "OpenRouter" : Url.Text.Contains("api.deepseek.com") ? "DeepSeek" : "自定义");
        Model.Text = config[role + "_model"]!.ToString();
        var protocol = config[role + "_protocol"]?.ToString() ?? (combat ? "decisions" : "chat_schema");
        Protocol.SelectedItem = Protocol.Items.Cast<ComboBoxItem>().First(i => i.Tag.ToString() == protocol);
        if (!combat) {
            var effort = config["planner_reasoning_effort"]?.ToString() ?? "low";
            ReasoningEffort.SelectedItem = ReasoningEffort.Items.Cast<ComboBoxItem>()
                .FirstOrDefault(i => i.Tag.ToString() == effort) ?? ReasoningEffort.Items[0];
        }
        loading = false;
        RefreshCredentialState();
    }

    public void SaveCredential()
    {
        if (RememberKey.IsChecked != true) {
            CredentialStore.DeleteFor(role, ProviderId, Url.Text);
            RefreshCredentialState();
            return;
        }
        if (!string.IsNullOrWhiteSpace(Key.Password)) {
            CredentialStore.SaveFor(role, ProviderId, Url.Text, Key.Password);
            Key.Password = "";
        }
        RefreshCredentialState();
    }

    public string KeyForRequest()
    {
        if (!string.IsNullOrWhiteSpace(Key.Password)) return Key.Password;
        return RememberKey.IsChecked == true ? CredentialStore.ReadFor(role, ProviderId, Url.Text) ?? "" : "";
    }

    public void ClearTransientKey() => Key.Password = "";

    void RefreshCredentialState()
    {
        if (loading || string.IsNullOrEmpty(role)) return;
        var saved = CredentialStore.ReadFor(role, ProviderId, Url.Text) is not null;
        forgetKey.IsEnabled = saved;
        Key.PlaceholderText = saved
            ? "已安全保存；留空继续使用"
            : "留空读取 " + (combat ? "SPIRE_COMBAT_KEY" : "SPIRE_PLANNER_KEY");
        credentialStatus.Text = saved ? "已为当前提供商地址保存密钥。" : "当前提供商地址没有已保存密钥。";
    }
    public UIElement View()
    {
        var panel = new StackPanel { Spacing = 12 };
        foreach (var item in new UIElement[] { Provider, Model }) panel.Children.Add(item);
        if (!combat) panel.Children.Add(ReasoningEffort);
        foreach (var item in new UIElement[] { Key, RememberKey,
                     credentialStatus, forgetKey, Url, Protocol }) panel.Children.Add(item);
        return panel;
    }
}
