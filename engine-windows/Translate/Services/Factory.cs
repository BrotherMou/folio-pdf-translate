using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Folio.Core.Translate.Layout;

namespace Folio.Core.Translate.Services;

// Ports of ProviderFactory.swift, ReasoningEffort.swift, TranslationErrorClassifier.swift, ModelListFetcher.swift,
// ServiceTest.swift, TranslationProfiles.swift and SecretStore.swift (Windows: DPAPI instead of the Keychain).

public sealed class TranslationConfigurationError(string message) : Exception(message)
{
    public static TranslationConfigurationError UnknownService(string id) => new(Loc.S("未知的翻译服务：%@", id));
    public static TranslationConfigurationError MissingField(string service, string field) => new(Loc.S("%@ 需要填写“%@”，请在设置的“翻译”页补充。", service, field));
    public static TranslationConfigurationError AgentNotFound(string command) => new(Loc.S("在这台电脑上找不到 %@。请先安装并登录，或在 设置 ▸ 翻译 的高级选项里填写它的路径。", command));
}

public static class ProviderFactory
{
    /// <summary>The provider for serviceId with the user's values. concurrency overrides the provider's own.</summary>
    public static ITranslationProvider Make(string serviceId, IReadOnlyDictionary<string, string> fields, IReadOnlyDictionary<string, string> secrets, int? concurrency)
    {
        if (serviceId == "agent")
            return new AgentMailboxProvider(fields.GetValueOrDefault("--agent-exchange-directory") ?? "");
        var service = TranslationServiceCatalog.Service(serviceId) ?? throw TranslationConfigurationError.UnknownService(serviceId);
        string? Value(string option)
        {
            var field = service.Fields.FirstOrDefault(f => f.Option == option);
            if (field == null) return null;
            var raw = (field.IsSecret ? secrets.GetValueOrDefault(option) : fields.GetValueOrDefault(option))?.Trim();
            return !string.IsNullOrEmpty(raw) ? raw : field.DefaultValue;
        }
        string Required(string option)
        {
            if (Value(option) is { } v) return v;
            var title = service.Fields.FirstOrDefault(f => f.Option == option)?.Title ?? option;
            throw TranslationConfigurationError.MissingField(service.DisplayName, title);
        }
        foreach (var field in service.RequiredFields) Required(field.Option);
        var modelOption = service.ModelField?.Option;
        var llmLimits = new ProviderLimits(2600, 30, 8, true);

        ITranslationProvider provider;
        switch (service.Backend)
        {
            case TranslationBackend.OpenAI openAI:
            {
                bool local = service.Category == ServiceCategory.Local;
                var baseOption = service.Fields.FirstOrDefault(f => f.Kind == FieldKind.Url)?.Option;
                var @base = (baseOption != null ? Value(baseOption) : null) ?? openAI.DefaultBase;
                if (local && !@base.Contains("/v1")) @base = OpenAIBaseUrl.Normalized(@base);
                var endpoint = OpenAIChatProvider.ChatUrl(@base) ?? throw TranslationConfigurationError.MissingField(service.DisplayName, "Base URL");
                var key = service.SecretFields.FirstOrDefault() is { } secret ? Value(secret.Option) : null;
                var extra = new Dictionary<string, JsonNode?>();
                var effort = ReasoningEffort.Apply(serviceId, fields);
                switch (serviceId)
                {
                    case "openai":
                        if (effort.GetValueOrDefault("--openai-reasoning-effort") is { Length: > 0 } e1) extra["reasoning_effort"] = e1;
                        break;
                    case "openaicompatible":
                        if (effort.GetValueOrDefault("--openai-compatible-reasoning-effort") is { Length: > 0 } e2) extra["reasoning_effort"] = e2;
                        break;
                    case "deepseek":
                        if (effort.GetValueOrDefault("--deepseek-thinking-mode") == "disabled") extra["thinking"] = new JsonObject { ["type"] = "disabled" };
                        if (effort.GetValueOrDefault("--deepseek-reasoning-effort") is { Length: > 0 } e3)
                        {
                            extra["thinking"] = new JsonObject { ["type"] = "enabled" };
                            extra["reasoning_effort"] = e3;
                        }
                        break;
                    case "siliconflow":
                        if (effort.GetValueOrDefault("--siliconflow-send-enable-thinking-param") == "true")
                            extra["enable_thinking"] = effort.GetValueOrDefault("--siliconflow-enable-thinking") == "true";
                        break;
                    case "ollama":
                        // Qwen 3 and other reasoning models think at length unless told not to.
                        extra["think"] = false;
                        break;
                }
                var temperatureOption = service.Fields.FirstOrDefault(f => f.Title == "Temperature")?.Option;
                double? temperature = temperatureOption != null && double.TryParse(fields.GetValueOrDefault(temperatureOption), System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var t) ? t : extra.ContainsKey("reasoning_effort") ? null : 0.2;
                provider = new OpenAIChatProvider(endpoint, key, Required(modelOption ?? ""), temperature, extra, null,
                    local ? new ProviderLimits(1800, 20, 2, true, 2, 0.04) : llmLimits);
                break;
            }
            case TranslationBackend.AzureOpenAI:
                provider = new AzureOpenAIProvider(Required("--azure-openai-base-url"), Required("--azure-openai-api-key"), Required("--azure-openai-model"),
                    Value("--azure-openai-api-version") ?? "2024-10-21", llmLimits);
                break;
            case TranslationBackend.Anthropic:
                provider = new AnthropicProvider(Value("--anthropic-base-url") ?? "https://api.anthropic.com", Required("--anthropic-api-key"), Required("--anthropic-model"), llmLimits);
                break;
            case TranslationBackend.Gemini:
                provider = new GeminiProvider(Required("--gemini-api-key"), Required("--gemini-model"), llmLimits);
                break;
            case TranslationBackend.QwenMT:
                provider = new QwenMTProvider(OpenAIChatProvider.ChatUrl(Value("--qwenmt-base-url") ?? "https://dashscope.aliyuncs.com/compatible-mode/v1")
                                              ?? throw TranslationConfigurationError.MissingField(service.DisplayName, "Base URL"),
                    Required("--qwenmt-api-key"), Required("--qwenmt-model"), fields.GetValueOrDefault("--ali-domains"));
                break;
            case TranslationBackend.DeepL:
                provider = new DeepLProvider(Required("--deepl-auth-key"));
                break;
            case TranslationBackend.AzureTranslator:
                provider = new MicrosoftTranslatorProvider(Required("--azure-api-key"), Value("--azure-region"), Value("--azure-endpoint") ?? "");
                break;
            case TranslationBackend.Tencent:
                provider = new TencentProvider(Required("--tencentcloud-secret-id"), Required("--tencentcloud-secret-key"), Value("--tencentcloud-region") ?? "ap-guangzhou");
                break;
            case TranslationBackend.GoogleWeb:
                provider = new GoogleWebProvider();
                break;
            case TranslationBackend.BingWeb:
                provider = new BingWebProvider();
                break;
            case TranslationBackend.Agent agent:
            {
                var pathOption = service.Fields.FirstOrDefault(f => f.Option.EndsWith("-path"))?.Option;
                var executable = agent.Which.Locate(pathOption != null ? fields.GetValueOrDefault(pathOption) : null)
                                 ?? throw TranslationConfigurationError.AgentNotFound(agent.Which.Command());
                var model = modelOption != null ? Value(modelOption) : null;
                // CodeBuddy without a model chosen: a quick one of the account's, not its own default (minutes a page).
                if (agent.Which == LocalAgent.Codebuddy && string.IsNullOrEmpty(model)) model = CodeBuddyAccount.QuickModel(CodeBuddyAccount.Models());
                provider = new AgentProvider(agent.Which, executable, model, ReasoningEffort.AgentEffort(serviceId, fields));
                break;
            }
            case TranslationBackend.Command:
                provider = new CommandProvider(Required("--clitranslator-command"),
                    double.TryParse(Value("--clitranslator-timeout"), out var timeout) ? timeout : 60);
                break;
            default:
                throw TranslationConfigurationError.UnknownService(serviceId);
        }
        if (concurrency is > 0) provider = new ConcurrencyOverride(provider, concurrency.Value);
        return provider;
    }
}

/// <summary>Reasoning effort as offered by each service.</summary>
public static class ReasoningEffort
{
    public sealed record Choice(string Value, string Title);

    public abstract record Support
    {
        public sealed record None : Support;
        public sealed record UnsupportedModel : Support;
        public sealed record DecidedByModel(string Title) : Support;
        public sealed record Choices(List<Choice> List, string Default) : Support;
    }

    static readonly Dictionary<string, string> ValueOption = new()
    {
        ["openai"] = "--openai-reasoning-effort", ["openaicompatible"] = "--openai-compatible-reasoning-effort",
        ["deepseek"] = "--deepseek-reasoning-effort", ["siliconflow"] = "--siliconflow-enable-thinking",
        ["claudecode"] = "--claude-code-effort", ["codex"] = "--codex-effort", ["antigravitycli"] = "--antigravity-cli-effort",
        ["grokcli"] = "--grok-cli-effort", ["picli"] = "--pi-effort", ["hermesagent"] = "--hermes-effort",
    };

    public static readonly HashSet<string> ManagedOptions =
    [
        "--openai-reasoning-effort", "--openai-send-reasoning-effort", "--openai-compatible-reasoning-effort", "--openai-compatible-send-reasoning-effort",
        "--deepseek-reasoning-effort", "--deepseek-thinking-mode", "--siliconflow-enable-thinking", "--siliconflow-send-enable-thinking-param",
    ];

    static readonly Dictionary<string, string> ModelOption = new() { ["openai"] = "--openai-model", ["openaicompatible"] = "--openai-compatible-model" };

    static List<Choice> FullRange =>
        [new("minimal", Loc.S("最低")), new("low", Loc.S("低")), new("medium", Loc.S("中")), new("high", Loc.S("高")), new("xhigh", Loc.S("极高"))];

    public static string TitleOfLevel(string level) => level switch
    {
        "off" or "none" => Loc.S("关闭"),
        "minimal" => Loc.S("最低"),
        "low" => Loc.S("低"),
        "medium" => Loc.S("中"),
        "high" => Loc.S("高"),
        "xhigh" => Loc.S("极高"),
        "max" => Loc.S("最高"),
        "ultra" => Loc.S("超高"),
        "thinking" => Loc.S("深度思考"),
        _ => level,
    };

    static Support AgentSupport(LocalAgent agent, TranslationService service, IReadOnlyDictionary<string, string> fields)
    {
        if (agent.EffortLevels().Length == 0) return new Support.None();
        var field = service.ModelField;
        var chosen = (field != null ? fields.GetValueOrDefault(field.Option) : null)?.Trim() ?? "";
        var model = chosen.Length == 0 ? field?.DefaultValue : chosen;
        if (LocalAgents.EffortInModelName(model) is { } level) return new Support.DecidedByModel(TitleOfLevel(level));
        if (agent.ModelDecidesEffort() && chosen.Length > 0) return new Support.DecidedByModel(Loc.S("模型默认"));
        var offered = agent.EffortLevels().ToList();
        var usual = agent.DefaultEffort() ?? "";
        if (agent == LocalAgent.Codex && AgentModels.CodexLevels(chosen) is { } listed)
        {
            var levels = listed.Levels.Where(l => l != "none").ToList();
            if (levels.Count == 0) return new Support.UnsupportedModel();
            offered = levels;
            usual = levels.Contains("low") ? "low" : listed.Usual is { } u && levels.Contains(u) ? u : levels[0];
        }
        return new Support.Choices([.. offered.Select(l => new Choice(l, TitleOfLevel(l))), new Choice("", Loc.S("由智能体决定"))], usual);
    }

    public static string AgentEffort(string serviceId, IReadOnlyDictionary<string, string> fields) =>
        GetSupport(serviceId, fields) is Support.Choices ? Current(serviceId, fields) ?? "" : "";

    public static Support GetSupport(string serviceId, IReadOnlyDictionary<string, string> fields)
    {
        if (TranslationServiceCatalog.Service(serviceId) is { Backend: TranslationBackend.Agent agent } service) return AgentSupport(agent.Which, service, fields);
        switch (serviceId)
        {
            case "openai" or "openaicompatible":
            {
                var fallback = TranslationServiceCatalog.Service(serviceId)?.Fields.FirstOrDefault(f => f.Option == ModelOption[serviceId])?.DefaultValue ?? "";
                var model = fields.GetValueOrDefault(ModelOption[serviceId])?.Trim() ?? "";
                var name = (model.Length == 0 ? fallback : model).ToLowerInvariant();
                var bare = name.Split('/').Last();
                if (Regex.IsMatch(bare, @"^gpt-([5-9]|\d{2})")) return new Support.Choices(FullRange, "medium");
                if (Regex.IsMatch(bare, "^o[1-9]")) return new Support.Choices([new("low", Loc.S("低")), new("medium", Loc.S("中")), new("high", Loc.S("高"))], "medium");
                if (bare.StartsWith("gpt-4") || bare.StartsWith("gpt-3") || bare.StartsWith("chatgpt")) return new Support.UnsupportedModel();
                if (serviceId == "openaicompatible") return new Support.Choices([new("", Loc.S("不设置")), .. FullRange], "");
                return new Support.UnsupportedModel();
            }
            case "deepseek":
                return new Support.Choices([new("", Loc.S("默认")), new("off", Loc.S("关闭思考")), new("high", Loc.S("高")), new("max", Loc.S("最高"))], "");
            case "siliconflow":
                return new Support.Choices([new("", Loc.S("默认")), new("on", Loc.S("开启思考")), new("off", Loc.S("关闭思考"))], "");
            default:
                return new Support.None();
        }
    }

    /// <summary>Where a service's level is kept: its own option, or for any local agent "--&lt;service&gt;-effort" (an agent
    /// added later is never left without one, which would keep its choice from being stored).</summary>
    static string? OptionFor(string serviceId)
    {
        if (ValueOption.TryGetValue(serviceId, out var known)) return known;
        return TranslationServiceCatalog.Service(serviceId)?.Backend is TranslationBackend.Agent ? $"--{serviceId}-effort" : null;
    }

    public static string? Current(string serviceId, IReadOnlyDictionary<string, string> fields)
    {
        if (GetSupport(serviceId, fields) is not Support.Choices choices || OptionFor(serviceId) is not { } option) return null;
        var stored = fields.GetValueOrDefault(option) ?? choices.Default;
        return choices.List.Any(c => c.Value == stored) ? stored : choices.Default;
    }

    public static void Set(string value, string serviceId, IDictionary<string, string> fields)
    {
        if (OptionFor(serviceId) is { } option) fields[option] = value;
    }

    public static Dictionary<string, string> Apply(string serviceId, IReadOnlyDictionary<string, string> fields)
    {
        var result = fields.Where(kv => !ManagedOptions.Contains(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value);
        if (Current(serviceId, fields) is not { Length: > 0 } value) return result;
        switch (serviceId)
        {
            case "openai":
                result["--openai-reasoning-effort"] = value;
                result["--openai-send-reasoning-effort"] = "true";
                break;
            case "openaicompatible":
                result["--openai-compatible-reasoning-effort"] = value;
                result["--openai-compatible-send-reasoning-effort"] = "true";
                break;
            case "deepseek":
                if (value == "off") result["--deepseek-thinking-mode"] = "disabled";
                else
                {
                    result["--deepseek-thinking-mode"] = "enabled";
                    result["--deepseek-reasoning-effort"] = value;
                }
                break;
            case "siliconflow":
                result["--siliconflow-send-enable-thinking-param"] = "true";
                if (value == "on") result["--siliconflow-enable-thinking"] = "true";
                break;
        }
        return result;
    }
}

public enum TranslationFailureReason { Authentication, Quota, Network, ModelNotFound, ClientOutdated, AgentSetup, ServerError, Configuration, EncryptedPdf, OutOfMemory, DiskFull, Unknown }

public sealed record TranslationFailure(TranslationFailureReason Reason, string Message, string RawMessage);

/// <summary>Maps raw errors to one specific message: not "the key is invalid, expired or lacks permission" but which of them.</summary>
public static class TranslationErrorClassifier
{
    static List<string> HttpCode(int code) =>
        [$"error code: {code}", $@"status(_code)?[""']?[=: ]+{code}", $@"\b{code} (client|server) error", $"http {code}", $"http/1.1 {code}"];

    static readonly List<string> Balance = [.. HttpCode(402), "insufficient.?balance", "insufficient_quota", "余额不足", "payment required", "exceeded your current quota", "quota exceeded", "credit"];
    static readonly List<string> RateLimit = [.. HttpCode(429), "too many requests", "rate[ -]limit", "ratelimiterror", "rate_limit_exceeded"];
    static readonly List<string> Forbidden = [.. HttpCode(403), "forbidden", "permissiondenied", "permission denied", "not have access"];
    static readonly List<string> BadKey = [.. HttpCode(401), "unauthori[sz]ed", "invalid.?api.?key", "incorrect api key", "authenticationerror", "api key not valid", "invalid.?auth"];

    static readonly List<(TranslationFailureReason Reason, List<string> Patterns)> Rules =
    [
        (TranslationFailureReason.AgentSetup, ["agent-setup "]),
        (TranslationFailureReason.ClientOutdated, [.. HttpCode(426), "upgrade required", @"version[^\n]{0,40}(is )?outdated", @"please (update|upgrade) to (version )?\d", "client version"]),
        (TranslationFailureReason.ModelNotFound, ["model_not_found", @"model[^\n]{0,80}(does not exist|not found|not exist)", "no such model", "unknown model", "invalid model", "模型不存在"]),
        (TranslationFailureReason.Quota, [.. RateLimit, .. Balance]),
        (TranslationFailureReason.Authentication, [.. BadKey, .. Forbidden]),
        (TranslationFailureReason.Configuration, ["is required", "invalid clitranslator", "not found at", "command '.*' not found", "invalid arguments",
                                                  "context_length_exceeded", "maximum context length", .. HttpCode(400)]),
        (TranslationFailureReason.EncryptedPdf, ["password", "encrypted"]),
        (TranslationFailureReason.OutOfMemory, ["memoryerror", "out of memory", "outofmemoryexception"]),
        (TranslationFailureReason.DiskFull, ["no space left on device", "disk full", "not enough space on the disk"]),
        (TranslationFailureReason.ServerError, [.. HttpCode(500), .. HttpCode(502), .. HttpCode(503), .. HttpCode(504), "internal server error", "bad gateway",
                                                "service unavailable", "gateway timeout", "overloaded"]),
        (TranslationFailureReason.Network, ["connection error", "connecterror", "connecttimeout", "readtimeout", "timed out", "timeout error",
                                            "name or service not known", "nodename nor servname", "failed to establish a new connection", "max retries exceeded",
                                            "network is unreachable", "connection refused", "connection reset", "sslerror", "ssl: ", "proxyerror",
                                            "temporary failure in name resolution", "no reachable upstream", "remoteprotocolerror", "server disconnected"]),
    ];

    public static TranslationFailure Classify(string message, string? details = null)
    {
        var raw = message.Trim();
        var original = raw + "\n" + (details ?? "");
        var haystack = original.ToLowerInvariant();
        foreach (var (reason, patterns) in Rules)
            if (Matches(haystack, patterns)) return new TranslationFailure(reason, Text(reason, raw, haystack, original), raw);
        return new TranslationFailure(TranslationFailureReason.Unknown, Text(TranslationFailureReason.Unknown, raw, haystack, original), raw);
    }

    static bool Matches(string haystack, IEnumerable<string> patterns) => patterns.Any(p => Regex.IsMatch(haystack, p.ToLowerInvariant()));

    static string TrimmedSentence(string text) => Shortened(text).Trim(' ', '.', '。');

    static string Text(TranslationFailureReason reason, string raw, string haystack, string original)
    {
        if (FirstMatch(@"agent ([\w-]+):", original) is { } agent && reason is TranslationFailureReason.Authentication or TranslationFailureReason.Quota
                or TranslationFailureReason.ServerError or TranslationFailureReason.Unknown)
        {
            var said = TrimmedSentence(Regex.Replace(FirstMatch(@"agent [\w-]+:\s*([^\n]+)", original) ?? raw, @"\s+http \d{3}$", ""));
            return reason switch
            {
                TranslationFailureReason.Quota when Matches(haystack, Balance) => Loc.S("%@ 的账户额度已用完：%@", agent, said),
                TranslationFailureReason.Quota => Loc.S("%@ 的模型服务限流了请求，请稍后重试或换一个模型：%@", agent, said),
                TranslationFailureReason.Unknown => Loc.S("%@ 运行失败：%@", agent, said),
                _ => Loc.S("%@ 的模型服务返回错误：%@", agent, said),
            };
        }
        var found = Host(original);
        string host = found != null ? " " + found : "", hostThen = found != null ? Loc.S(" %@ ", found) : "";
        string Code(params int[] codes) => StatusCode(haystack, codes) is { } c ? Loc.S("（%@）", c.ToString()) : "";
        switch (reason)
        {
            case TranslationFailureReason.Authentication:
                if (Matches(haystack, Forbidden)) return Loc.S("翻译服务拒绝访问%@：这个 API Key 没有使用该服务或模型的权限", Code(403));
                if (haystack.Contains("expired")) return Loc.S("API Key 已过期%@，请在 设置 ▸ 翻译 中换用新的 Key", Code(401));
                return Loc.S("API Key 无效%@，请在 设置 ▸ 翻译 中检查是否填写正确", Code(401));
            case TranslationFailureReason.Quota:
                if (Matches(haystack, Balance)) return Loc.S("翻译服务的账户余额或额度已用完%@，请充值或换用其他服务", Code(402, 429));
                return Loc.S("请求过于频繁，被翻译服务限流%@，请调低 设置 ▸ 翻译 ▸ 同时请求数，或换用其他服务；已翻译的段落会保留，重试时不会重复翻译", Code(429));
            case TranslationFailureReason.ModelNotFound:
                return Loc.S("模型%@ 不存在或无权使用，请在 设置 ▸ 翻译 中检查模型名称", Model(original) is { } m ? " " + m : "");
            case TranslationFailureReason.ClientOutdated:
            {
                var current = FirstMatch(@"version \(?v?(\d+(?:\.\d+)+)\)?\s*(?:is )?(?:outdated|too old)", original);
                var required = FirstMatch(@"(?:to|least|version) v?(\d+(?:\.\d+)+)(?: or (?:later|newer|above))", original);
                var versions = current != null
                    ? required != null ? Loc.S("它上报的客户端版本 %@ 已过期（要求 %@ 或更新）", current, required) : Loc.S("它上报的客户端版本 %@ 已过期", current)
                    : Loc.S("它上报的客户端版本已过期");
                if (FirstMatch(@"agent ([\w-]+):", original) is { } a) return Loc.S("%@ 的版本过旧：%@。请在终端更新 %@ 后重试", a, versions, a);
                return Loc.S("服务%@的上游拒绝了请求（426）：%@。这个版本号是该接口服务自己上报的，和这台电脑上安装的命令行工具无关，请更新这个接口服务（例如 grok2api）或在它的设置里改高版本号", hostThen, versions);
            }
            case TranslationFailureReason.AgentSetup:
            {
                var name = FirstMatch(@"agent-setup ([\w-]+):", original) ?? "";
                // Its command line can't use the account the app signed in with: the app keeps that sign-in to itself.
                if (name == "codex" && haystack.Contains("stream-disconnected"))
                {
                    var url = FirstMatch(@"stream-disconnected (\S+)", original);
                    if (url != null && Uri.TryCreate(url, UriKind.Absolute, out var address) && address.AbsolutePath.Trim('/').Length == 0)
                        return Loc.S("codex 连不上它的服务商 %@：回复还没完成连接就断了。这个地址打开的是网站而不是接口，中转服务的地址通常要以 /v1 结尾（例如 %@/v1）。请在 CC Switch 或 codex 的配置里改正后再试", url, url);
                    return Loc.S("codex 连不上它的服务商：回复还没完成连接就断了。请检查 codex 配置里的服务商地址和网络后再试");
                }
                // CodeBuddy: signed in in WorkBuddy is not signed in here.
                if (name == "codebuddy" && System.Text.RegularExpressions.Regex.IsMatch(original, @"(?i)authenticat|log ?in|401"))
                    return Loc.S("CodeBuddy 命令行还没登录：请在 设置 ▸ 翻译 ▸ CodeBuddy 点“在终端登录”，用 WorkBuddy 的腾讯账号登录一次后再试");
                if (name == "dsh" && Matches(haystack, ["missing_credential", "account_sign_in_required"]))
                    return Loc.S("DeepSeek Harness 的命令行不能使用桌面版的账号登录。请在 DeepSeek Harness 的模型设置中填写 DeepSeek API Key（或设置环境变量 DEEPSEEK_API_KEY）后再试");
                var why = TrimmedSentence(FirstMatch(@"agent-setup [\w-]+:\s*([^\n]+)", original) ?? raw);
                return Loc.S("%@ 还不能使用：%@。请先在终端运行一次 %@，完成登录或设置后再试", name, why, name);
            }
            case TranslationFailureReason.ServerError:
                return Loc.S("翻译服务%@暂时出错%@，这是服务端的问题，请稍后重试", hostThen, Code(500, 502, 503, 504));
            case TranslationFailureReason.Network:
                if (Matches(haystack, ["nodename nor servname", "name or service not known", "temporary failure in name resolution"])) return Loc.S("找不到服务器%@，请检查 Base URL 是否正确", host);
                if (haystack.Contains("connection refused")) return Loc.S("服务器%@拒绝连接：服务没有运行或端口不对（本地服务如 Ollama 需要先启动）", hostThen);
                if (Matches(haystack, ["sslerror", "ssl: ", "certificate"])) return Loc.S("与服务器%@的安全连接（SSL）失败，请检查代理或证书设置", hostThen);
                if (haystack.Contains("proxyerror")) return Loc.S("代理服务器连接失败，请检查代理设置");
                if (Matches(haystack, ["timed out", "timeout", "connecttimeout", "readtimeout"])) return Loc.S("连接服务器%@超时，网络较慢或需要代理", hostThen);
                if (Matches(haystack, ["connection reset", "server disconnected", "remoteprotocolerror"])) return Loc.S("服务器%@中断了连接，请稍后重试", hostThen);
                if (haystack.Contains("network is unreachable")) return Loc.S("网络不可用，请检查网络连接");
                return Loc.S("无法连接翻译服务%@，请检查网络", host);
            case TranslationFailureReason.Configuration:
                if (Matches(haystack, ["context_length_exceeded", "maximum context length"])) return Loc.S("文本超过了模型的上下文长度，请换用上下文更长的模型");
                if (Matches(haystack, HttpCode(400))) return Loc.S("翻译服务不接受这次请求%@：%@", Code(400), Shortened(ServiceMessage(original) ?? raw));
                return Loc.S("翻译服务配置不完整：%@", Shortened(raw));
            case TranslationFailureReason.EncryptedPdf:
                return Loc.S("PDF 已加密或受密码保护，无法翻译");
            case TranslationFailureReason.OutOfMemory:
                return Loc.S("内存不足，翻译被中止，请只翻译部分页码");
            case TranslationFailureReason.DiskFull:
                return Loc.S("磁盘空间不足，无法保存译文");
            default:
                return raw.Length == 0 ? Loc.S("翻译失败") : Loc.S("翻译失败：%@", Shortened(raw));
        }
    }

    public static string? Host(string text) => FirstMatch("host='([^']+)'", text) ?? FirstMatch(@"https?://([A-Za-z0-9.\-]+(?::\d+)?)", text);
    static string? Model(string text) => FirstMatch(@"model[\s:=]*[`'""]([^`'""\s]+)[`'""]", text);
    static string? ServiceMessage(string text) => FirstMatch(@"['""]message['""]\s*:\s*['""]([^'""]+)['""]", text);
    static int? StatusCode(string haystack, int[] codes) => codes.Cast<int?>().FirstOrDefault(c => Matches(haystack, HttpCode(c!.Value)));

    public static string? FirstMatch(string pattern, string text)
    {
        var m = Regex.Match(text, pattern, RegexOptions.IgnoreCase);
        return m.Success && m.Groups.Count > 1 ? m.Groups[1].Value : null;
    }

    public static string Shortened(string text, int limit = 200)
    {
        var first = text.Split('\n', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? text;
        return first.Length > limit ? first[..limit] + "…" : first;
    }
}
