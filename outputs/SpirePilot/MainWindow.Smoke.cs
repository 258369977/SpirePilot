using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Graphics.Imaging;

namespace SpirePilot;

public sealed partial class MainWindow
{
    async Task CapturePreview(string name)
    {
        try {
            var bitmap = new RenderTargetBitmap();
            await bitmap.RenderAsync(shell);
            var pixels = (await bitmap.GetPixelsAsync()).ToArray();
            using var stream = File.Create(Path.Combine(AppContext.BaseDirectory, name + ".png"));
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream.AsRandomAccessStream());
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied,
                (uint)bitmap.PixelWidth, (uint)bitmap.PixelHeight, 96, 96, pixels);
            await encoder.FlushAsync();
        } catch (Exception e) {
            File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "preview-error.log"), e.Message);
        }
    }
}
