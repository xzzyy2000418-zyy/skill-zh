# AGENTS.md — 给 AI 编码代理的项目说明

本仓库就是 skill-zh 技能本体（仓库根目录 = 可直接放进 `~/.agents/skills/skill-zh` 的技能目录）。
任何 AI 编码代理（Codex / ChatGPT / Copilot / Cursor 等）在改代码前请先读本文件。

## 项目是什么

`skill-zh` 是给 DeepSeek Harness（DSH）用的技能汉化工具：扫描本机已安装/下载的 skill，
为每个技能生成中文名、关键词、一句话说明，把中文标签写回 `SKILL.md` 的 `description`，
生成中文索引，并支持中文查询定位精确技能名。所有数据留在用户本机 `~/.skills-zh/`。

## 目录结构

```text
SKILL.md                     # DSH 技能入口（frontmatter: name + description）
README.md                    # 面向用户的说明与安装方式
scripts/skill_zh.py          # 唯一实现文件（全部子命令）
references/translation-spec.md    # 译文规格（label/keywords/summary/category 限制）
references/translation-prompt.md  # 翻译子代理提示词模板
references/glossary.md            # 统一术语表
references/commands.md            # 命令参考、状态库结构、排错
.github/workflows/ci.yml          # 语法检查 + 冒烟测试
.github/workflows/release.yml     # 打 v* tag 自动构建 zip 并发布 Release
```

## 环境与依赖

- Python 3.8+（CI 覆盖 3.9 与 3.12），只依赖 PyYAML。
- 安装依赖：`python3 -m pip install pyyaml`
- 无需网络（除 GitHub Actions / 发布外）。

## 修改前必须知道的约束

1. **只改一个键**：`apply` 只允许修改 `SKILL.md` 的 `description` 字段，其他 frontmatter
   字段、缩进、正文一律不动；写前备份、写后校验。
2. **幂等 + 可回滚**：`apply` 重复执行不得叠加标签；`revert` 必须与标注前逐字节一致
   （用 `backups/<name>.frontmatter` 还原整段 frontmatter）。
3. **不碰用户状态**：仓库里不得出现 `~/.skills-zh/` 内容（state/译文/备份/索引/报告），
   也不要在测试中写用户真实技能目录。
4. **翻译规范**：任何改动翻译字段（label/keywords/summary/category）的代码都要遵守
   `references/translation-spec.md` 的长度与分类枚举限制。
5. **兼容性**：脚本需在 Python 3.8+ 可运行；路径处理用 `pathlib`，不要写死 `/Users/...`。
6. **README 链接**：仓库地址为 `https://github.com/xzzyy2000418-zyy/skill-zh`；
   除非仓库迁移，不要改所有者/仓库名。

## 必须运行的验证（与 CI 等价）

```bash
python -m py_compile scripts/skill_zh.py
python scripts/skill_zh.py --help
```

涉及 `scan` / `pending` / `merge` / `index` / `apply` / `revert` / `verify` 的改动，
必须再做一次 fixture 回环（参考 `.github/workflows/ci.yml` 的 smoke test）：

```bash
TMP=$(mktemp -d)
export HOME="$TMP" DSH_HOME="$TMP/.dsh" DSH_AGENTS_HOME="$TMP/.agents" \
       DSH_BUNDLED_SKILL_DIR="$TMP/empty-bundled"
mkdir -p "$DSH_AGENTS_HOME/skills" "$DSH_BUNDLED_SKILL_DIR" "$TMP/skills/demo-skill"
printf -- '---\nname: demo-skill\ndescription: Demo.\n---\n# Demo\n' > "$TMP/skills/demo-skill/SKILL.md"
python scripts/skill_zh.py --extra-root "$TMP/skills" init --split 1
# 造一条译文 → check --strict → merge → index → apply → verify → revert
# revert 后 demo-skill/SKILL.md 必须与最初写入内容逐字节一致
```

## 发布流程

1. 修改 `scripts/skill_zh.py` 时同步更新 `TOOL_VERSION` 与 `CHANGELOG.md`。
2. 本地验证通过后：`git commit` → `git tag -a vX.Y.Z -m "skill-zh X.Y.Z"`。
3. `git push origin main vX.Y.Z`；`release.yml` 会自动构建 `skill-zh-X.Y.Z.zip` 并发布 Release。
4. 打 tag 前请确认 CI 在 `main` 上是绿的。

## 提交信息风格

`feat: ...` / `fix: ...` / `docs: ...` / `ci: ...`，一行说清改了什么。

## 特别提醒

- 本技能的所有行为都要在**用户本机**可回滚；不要设计"删除/覆盖用户原文件"的路径。
- 内置（bundled）技能根目录只读，不得修改系统文件。
- 翻译工作由调用方模型完成，本仓库只提供流程、校验和模板。
