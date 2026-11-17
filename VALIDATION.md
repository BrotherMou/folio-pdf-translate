# Validation record

Date: 2026-11-17. This record describes checks of the source-only distribution. Private inputs, raw logs, local directory paths, built engines and virtual environments are not part of the repository.

## Clean macOS installation

Two separate temporary copies of the source were used. Neither contained a virtual environment or compiled engine before installation. `scripts/setup.sh` created new virtual environments with `include-system-site-packages = false`, installed the hashed dependency lock, installed the project, and compiled Swift sources. `PYTHONNOUSERSITE=1` was set during verification.

| Environment | Install + pip check | Real stdio MCP end-to-end check | Regression suite |
| --- | --- | --- | --- |
| macOS ARM64, CPython 3.14.6 | Passed | Passed | 23 passed, 0 skipped |
| macOS ARM64, CPython 3.11.15, checkout path containing spaces | Passed | Passed | 23 passed, 0 skipped |

Both builds used Apple Swift 6.4.2 and Apple SDK 27.2. The package declares Swift 6.2 and macOS 14 as its lower bounds; those exact lower-bound compiler/OS combinations were not independently tested. JavaScript mock tests used Node.js 24.18.0. Node is a test dependency, not a translation runtime dependency.

Dependency checks confirmed that MCP, PyMuPDF and setuptools came from the new virtual environments, not global site-packages. Direct versions: MCP 1.28.1, PyMuPDF 1.28.2, setuptools 80.9.0; the complete tested Python dependency graph is in `requirements.lock`. One dependency download was interrupted; rerunning installation with the same hashes succeeded. Download caches are permitted; no packages were imported from another environment.

`scripts/verify_install.py` exercised the actual launcher, verified all five MCP tool registrations, and called start, pending, submit and status through stdio. Its temporary PDF and two fixed Chinese test translations completed the native engine and hover flow. The output contained two paired hover groups, a classification report, selectable original/translated text and no new overlay annotations. Source bytes and inactive hover appearance were unchanged. This tests installation and integration, not translation-model quality.

The regression suite checks native formula preservation, keywords, lists/algorithm prose, margin body text, original-page appearance, placeholder rejection, Agent exchange/concurrent submissions, cancellation, error handling, MCP transport and mocked hover behavior. All fixtures are self-generated or use the repository's synthetic formula sample.

## Windows build boundary

Using .NET SDK 10.0.100 on macOS, the C# source was successfully published as a `win-x64` self-contained application with its native libraries. Existing downloaded NuGet packages were reused for this cross-build. The source project and publish flags match `scripts/build-engine.ps1`; Windows PowerShell was not executed on this host.

This is a cross-compilation result, **not a clean Windows installation or Windows execution test**. Windows x64 runtime behavior, Windows font availability, Windows ARM64, and the newly supplied GitHub workflows still need execution on their target hosts. The workflows will run only after the user uploads/enables them. No repository has been uploaded as part of this preparation.

## Reader boundary

No Adobe desktop UI test was performed in these clean environments. PDF structure/rendering and simulated JavaScript checks cannot establish that hover, drag-selection/copy, continuous scrolling and pointer exit behavior work simultaneously in a particular Adobe version. Non-Adobe readers may ignore the embedded JavaScript while rendering the PDF normally.

## Distribution checks

`AGENT_INSTALL.md` adds an Agent-operated bootstrap and client configuration workflow. Its commands were checked against repository scripts, local Codex CLI help, and official dependency/client documentation. Local document links, referenced script paths, code-fence pairing and absence of author-machine paths were checked. The guide itself was not used to install missing system dependencies or configure another client in this validation. In particular, Windows dependency bootstrap and client reloading remain target-host checks; the earlier clean macOS results above are not evidence of those steps.

- Source-only directory; no `.venv`, native build caches, compiled binaries, job directories or raw logs.
- No personal papers, translated papers, machine username paths or detected credential tokens.
- The only PDF is the two-page synthetic `examples/formula-sample.pdf`; its author metadata is empty and it contains no embedded attachments.
- Installed-user Skill paths were not copied. The distributed Skill handles relocation and does not assume that a copied client Skill remains inside the checkout.
- `.gitignore` excludes private inputs, PDFs except the approved sample, outputs, logs, credentials and build artifacts. `.gitattributes` preserves LF for shell/Python scripts.
- Removed historical standalone demo scripts/tests that depended on unpublished local output files. Their production hover invariants are covered by self-contained pipeline tests.
- LICENSE, provenance, resources and third-party notices are retained. Python dependencies and build tooling are version/hash locked; NuGet direct versions are explicit but its full transitive graph is not locked.

## Final source publication audit (2026-11-17)

- Inspected all 142 files, including hidden files. No personal papers, translations, logs, virtual environments, build products, symlinks, developer-user paths or detected credential values were found. Email addresses belong to retained third-party notices; loopback URLs are optional service defaults and test fixtures. Standard platform paths in runtime code are retained.
- Inspected the only binary file, `examples/formula-sample.pdf`: two synthetic pages, empty author/title fields, no embedded attachments, and no detected personal content or developer paths in PDF objects.
- Compared Python direct dependency versions with `requirements.lock` and README, and NuGet versions with the C# project and README. Checked Python syntax, JSON/resource parsing, shell syntax and local documentation links. The macOS/Windows build targets, launcher paths and MCP interface match the installation documentation.
- Performed a local Git staging check in a temporary copy, without creating a repository or commits in the publication directory. All 142 intended source files were included. Ignore checks cover environments, builds, personal inputs, outputs, logs and local client configuration. Added `.agents/` alongside `.codex/` to exclude project-local client installations.
- README and UPSTREAM explicitly identify the project as an independently maintained derivative of Folio and thank Alonemo-Nnqc and the Folio contributors. The retained MIT notice was checked against the linked upstream extraction commit.
- Clarified that optional plugin metadata requires a host capable of resolving `python` and `${PLUGIN_ROOT}`. Normal installation uses `print_mcp_config.py` and the project interpreter's absolute path.

A further fresh source copy in a path containing spaces passed `scripts/setup.sh`, hashed dependency installation, native Swift compilation, `pip check` and the real stdio `verify_install.py` flow on macOS ARM64 with CPython 3.14.6. The regression suite passed all 23 tests with 0 skipped. Non-fatal Swift/Apple toolchain and Pydantic annotation warnings were emitted; no check failed. No system dependency bootstrap, Windows host execution, client reconfiguration or Adobe UI test was performed during this audit. Temporary build/test artifacts remain outside the publication directory. Nothing was uploaded to GitHub.
