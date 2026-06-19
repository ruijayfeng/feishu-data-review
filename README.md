# 飞书数据复盘分析

从飞书表格提取数据 → 通用复盘分析 → 生成 Markdown 报告 + PPT 汇报材料。

## 功能

- 自动检查环境依赖（飞书 CLI、认证状态、PPT 生成 Skill）
- 从飞书表格链接获取数据（支持 wiki 链接、直接链接）
- 通用数据分析（趋势、对比、相关性、异常检测）
- 生成 Markdown 复盘报告
- 生成 PPT 可视化汇报材料

## 安装

```bash
npx skills add ruijayfeng/feishu-data-review -y
```

或者手动安装：

```bash
git clone https://github.com/ruijayfeng/feishu-data-review.git
cd feishu-data-review
npx skills add skills/feishu-data-review -y
```

## 一键安装

复制以下命令发送给你的 Agent，它会自动帮你完成安装：

```bash
npx skills add ruijayfeng/feishu-data-review -y
```

---

## 前置依赖

- 飞书 CLI: `npm install -g @larksuite/cli`
- Python 3（分析脚本仅使用标准库，零额外依赖）
- baoyu-design skill（首次运行自动安装）

## 使用

向 Claude Code 提供飞书表格链接：

> 帮我分析这个表格 https://my.feishu.cn/sheets/XXX

## 输出

- `output/report.md` — 结构化分析报告
- `output/presentation.pptx` — 可视化 PPT 汇报材料
- `output/data.csv` — 原始数据备份

## License

MIT
