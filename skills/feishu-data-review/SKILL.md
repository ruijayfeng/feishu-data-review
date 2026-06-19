---
name: feishu-data-review
description: "飞书数据复盘分析与可视化报告生成。从飞书电子表格或多维表格中提取数据，进行通用数据复盘分析（趋势、对比、分布、相关性、异常检测），输出结构化 Markdown 报告和 PPT 可视化汇报材料。当用户需要对飞书表格数据做分析、复盘、生成报告、制作 PPT、数据可视化、业绩回顾、内容表现分析等任务时触发。也适用于用户说'分析这个表格'、'帮我复盘下数据'、'生成汇报 PPT'、'看看这些数据的趋势'等场景。即使用户没有明确说'复盘'，只要涉及飞书表格数据的分析和可视化输出，都应使用本 skill。"
---

# 飞书数据复盘分析

从飞书表格提取数据 → 通用复盘分析 → 生成 Markdown 报告 + PPT 可视化汇报材料。

## 工作流

```
环境检查 → 获取表格数据 → 运行分析脚本 → 生成报告 → 生成 PPT
```

---

## 第一步：环境守卫

**每次执行前必须检查以下三项，缺一不可。**

### 1. lark-cli 是否安装

```bash
lark-cli --version 2>/dev/null || echo "NOT_INSTALLED"
```

如果未安装，引导用户执行：

```bash
npm install -g @larksuite/cli
npx -y skills add https://open.feishu.cn --skill -y
```

### 2. lark-cli 认证状态

```bash
lark-cli auth status
```

检查返回中 `identities.user.status` 是否为 `"ready"` 且 `identities.user.tokenStatus` 是否为 `"valid"`。

如果未认证或 token 过期，引导用户：

```bash
lark-cli auth login --recommend
```

如果缺少 `search:docs:read` 或 `space:document:retrieve` 权限：

```bash
lark-cli auth login --scope "search:docs:read space:document:retrieve"
```

### 3. baoyu-design skill 是否可用

检查当前项目是否已安装 `baoyu-design` skill：

```bash
ls .agents/skills/baoyu-design/SKILL.md 2>/dev/null || ls .claude/skills/baoyu-design/SKILL.md 2>/dev/null || echo "NOT_INSTALLED"
```

如果未安装，自动安装到当前项目：

```bash
npx -y skills add JimLiu/baoyu-design --scope project -y
```

如果 GitHub 连接失败（国内网络问题），告知用户需要手动安装或配置代理。

---

## 第二步：获取表格数据

用户会提供一个飞书表格链接。

### 2.1 解析链接

先用 `lark-cli drive +inspect` 解析链接，获取真实的文档类型和 token：

```bash
lark-cli drive +inspect --url "<用户提供的链接>"
```

- 如果返回 `doc_types: "SHEET"` → 电子表格，走 2.2A
- 如果返回 `doc_types: "BITABLE"` → 多维表格，走 2.2B
- 如果是 `/wiki/` 链接，inspect 会自动 unwrap 到真实文档

### 2.2A 电子表格数据获取

**先获取工作簿信息，确定有哪些子表：**

```bash
lark-cli sheets +workbook-info --url "<表格URL>"
```

从返回的 `sheets[]` 中选择目标子表。如果用户没指定，选数据行数最多的那个。

**导出 CSV 数据：**

```bash
lark-cli sheets +csv-get --url "<表格URL>" --sheet-id "<选定的sheet_id>" --range "A1:ZZ99999" --format csv --output /tmp/feishu_data.csv
```

如果 `--output` 不被支持，使用重定向：

```bash
lark-cli sheets +csv-get --url "<表格URL>" --sheet-id "<选定的sheet_id>" --range "A1:ZZ99999" --format csv > /tmp/feishu_data.csv
```

如果表格行数很多（超过 5000 行），先试一个较大的 range，如果数据被截断再分批读取。

### 2.2B 多维表格数据获取

**先获取表格列表：**

```bash
lark-cli base tables list --params '{"app_token":"<从inspect获取的token>"}'
```

选择目标数据表，然后导出记录：

```bash
lark-cli base records list --params '{"app_token":"<token>","table_id":"<table_id>","page_size":500}' --page-all --format csv -o /tmp/feishu_data.csv
```

### 2.3 数据预检

读取 CSV 的前 10 行，快速检查：
- 是否有合并单元格导致的空行（跳过）
- 表头是否干净（没有多行表头）
- 数据编码是否正确（UTF-8）

如果有问题，在传递给分析脚本前做清理。

---

## 第三步：运行通用分析

使用 `scripts/analyze.py` 对数据进行通用分析。**分析是确定性的数学计算，不让 LLM 做算术。**

```bash
python <skill-path>/scripts/analyze.py --input /tmp/feishu_data.csv --output /tmp/feishu_analysis.json --top 10
```

脚本自动完成：
1. **列类型识别** — 数值列、时间列、分类列、文本列
2. **基础统计** — 每个数值列的总量、均值、中位数、标准差、最大最小值、分位数
3. **趋势检测** — 如有时间列，自动计算首尾 1/3 均值变化率，判断上升/下降/持平
4. **分类对比** — 如有分类列，按类别聚合数值列，找出显著差异
5. **相关性分析** — 数值列之间的 Pearson 相关系数
6. **异常检测** — 超出 1.5 倍标准差的数据点
7. **关键洞察** — 按优先级排序的 top N 发现

**读取分析结果 JSON**，理解数据结构和分析发现，为下一步报告生成做准备。

---

## 第四步：生成 Markdown 报告

基于分析结果，生成一份结构清晰的复盘报告。报告是**人类可读的叙述**，不是 JSON 的复读。

### 报告结构

```markdown
# [数据源名称] 数据复盘报告

> 分析时间：YYYY-MM-DD | 数据范围：[时间范围或行数] | 数据来源：[飞书表格名称/链接]

## 一、数据概览

[一段话总结数据整体情况：涵盖哪些维度、多少条记录、时间跨度]

| 指标 | 总量 | 均值 | 最大值 | 最小值 |
|------|------|------|--------|--------|
| ... | ... | ... | ... | ... |

## 二、关键发现

[从 insights 中提取 3-5 个最值得汇报的发现，每个发现包含：]
[1. 现象描述  2. 数据支撑  3. 可能的原因或建议]

### 发现 1：[标题]
[描述 + 数据 + 解读]

### 发现 2：[标题]
...

## 三、趋势分析

[如果有时间列，描述各数值指标的趋势变化]
[标注拐点、异常波动、周期性特征]

## 四、对比分析

[如果有分类列，描述各类别之间的差异]
[哪些类别表现突出，哪些拖后腿]

## 五、相关性发现

[如果有显著相关性，说明哪些指标联动变化]

## 六、建议与下一步

[基于数据发现，给出 2-3 条可执行的建议]
```

将报告保存到项目目录：`output/report.md`

---

## 第五步：生成 PPT 汇报材料

**铁律：PPT 必须由 baoyu-design skill 全流程生成，禁止自己手写 CSS 或代码。**

PPT 是 baoyu-design skill 的专长领域，你（feishu-data-review）的职责是准备内容，把设计决策交给 baoyu-design。

### 标准流程（必须按顺序执行，不可跳过任何步骤）

1. **读取 baoyu-design 的 SKILL.md**
   - 路径：`.agents/skills/baoyu-design/SKILL.md` 或 `.claude/skills/baoyu-design/SKILL.md`
   - 必须理解 baoyu-design 的设计方法论、风格选择流程、色彩系统
   - 读取完成后，**向用户展示 2-3 个可选的设计风格方向**，让用户选择（不要自作主张）

2. **调用 baoyu-design 的 PPT 生成流程**
   - 使用 baoyu-design 提供的标准命令/工具生成 PPT
   - 将第四步生成的 Markdown 报告内容作为输入传递给 baoyu-design
   - 让 baoyu-design 自动完成：设计系统选择 → 风格决策 → 幻灯片布局 → PPT 文件生成

3. **验证输出**
   - 检查 baoyu-design 输出的 PPT 文件是否存在
   - 检查是否遵循了 baoyu-design 的设计标准
   - 如果不符合，回到第 1 步选择其他风格重新生成

**禁止行为：**
- ❌ 自己写 HTML/CSS 来模拟 PPT 效果
- ❌ 跳过设计系统选择环节
- ❌ 跳过风格方向选择环节
- ❌ 跳过 baoyu-design 的完整流程直接生成内容
- ❌ 用其他 PPT 生成工具替代 baoyu-design

**PPT 内容结构建议（由 baoyu-design 排版，你只提供内容要点）：**

| 页面 | 内容要点 |
|------|---------|
| 封面 | 标题 + 数据范围 + 日期 |
| 数据概览 | 核心指标一览表 |
| 关键发现 1 | 最重要的一个发现 + 数据支撑 |
| 关键发现 2 | 第二重要的发现 + 数据支撑 |
| 趋势总览 | 趋势数据摘要 |
| 对比分析 | 分类对比数据摘要 |
| 总结建议 | 2-3 条行动建议 |

保存到：`output/presentation.pptx`

---

## 输出清单

最终交付物：

```
output/
├── report.md              # 结构化分析报告
├── presentation.pptx      # 可视化 PPT 汇报材料
└── data.csv               # 原始数据备份
```

完成后告知用户每个文件的位置和用途。

---

## 注意事项

- 分析脚本零外部依赖（纯 Python 标准库），不需要 pip install
- 如果 CSV 文件很大（>10MB），分析可能需要几秒，告知用户稍等
- 数值列如果全是 0 或全是同一个值，脚本会跳过统计，报告中说明即可
- 如果用户没有提供链接，可以用 `lark-cli drive +search` 帮用户搜索表格
- 报告语言跟随用户语言（用户用中文就中文报告，英文就英文报告）
