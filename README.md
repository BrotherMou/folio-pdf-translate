# Folio PDF Translate

本项目基于 [Alonemo-Nnqc/Folio](https://github.com/Alonemo-Nnqc/Folio) 二次开发，提取其 PDF 翻译引擎，配套本地 MCP 和 Agent Skill。面向 Windows/macOS。无需安装 Folio 应用。

当前 Agent 翻译可选中文字的英文 PDF，引擎保护原公式字形并排版，输出原文在左、译文在右的双语 PDF。默认包含面向 Adobe Acrobat 桌面版的双向悬浮高亮。公式和图片不参与高亮，文字保持可选，不增加覆盖正文的 Link/Widget。

## 翻译演示

[下载《Attention Is All You Need》中英双语 PDF](examples/attention-is-all-you-need.en-zh.bilingual.pdf)（15 页，约 3.1 MB）。由当前 Agent 按 `folio-pdf-translate` Skill，通过 MCP 分批翻译，原文在左、中文在右，包含 282 组句子高亮。

请下载后用 Adobe Acrobat 桌面版测试悬浮和文字拖选复制；GitHub 网页预览不用于验证交互。本演示有 3 处高亮定位排除、少量保留英文的短标签，并包含两处图形数据流修复。论文来源、处理步骤、验证结果和限制见 [演示说明](examples/README.md)。

## 致谢与项目来源

感谢 **Alonemo-Nnqc** 及 Folio 贡献者开源 PDF 解析、翻译、公式保护与排版实现。本项目的 Swift 和 C# 引擎基于这些代码提取和修改，并非从零实现。

本项目在此基础上增加独立构建、本地 MCP、Agent Skill、当前 Agent 翻译流程、双语 PDF 双向悬浮高亮及分类修复。这是独立维护的二次开发项目，不是 Folio 官方发行版。欢迎访问和支持原项目：[Alonemo-Nnqc/Folio](https://github.com/Alonemo-Nnqc/Folio)。

提取提交、代码范围和修改记录见 [UPSTREAM.md](UPSTREAM.md)。原作者版权声明和许可证完整保留于 [LICENSE](LICENSE)，第三方组件说明见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 让 Agent 安装

将仓库下载到准备长期保留的目录，在具有本机终端权限的 Agent 客户端中打开目录，发送：

> 请读取 README.md 和 AGENT_INSTALL.md，检查当前电脑的依赖，安装缺少的环境，构建并验证引擎，将 folio-pdf-translate MCP 和 Skill 安装到我当前使用的 Agent 客户端。复用符合要求的环境，保留其他客户端配置。完成后验证客户端能识别 MCP 工具和 Skill。只有需要我操作系统弹窗、登录或重新连接客户端时，再告诉我具体操作。

[AGENT_INSTALL.md](AGENT_INSTALL.md) 提供 Windows/macOS 分流、依赖补齐、构建、客户端配置及验收步骤。Agent 应执行这些步骤，而不是把命令清单交回用户。`scripts/setup.ps1` / `scripts/setup.sh` 负责 Python 包和引擎构建；系统依赖及客户端接入由安装 Agent 按指南完成。系统权限和客户端能力可能需要少量人工操作。

## 支持范围

- 输入：具有可选文字、未加密的 PDF。当前流程不提供扫描件 OCR。
- 默认 `service="agent"`：调用 MCP 的 Agent 负责逐句翻译，不需要额外翻译 API Key，不另起 Agent CLI。模型服务、联网和费用取决于 Agent 客户端。
- 输出：双语 PDF、纯译文 PDF、普通双语 PDF、源文分类报告和高亮覆盖报告。无 HTML 输出。
- 作者信息、参考文献、出版信息、图内标签默认保留原文；标题、正文、关键词、列表及算法自然语言参与翻译。
- 公式使用原 PDF 字形，位置可能随排版调整。需要检查上下标、矩阵、遮挡及遗漏，不能承诺任意 PDF 都能无损排版。
- 悬浮需 Adobe Acrobat 桌面版允许 Acrobat JavaScript；默认单页视图。其他阅读器可正常预览，不承诺执行悬浮。Adobe 的实际悬浮、拖选复制和离开窗口清除需验收。
- macOS 与 Windows 使用相同 MCP 参数，按 MCP 进程的操作系统自动选择 Swift 或 C# 引擎。不支持 Linux。

## 依赖

| 项目 | Windows | macOS |
| --- | --- | --- |
| 系统/架构 | 默认 `win-x64`；`win-arm64` 构建选项尚未实测 | 引擎最低 macOS 14；构建主机还须能运行所选 Swift/Apple SDK |
| Python | CPython 3.11+，含 pip 和 venv，加入 PATH | CPython 3.11+，命令为 `python3` |
| 构建工具 | [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)；PowerShell | Swift 6.2+、配套 Apple SDK/Command Line Tools 或 Xcode；`swift`、`xcrun` 可用 |
| 中文字体 | 宋体/微软雅黑，或引擎支持的 Noto CJK、思源字体 | 宋体/苹方等系统字体 |
| Agent | 支持本地 stdio MCP、能领取并回填待译批次的客户端；Skill 安装方式由客户端决定 | 同左 |
| 交互阅读器 | Adobe Acrobat 桌面版，仅用于查看悬浮效果；生成 PDF 不依赖 Adobe | 同左 |

Python 直接依赖：`mcp==1.28.1`、`PyMuPDF==1.28.2`。`requirements.lock` 锁定直接/间接依赖、平台条件和下载文件哈希，并包含构建后端 `setuptools==80.9.0`。安装脚本用 pip 校验哈希，不依赖 uv。

Windows 原生直接依赖在 `engine-windows/PDFTranslateEngine.csproj` 中固定：`PdfPig 0.1.16`、`SkiaSharp 3.119.4`、`SkiaSharp.HarfBuzz 3.119.4`。NuGet 自动还原间接依赖及本机库。macOS 使用 PDFKit、CoreGraphics、CoreText 等系统框架，无外部 Swift Package 依赖。

首次安装需访问 PyPI、NuGet 及所需 SDK 下载源。默认翻译不需要 GPU、本地模型、Node.js、LaTeX、Poppler、Pillow 或浏览器。Node.js 只用于 JavaScript 模拟测试；没有 Node.js 时该项测试会跳过。自制 PDF 样例已提交，不需要安装 LaTeX 重建。

## 从源码安装

下载仓库 ZIP 后解压，或用 Git 克隆。以下命令都在含本 README 的项目根目录执行。安装会创建 `.venv` 和本机引擎，不修改 Agent 客户端配置。

### Windows

先确认 `python --version`、`dotnet --version` 可运行，且满足上表版本要求。

```powershell
./scripts/setup.ps1
```

若 PowerShell 阻止本次本地安装脚本，可仅为此次进程指定执行策略，不修改全局设置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/setup.ps1
```

默认构建 `win-x64`。显式 ARM64 构建：`./scripts/setup.ps1 -Runtime win-arm64`；还需确认所用 Python/PyMuPDF 提供匹配架构的安装包，此组合尚未验证。

### macOS

检查 `python3 --version`、`swift --version`、`xcrun --show-sdk-path`。缺少 Apple 工具时先安装或更新 Command Line Tools/Xcode；旧版本工具不一定满足 Swift 6.2。

```sh
sh scripts/setup.sh
```

脚本拒绝复用允许全局包的 `.venv`。遇到该提示，将原 `.venv` 改名保留后重新安装。正常新安装不读取全局 Python site-packages。

### 安装后的文件

| 平台 | Python | 引擎 |
| --- | --- | --- |
| Windows | `.venv/Scripts/python.exe` | `bin/windows/pdf-translate-engine.exe` 及同目录依赖 |
| macOS | `.venv/bin/python` | `bin/pdf-translate-engine` 和 `bin/*.bundle` |

必须保留完整项目目录。仅 `pip install .` 只安装 Python 服务，不构建或携带原生引擎、Skill，不能作为完整安装方式。

## 配置 MCP 和 Skill

安装完成后生成当前目录的 MCP 配置，Windows 使用：

```powershell
./.venv/Scripts/python.exe scripts/print_mcp_config.py
```

macOS 使用：

```sh
./.venv/bin/python scripts/print_mcp_config.py
```

输出是通用 `mcpServers` JSON。支持此格式的客户端可合并该条目；使用其他格式的客户端，填写相同的服务器名称 `folio-pdf-translate`、`command` 和 `args`。路径由脚本根据本机目录生成，不需要复制作者电脑的路径。不要把生成的本机配置提交到公共仓库。

启动程序 `scripts/launch_mcp.py` 会切换到项目目录，并调用项目 `.venv`。不需要依赖客户端的工作目录。根目录 `plugin.json`、`mcp.json` 是可选插件元数据；`${PLUGIN_ROOT}` 只适用于支持该变量的宿主，不是所有 MCP 客户端通用的配置。该元数据的 `command="python"` 还要求宿主 PATH 中有可用的 `python`；常规安装应使用 `print_mcp_config.py` 生成的项目 Python 绝对路径，不能仅导入元数据就视为安装完成。

将 `skills/folio-pdf-translate/` 整个文件夹安装到客户端支持的 Skill 目录，或通过客户端从仓库安装该目录。Skill 指导调用流程，不包含引擎；MCP 和 Skill 都需要配置。移动项目目录后应重新生成 MCP 配置，并重新建立连接。

## 使用

向已配置的 Agent 提交 PDF，例如：

> 使用 folio-pdf-translate 全文翻译这篇论文。原文在左，中文在右，保留公式和图片，生成带双向悬浮高亮的 PDF。检查关键词、标题、列表、算法说明和所有排除项。

Agent 依次调用：

1. `start_translation(input_path, output_directory)`，默认 `service="agent"`、`hover_highlight=true`。
2. `get_pending_translations(job_id)`，自行翻译每个句子，结合 `paragraph_source` 理解上下文。
3. `submit_translations(job_id, request_id, translations)`，按原 ID 回填，逐字保留 `{vN}` 和出现次数；不跨 ID 合并或移动译文。
4. 循环领取/提交，查询 `get_translation_status`，直到 `state="completed"`。`waiting_for_translation` 表示等待 Agent，`building_hover` 表示尚未完成交互层。
5. 检查输出和报告，再交付 PDF。

`pages="1,3-5"` 用于试译；其余页保留原文。全文翻译省略 `pages`。用户取消时使用 `cancel_translation`。新任务创建独立输出目录，不覆盖源文件。

| artifact | 内容 |
| --- | --- |
| `dual_pdf` | 默认交付的双语悬浮 PDF |
| `plain_dual_pdf` | 启用悬浮时保留的普通双语 PDF |
| `mono_pdf` | 纯译文 PDF |
| `coverage_report` | 全部已分析文本块的页码、原文、分类和是否翻译 |
| `hover_report` | 高亮对应关系、保护区域和未能定位的排除项 |

高亮覆盖统计只针对已翻译文本，不证明全文没有漏译。必须对照源 PDF 检查 `coverage_report` 的排除项。无法准确定位的文本保持可阅读，记录在 `hover_report.skipped`，不猜测高亮位置。

### CLI（MCP 不可用时）

以下示例中的 `python` 应替换为上表中的项目 Python：

```sh
python -m server translate INPUT.pdf --output-dir output --service agent
python -m server agent-pending --exchange-directory EXCHANGE_DIRECTORY
python -m server agent-submit --exchange-directory EXCHANGE_DIRECTORY --request-id REQUEST_ID --translations-file TRANSLATIONS.json
```

第一条命令保持运行；另一个终端/工具调用领取并回填。`TRANSLATIONS.json` 为 ID 到译文的 JSON 对象。CLI 不会自行产生 Agent 译文，等待状态不是卡死。支持 `--pages`、`--from`、`--to`、`--glossary-file`；完整参数见 `python -m server translate --help`。

只有明确选用外部服务时才传入 `google`、`bing`、`openai`、`openaicompatible`、`ollama` 或 `deepseek`，同时设置 `hover_highlight=false`（CLI：`--no-hover-highlight`）。凭证用 `secret_env` 映射已有环境变量，不写入 Skill、命令参数或公共配置。Agent 模式失败不会自动切换外部服务。

## 验证与维护

```sh
python -m pip check
python scripts/verify_install.py
python -m unittest discover -s tests -v
```

这里也应使用项目 Python。`verify_install.py` 使用自制输入、固定测试译文，通过真实 stdio MCP 完成原生引擎到悬浮 PDF 的流程，不调用翻译 API，不代表模型翻译质量评测。测试在临时目录运行；不需要用户论文。

2026-11-17，提交 [`3601d00`](https://github.com/BrotherMou/folio-pdf-translate/commit/3601d002b8ba9010684cc09c5662d696221294f1) 已在 GitHub Actions 的 Windows 和 macOS 环境通过完整检查：

| 平台 | 依赖安装与引擎构建 | 真实 stdio MCP 集成 | 回归测试 | CI 记录 |
| --- | --- | --- | --- | --- |
| Windows（win-x64） | 通过 | 通过 | 23 项通过，0 项跳过 | [Windows engine](https://github.com/BrotherMou/folio-pdf-translate/actions/runs/44010883480) |
| macOS | 通过 | 通过 | 23 项通过，0 项跳过 | [macOS engine](https://github.com/BrotherMou/folio-pdf-translate/actions/runs/44010883479) |

两套 CI 均已上传引擎构建产物。Windows 还通过了原生 PDF 输出自检。上述结果验证构建和程序集成，不代表所有系统版本、Windows ARM64、Agent 客户端配置或 Adobe 桌面交互均已验证。实际 Adobe 悬浮高亮和拖选复制不能由 PDF 结构检查或模拟 JavaScript 测试替代。完整范围见 [VALIDATION.md](VALIDATION.md)。

更新 Python 依赖时修改 `pyproject.toml` / `requirements-build.in`，使用维护工具 uv 重新生成锁文件，并在干净环境测试：

```sh
uv pip compile pyproject.toml requirements-build.in --universal --python-version 3.11 --generate-hashes --output-file requirements.lock
```

不要直接复制开发机的全局 `pip freeze`。NuGet 直接依赖版本固定在项目文件；当前未锁定其完整传递依赖图。平台构建包应在目标系统测试后放 GitHub Releases，不提交源码仓库。Windows 自包含发布必须包含整个 `bin/windows/`，运行者无需另装 .NET Runtime；macOS 必须同时携带 `.bundle` 资源。两者仍需要 Python 环境及 Agent 客户端。

## 仓库内容与许可

源码目录包括 `server/`、`engine/`、`engine-windows/`、`skills/`、`scripts/`、`tests/` 和 `examples/`。PDF 文件仅保留自制 `examples/formula-sample.pdf` 和上述公开论文的双语演示。其他输入论文、译文、日志、虚拟环境和构建产物由 `.gitignore` 排除；发布前仍须检查实际文件。Python 锁文件、NuGet 项目文件、资源和第三方声明应一起上传。演示论文的来源及版权说明见 [examples/README.md](examples/README.md)，仓库代码的 MIT 许可不覆盖原论文。

来源和修改范围见 [UPSTREAM.md](UPSTREAM.md)，上游 Folio 的 MIT 声明见 [LICENSE](LICENSE)，组合依赖说明见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。PyMuPDF/MuPDF 使用 AGPL 或商业许可，保留 MIT 文件不表示整个组合包只受 MIT 约束。发布或再分发时需遵守实际组件的许可。
