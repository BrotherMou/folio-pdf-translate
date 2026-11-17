# Windows translation engine

Source: [Alonemo-Nnqc/Folio](https://github.com/Alonemo-Nnqc/Folio), commit `767b9acb571d04e24794ec678f2a514049d97d78`, `windows/src/Folio.Core/Translate`, plus `Loc` and selected text/OCR layout helpers. Folio source copyright (c) 2026 Alonemo-Nnqc, MIT; preserve the root `LICENSE` and third-party notices.

This executable requires no Folio application, library database, desktop UI, or Folio settings. It accepts a JSON request on stdin and emits JSONL events, matching the macOS engine contract. Credentials supplied for explicitly selected external services arrive on stdin, not command arguments.

Local changes:

- Independent .NET console target and strict path/page/input checks.
- Default calling-Agent mailbox provider, with no translation API or nested Agent process.
- Formula placeholder validation on fresh translations, cache reads, and merged results.
- Preservation of Computer Modern matrix tails and correct font stream compression metadata.
- Keyword boundary detection, per-line algorithm prose classification, distinct numbered items, and body text/heading handling at page margins.
- Source classification coverage and glyph/formula/image geometry export for the shared hover PDF generator.

`PDFTranslateEngine.csproj` lists the direct NuGet dependencies and embedded resources. Build with `scripts/build-engine.ps1`. Its self-contained publish directory includes the .NET runtime and native dependencies and must be distributed as a whole. Python dependencies, MCP configuration, and Skill installation are separate steps documented in the root README.

The project retains necessary upstream implementation files and resource strings beyond the narrow default Agent path; their presence does not enable every original Folio feature or service in the public MCP interface. Current supported services are validated by `server/jobs.py`.

See `VALIDATION.md` for current verification boundaries. Cross-compilation on macOS and successful .NET tests on macOS do not establish Windows host or Adobe Reader compatibility.
