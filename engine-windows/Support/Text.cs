using System.Globalization;
using System.Text;
namespace Folio.Core;

/// <summary>Text helpers standing in for Foundation's string folding.</summary>
public static class Text
{
    /// <summary>Case-, diacritic- and width-insensitive form (like Foundation's folding options).</summary>
    public static string Fold(string text)
    {
        var decomposed = text.Normalize(NormalizationForm.FormKD);
        var sb = new StringBuilder(decomposed.Length);
        foreach (var ch in decomposed)
            if (CharUnicodeInfo.GetUnicodeCategory(ch) != UnicodeCategory.NonSpacingMark) sb.Append(ch);
        return sb.ToString().Normalize(NormalizationForm.FormKC).ToLowerInvariant();
    }

    public static string? NonEmpty(string? s)
    {
        var t = s?.Trim();
        return string.IsNullOrEmpty(t) ? null : t;
    }

    public static string CollapseWhitespace(string s) =>
        string.Join(' ', s.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    public static int LetterCount(string s) => s.Count(char.IsLetter);

    /// <summary>Share of CJK ideographs / kana / hangul among the letters of text.</summary>
    public static double CjkRatio(string text)
    {
        int letters = 0, cjk = 0;
        foreach (var r in text.EnumerateRunes())
        {
            if (!Rune.IsLetter(r)) continue;
            letters++;
            int v = r.Value;
            if (v is >= 0x3040 and <= 0x30FF or >= 0x3400 and <= 0x4DBF or >= 0x4E00 and <= 0x9FFF or >= 0xAC00 and <= 0xD7AF or >= 0xF900 and <= 0xFAFF)
                cjk++;
        }
        return letters == 0 ? 0 : (double)cjk / letters;
    }

    /// <summary>Character count as Swift counts it (grapheme clusters).</summary>
    public static int Graphemes(string s) => new StringInfo(s).LengthInTextElements;

    public static string PrefixGraphemes(string s, int n)
    {
        var info = new StringInfo(s);
        return info.LengthInTextElements <= n ? s : info.SubstringByTextElements(0, n);
    }
}

