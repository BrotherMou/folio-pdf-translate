import Foundation

/// The calling Agent supplies translations through local files. No model process or network request is started.
struct AgentExchangeProvider: TranslationProvider {
    let directory: URL
    let limits = ProviderLimits(batchCharacters: 4000, batchItems: 20, concurrency: 1, usesContext: true)

    init(directory: String) throws {
        guard directory.hasPrefix("/") else {
            throw ProviderError(kind: .agentSetup, detail: "--agent-exchange-directory must be an absolute path")
        }
        self.directory = URL(fileURLWithPath: directory, isDirectory: true).standardizedFileURL
    }

    // Uses the protocol's empty extractTerms/prewarm defaults: the Agent handles terminology in the same task.
    func translate(_ items: [TranslationItem], context: TranslationContext) async throws -> [String] {
        if items.isEmpty { return [] }
        try Task.checkCancellation()
        let requestID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let requests = directory.appending(path: "requests", directoryHint: .isDirectory)
        let responses = directory.appending(path: "responses", directoryHint: .isDirectory)
        for folder in [requests, responses] {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                                    attributes: [.posixPermissions: 0o700])
        }
        let request = ExchangeRequest(request_id: requestID, source_language: context.sourceLanguage,
                                      target_language: context.targetLanguage, instructions: LLMBatch.systemPrompt(context),
                                      context: ExchangeContext(title: context.title, summary: context.summary,
                                                               glossary: context.glossary, figure_captions: context.figureCaptions),
                                      items: items.enumerated().map {
                                          ExchangeItem(id: String($0.offset + 1), source: $0.element.text,
                                                       kind: $0.element.kind.rawValue, is_short: $0.element.isShort)
                                      })
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let requestURL = requests.appending(path: requestID + ".json")
        try encoder.encode(request).write(to: requestURL, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: requestURL.path)

        let responseURL = responses.appending(path: requestID + ".json")
        while !FileManager.default.fileExists(atPath: responseURL.path) {
            try Task.checkCancellation()
            try await Task.sleep(for: .milliseconds(250))
        }
        try Task.checkCancellation()
        let response: ExchangeResponse
        do {
            response = try JSONDecoder().decode(ExchangeResponse.self, from: Data(contentsOf: responseURL))
        } catch {
            throw ProviderError(kind: .agentSetup, detail: "Invalid Agent translation response: " + error.localizedDescription)
        }
        guard response.version == 1, response.request_id == requestID,
              Set(response.translations.keys) == Set(request.items.map(\.id)) else {
            throw ProviderError(kind: .agentSetup, detail: "Agent response version, request_id or translation keys do not match")
        }
        return try request.items.map { item in
            let text = response.translations[item.id]!
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  Self.placeholderTokens(text) == Self.placeholderTokens(item.source) else {
                throw ProviderError(kind: .agentSetup, detail: "Agent translation is empty or changed formula/break placeholders for item " + item.id)
            }
            return text
        }
    }

    /// Match exact spellings and multiplicities, including the {v0} continuation marker.
    private static func placeholderTokens(_ text: String) -> [String] {
        let ns = text as NSString
        return Placeholders.pattern.matches(in: text, range: NSRange(location: 0, length: ns.length))
            .map { ns.substring(with: $0.range) }.sorted()
    }
}

private struct ExchangeRequest: Encodable {
    let version = 1
    let request_id: String
    let source_language: String
    let target_language: String
    let instructions: String
    let context: ExchangeContext
    let items: [ExchangeItem]
}

private struct ExchangeContext: Encodable {
    let title: String?
    let summary: String?
    let glossary: [GlossaryEntry]
    let figure_captions: [String]

    private enum CodingKeys: String, CodingKey { case title, summary, glossary, figure_captions }
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(title, forKey: .title)
        try container.encode(summary, forKey: .summary)
        try container.encode(glossary, forKey: .glossary)
        try container.encode(figure_captions, forKey: .figure_captions)
    }
}

private struct ExchangeItem: Encodable {
    let id: String
    let source: String
    let kind: String
    let is_short: Bool
}

private struct ExchangeResponse: Decodable {
    let version: Int
    let request_id: String
    let translations: [String: String]
}
