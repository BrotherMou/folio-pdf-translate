# 上游来源与本地修改

上游：[Alonemo-Nnqc/Folio](https://github.com/Alonemo-Nnqc/Folio)

本项目是基于 Folio 的独立二次开发项目，不是 Folio 官方发行版。感谢 Alonemo-Nnqc 及 Folio 贡献者提供原有 PDF 翻译引擎；本项目保留原作者署名、MIT 许可证和第三方声明，并在此记录提取范围与后续修改。

提取提交：`767b9acb571d04e24794ec678f2a514049d97d78`，核对日期：2026-11-16。

## 提取范围

- `engine/Sources/FolioTranslate/`：来自上游 `macos/Packages/FolioCore/Sources/FolioTranslate/`。
- `engine-windows/`：基于上游 `windows/src/Folio.Core/Translate/` 及其必要支持代码。具体保留文件以该目录内容为准。
- 不包含 Folio 应用界面、文献数据库、引用管理、Zotero 导入和浏览器扩展。

## 本地修改

- 建立独立 Swift Package 和 Windows 构建目标。
- 新增 JSON stdin / JSONL stdout 引擎入口，供本地 CLI 和 MCP 使用。
- 将 Swift 的 `Localizable.xcstrings` 转换为 `.strings` 资源，允许使用 Command Line Tools 构建。
- 将任务缓存和日志放入独立目录，不使用 Folio 文献库或应用状态。
- 加强公式占位符完整性检查，拒绝丢失或重复占位符的翻译结果。该检查不代替版面和公式视觉检查。
- 修复与已识别公式紧邻的 Computer Modern 粗体矩阵乘积末尾被当作正文的问题；两平台采用相同的窄范围规则。
- 新增共用 Python MCP、任务状态和取消控制。
- 新增默认 `agent` 翻译模式：本地引擎写出待译批次，当前 Agent 回填译文，引擎继续排版；不调用外部翻译 API 或另起 Agent CLI。
- 新增跨平台批次领取、提交和占位符校验；Agent 模式按实际完成段落显示进度。
- 修复 Windows 双语 PDF 合成的字体流缓存：按实际压缩操作保留 `/FlateDecode`，不再通过压缩前后长度推测是否压缩，避免特定公式字形缺失。
- 修复两平台首篇页的作者区域边界：在 `Keywords`、`Key words`、`Index terms` 或摘要中先出现的位置结束，避免关键词及其换行条目被当作作者信息跳过。增加真实引擎回归测试，MCP 和 Skill 增加关键词完整性检查提示。

- 两平台引擎导出正文字符位置、译文行位置及公式/图片保护区域；MCP 在 Agent 逐句翻译后生成内嵌 Acrobat JavaScript 的双向悬浮 PDF。保留普通双语输出和覆盖报告，不增加覆盖正文的交互注释。

- 两端分类修复：算法区域按行保留代码语法、翻译自然语言；保留编号列表分项；页边距不再排除完整正文和加粗标题。导出 `translation-coverage.json` 供全文排除项审核。
- 发布目录使用 Python 依赖锁文件与哈希校验、独立虚拟环境安装、可移植 MCP 配置生成器和不依赖个人论文的 stdio 安装验证。

## 许可证

Folio：MIT，Copyright (c) 2026 Alonemo-Nnqc。完整声明保留在根目录 `LICENSE`。

运行依赖保留各自的许可证。主要包括：

| 依赖 | 用途 | 许可证 |
| --- | --- | --- |
| Python MCP SDK | MCP 服务 | MIT |
| PyMuPDF / MuPDF | PDF 检查及悬浮 PDF 生成 | AGPL 或商业许可 |
| PdfPig | Windows PDF 解析 | Apache-2.0 |
| SkiaSharp / SkiaSharp.HarfBuzz | Windows 绘制与文字排版 | MIT |

其余 Windows 构建依赖以 `engine-windows` 的项目文件和随依赖提供的许可证为准。Apple 系统框架不是本仓库复制的源码。

原 Folio 的 MIT 声明不改变 PyMuPDF / MuPDF 的许可条件。分发组合程序时应包含实际保留组件的许可证并遵守所选许可；本项目未声称整包只适用 MIT。

参考：[Folio 第三方声明](https://github.com/Alonemo-Nnqc/Folio/blob/767b9acb571d04e24794ec678f2a514049d97d78/THIRD-PARTY-NOTICES.md)、[PyMuPDF 许可说明](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)。
