# 技能汉化管家 · skill-zh

> 本机技能汉化工具。为已安装的技能补充中文名、关键词和一句话说明，并生成中文技能目录。
> 支持两种入口：适用于兼容 `SKILL.md` 的本地 Agent 的通用技能，以及可浏览目录的 Codex 桌面插件。

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

## 通用技能安装

需要支持加载 `SKILL.md`、读写本地文件和运行脚本的 Agent，以及 Python 3.8+ 和
[PyYAML](https://pypi.org/project/PyYAML/)。默认用 `~/.agents/skills`，其他宿主可将
`skill-zh` 放到它自己的技能目录，或运行 `./install.sh <宿主的技能根目录>`。

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

安装后在 Agent 的技能列表里查找 `skill-zh`，或直接说「把本机技能整理成中文目录」。
扫描默认覆盖 DSH 和共享的 `.agents/skills`。宿主使用其他目录时，可用
`--extra-root <技能根目录>` 加到 `init` 或 `scan` 前面。是否自动加载、何时重载由宿主决定。

## Codex 桌面插件安装与预览

1. 下载并解压同一份 Release 包，或克隆仓库。在 Codex 中把含 `.agents/plugins/marketplace.json` 的文件夹打开为本地项目。
2. 进入「插件」，选择来源「技能汉化管家」，安装同名插件。若来源没有出现，重启桌面端。也可以一次性运行 `codex plugin marketplace add /path/to/skill-zh`，让其他本地项目也能发现这个来源。
3. 安装后，在支持插件全局入口的桌面端，从侧栏打开「中文技能目录」。也可以在插件详情页点击「打开技能汉化管家的中文技能目录预览」示例请求，按桌面端提示在本地聊天打开面板。

目录支持中文名、英文 ID、关键词搜索及分类筛选。点击「刷新目录」会重新读取本机索引和技能说明。
插件使用已有的 `~/.skills-zh/index.json`，并在有 PyYAML 时补充扫描常见的本机技能目录。
首次打开时，已带中文标签的技能会显示该标签，其余会显示原说明。生成中文译文后，再刷新即可查看。
Codex 插件缓存中的技能只有在已生成的索引里收录时才会出现在目录。安装桌面插件不要求先安装通用技能。

预览需要桌面端能运行 `python3`。在新机器上直接扫描技能前，请先安装 PyYAML。如果客户端只返回文本，使用插件示例请求后可让它导出离线 HTML。
在 Windows 上，如果 Python 命令是 `python`，安装前将本地包 `mcp.json` 中的 `command` 改为 `python`。

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
├── SKILL.md                   # 通用技能入口
├── .agents/plugins/marketplace.json # Codex 本地插件来源
├── plugin.json               # Codex 插件详情
├── mcp.json                  # 桌面目录服务配置
├── preview/catalog.html     # 可搜索的目录面板
├── skills/skill-zh-preview/  # Codex 目录入口
├── README.md                  # 本文件
├── LICENSE
├── CHANGELOG.md
├── install.sh                 # 可选的本地安装脚本
├── scripts/                   # 通用汉化命令与桌面预览服务
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
