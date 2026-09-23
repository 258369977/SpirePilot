using System.Diagnostics;
using System.Text.Json.Nodes;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;

namespace SpirePilot;

public sealed partial class MainWindow : Window
{
    readonly Backend backend = new();
    readonly Grid shell = new();
    readonly ContentControl content = new() { HorizontalContentAlignment = HorizontalAlignment.Stretch };
    readonly Dictionary<string, UIElement> pages = new();
    readonly InfoBar notice = new() { IsClosable = true };
    readonly TextBlock status = Text("尚未连接", 15), character = Text("—", 28), floor = Text("—", 28), hp = Text("—", 28);
    readonly TextBlock plan = Text("开始对局后，这里会显示规划模型的构筑方向与战斗指导。", 15);
    readonly TextBox log = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 230, MaxHeight = 340, FontFamily = new FontFamily("Cascadia Mono"), FontSize = 12 };
    readonly TextBox rootInput = new() { Header = "控制器目录（hybrid）" }, pythonInput = new() { Header = "Python 可执行文件", Text = "python" };
    readonly ModelSettings plannerSettings = new(false), combatSettings = new(true);
    readonly TextBox scope = new() { Header = "记忆版本范围" };
    readonly ToggleSwitch memory = new() { Header = "跨局记忆", IsOn = true, OnContent = "启用复盘与经验检索", OffContent = "不读取和写入跨局经验" };
    readonly ListView history = new() { SelectionMode = ListViewSelectionMode.Single, MaxHeight = 240 };
    readonly TextBox review = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 220, MaxHeight = 460 };
    readonly ListView memories = new() { MaxHeight = 250 };
    readonly TextBox memoryDetail = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 260, MaxHeight = 460 };
    readonly Button start = new() { Content = "开始 / 接管当前对局" }, stop = new() { Content = "停止自动游玩" };
    readonly TextBlock historyEmpty = Text("还没有对局记录。到“对局控制台”启动第一局后，记录会出现在这里。");
    readonly TextBlock memoryEmpty = Text("经验库为空。完整对局结束后，模型会自动复盘并写入经验。");
    Border? reviewCard, memoryCard;
    Button? resumeRun, reviewRun, openRun, deleteRun;
    readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(3) };
    NavigationView? navigation;
    bool smokeSelecting;
    string page = "dashboard";
    bool polling, busy;
    string? selectedRun;
    readonly string settingsPath = Path.Combine(AppContext.BaseDirectory, "desktop-settings.json");

    public MainWindow()
    {
        Title = "Spire Pilot · 双模型自动游玩";
        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "SpirePilot.ico");
        if (File.Exists(iconPath)) AppWindow.SetIcon(iconPath);
        AppWindow.Resize(Environment.GetCommandLineArgs().Contains("--wide")
            ? new Windows.Graphics.SizeInt32(2560, 1600) : new Windows.Graphics.SizeInt32(1440, 960));
        if (Environment.GetCommandLineArgs().Contains("--maximized"))
            ((Microsoft.UI.Windowing.OverlappedPresenter)AppWindow.Presenter).Maximize();
        SystemBackdrop = new MicaBackdrop();
        shell.RequestedTheme = Environment.GetCommandLineArgs().Contains("--light-theme") ? ElementTheme.Light
            : Environment.GetCommandLineArgs().Contains("--dark-theme") ? ElementTheme.Dark
            : ReadSystemTheme();
        shell.RowDefinitions.Add(new() { Height = GridLength.Auto });
        shell.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var titleRegion = new Grid { Height = 48, Background = new SolidColorBrush(Colors.Transparent) };
        var brand = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12, Margin = new Thickness(20, 0, 160, 0), VerticalAlignment = VerticalAlignment.Center };
        brand.Children.Add(new Image
        {
            Source = new BitmapImage(new Uri("ms-appx:///Assets/SpirePilot.png")),
            Width = 30,
            Height = 30
        });
        brand.Children.Add(Text("SPIRE PILOT", 20));
        titleRegion.Children.Add(brand);
        shell.Children.Add(titleRegion);
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(titleRegion);
        var nav = new NavigationView { IsBackButtonVisible = NavigationViewBackButtonVisible.Collapsed, IsSettingsVisible = false,
            PaneDisplayMode = NavigationViewPaneDisplayMode.Auto, OpenPaneLength = 205, IsPaneToggleButtonVisible = true, AlwaysShowHeader = false, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        navigation = nav;
        foreach (var item in new[] { ("对局控制台", "dashboard", Symbol.Play), ("模型与设置", "settings", Symbol.Setting), ("历史与复盘", "history", Symbol.Clock), ("跨局经验库", "memory", Symbol.Library) })
            nav.MenuItems.Add(new NavigationViewItem { Content = item.Item1, Tag = item.Item2, Icon = new SymbolIcon(item.Item3) });
        var body = new StackPanel { Spacing = 16, Margin = new Thickness(28, 16, 28, 28), HorizontalAlignment = HorizontalAlignment.Left };
        body.Children.Add(notice); body.Children.Add(content);
        var viewport = new ScrollViewer { Content = body, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, HorizontalScrollMode = ScrollMode.Disabled };
        // Constrain measure to the viewport, including at non-default DPI and maximized sizes.
        viewport.SizeChanged += (_, e) => body.Width = Math.Max(0, Math.Min(1280, e.NewSize.Width - body.Margin.Left - body.Margin.Right));
        nav.Content = viewport;
        Grid.SetRow(nav, 1); shell.Children.Add(nav); Content = shell;
        shell.Loaded += (_, _) => ApplySystemTheme();
        shell.ActualThemeChanged += (_, _) => ApplySystemTheme();
        nav.SelectionChanged += async (_, e) => { if (smokeSelecting) return; page = ((NavigationViewItem)e.SelectedItem).Tag.ToString()!; ShowPage(); if (page is "history" or "memory") await Guard(RefreshLists); };
        start.Click += async (_, _) => await Guard(async () => {
            await SaveSettings();
            var result = await backend.Call("start", new { planner_key = plannerSettings.KeyForRequest(), combat_key = combatSettings.KeyForRequest() });
            plannerSettings.ClearTransientKey(); combatSettings.ClearTransientKey();
            Notify("已启动后台对局：" + result["run"], InfoBarSeverity.Success);
            await Poll();
        });
        stop.Click += async (_, _) => await Guard(async () => { await backend.Call("stop"); Notify("已请求停止，正在等待当前调用返回。", InfoBarSeverity.Informational); });
        history.SelectionChanged += async (_, _) => {
            UpdateHistorySelection();
            if (history.SelectedItem is ListViewItem i) { selectedRun = i.Tag.ToString(); await Guard(async () => review.Text = (await backend.Call("review-text", new { run = selectedRun }))["text"]!.ToString()); }
        };
        memories.SelectionChanged += (_, _) => { if (memoryCard != null) memoryCard.Visibility = memories.SelectedItem == null ? Visibility.Collapsed : Visibility.Visible; if (memories.SelectedItem is ListViewItem i) memoryDetail.Text = i.Tag.ToString(); };
        LoadPaths();
        nav.SelectedItem = nav.MenuItems[0];
        timer.Tick += async (_, _) => await Poll();
        uiSettings.ColorValuesChanged += SystemColorsChanged;
        Closed += (_, _) => {
            timer.Stop(); // Background controller deliberately stays alive.
            uiSettings.ColorValuesChanged -= SystemColorsChanged;
        };
        timer.Start();
        _ = InitializeSafely();
    }

    async Task InitializeSafely()
    {
        try { await Initialize(); }
        catch (Exception e) {
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "ui-test-error.log"), e.ToString());
            Notify(e.Message, InfoBarSeverity.Error);
            if (Environment.GetCommandLineArgs().Contains("--smoke-test") || Environment.GetCommandLineArgs().Contains("--credential-test")) {
                Environment.ExitCode = 1;
                Close();
            }
        }
    }

    async Task Initialize()
    {
        if (Environment.GetCommandLineArgs().Contains("--credential-test")) {
            CredentialStore.VerifyRoundTrip();
            Close();
            return;
        }
        await Guard(async () => {
            var c = await backend.Call("config");
            plannerSettings.Load(c, "planner"); combatSettings.Load(c, "combat");
            scope.Text = c["memory_scope"]?.ToString() ?? "local";
            memory.IsOn = c["cross_run_memory"]?.GetValue<bool>() ?? true;
        });
        await Poll();
        if (Environment.GetCommandLineArgs().Contains("--smoke-test")) {
            var checkedPages = new JsonArray();
            foreach (var testPage in new[] { "settings", "history", "memory", "dashboard" }) {
                smokeSelecting = true;
                navigation!.SelectedItem = navigation.MenuItems.Cast<NavigationViewItem>().First(i => i.Tag.ToString() == testPage);
                smokeSelecting = false;
                page = testPage; ShowPage();
                if (page is "history" or "memory") await RefreshLists();
                await Task.Delay(250);
                shell.UpdateLayout();
                var origin = content.TransformToVisual(shell).TransformPoint(new Windows.Foundation.Point());
                var width = content.ActualWidth;
                if (origin.X < 0 || origin.X + width > shell.ActualWidth + 1 || width <= 0)
                    throw new InvalidOperationException($"Layout overflow: {page}, x={origin.X}, width={width}, window={shell.ActualWidth}");
                await CapturePreview("ui-" + page);
                checkedPages.Add(new JsonObject { ["page"] = page, ["x"] = origin.X, ["width"] = width, ["window_width"] = shell.ActualWidth, ["scale"] = shell.XamlRoot.RasterizationScale });
            }
            await CapturePreview("ui-preview");
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "ui-smoke.json"), new JsonObject { ["window"] = Title, ["theme"] = shell.ActualTheme.ToString(), ["backend_found"] = File.Exists(Path.Combine(backend.Root, "desktop_bridge.py")), ["pages"] = checkedPages }.ToJsonString());
            Close();
        }
    }

    void LoadPaths()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null) {
            var candidate = Path.Combine(dir.FullName, "hybrid");
            if (File.Exists(Path.Combine(candidate, "desktop_bridge.py"))) { backend.Root = candidate; break; }
            dir = dir.Parent;
        }
        try {
            if (File.Exists(settingsPath)) { var s = JsonNode.Parse(File.ReadAllText(settingsPath))!; backend.Root = s["root"]?.ToString() ?? backend.Root; backend.Python = s["python"]?.ToString() ?? "python"; }
        } catch { }
        rootInput.Text = backend.Root; pythonInput.Text = backend.Python;
    }

    static TextBlock Text(string value, double size = 14) => new() { Text = value, FontSize = size, TextWrapping = TextWrapping.Wrap };
    static StackPanel Stack(params UIElement[] children) { var p = new StackPanel { Spacing = 16 }; foreach (var c in children) p.Children.Add(c); return p; }
    Button Action(string label, Func<Task> action) { var b = new Button { Content = label }; b.Click += async (_, _) => await Guard(action); return b; }
    static StackPanel Row(params UIElement[] children) { var p = Stack(children); p.Orientation = Orientation.Horizontal; p.Spacing = 10; return p; }

    async Task SaveSettings()
    {
        backend.Root = rootInput.Text.Trim();
        backend.Python = pythonInput.Text.Trim();
        await backend.Call("save-config", new {
            planner_model = plannerSettings.Model.Text,
            planner_provider = plannerSettings.ProviderId,
            planner_url = plannerSettings.Url.Text,
            planner_protocol = plannerSettings.ProtocolId,
            planner_reasoning_effort = plannerSettings.ReasoningEffortId,
            combat_model = combatSettings.Model.Text,
            combat_provider = combatSettings.ProviderId,
            combat_url = combatSettings.Url.Text,
            combat_protocol = combatSettings.ProtocolId,
            memory_scope = scope.Text,
            cross_run_memory = memory.IsOn
        });
        plannerSettings.SaveCredential();
        combatSettings.SaveCredential();
        File.WriteAllText(settingsPath, new JsonObject {
            ["root"] = backend.Root,
            ["python"] = backend.Python
        }.ToJsonString());
    }

    UIElement ModelCards()
    {
        var grid = new Grid { ColumnSpacing = 16, RowSpacing = 16 };
        grid.ColumnDefinitions.Add(new()); grid.ColumnDefinitions.Add(new());
        grid.RowDefinitions.Add(new() { Height = GridLength.Auto }); grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var strategic = Card(Stack(Text("长期规划模型", 18), plannerSettings.View()));
        var tactical = Card(Stack(Text("战斗模型", 18), combatSettings.View()));
        grid.Children.Add(strategic); grid.Children.Add(tactical);
        grid.SizeChanged += (_, e) => {
            bool narrow = e.NewSize.Width < 780;
            Grid.SetColumnSpan(strategic, narrow ? 2 : 1);
            Grid.SetColumnSpan(tactical, narrow ? 2 : 1);
            Grid.SetColumn(tactical, narrow ? 0 : 1); Grid.SetRow(tactical, narrow ? 1 : 0);
        };
        return grid;
    }

    void ShowPage()
    {
        // Keep each page's controls in one tree when switching navigation tabs.
        if (pages.TryGetValue(page, out var existing)) { content.Content = existing; return; }
        content.Content = null;
        if (page == "dashboard") {
            var metrics = new Grid { ColumnSpacing = 12 };
            var entries = new[] { ("当前角色", character), ("幕 / 层数", floor), ("生命值", hp) };
            for (int i = 0; i < entries.Length; i++) {
                metrics.ColumnDefinitions.Add(new());
                var card = Card(Stack(Text(entries[i].Item1, 12), entries[i].Item2));
                Grid.SetColumn(card, i); metrics.Children.Add(card);
            }
            start.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
            content.Content = Stack(Text("对局控制台", 30),
                Card(Stack(status, Row(start, stop, Action("检查游戏连接", async () => { var r = await backend.Call("probe"); Notify("游戏已连接 · " + r["screen"] + " · 完整牌组：" + r["deck_available"], InfoBarSeverity.Success); })),
                    Text("先在“模型与设置”配置模型密钥。关闭应用会保留后台游玩；停止请使用上方按钮。", 12))),
                metrics, Card(Stack(Text("整局计划", 18), plan)), Card(Stack(Text("运行日志", 18), log)));
        } else if (page == "settings") {
            content.Content = Stack(Text("模型与设置", 30), Text("设置在下一次启动控制器时生效。", 14),
                ModelCards(),
                Card(Stack(Text("跨局记忆", 18), memory, scope)),
                Card(Stack(Text("本地连接", 18), rootInput, pythonInput)),
                Action("保存设置", async () => {
                    await SaveSettings();
                    Notify("设置已保存。勾选保存的密钥已写入 Windows 凭据管理器。", InfoBarSeverity.Success);
                }));
        } else if (page == "history") {
            resumeRun = Action("继续所选对局", async () => {
                if (selectedRun == null) return;
                await SaveSettings();
                await backend.Call("start", new { run = selectedRun, planner_key = plannerSettings.KeyForRequest(), combat_key = combatSettings.KeyForRequest() });
                plannerSettings.ClearTransientKey(); combatSettings.ClearTransientKey();
                Notify("已恢复所选对局控制器；请确保游戏加载的是同一局。", InfoBarSeverity.Success);
            });
            reviewRun = Action("补跑复盘", async () => {
                if (selectedRun == null) return;
                await SaveSettings();
                await backend.Call("review", new { run = selectedRun, planner_key = plannerSettings.KeyForRequest() });
                plannerSettings.ClearTransientKey();
                Notify("复盘已转入后台。完成后点击刷新并重新选择该局。", InfoBarSeverity.Success);
            });
            openRun = Action("打开对局文件夹", () => { if (selectedRun != null) OpenFolder(Path.Combine(backend.Root, "runs", selectedRun)); return Task.CompletedTask; });
            deleteRun = Action("删除所选记录", async () => {
                if (selectedRun == null) return;
                var run = selectedRun;
                var dialog = new ContentDialog {
                    Title = "永久删除这条对局记录？",
                    Content = $"将删除 {run} 的状态、日志和复盘文件。已写入跨局经验库的经验会保留。",
                    PrimaryButtonText = "删除",
                    CloseButtonText = "取消",
                    DefaultButton = ContentDialogButton.Close,
                    XamlRoot = shell.XamlRoot
                };
                if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
                await backend.Call("delete-run", new { run });
                review.Text = "";
                selectedRun = null;
                await RefreshLists();
                Notify("已删除对局记录：" + run, InfoBarSeverity.Success);
            });
            reviewCard = Card(Stack(Text("复盘内容", 18), review));
            content.Content = Stack(Text("历史与复盘", 30), Text("继续中断的对局，或为已结束的对局补跑复盘。", 14),
                Row(Action("刷新", RefreshLists), resumeRun, reviewRun, openRun, deleteRun),
                Card(Stack(Text("对局记录", 18), historyEmpty, history)), reviewCard);
            UpdateHistorySelection();
        } else {
            memoryCard = Card(Stack(Text("经验与来源", 18), memoryDetail));
            memoryCard.Visibility = Visibility.Collapsed;
            content.Content = Stack(Text("跨局经验库", 30), Text("经验是带证据的策略假设，不是已证明的规则。模型按角色、版本和场景检索。", 14),
                Row(Action("刷新经验库", RefreshLists), Action("打开记忆文件夹", () => { OpenFolder(Path.Combine(backend.Root, "experience")); return Task.CompletedTask; })),
                Card(Stack(Text("已保存经验", 18), memoryEmpty, memories)), memoryCard);
        }
        pages[page] = (UIElement)content.Content;
    }

    void UpdateHistorySelection()
    {
        var selected = history.SelectedItem is ListViewItem;
        if (!selected) { selectedRun = null; review.Text = ""; }
        foreach (var button in new[] { resumeRun, reviewRun, openRun, deleteRun })
            if (button != null) button.IsEnabled = selected;
        if (reviewCard != null) reviewCard.Visibility = selected ? Visibility.Visible : Visibility.Collapsed;
    }

    async Task RefreshLists()
    {
        if (page == "history") {
            history.Items.Clear(); selectedRun = null;
            foreach (var item in (JsonArray)await backend.Call("history")) {
                var s = item!; history.Items.Add(new ListViewItem { Content = $"{s["name"]}   ·   {s["character"]}   ·   第 {s["floor"]} 层   ·   {s["review_status"]}", Tag = s["name"]!.ToString() });
            }
            history.Visibility = history.Items.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
            historyEmpty.Visibility = history.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
            UpdateHistorySelection();
        } else {
            memories.Items.Clear();
            foreach (var item in (JsonArray)await backend.Call("memories")) {
                var s = item!;
                var role = s["role"]?.ToString() == "combat" ? "战斗" : "规划";
                memories.Items.Add(new ListViewItem { Content = $"{role}   ·   {s["character"]}   ·   {s["scope"]}   ·   {s["summary"]}", Tag = s["document"]!.ToJsonString(new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) });
            }
            memories.Visibility = memories.Items.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
            memoryEmpty.Visibility = memories.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
            if (memoryCard != null) memoryCard.Visibility = Visibility.Collapsed;
        }
    }

    async Task Poll()
    {
        if (polling || string.IsNullOrWhiteSpace(backend.Root)) return;
        polling = true;
        try {
            var r = await backend.Call("status"); var s = r["state"]; var m = r["memory"];
            var running = r["running"]?.GetValue<bool>() == true;
            status.Text = running ? (r["stop_requested"]?.GetValue<bool>() == true ? "正在停止 · 等待当前请求结束" : "后台运行中 · " + r["process"]?["mode"]) : "控制器未运行";
            character.Text = s?["player"]?["character"]?.ToString() ?? "—";
            floor.Text = s?["run"] == null ? "—" : $"{s["run"]?["act"]} / {s["run"]?["floor"]}";
            hp.Text = s?["player"] == null ? "—" : $"{s["player"]?["hp"]} / {s["player"]?["max_hp"]}";
            if (m?["plan"] is JsonObject p) plan.Text = string.Join("\n\n", p.Select(x => $"{PlanLabel(x.Key)}\n{x.Value}"));
            log.Text = r["log"]?.ToString() ?? "";
            start.IsEnabled = !running && !busy; stop.IsEnabled = running && !busy;
        } catch (Exception e) { status.Text = "连接不可用 · " + e.Message; }
        finally { polling = false; }
    }

    static string PlanLabel(string key) => key switch { "deck_direction" => "构筑方向", "card_priorities" => "抓牌优先级", "route_policy" => "路线策略", "resource_policy" => "资源策略", "combat_guidance" => "战斗指导", _ => key };
    async Task Guard(Func<Task> action)
    {
        if (busy) return;
        busy = true; start.IsEnabled = false;
        try { await action(); }
        catch (Exception e) { Notify(e.Message, InfoBarSeverity.Error); }
        finally { busy = false; }
    }
    void Notify(string text, InfoBarSeverity severity) { notice.Message = text; notice.Severity = severity; notice.IsOpen = true; }
    static void OpenFolder(string path) { Directory.CreateDirectory(path); Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
}
