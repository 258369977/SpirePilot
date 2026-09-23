using Microsoft.UI.Xaml;

namespace SpirePilot;

internal static class Program
{
    [STAThread]
    static void Main()
    {
        try {
            WinRT.ComWrappersSupport.InitializeComWrappers();
            Application.Start(args => {
                SynchronizationContext.SetSynchronizationContext(
                    new Microsoft.UI.Dispatching.DispatcherQueueSynchronizationContext(
                        Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread()));
                _ = new PilotApp();
            });
        } catch (Exception e) {
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "startup-error.log"), e.ToString());
        }
    }
}

public sealed partial class PilotApp : Application
{
    private Window? window;
    public PilotApp()
    {
        InitializeComponent();
        UnhandledException += (_, e) => {
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "crash.log"), e.Exception.ToString());
        };
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        window = new MainWindow();
        window.Activate();
    }
}
