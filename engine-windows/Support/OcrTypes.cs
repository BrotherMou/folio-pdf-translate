// Extracted from Folio.Core/Pdf/OcrTextLayer.cs (MIT, Alonemo-Nnqc).
// Only image-label layout types are needed. No desktop OCR service is loaded.
namespace Folio.Core;

public sealed record OcrWord(string Text, double X, double Y, double Width, double Height);
public sealed record OcrLine(IReadOnlyList<OcrWord> Words);
public static class OcrTextLayer
{
    public static bool NeedsSpace(string left, string right) =>
        left.Length > 0 && right.Length > 0 && !(IsCjk(char.ConvertToUtf32(left, left.Length - (char.IsLowSurrogate(left[^1]) && left.Length > 1 ? 2 : 1))) || IsCjk(char.ConvertToUtf32(right, 0)));
    public static bool IsCjk(int c) => c is >= 0x2E80 and <= 0x2FFF or >= 0x3000 and <= 0x303F or >= 0x3040 and <= 0x30FF or >= 0x3100 and <= 0x31FF
        or >= 0x3400 and <= 0x4DBF or >= 0x4E00 and <= 0x9FFF or >= 0xAC00 and <= 0xD7AF or >= 0xF900 and <= 0xFAFF or >= 0xFE30 and <= 0xFE4F
        or >= 0xFF00 and <= 0xFFEF or >= 0x20000 and <= 0x3FFFF;
}
