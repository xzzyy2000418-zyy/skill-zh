# skill-zh 命令参考

脚本：`scripts/skill_zh.py`（相对技能目录；也可用绝对路径调用）
依赖：Python 3.8+、PyYAML。状态库：`~/.skills-zh/`（`SKILL_ZH_HOME` 可覆盖）。
版本：`python3 scripts/skill_zh.py doctor` 会打印版本与环境。

## 状态库结构

```
~/.skills-zh/
├── state.json            # 技能清单 + 原文哈希 + 中文翻译 + 标注状态（唯一事实来源）
├── index.md              # 给人看的中文目录（按 13 类分组）
├── index.json            # 给程序用的同一份目录
├── pending.json          # 最近一次导出的待翻译清单
├── translations/         # 翻译输入 pending-part-*.json 与产出 part-*.zh.json
├── backups/<name>.frontmatter   # 每个技能标注前的原始 frontmatter 备份（逐字节回滚用）
└── reports/verify-*.json # verify 报告
```

`state.json` 里每个技能记录：`path`、`root`、`rank`、`writable`、`original_description`、
`source_hash`、`original_block_sha`、`zh{label,keywords,summary,category,source_hash}`、
`apply{label,applied_at,block_sha,backup}`。状态库只存本机扫描结果与译文，**不含技能正文**，
可以整体备份/迁移/删除；删除后重新 `init` 即可。

## 命令总览

| 命令 | 作用 |
| --- | --- |
| `doctor` | 环境自检：Python/PyYAML/项目根/技能根目录/内置目录/状态库（缺依赖也能运行） |
| `init [--split N]` | 首次初始化：扫描本机技能 + 生成待翻译清单（默认拆 3 份）+ 索引预览 |
| `scan` | 重新扫描技能根目录，刷新状态（保留译文与标注记录） |
| `status` | 统计：总数/可写/已译/已标注/待译/需重译 |
| `pending [--split N] [--outdir DIR]` | 导出待翻译清单；只列没译或描述变了的 |
| `check FILES [--strict]` | 只校验译文 JSON（不写状态）；`--strict` 同时校验技能名存在 |
| `merge FILES...` | 校验并合并译文到状态库 |
| `index [--out PATH]` | 生成 `index.md` / `index.json` |
| `apply [--dry-run] [--only NAME]` | 给描述加 `【中文标签】`（幂等、写前备份、写后校验） |
| `revert [--dry-run] [--force] [--only NAME]` | 用备份逐字节回滚标签 |
| `lookup "中文查询" [--limit N] [--json]` | 中文检索，输出候选技能名与加载方式 |
| `verify` | 校验：YAML 可解析、标签/原文一致、备份存在、索引覆盖全部技能 |
| `ingest PATH [--target DIR] [--force] [--dry-run]` | 整理下载的目录/单个 SKILL.md/zip 并安装 |
| `pull-bundled [--target DIR] [--force]` | 把内置只读技能复制到用户目录（副本按 user 优先级覆盖内置） |

全局参数：`--cwd`（定位项目级技能根，默认当前目录）、`--extra-root`（追加根目录，可重复，
优先级在用户根之前）。

## 技能根目录与优先级（与 DSH 一致）

| rank | 来源 | 路径 |
| --- | --- | --- |
| 100 | project-dsh | `<projectRoot>/.dsh/skills` |
| 200 | project-agents | `<projectRoot>/.agents/skills` |
| 300 | custom | `DSH_CUSTOM_SKILL_DIRS` / `--extra-root` |
| 400 | user-dsh | `$DSH_HOME/skills`（默认 `~/.dsh/skills`） |
| 500 | user-agents | `$DSH_AGENTS_HOME/skills`（默认 `~/.agents/skills`） |
| 600 | bundled | 内置技能目录（`DSH_BUNDLED_SKILL_DIR` / `DSH_BUNDLED_OFFICE_SKILLS`，只读） |

项目根 = 最近的含 `.git` 的祖先目录；没有则用 `--cwd` 指定的目录。
同一个技能名出现在多个根时 rank 小者生效；`scan` 把其余副本记入 `shadowed`，不会重复标注。
技能目录内只认 `<name>/SKILL.md` 与 `<name>.md`（不递归）；`ingest` 才递归找包。

## 首次使用（任何一台新电脑）

```bash
cd ~/.agents/skills/skill-zh        # 换成你的实际安装目录
python3 scripts/skill_zh.py doctor     # 缺 PyYAML 会提示安装命令
python3 scripts/skill_zh.py init       # 扫描 + 生成 pending-part-*.json + 索引预览
# 按 references/translation-prompt.md 启动 2–3 个翻译子代理 → part-*.zh.json
python3 scripts/skill_zh.py check --strict ~/.skills-zh/translations/part-*.zh.json
python3 scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json
python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py apply --dry-run
python3 scripts/skill_zh.py apply
python3 scripts/skill_zh.py verify
```

## 日常使用

```bash
python3 scripts/skill_zh.py scan
python3 scripts/skill_zh.py index
python3 scripts/skill_zh.py status
# 中文查询 -> 技能名（再用 skill 工具加载精确英文名）
python3 scripts/skill_zh.py lookup "单细胞聚类"
```

## 新增技能后补翻译

```bash
python3 scripts/skill_zh.py scan        # 新技能进入待翻译
python3 scripts/skill_zh.py pending     # 只列没译/描述变了的
# 翻译 → check → merge → index → apply → verify（apply 会替换旧标签，幂等）
```

`pending --split N` 会先清掉上一轮的 `pending-part-*.json` 再写新分片，避免旧条目
误导翻译队员；`part-*.zh.json` 产出不会被删。

作者更新了描述时，`pending` 会标记「需重译」；重译并 merge 后 `apply` 自动更新标签。

## 整理下载的技能包

```bash
python3 scripts/skill_zh.py ingest ~/Downloads/awesome-skill.zip --dry-run
python3 scripts/skill_zh.py ingest ~/Downloads/awesome-skill.zip
python3 scripts/skill_zh.py scan
```

`ingest` 递归找 `SKILL.md`，校验 frontmatter（name 必须 kebab-case、description 非空），
复制到 `~/.agents/skills/<name>/` 并写 `.skill-zh-origin`。同名默认不覆盖，需 `--force`；
也支持直接传单个 `SKILL.md` 或技能目录。有跳过/冲突时退出码为 1（便于脚本判断）。
安装后 DSH 会自动发现（文件监听），无需重启。

## 内置技能（只读）

应用内置的技能目录不修改系统文件：默认只进索引、不加标签。需要汉化时：

```bash
python3 scripts/skill_zh.py pull-bundled            # 复制到 ~/.agents/skills 后再汉化
python3 scripts/skill_zh.py pull-bundled --force    # app 升级后重新同步副本
python3 scripts/skill_zh.py scan
```

## 回滚

```bash
python3 scripts/skill_zh.py revert --dry-run
python3 scripts/skill_zh.py revert                      # 全部回滚
python3 scripts/skill_zh.py revert --only diffdock      # 单个
python3 scripts/skill_zh.py revert --force              # 标注后文件又被改过时强制回滚
```

回滚优先用 `backups/<name>.frontmatter` 还原整段 frontmatter，保证与标注前逐字节一致。

## 译文 JSON 格式

```json
{
  "entries": [
    {
      "name": "diffdock",
      "zh": {
        "label": "分子对接 · 蛋白-配体结合位姿",
        "keywords": ["分子对接", "蛋白配体", "结合位姿", "虚拟筛选"],
        "summary": "用扩散模型预测小分子在蛋白口袋中的结合位姿，支持批量对接与虚拟筛选。",
        "category": "分子与药物发现"
      }
    }
  ]
}
```

`merge` 兼容「列表」或「含 entries 的对象」；传目录时只读 `*.zh.json`（找不到时读
非 `pending-*` 的 `*.json`），避免把待翻译输入当译文校验。`check` 校验长度/分类/重复/技能名存在。

## 为什么中文必须放在描述最前面

DSH 生成模型技能目录时**只看 `name` 和截断后的 `description`**（默认上限 500 字符），
不渲染 `whenToUse`、来源等字段；目录条目形如：

```
- `diffdock`: 【分子对接 · 蛋白-配体结合位姿】DiffDock and DiffDock-L molecular docking. Use for ...
```

所以 `apply` 把 `【...】` 前置，英文原描述完整保留。`apply` 只替换 `description`
一个键（多行 `>`/`|` 折叠值会折叠为单行双引号标量，语义不变），其他字段与正文不动；
`whenToUse` 写中文对路由无效。

## 平台与依赖

- Python 3.8+；macOS/Linux 用 `python3`，Windows 用 `python`（命令同理）。
- 缺少 PyYAML 时先安装：`python3 -m pip install pyyaml`（Windows：`python -m pip install pyyaml`）。
- `doctor` 不依赖 PyYAML 也能运行，用于排查安装问题。
- 脚本只用标准库 + PyYAML，状态库是普通 JSON/Markdown，可跨平台迁移。

## 常见问题

- **状态库想换位置**：`export SKILL_ZH_HOME=/path/to/store`。
- **技能根目录识别不对**：`doctor` 会打印实际根目录；项目级根按最近 `.git` 祖先判定，
  否则用 `--cwd`；也可用 `--extra-root` 追加。
- **改完为什么不生效**：DSH 监视技能根目录并自动刷新，无需重启；若界面未变，
  重新 `scan` + 刷新会话即可。
- **描述被截断**：目录只展示描述前约 500 字符，所以中文标签必须前置；长描述尾部本来
  就会在目录里被裁掉，不影响技能正文。
- **不想改文件**：只跑 `scan` + `index`，或 `apply --dry-run` 预览。
- **恢复出厂**：`revert` 还原所有被改写的描述；`pull-bundled` 复制出来的副本可手动删除。
- **分享给别人**：打包整个 `skill-zh/` 目录（含 README）即可；对方的状态库从零开始，
  不携带你的译文与技能清单。
