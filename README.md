# 技能汉化管家 · skill-zh

> 给 [DeepSeek Harness](https://github.com/deepseek-ai) 的通用技能汉化工具：
> 安装到任意一台电脑后，扫描**该机器**上已安装或下载的所有 skill，生成中文名、中文关键词
> 和一句话说明，写回技能描述，并生成一份中文技能目录，让中文提问能精准命中技能。

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**特点**

- 不内置任何人的技能清单：首次运行扫描你机器上的技能，按需翻译。
- 中文标签写在 `description` 最前面（DSH 技能目录只读 name + 描述前 500 字符），
  所以中文提问能命中，英文路由也不受影响。
- 只改描述一行：改前备份、改后可逐字节回滚；`apply` 幂等。
- 翻译由当前会话的模型完成，支持任何领域的技能；附术语表和子代理提示词模板。
- 状态库在各自的 `~/.skills-zh/`，互不影响，可整体删除重建。

## 效果示例

汉化后，技能目录里的每个条目都会变成：

```text
- `diffdock`: 【分子对接 · 蛋白-配体结合位姿】DiffDock and DiffDock-L molecular docking. Use for ...
- `scanpy`:   【单细胞分析 · 标准流程】Standard single-cell RNA-seq analysis pipeline. Use for ...
- `pptx`:     【PPT 演示文稿 · 全流程处理】Use this skill any time a .pptx or .potx file ...
```

之后直接说「帮我做分子对接」「把论文转成 PPT」「跑个单细胞聚类」即可命中技能。

## 安装

需要 DSH、Python 3.8+、[PyYAML](https://pypi.org/project/PyYAML/)。

**方式一：git clone（推荐，可 `git pull` 更新）**

```bash
git clone https://github.com/xzzyy2000418-zyy/skill-zh.git ~/.agents/skills/skill-zh
python3 -m pip install pyyaml
```

> 项目级安装：把克隆路径换成 `<project>/.agents/skills/skill-zh`。

**方式二：下载 Release 压缩包**

从 [Releases](https://github.com/xzzyy2000418-zyy/skill-zh/releases) 下载
`skill-zh-<version>.zip`，解压到技能根目录：

```bash
unzip skill-zh-<version>.zip -d ~/.agents/skills/
python3 -m pip install pyyaml
```

装好后 DSH 会自动发现新技能，无需重启。

## 快速开始

```bash
cd ~/.agents/skills/skill-zh
python3 scripts/skill_zh.py doctor   # 环境自检：Python/PyYAML/技能根目录
python3 scripts/skill_zh.py init     # 扫描本机技能 + 生成待翻译清单 + 中文索引预览
```

`init` 会打印「待翻译 N 个」并生成 `~/.skills-zh/translations/pending-part-*.json`。
接着把英文描述翻成中文（由当前会话模型完成，见
[`references/translation-prompt.md`](references/translation-prompt.md)）：

1. 按提示词模板启动 **2–3 个翻译子代理**，每个子代理只负责一份 `pending-part-<x>.json`，
   产出 `part-<x>.zh.json`，并用 `check --strict` 自检到 0 问题。
2. 合并、生成索引、预览并写入标签、验收：

```bash
python3 scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json
python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py apply --dry-run    # 先看会改哪些描述
python3 scripts/skill_zh.py apply              # 写入【中文标签】
python3 scripts/skill_zh.py verify             # 0 问题才算完成
```

## 日常使用

```bash
python3 scripts/skill_zh.py status        # 覆盖率
python3 scripts/skill_zh.py scan && python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py lookup "帮我把论文转成PPT"   # 中文 -> 精确技能名
cat ~/.skills-zh/index.md                 # 中文技能目录（按 13 类分组）
```

- 用户问「有哪些技能 / 这个技能中文叫什么」→ 读 `~/.skills-zh/index.md` 回答。
- 用户用中文提需求 → 模型按中文标签直接命中技能；也可先 `lookup`，再用 `skill`
  工具加载**精确英文技能名**。
- 新增/删除技能后：`scan` → `pending`（只列没译或描述变了的）→ 翻译 → `merge` →
  `index` → `apply` → `verify`。

## 整理别人给的技能包

```bash
python3 scripts/skill_zh.py ingest ~/Downloads/some-skill.zip   # 支持目录/单个 SKILL.md
python3 scripts/skill_zh.py ingest ./some-skill-dir --dry-run
python3 scripts/skill_zh.py scan && python3 scripts/skill_zh.py pending --split 2
```

默认安装到 `~/.agents/skills/<name>/`（同名需 `--force`），并写入 `.skill-zh-origin`。

## 回滚与安全

```bash
python3 scripts/skill_zh.py revert --dry-run
python3 scripts/skill_zh.py revert                 # 用原始 frontmatter 备份逐字节回滚
python3 scripts/skill_zh.py revert --only diffdock
```

- 只改 `description` 一个键，其他 frontmatter 字段、缩进、正文一律不动。
- 改前备份到 `~/.skills-zh/backups/`，改后 YAML 校验，`apply` 幂等。
- 内置（bundled）根目录只读，不修改系统文件；要汉化先 `pull-bundled` 复制副本。
- 同名技能按 DSH 优先级去重（project > custom > user > bundled），只标注实际生效的那份。

## 为什么中文必须放在描述最前面

DSH 生成模型技能目录时**只看 `name` 和截断后的 `description`**（默认上限 500 字符），
不渲染 `whenToUse`、来源等字段。技能目录条目形如：

```text
- `diffdock`: 【分子对接 · 蛋白-配体结合位姿】DiffDock and DiffDock-L molecular docking. Use for ...
```

所以 `apply` 把 `【...】` 前置；英文原描述完整保留。`whenToUse` 写中文对路由无效。

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `doctor` | 环境自检（缺依赖也能运行） |
| `init [--split N]` | 首次初始化：扫描 + 生成待翻译清单 + 索引预览 |
| `scan` / `status` | 重新扫描 / 看覆盖率 |
| `pending [--split N]` | 导出待翻译清单（增量） |
| `check FILES [--strict]` | 只校验译文 JSON |
| `merge FILES...` | 合并译文到状态库 |
| `index` | 生成 `index.md` / `index.json` |
| `apply [--dry-run] [--only NAME]` | 给描述加中文标签（幂等） |
| `revert [--dry-run] [--force] [--only NAME]` | 逐字节回滚 |
| `lookup "中文查询"` | 中文检索 → 精确技能名 |
| `verify` | 校验标注/备份/索引一致性 |
| `ingest PATH` | 整理下载的技能包 |
| `pull-bundled` | 复制内置只读技能以便汉化 |

完整说明见 [`references/commands.md`](references/commands.md)。

## 目录结构

```text
skill-zh/                      # 仓库根目录 = 可直接放进 ~/.agents/skills/skill-zh
├── SKILL.md                   # DSH 技能入口（加载时读取）
├── README.md                  # 本文件
├── LICENSE
├── CHANGELOG.md
├── install.sh                 # 可选的本地安装脚本
├── scripts/skill_zh.py        # 全部命令（Python 3 + PyYAML）
├── references/
│   ├── translation-spec.md    # 译文规格（label/keywords/summary/category）
│   ├── translation-prompt.md  # 翻译子代理提示词模板
│   ├── glossary.md            # 统一术语表
│   └── commands.md            # 命令参考、状态库结构、排错
└── .github/workflows/release.yml  # 打 tag 自动构建 Release 包
```

## 依赖与平台

- Python 3.8+；macOS/Linux 用 `python3`，Windows 用 `python`。
- PyYAML：`python3 -m pip install pyyaml`（缺依赖时 `doctor` 会给出明确提示）。
- 仅使用标准库 + PyYAML，无网络上传代码；状态库是普通 JSON/Markdown，可跨平台迁移。
- 已在 macOS（Python 3.9.6 / 3.14）验证新用户从零安装到汉化全流程；Windows 未实测。

## FAQ

- **会不会改坏我的技能？** 只改 `description` 一行，改前备份、改后校验、支持逐字节回滚。
- **会把我机器上的技能列表传到哪里吗？** 不会。全部本地读写；只有当前会话的模型会看到
  你要求翻译的英文描述。
- **技能很多，要翻译多久？** 建议 2–4 个子代理并行，每批 ≤60 条；180 个技能约 10–20 分钟。
- **中文名可以改吗？** 可以，改译文后重新 `merge` + `apply` 即可（幂等）。

## License

[MIT](LICENSE) © 2026 清也
