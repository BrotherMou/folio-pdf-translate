import Foundation
import PDFKit
import FolioTranslate

// Independent JSONL entrypoint. Credentials arrive on stdin, never argv or disk.
struct Input: Decodable {
    var input: String
    var output_directory: String
    var service: String?
    var fields: [String: String]?
    var secrets: [String: String]?
    var pages: String?
    var lang_in: String?
    var lang_out: String?
    var outputs: String?
    var translate_images: Bool?
    var cache_directory: String
    var glossary_file: String?
}

func emit(_ object: [String: Any]) {
    if let bytes = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) {
        FileHandle.standardOutput.write(bytes + Data([10]))
    }
}
struct InvalidInput: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}
func validate(_ condition: Bool, _ message: String) throws {
    if !condition { throw InvalidInput(message: message) }
}

do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    try validate(data.count < 1_048_576, "Request exceeds 1 MiB")
    let request = try JSONDecoder().decode(Input.self, from: data)
    let allowed = ["agent", "google", "bing", "openai", "openaicompatible", "ollama", "deepseek"]
    let service = request.service ?? "agent"
    try validate(allowed.contains(service), "Supported services: " + allowed.joined(separator: ", "))
    try validate(request.outputs == nil || request.outputs == "both", "Engine outputs must be both")
    for path in [request.input, request.output_directory, request.cache_directory] {
        try validate(path.hasPrefix("/"), "Paths must be absolute")
    }
    let source = URL(fileURLWithPath: request.input).standardizedFileURL
    let destination = URL(fileURLWithPath: request.output_directory).standardizedFileURL
    try validate(source.pathExtension.lowercased() == "pdf", "Input must be a PDF")
    guard let document = PDFDocument(url: source), document.pageCount > 0 else {
        throw InvalidInput(message: "Cannot open PDF or PDF has no pages")
    }
    try validate(!document.isLocked, "Password-protected PDF is not supported")
    if let pages = request.pages {
        try validate(pages.range(of: "^[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*$", options: .regularExpression) != nil,
                     "pages must use 1,3,5-7 syntax")
        for part in pages.split(separator: ",") {
            let tokens = part.split(separator: "-")
            let bounds = tokens.compactMap { Int($0) }
            try validate(bounds.count == tokens.count && !bounds.isEmpty && bounds.allSatisfy { $0 <= document.pageCount } && bounds.first! <= bounds.last!, "Page range outside PDF")
        }
    }
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
    try validate(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty,
                 "Engine output directory must be empty; source files are never overwritten")
    TranslationJob.supportDirectory = URL(fileURLWithPath: request.cache_directory, isDirectory: true)
    var options = TranslationOptions(langIn: request.lang_in ?? "en", langOut: request.lang_out ?? "zh",
                                     outputs: .both, dualLayout: .sideBySide, pages: request.pages)
    options.translateImageText = request.translate_images ?? false
    if let glossary = request.glossary_file {
        try validate(glossary.hasPrefix("/") && FileManager.default.isReadableFile(atPath: glossary), "Glossary must be a readable absolute path")
        options.glossaryFile = URL(fileURLWithPath: glossary)
    }
    let job = TranslationJob(request: TranslationRequest(input: source, outputDirectory: destination,
        serviceID: service, fieldValues: request.fields ?? [:], secrets: request.secrets ?? [:], options: options))
    var succeeded = false
    for await event in job.start() {
        switch event {
        case .stage(let message): emit(["type": "stage", "message": message])
        case .progress(let value): emit(["type": "progress", "value": value])
        case .preview(let url): emit(["type": "preview", "path": url.path])
        case .notice(let message): emit(["type": "notice", "message": message])
        case .problem(let message): emit(["type": "problem", "message": message])
        case .finished(let mono, let dual):
            guard let mono, let dual else { throw InvalidInput(message: "Missing output PDF") }
            emit(["type": "finished", "mono_pdf": mono.path, "dual_pdf": dual.path])
            succeeded = true
        case .failed(let message, let log): emit(["type": "failed", "message": message, "log": log.path])
        case .cancelled: emit(["type": "cancelled"])
        }
    }
    if !succeeded { exit(1) }
} catch {
    emit(["type": "failed", "message": error.localizedDescription])
    exit(1)
}
