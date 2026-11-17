using System.Globalization;
using System.Text.Json;
using Folio.Core.Translate.Engine;

namespace Folio.Core.Translate.Services;

/// <summary>The calling agent supplies translations through the job's local JSON mailbox.</summary>
public sealed class AgentMailboxProvider : ITranslationProvider
{
    readonly string _requests;
    readonly string _responses;
    static readonly JsonSerializerOptions JsonOptions = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public AgentMailboxProvider(string directory)
    {
        if (string.IsNullOrWhiteSpace(directory) || !Path.IsPathFullyQualified(directory))
            throw new TranslationConfigurationError("agent requires an absolute --agent-exchange-directory path");
        directory = Path.GetFullPath(directory);
        _requests = Path.Combine(directory, "requests");
        _responses = Path.Combine(directory, "responses");
        Directory.CreateDirectory(_requests);
        Directory.CreateDirectory(_responses);
    }

    public ProviderLimits Limits { get; } = new(4000, 20, 1, true);

    public Task<List<GlossaryEntry>> ExtractTerms(string excerpt, TranslationContext context, CancellationToken cancel) =>
        Task.FromResult(new List<GlossaryEntry>());

    public async Task<List<string>> Translate(List<TranslationItem> items, TranslationContext context, CancellationToken cancel)
    {
        cancel.ThrowIfCancellationRequested();
        string id = Guid.NewGuid().ToString("N");
        var request = new
        {
            version = 1,
            request_id = id,
            source_language = context.SourceLanguage,
            target_language = context.TargetLanguage,
            instructions = LLMBatch.SystemPrompt(context),
            context = new
            {
                title = context.Title,
                summary = context.Summary,
                glossary = context.Glossary.Select(term => new { source = term.Source, target = term.Target }),
                figure_captions = context.FigureCaptions,
            },
            items = items.Select((item, index) => new
            {
                id = (index + 1).ToString(CultureInfo.InvariantCulture),
                source = item.Text,
                kind = item.Kind.ToString(),
                is_short = item.IsShort,
            }),
        };
        string temporary = Path.Combine(_requests, id + ".tmp");
        string destination = Path.Combine(_requests, id + ".json");
        try
        {
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(request, JsonOptions), cancel);
            cancel.ThrowIfCancellationRequested();
            File.Move(temporary, destination);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }

        string responsePath = Path.Combine(_responses, id + ".json");
        while (!File.Exists(responsePath)) await Task.Delay(250, cancel);
        cancel.ThrowIfCancellationRequested();
        if (new FileInfo(responsePath).Length > 4 * 1024 * 1024)
            throw new InvalidDataException("Agent response exceeds 4 MiB");
        using var response = JsonDocument.Parse(await File.ReadAllTextAsync(responsePath, cancel));
        return ReadResponse(response.RootElement, id, items);
    }

    static List<string> ReadResponse(JsonElement response, string id, List<TranslationItem> items)
    {
        if (response.ValueKind != JsonValueKind.Object
            || response.EnumerateObject().Count() != 3
            || !response.TryGetProperty("version", out var version) || version.ValueKind != JsonValueKind.Number || !version.TryGetInt32(out int number) || number != 1
            || !response.TryGetProperty("request_id", out var requestId) || requestId.ValueKind != JsonValueKind.String || requestId.GetString() != id
            || !response.TryGetProperty("translations", out var translations) || translations.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("Invalid agent response envelope");

        var entries = translations.EnumerateObject().ToList();
        var expected = Enumerable.Range(1, items.Count).Select(i => i.ToString(CultureInfo.InvariantCulture)).ToHashSet(StringComparer.Ordinal);
        if (entries.Count != items.Count || !expected.SetEquals(entries.Select(entry => entry.Name)))
            throw new InvalidDataException("Agent translations must contain exactly the requested item IDs");
        var result = new List<string>(items.Count);
        for (int i = 0; i < items.Count; i++)
        {
            string key = (i + 1).ToString(CultureInfo.InvariantCulture);
            var value = translations.GetProperty(key);
            if (value.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(value.GetString()))
                throw new InvalidDataException($"Agent translation {key} must be a non-empty string");
            string text = value.GetString()!;
            var want = PlaceholderCounts(items[i].Text);
            var got = PlaceholderCounts(text);
            if (want.Count != got.Count || want.Any(entry => got.GetValueOrDefault(entry.Key) != entry.Value))
                throw new InvalidDataException($"Agent translation {key} changed formula or page-break placeholders");
            result.Add(text);
        }
        return result;
    }

    static Dictionary<string, int> PlaceholderCounts(string text)
    {
        var matches = Placeholders.Pattern().Matches(text).Cast<System.Text.RegularExpressions.Match>().ToList();
        if (matches.Any(match => match.Value != "{v" + match.Groups[1].Value + "}"))
            throw new InvalidDataException("Agent translations must preserve the exact {vN} placeholder syntax");
        return matches.GroupBy(match => match.Value).ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
    }
}
