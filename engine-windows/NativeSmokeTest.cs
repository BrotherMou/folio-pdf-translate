using Folio.Core.Translate;
using Folio.Core.Translate.Engine;
using Folio.Core.Translate.Layout;
using Folio.Core.Translate.Pdf;
using SkiaSharp;

// A local, network-free native rendering check for Windows CI.
static class NativeSmokeTest
{
    public static void Run()
    {
        static void Check(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
        Check(TranslationJob.PlaceholdersIntact("Energy {v1} and mass {v2}", "能量 {v1} 与质量 {v2}"), "Intact formula markers rejected");
        Check(!TranslationJob.PlaceholdersIntact("Energy {v1}", "能量 {v1} 与质量 {v2}"), "Missing formula marker accepted");
        Check(!TranslationJob.PlaceholdersIntact("Energy {v1} {v1}", "能量 {v1}"), "Duplicate formula marker accepted");
        var folder = Path.Combine(Path.GetTempPath(), "folio-native-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        try
        {
            var input = Path.Combine(folder, "source.pdf");
            using (var stream = File.Create(input))
            using (var pdf = SKDocument.CreatePdf(stream))
            using (var typeface = SKTypeface.FromFamilyName("Arial"))
            using (var font = new SKFont(typeface, 12))
            using (var paint = new SKPaint { Color = SKColors.Black, IsAntialias = true })
            {
                for (var page = 0; page < 2; page++)
                {
                    var canvas = pdf.BeginPage(400, 500);
                    canvas.DrawText(page == 0 ? "Energy and mass are related in this model." : "The second experiment uses a finer spatial grid.",
                        30, 150, SKTextAlign.Left, font, paint);
                    canvas.DrawText(page == 0 ? "We evaluate the numerical method on two examples." : "The numerical solution converges as expected.",
                        30, 175, SKTextAlign.Left, font, paint);
                    pdf.EndPage();
                }
                pdf.Close();
            }
            using var source = PdfSource.Open(input);
            var layouts = new LayoutAnalyzer(new LayoutAnalyzer.Options()).Analyze(source, new[] { 1, 2 });
            var segments = SegmentBuilder.Segments(layouts, "zh");
            Check(segments.Count > 0, "Native layout found no text");
            // Same content exercises extraction, shaping, original glyph reuse and dual output without a translation API.
            var translations = segments.ToDictionary(segment => segment.Id, segment => segment.Source);
            var rendered = new TranslationRenderer(source, "en").Render(layouts, segments, translations, true, true,
                TranslationOptions.DualLayouts.sideBySide, null);
            Check(rendered.Mono != null && rendered.Dual != null, "Renderer returned no PDFs");
            using var mono = PdfSource.Open(rendered.Mono!);
            using var dual = PdfSource.Open(rendered.Dual!);
            Check(mono.Pages.Count == 2 && dual.Pages.Count == 2, "Renderer changed page count");
            var originalBox = PdfComposer.Geometry(source.Pages[0]).CropBox;
            var dualBox = PdfComposer.Geometry(dual.Pages[0]).CropBox;
            Check(dualBox.Width >= originalBox.Width * 1.9, "Dual output is not side by side");
        }
        finally { Directory.Delete(folder, true); }
    }
}
