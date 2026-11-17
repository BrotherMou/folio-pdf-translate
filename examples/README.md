# PDF 演示

## Attention Is All You Need

[下载中英双语 PDF](attention-is-all-you-need.en-zh.bilingual.pdf)

| 项目 | 内容 |
| --- | --- |
| 论文 | Ashish Vaswani 等，Attention Is All You Need，NIPS 2017 |
| 来源 | [arXiv:1706.03762v7](https://arxiv.org/abs/1706.03762v7)；输入文件第一页标记为此版本 |
| 生成日期 | 2026-11-17 |
| 文件名 | `attention-is-all-you-need.en-zh.bilingual.pdf` |
| 页面与大小 | 15 页，每页左侧原文、右侧中文；3,099,817 字节 |
| 翻译方式 | 当前 Agent 按 `folio-pdf-translate` Skill 调用 MCP；`service=agent`，`en` → `zh`，`hover_highlight=true`，全文模式 |
| 执行平台 | macOS；本文件不是 Windows 引擎生成的示例 |
| 高亮统计 | 282 组句子高亮；141/144 个待定位文本块成功，3 个排除项 |

翻译由当前 Agent 分批完成，没有调用额外翻译 API。标题、摘要、正文、部分表格文字、脚注和图注参与翻译。作者信息、参考文献、公式、数值、模型名及图内标签主要保留原文。原论文及图表版权归原作者或相应权利人所有，保留原文署名和许可说明；仓库代码的 MIT 许可不覆盖原论文。译文供项目效果演示，未经原作者审校。

### 生成与额外处理

1. 先通过 MCP 试译第 3–4 页，检查模型架构图和注意力公式附近的排版，再运行全文翻译。
2. 对输入副本使用 PyMuPDF `save(expand=255)` 展开 PDF 内容流。输入副本与原文件全部 15 页的提取文字及渲染像素一致；原文件保持不变。
3. 通过 `get_pending_translations` 领取句子，保留 ID 和公式占位符，使用 `submit_translations` 回填当前 Agent 的译文。全文任务完成后检查分类和高亮报告。
4. 对最终 MCP 输出中的两处 Form XObject 修复额外的 zlib 压缩层。这两处流仅包含附录图中的填色矩形绘制指令；未修改文字、公式、注释或高亮层。此项是本演示的额外修复，尚未接入默认 MCP 流程。

### 阅读与验证

- 下载 PDF，用 Adobe Acrobat 桌面版打开并允许 Acrobat JavaScript，使用单页视图测试原文和译文之间的悬浮高亮。
- GitHub 网页预览及其他阅读器可用于查看排版；是否执行交互取决于阅读器。
- 已检查全部页面概览及公式、表格和附录图；修复后的 PDF 可由 Poppler 渲染，未报告 PDF 语法错误。
- 已核对文字层、原有注释和 282 个可选内容组在图形流修复前后保持一致。文件没有新增覆盖正文的 Link/Widget，保留可提取的英文和中文文字。
- 本次未执行 Adobe 桌面 UI 验收。实际悬浮、拖选复制、离开窗口清除等行为仍需在目标阅读器中测试。

### 已知限制

以下三处保留可读文字，但没有悬浮高亮：

| 页码 | 内容 | 排除原因 |
| --- | --- | --- |
| 2 | 介绍自注意力定义及应用的段落 | 原文文本与几何定位不匹配 |
| 9 | 表 3 的 `params` 表头（译为“参数量”） | 没有对应句子记录 |
| 10 | 提供 tensor2tensor 代码链接的句子 | 原文文本与几何定位不匹配 |

分类规则还保留了表 1 的 `Self-Attention`、表 4 的 `semi-supervised` 和 `multi-task` 等短标签，以及第 13 页的 `Attention Visualizations` 标题。这些是当前示例的漏译范围；正文、图注已翻译，不以高亮覆盖率作为全文无漏译的证明。公式中包含的 `where`、`and` 等词随公式原样保留。第 11–12 页为参考文献，左右两侧均保留英文。

### 文件校验

```text
输入文件 SHA-256:
bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697

演示 PDF SHA-256:
6356cb1b184200a86b7d417e06ef98f9718afa03f81bd02549eeab8fbd78e9a6
```

## 自制公式样例

`formula-sample.pdf` 是供自动化回归测试使用的两页合成 PDF，包含公式、矩阵等内容。它不依赖用户论文，也不是上述论文的译文。
