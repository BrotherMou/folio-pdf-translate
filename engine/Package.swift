// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "PDFTranslate",
    defaultLocalization: "zh-Hans",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "pdf-translate-engine", targets: ["PDFTranslateEngine"])],
    targets: [
        .target(name: "FolioTranslate", resources: [.process("Resources")]),
        .executableTarget(name: "PDFTranslateEngine", dependencies: ["FolioTranslate"]),
    ]
)
