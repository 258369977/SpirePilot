using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI;
using Windows.UI.ViewManagement;

namespace SpirePilot;

public sealed partial class MainWindow
{
    readonly UISettings uiSettings = new();
    readonly List<Border> themeCards = new();

    static SolidColorBrush Brush(byte r, byte g, byte b) => new(Color.FromArgb(255, r, g, b));

    Border Card(UIElement child)
    {
        var card = new Border {
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(12),
            Padding = new Thickness(20),
            Child = child
        };
        themeCards.Add(card);
        ApplyCardTheme(card, shell.ActualTheme == ElementTheme.Dark);
        return card;
    }

    void ApplySystemTheme()
    {
        var dark = shell.ActualTheme == ElementTheme.Dark;
        shell.Background = dark ? Brush(19, 22, 28) : Brush(243, 243, 243);
        foreach (var card in themeCards) ApplyCardTheme(card, dark);

        var caption = AppWindow.TitleBar;
        caption.ButtonBackgroundColor = Colors.Transparent;
        caption.ButtonInactiveBackgroundColor = Colors.Transparent;
        caption.ButtonForegroundColor = dark ? Colors.White : Color.FromArgb(255, 31, 31, 31);
        caption.ButtonInactiveForegroundColor = dark ? Color.FromArgb(255, 155, 163, 175) : Color.FromArgb(255, 110, 110, 110);
        caption.ButtonHoverBackgroundColor = dark ? Color.FromArgb(255, 49, 57, 69) : Color.FromArgb(255, 226, 226, 226);
        caption.ButtonHoverForegroundColor = dark ? Colors.White : Colors.Black;
        caption.ButtonPressedBackgroundColor = dark ? Color.FromArgb(255, 65, 74, 86) : Color.FromArgb(255, 211, 211, 211);
        caption.ButtonPressedForegroundColor = dark ? Colors.White : Colors.Black;
    }

    ElementTheme ReadSystemTheme()
    {
        var background = uiSettings.GetColorValue(UIColorType.Background);
        return background.R + background.G + background.B < 384 ? ElementTheme.Dark : ElementTheme.Light;
    }

    void SystemColorsChanged(UISettings sender, object args)
    {
        shell.DispatcherQueue.TryEnqueue(() => {
            shell.RequestedTheme = ReadSystemTheme();
            ApplySystemTheme();
        });
    }

    static void ApplyCardTheme(Border card, bool dark)
    {
        card.Background = dark ? Brush(28, 33, 42) : new SolidColorBrush(Colors.White);
        card.BorderBrush = dark ? Brush(49, 57, 69) : Brush(224, 224, 224);
    }
}
