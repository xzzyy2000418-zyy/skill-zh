---
name: skill-zh
description: "【技能汉化管家｜中文技能目录】可分享的通用技能：安装后扫描本机已配置目录中的 skill，生成中文名/关键词/一句话说明写回描述，产出中文索引，并支持「中文口语查询 → 精确英文技能名」。不内置任何人的技能清单，首次运行按你的机器现生成；新增或下载的 skill 可增量汉化。当用户说“把技能汉化/整理技能目录/用中文调用技能/我有哪些技能/这个技能中文叫什么/把下载的 skill 装上/更新技能中文目录/给技能加中文名”时使用。"
---

# 技能汉化管家（skill-zh）

一个**可以分享给别人用**的技能：它不携带任何现成技能清单，而是在运行时扫描
本机已配置目录中的 skill（默认包括 `~/.agents/skills`、`~/.dsh/skills` 和
项目 `.agents/skills` 等；其他本地 Agent 的目录可用 `--extra-root` 指定），为每个技能生成中文名/关键词/一句话说明，把中文标签写回
技能描述，产出中文索引，并支持中文查询定位精确技能名。

- 状态库：`~/.skills-zh/`（可用 `SKILL_ZH_HOME` 覆盖）——每个用户各自一份，互不影响。
- 工具：`scripts/skill_zh.py`（本技能目录内）。依赖 Python 3.8+ 与 PyYAML。
  下文命令里的 `scripts/skill_zh.py` 都相对**本技能目录**：先 `cd` 到技能目录再执行，
  或换成绝对路径（加载技能时会给出 base directory）。
- 版本：1.1.0（`python3 scripts/skill_zh.py doctor` 可自检环境）。

其他宿主可将本技能安装到自己的技能目录。其待汉化技能若位于自定义目录，
在每次 `init` 或 `scan` 前指定相同的 `--extra-root <目录>`。Codex 桌面插件的安装入口
见 [README.md](README.md#codex-桌面插件安装与预览)。

## 首次使用（在一台新电脑上）

```bash
python3 scripts/skill_zh.py doctor   # 自检：Python/PyYAML/技能根目录
python3 scripts/skill_zh.py init     # 扫描本机技能 + 生成待翻译清单 + 中文索引预览
```

`init` 会打印「待翻译 N 个」并生成 `~/.skills-zh/translations/pending-part-*.json`。
接着把英文描述翻成中文（**由当前会话的模型完成，因此任何语言的技能都能处理**）：

1. 按 `references/translation-prompt.md` 启动 **2–3 个翻译子代理**，每个子代理只负责
   一份 `pending-part-<x>.json`，产出 `part-<x>.zh.json`，并用
   `python3 scripts/skill_zh.py check --strict <file>` 自检到 0 问题。
2. 合并、重建索引、先预览再加标签、验收：

```bash
python3 scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json
python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py apply --dry-run    # 先看会改哪些描述
python3 scripts/skill_zh.py apply              # 写入【中文标签】
python3 scripts/skill_zh.py verify             # 0 问题才算完成
```

## 日常使用

```bash
python3 scripts/skill_zh.py status                     # 覆盖率
python3 scripts/skill_zh.py scan && python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py lookup "帮我把论文转成PPT"   # 中文 -> 精确技能名
```

- 用户问「有哪些技能 / 这个技能中文叫什么」→ 直接读 `~/.skills-zh/index.md` 回答。
- 用户用中文提需求 → 模型会按中文标签直接命中技能；也可先 `lookup`，再用 `skill`
  工具加载**精确英文技能名**（不要在 `skill` 参数里写中文）。
- 新增/删除技能后：`scan` → `pending`（只列没译或描述变了的）→ 翻译 → `merge` →
  `index` → `apply`（幂等，会替换旧标签）→ `verify`。

## 整理别人给的技能包

```bash
python3 scripts/skill_zh.py ingest ~/Downloads/某技能包.zip   # 支持目录 / 单个 SKILL.md
python3 scripts/skill_zh.py ingest ./some-skill-dir --dry-run
python3 scripts/skill_zh.py scan && python3 scripts/skill_zh.py pending --split 2
```

`ingest` 默认安装到 `~/.agents/skills/<name>/`（同名需 `--force`），写入
`.skill-zh-origin` 记录来源；装好后 DSH 会自动发现，无需重启。

## 回滚与安全

```bash
python3 scripts/skill_zh.py revert --dry-run
python3 scripts/skill_zh.py revert                 # 用原始 frontmatter 备份逐字节回滚
python3 scripts/skill_zh.py revert --only diffdock
```

- 只改 `description` 一个键，其他 frontmatter 字段、缩进、正文一律不动；
  改前备份到 `~/.skills-zh/backups/`，改后 YAML 校验，`apply` 幂等。
- 内置（bundled）根目录只读，不修改系统文件；要汉化先 `pull-bundled` 复制到用户目录
  （副本按 user 优先级覆盖内置版本；app 升级后可 `pull-bundled --force` 重新同步）。
- 同名技能按 DSH 优先级去重（project > custom > user > bundled），只标注实际生效的那份。

## 关键事实（决定实现方式）

- DSH 技能目录**只读 `name` + 描述前 500 字符**，`whenToUse` 不参与路由——所以中文标签
  必须放在描述最前面（`apply` 就是做这件事，标签 ≤36 字）。
- 目录条目形如 `- \`diffdock\`: 【分子对接 · 蛋白-配体结合位姿】DiffDock ...`，因此英文原
  描述完整保留，中文可命中，英文路由也不受影响。
- 一批技能很多时，翻译要分批并行（每批 ≤60 条），每人写独立文件，最后统一 `merge`。

## 文件结构

```
skill-zh/
├── SKILL.md                     # 本文件（DSH 加载入口）
├── README.md                    # 分享/安装说明
├── scripts/skill_zh.py          # 全部命令
└── references/
    ├── translation-spec.md      # 译文规格（label/keywords/summary/category）
    ├── translation-prompt.md    # 可直接粘贴给翻译子代理的任务提示词
    ├── glossary.md              # 统一术语表
    └── commands.md              # 命令参考、状态库结构、排错
```

详细命令与故障排查见 `references/commands.md`。
