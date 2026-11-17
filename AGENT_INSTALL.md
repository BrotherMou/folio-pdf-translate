# Agent 安装指南

本指南供具有本机终端、文件读写权限的 Agent 执行。用户提出安装请求后，依次完成检查、补齐依赖、构建、验证、配置 MCP 和安装 Skill。只阅读仓库或解释项目时，不执行安装。

默认安装到当前用户、当前 Agent 客户端。已有符合要求的依赖直接复用。不要求用户逐条执行命令，不为已经授权的安装步骤重复确认。遇到确实需要用户输入密码、登录或操作系统弹窗的步骤，说明具体原因和操作；完成后继续安装。

## 1. 确定运行位置和客户端

1. 读取 [README.md](README.md)、[pyproject.toml](pyproject.toml) 及当前平台的 `scripts/setup.*`。以当前仓库文件为依赖依据。
2. 确认 MCP 实际运行环境的操作系统、CPU 架构和当前客户端。当前客户端由会话上下文判断，不能因为电脑安装了某个 CLI 就假定用户正在使用该客户端。
3. Windows 使用本机 PowerShell 和 C# 引擎；macOS 使用 shell 和 Swift 引擎。Linux/WSL/远程 Linux 容器不支持运行这些引擎。若 Agent 工具实际运行在此类环境，先确认是否能在用户 Windows/macOS 主机执行；不能直接在那里安装 Linux 依赖后宣称可用。
4. 确认当前客户端支持本地 stdio MCP。仅支持远程 HTTP MCP 的客户端不能直接使用本项目。不要自动改造成公开 HTTP 服务。
5. 将完整仓库放在用户可写、准备长期保留的目录。若已在合适目录，不移动。ZIP 解压即可，不必为安装本项目额外安装 Git。
6. 默认配置当前客户端的用户级 MCP 和 Skill；用户指定项目级范围时遵从指定范围。若无法判断当前客户端，只询问这一个必要信息；先继续不依赖客户端的环境检查和构建。

所有路径从当前仓库根目录解析。不要复制维护者的绝对路径。日志和临时下载放入已忽略的 `.cache/` 或 `output/`，不写入公共配置和 Skill 正文。

## 2. 检查并补齐系统依赖

先检查命令能否实际执行及版本，不只检查文件存在。安装成功后重新定位可执行文件；当前进程可能尚未继承安装器修改的 PATH。PATH 调整优先限于本次安装进程，后续 MCP 使用项目 Python 的绝对路径。

### Windows

在仓库根目录执行检查。缺失命令是待安装项，不应导致整个检查提前结束：

```powershell
$ErrorActionPreference = 'Stop'
$FolioRoot = (Get-Location).Path
Get-Command python, py, dotnet, winget -ErrorAction SilentlyContinue
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
# 仅对找到的命令执行：
python -c "import sys, platform, venv, ensurepip; print(sys.executable); print(sys.version); print(platform.machine()); assert sys.version_info >= (3, 11)"
dotnet --list-sdks
```

需要 CPython 3.11+（含 pip/venv）和 .NET 10 SDK。仅有 .NET Runtime 不够。检查 Python 架构、SDK 架构和引擎目标匹配；常规 Windows x64 使用 `win-x64`。Windows ARM64 使用 `win-arm64` 前，确认该 Python/PyMuPDF 组合有可用安装包；本仓库尚未验证 ARM64。

**缺少 Python：** 优先复用已安装的合格 Python，`py` 能找到的解释器也可使用。让该解释器所在目录在当前进程 PATH 中优先出现，再确认 `python` 指向它。不要使用仅触发 Microsoft Store 的占位命令。

如果确实缺少 Python 且已有 WinGet，先查询包信息，再安装匹配架构的用户级 Python。例如以下包 ID 必须先由 `winget show` 验证，不能假定所有源都提供：

```powershell
winget show --id Python.Python.3.12 --exact --source winget
winget install --id Python.Python.3.12 --exact --source winget --scope user
```

WinGet 不可用或该包不支持当前机器时，从 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/) 选择符合版本和架构的正式发行版，按该发行版安装文档执行用户级安装。安装 Agent 应自行查找和下载官方安装器；仅将不可自动完成的系统交互交给用户。不要为了绕开版本检查修改项目依赖要求。

**缺少 .NET SDK：** 优先采用已有包管理器或 Microsoft 官方安装器。WinGet 路径如下，系统级安装可能出现 UAC：

```powershell
winget show --id Microsoft.DotNet.SDK.10 --exact --source winget
winget install --id Microsoft.DotNet.SDK.10 --exact --source winget
```

如果没有管理员权限，可采用 Microsoft 官方的非管理员安装方式。以下示例将 SDK 放到当前用户目录，仅供本项目构建使用。先根据前述架构检查设置 `$FolioArchitecture` 为 `x64` 或 `arm64`：

```powershell
$FolioSdkDir = Join-Path $env:LOCALAPPDATA 'FolioPDFTranslate/dotnet'
$FolioDownloadDir = Join-Path $FolioRoot '.cache/install'
New-Item -ItemType Directory -Force -Path $FolioDownloadDir | Out-Null
$FolioInstaller = Join-Path $FolioDownloadDir 'dotnet-install.ps1'
Invoke-WebRequest 'https://dot.net/v1/dotnet-install.ps1' -OutFile $FolioInstaller
& $FolioInstaller -Channel 10.0 -Quality GA -Architecture $FolioArchitecture -InstallDir $FolioSdkDir -NoPath
if ($LASTEXITCODE -ne 0) { throw 'SDK installation failed.' }
$env:DOTNET_ROOT = $FolioSdkDir
$env:PATH = "$FolioSdkDir;$env:PATH"
dotnet --list-sdks
```

下载后检查官方来源及脚本内容，再执行；下载和执行应分成两次工具调用。不要传 `-Runtime`，否则只安装运行时。该方式不会注册系统级 SDK，后续重建时需重新将此目录加入当前进程 PATH。构建输出采用 self-contained，不依赖客户端 PATH 中存在 `dotnet`。[Microsoft 安装说明](https://learn.microsoft.com/en-us/dotnet/core/install/windows)、[安装脚本参数](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script)。

### macOS

```sh
FolioRoot="$(pwd -P)"
sw_vers -productVersion
uname -m
command -v python3
command -v swift
command -v brew
# 仅对已安装的工具执行；Apple 工具尚未安装时可能触发系统安装提示：
python3 -c 'import sys, platform, venv, ensurepip; print(sys.executable); print(sys.version); print(platform.machine()); assert sys.version_info >= (3, 11)'
swift --version
xcrun --show-sdk-path
```

需要 CPython 3.11+、Swift 6.2+ 和配套 Apple SDK。引擎最低运行系统为 macOS 14，但构建主机还必须支持所选工具链；不能仅凭 macOS 版本就认定可构建。

**缺少 Python：** 已有 Homebrew 时可安装并仅调整当前 shell 的 PATH：

```sh
brew install python@3.12
export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"
python3 --version
```

路径规则见 [Homebrew Python 3.12 说明](https://formulae.brew.sh/formula/python@3.12)。如果没有 Homebrew，优先使用 [Python 官方 macOS 安装器](https://www.python.org/downloads/macos/)，不强制增加一套包管理器。执行前检查安装器支持当前系统；需要管理员验证时由用户完成该操作。

**缺少 Apple 工具：** 执行 `xcode-select --install` 后，系统安装对话框可能需要用户完成。已有 Xcode 不必重复安装 Command Line Tools。安装或更新后再次检查 Swift 版本和 SDK。若系统可用的工具链仍低于 Swift 6.2，说明具体缺项，不修改包声明来绕过构建要求。[Apple 官方安装说明](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)。

如果机器已有合适的其他 Xcode，可为本次构建设置 `DEVELOPER_DIR` 指向实际找到的开发者目录；不要为了本项目随意修改全局 `xcode-select` 设置。不要自动升级操作系统。

### 字体与非必需组件

检查当前用户能使用的中文字体。Windows 通常可用宋体/微软雅黑；macOS 通常可用宋体/苹方。精简系统缺少字体时，根据引擎字体选择代码确认支持的字体，再从官方来源安装 Noto CJK 或思源字体，并验证实际中文字形。

默认翻译由当前 Agent 完成，不安装本地模型，不索要翻译 API Key。无需安装 Node.js、LaTeX、Poppler 或 Adobe 来构建和生成 PDF。Adobe 只用于人工验收悬浮交互。完整依赖见 [README.md](README.md)。

## 3. 构建项目

确认前述检查通过后，在同一进程环境、仓库根目录执行对应脚本。每次执行后检查退出码；失败时先修复具体错误，不进入客户端配置阶段。

Windows x64：

```powershell
& (Join-Path $FolioRoot 'scripts/setup.ps1') -Runtime win-x64
if ($LASTEXITCODE -ne 0) { throw 'Project setup failed.' }
$FolioPython = Join-Path $FolioRoot '.venv/Scripts/python.exe'
```

Windows ARM64 将参数改为 `-Runtime win-arm64`，并在交付记录中注明该机器的实际验收结果。如果仅受本地 PowerShell 执行策略限制，可按 README 对本次进程使用 `-ExecutionPolicy Bypass`；不要修改全局执行策略或绕过组织管理策略。

macOS：

```sh
sh "$FolioRoot/scripts/setup.sh"
# 只有上一条命令成功后继续。
FolioPython="$FolioRoot/.venv/bin/python"
```

脚本创建独立 `.venv`、校验锁文件哈希、安装项目并构建对应引擎。不要改用全局 pip 安装。已有 `.venv` 若混用全局包、架构不符或损坏，先将其移到 `.cache/` 下的唯一备份目录，再重建。下载短暂失败可按原锁文件重试；不能通过删除哈希、改依赖版本或跳过构建把失败变为成功。

## 4. 先验证独立 MCP

Windows：

```powershell
& $FolioPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'pip check failed.' }
& $FolioPython (Join-Path $FolioRoot 'scripts/verify_install.py')
if ($LASTEXITCODE -ne 0) { throw 'MCP verification failed.' }
& $FolioPython (Join-Path $FolioRoot 'scripts/print_mcp_config.py')
```

macOS：

```sh
"$FolioPython" -m pip check
"$FolioPython" "$FolioRoot/scripts/verify_install.py"
"$FolioPython" "$FolioRoot/scripts/print_mcp_config.py"
```

逐条检查成功后再执行下一条。`verify_install.py` 使用临时自制 PDF 和固定测试译文，通过真实 stdio MCP 检查五个工具、原生引擎、中文/英文文字层、双语 PDF 及悬浮结构，不需要用户论文和翻译 API。临时测试文件自动清理。

该测试不证明客户端已加载 MCP，也不证明 Adobe 中的实际悬浮和拖选操作已通过。正常安装无需额外安装 Node.js 或重复运行完整回归；出现代码改动或回归疑点时再运行 README 中的测试。

## 5. 配置当前客户端的 MCP

`print_mcp_config.py` 输出当前机器的实际 `command` 和 `args`：使用项目 `.venv` 的 Python，运行本仓库的 `scripts/launch_mcp.py`。启动器自行设置工作目录。配置名称为 `folio-pdf-translate`。

1. 根据当前客户端及版本，优先使用客户端提供的 MCP 配置命令/接口。需要直接写文件时，先确认当前客户端实际使用的文件和范围。
2. 读取目标条目；相同配置不重复写入。已有同名配置指向旧目录时，备份目标配置后仅更新本项目条目，保留其他服务器、密钥、注释及权限设置。备份保留在客户端配置目录或私有目录，不提交仓库。
3. 不用生成的单服务器配置覆盖整个配置文件。JSON、JSONC、TOML 必须按客户端的实际格式修改。不要用正则替换整个配置块，或将 JSON 示例直接粘入 TOML。
4. 写入后重新读取目标条目，核实两个绝对路径都存在。配置文件含其他服务的凭证时，不输出完整文件。

### Codex

先执行 `codex mcp --help` 和 `codex mcp add --help` 核对当前 CLI。确认 CLI 属于当前 Codex 使用的配置环境；自定义 `CODEX_HOME` 或客户端管理范围不能忽略。通常配置文件为 `~/.codex/config.toml`，但不能不检查就硬写该路径。

查询目标条目：

```sh
codex mcp get folio-pdf-translate --json
```

条目不存在时，使用以下命令添加。Windows PowerShell：

```powershell
codex mcp add folio-pdf-translate -- $FolioPython (Join-Path $FolioRoot 'scripts/launch_mcp.py')
```

macOS：

```sh
codex mcp add folio-pdf-translate -- "$FolioPython" "$FolioRoot/scripts/launch_mcp.py"
```

已有同名条目需要更新时，先确认当前 CLI 对同名 `add` 的行为；不支持更新则只修改实际 TOML 中的目标条目。不假定存在 `codex mcp update` 命令。完成后用 `codex mcp get folio-pdf-translate --json` 读回。不要更改全局工具审批设置。[Codex MCP 官方说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

### 其他客户端

查阅当前客户端的官方 MCP 安装说明，确认本地 stdio、配置范围和重载方式。支持 `mcpServers` JSON 的客户端可合并脚本输出；其他格式使用相同的名称、命令和参数。不要猜测配置文件位置，也不要把配置写入所有已安装客户端。

根目录 `plugin.json` / `mcp.json` 的 `${PLUGIN_ROOT}` 仅用于支持该变量的插件宿主。一般客户端使用脚本生成的绝对路径。MCP 配置不需要外部翻译凭证。

## 6. 安装 Skill

源目录始终为本仓库 `skills/folio-pdf-translate/`。复制整个目录，包括 `SKILL.md` 和 `agents/openai.yaml`，不要只复制 Markdown，也不要复制另一台机器上改过路径的已安装版本。

Codex 当前官方用户级目录是 `~/.agents/skills/`，安装目标为该目录下的 `folio-pdf-translate/`。按当前用户真实主目录解析 Windows/macOS 路径。若客户端版本使用其他目录，以该版本实际发现规则为准；检查已有的同名 Skill，避免在新旧目录重复注册。[Codex Skill 目录说明](https://learn.chatgpt.com/docs/build-skills)。

其他客户端采用其官方 Skill 目录或安装接口。若客户端不支持 Skill，明确报告限制；仅加载 MCP 不能称为 MCP 和 Skill 均已安装。

复制前比较源目录与目标目录。内容一致则跳过；需要更新则将原目录备份到 Skill 扫描范围之外，再复制，保留其他 Skill。不要把备份放在同一个扫描目录中，以免出现两个同名 Skill。复制后核对文件清单和内容哈希。分发 Skill 已支持从 MCP 配置定位仓库，不需要注入本机绝对路径。

## 7. 验证客户端并交付

按当前客户端支持的方式重连或重新发现 MCP/Skill。若当前会话不能刷新，告诉用户所需的一个具体动作，例如新建会话或重新启动客户端。不要自行结束用户其他任务或强制关闭客户端进程。

客户端接入验收必须查看当前客户端实际暴露的工具，确认以下五个工具可用（宿主可能添加命名空间前缀）：

- `start_translation`
- `get_pending_translations`
- `submit_translations`
- `get_translation_status`
- `cancel_translation`

确认客户端发现 `folio-pdf-translate` Skill。若客户端连接可用，再从客户端用仓库自制的 `examples/formula-sample.pdf` 创建 `service="agent"` 试译任务，输出到 `output/` 下的唯一新目录。由当前 Agent 领取并翻译、回填，直到完成，并核对 `primary_artifact.path` 指向悬浮双语 PDF、`primary_artifact.kind="bilingual_hover_pdf"`，再检查 `artifacts.coverage_report`、`artifacts.hover_report`。默认只交付该主产物；普通双语版、纯译文版、预览及报告保留供内部检查。不要将等待 Agent 回填误判为引擎卡死。具体翻译和公式占位符规则按 [Skill](skills/folio-pdf-translate/SKILL.md) 执行。

交付时简要报告：

| 项目 | 应报告的证据 |
| --- | --- |
| 系统和依赖 | OS/架构、实际 Python 和 SDK/Swift 版本；复用与新增项目 |
| 本机文件 | 仓库目录、项目 Python、引擎路径 |
| 独立 MCP | `pip check`、`verify_install.py` 是否通过 |
| 当前客户端 | 配置位置、五个工具是否已发现、客户端试译结果或待重连原因 |
| Skill | 安装位置、是否已被客户端发现 |
| PDF | 试译输出路径；Adobe 实际交互未测试时明确注明 |

若当前客户端暂时不能刷新，准确写“构建和独立 MCP 验证通过，客户端接入等待重连”，不写全部完成。用户完成重连后继续客户端验收。安装报告和本机路径只保存在本机，不回写公共 README 或 Skill。

## 验证范围与更新

本指南提供 Agent 执行步骤，不是一份已经在所有机器运行过的系统安装程序。系统安装器、客户端命令及 Skill 目录随版本变化，执行时应结合实际 `--help` 和上述官方文档核实。项目已完成的测试及尚未完成的 Windows/Adobe 验证见 [VALIDATION.md](VALIDATION.md)。

后续更新项目时，复用合格的系统依赖，重新执行对应 `setup.*` 和 `verify_install.py`；只在路径或 Skill 内容变化时更新客户端配置或 Skill。正常翻译不重复执行安装流程。
