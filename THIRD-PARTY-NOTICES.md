# Third-party components

The extracted Folio source is copyright (c) 2026 Alonemo-Nnqc under MIT. Preserve the full upstream notice in `LICENSE`. Provenance and extraction scope are recorded in `UPSTREAM.md` and `engine-windows/EXTRACTION.md`.

This source repository does not include compiled dependency packages, proprietary system fonts, personal papers, or the Apple/.NET SDKs. Installing dependencies does not change their respective licenses. The upstream MIT notice must not be interpreted as the only license governing a combined distribution.

| Component | Use | License / primary reference |
| --- | --- | --- |
| Python MCP SDK | stdio MCP service | [MIT](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) |
| PyMuPDF / MuPDF | PDF inspection and interactive PDF generation | [AGPL or Artifex commercial license](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) |
| PdfPig | Windows PDF parsing | [Apache-2.0](https://github.com/UglyToad/PdfPig/blob/master/LICENSE) |
| SkiaSharp, SkiaSharp.HarfBuzz | Windows rendering and text shaping | MIT; license texts in `engine-windows/third-party/` |
| HarfBuzz and native components | Native text shaping | See retained native component notices in `engine-windows/third-party/` |
| .NET runtime and libraries | Included when publishing a self-contained Windows package | [MIT and component notices](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT) |
| setuptools | Python project installation | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |

Python transitive dependencies are enumerated with versions and hashes in `requirements.lock`; their distributions carry their own notices. NuGet direct dependencies are pinned in the C# project; NuGet resolves the transitive graph. Preserve all applicable notices when publishing binaries or vendoring dependencies, including the .NET runtime and native libraries. Do not copy system fonts into the repository without redistribution rights.

`engine-windows/THIRD-PARTY-NOTICES.md` retains the full Folio upstream notice as attribution history. It lists some Folio application components not used by this standalone project; the direct build dependencies are the ones actually referenced by `PDFTranslateEngine.csproj`.

Before distributing a combined package, determine the applicable AGPL/commercial terms for PyMuPDF/MuPDF. This project does not claim that keeping Folio's MIT notice alone meets all obligations for every distribution model.
