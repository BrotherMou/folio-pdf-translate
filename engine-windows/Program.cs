using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Folio.Core.Translate;
using Folio.Core.Translate.Pdf;

Console.InputEncoding = Encoding.UTF8;
Console.OutputEncoding = new UTF8Encoding(false);
var outputLock = new object();
void Emit(object value)
{
    lock (outputLock) { Console.WriteLine(JsonSerializer.Serialize(value)); Console.Out.Flush(); }
}
void Require(bool condition, string message)
{
    if (!condition) throw new ArgumentException(message);
}

try
{
    if (args.SequenceEqual(new[] { "--self-test" }))
    {
        NativeSmokeTest.Run();
        Emit(new { type = "self_test", status = "passed" });
        return 0;
    }
    Require(args.Length == 0, "Supply the request as JSON on stdin; credentials must not be command arguments.");
    using var inputStream = Console.OpenStandardInput();
    using var memory = new MemoryStream();
    var buffer = new byte[8192];
    while (true)
    {
        int length = await inputStream.ReadAsync(buffer);
        if (length == 0) break;
        Require(memory.Length + length <= 1_048_576, "Request exceeds 1 MiB");
        memory.Write(buffer, 0, length);
    }
    var input = JsonSerializer.Deserialize<Input>(memory.ToArray()) ?? throw new ArgumentException("Request is empty");
    string[] allowed = ["agent", "google", "bing", "openai", "openaicompatible", "ollama", "deepseek"];
    Require(allowed.Contains(input.Service), "Supported services: " + string.Join(", ", allowed));
    foreach (var path in new[] { input.Source, input.OutputDirectory, input.CacheDirectory })
        Require(!string.IsNullOrWhiteSpace(path) && Path.IsPathFullyQualified(path), "Paths must be absolute");
    Require(input.Outputs is null or "both", "The standalone engine produces both mono and side-by-side PDFs.");
    Require(!input.TranslateImages, "Image-text OCR is not included in the standalone Windows engine; set translate_images=false.");
    var source = Path.GetFullPath(input.Source);
    var destination = Path.GetFullPath(input.OutputDirectory);
    Require(Path.GetExtension(source).Equals(".pdf", StringComparison.OrdinalIgnoreCase), "Input must be a PDF");
    Require(File.Exists(source), "Input PDF does not exist");
    using (var pdf = PdfSource.Open(source))
    {
        int count = pdf.Pages.Count;
        Require(count > 0, "PDF has no pages");
        if (input.Pages != null)
        {
            Require(Regex.IsMatch(input.Pages, @"\A[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*\z"), "pages must use 1,3,5-7 syntax");
            foreach (var part in input.Pages.Split(','))
            {
                var bounds = part.Split('-').Select(value => int.TryParse(value, out var page) ? page : -1).ToArray();
                Require(bounds.All(page => page >= 1 && page <= count) && bounds[0] <= bounds[^1], "Page range outside PDF");
            }
        }
    }
    if (input.GlossaryFile != null)
        Require(Path.IsPathFullyQualified(input.GlossaryFile) && File.Exists(input.GlossaryFile), "Glossary must be a readable absolute path");
    Directory.CreateDirectory(destination);
    Require(!Directory.EnumerateFileSystemEntries(destination).Any(), "Engine output directory must be empty; source files are never overwritten");
    TranslationJob.SupportDirectory = Path.GetFullPath(input.CacheDirectory);
    var options = new TranslationOptions
    {
        LangIn = input.LangIn ?? "en", LangOut = input.LangOut ?? "zh", Pages = input.Pages,
        Outputs = TranslationOptions.OutputKinds.both, DualLayout = TranslationOptions.DualLayouts.sideBySide,
        TranslateImageText = false, GlossaryFile = input.GlossaryFile,
    };
    var job = new TranslationJob(new TranslationRequest
    {
        Input = source, OutputDirectory = destination, ServiceId = input.Service,
        FieldValues = input.Fields ?? [], Secrets = input.Secrets ?? [], Options = options,
    });
    Console.CancelKeyPress += (_, eventArgs) => { eventArgs.Cancel = true; job.Cancel(); };
    var final = await job.Run(value =>
    {
        switch (value)
        {
            case TranslationEvent.Stage stage: Emit(new { type = "stage", message = stage.Text }); break;
            case TranslationEvent.Progress progress: Emit(new { type = "progress", value = progress.Value }); break;
            case TranslationEvent.Notice notice: Emit(new { type = "notice", message = notice.Text }); break;
            case TranslationEvent.Problem problem: Emit(new { type = "problem", message = problem.Text }); break;
            case TranslationEvent.Preview preview: Emit(new { type = "preview", path = preview.Path }); break;
            case TranslationEvent.Failed failed: Emit(new { type = "failed", message = failed.Message, log = failed.LogPath }); break;
            case TranslationEvent.Cancelled: Emit(new { type = "cancelled" }); break;
            case TranslationEvent.Finished finished when finished.Mono != null && finished.Dual != null:
                Emit(new { type = "finished", mono_pdf = finished.Mono, dual_pdf = finished.Dual }); break;
            case TranslationEvent.Finished: Emit(new { type = "failed", message = "Missing output PDF" }); break;
        }
    });
    return final is TranslationEvent.Finished { Mono: not null, Dual: not null } ? 0 : 1;
}
catch (Exception error)
{
    Emit(new { type = "failed", message = error.Message });
    return 1;
}

sealed class Input
{
    [JsonPropertyName("input")] public required string Source { get; init; }
    [JsonPropertyName("output_directory")] public required string OutputDirectory { get; init; }
    [JsonPropertyName("cache_directory")] public required string CacheDirectory { get; init; }
    [JsonPropertyName("service")] public string Service { get; init; } = "agent";
    [JsonPropertyName("fields")] public Dictionary<string, string>? Fields { get; init; }
    [JsonPropertyName("secrets")] public Dictionary<string, string>? Secrets { get; init; }
    [JsonPropertyName("pages")] public string? Pages { get; init; }
    [JsonPropertyName("lang_in")] public string? LangIn { get; init; }
    [JsonPropertyName("lang_out")] public string? LangOut { get; init; }
    [JsonPropertyName("outputs")] public string? Outputs { get; init; }
    [JsonPropertyName("translate_images")] public bool TranslateImages { get; init; }
    [JsonPropertyName("glossary_file")] public string? GlossaryFile { get; init; }
}
