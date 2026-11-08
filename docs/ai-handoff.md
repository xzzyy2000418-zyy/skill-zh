# 把本项目的后续任务交给 GPT / Codex 操作

仓库地址：<https://github.com/xzzyy2000418-zyy/skill-zh>

这个项目已经按"AI 可接手"整理好：仓库根目录有 `AGENTS.md`（项目规则、验证命令、发布流程），
CI 会自动检查，Release 由 tag 自动构建。下面按使用方式分三种情况。

## 方式一：OpenAI Codex（推荐，"在 GPT 里做任务 + 直接改仓库"）

适合：让 GPT 读仓库、改代码、跑测试、开 PR。

1. 打开 Codex（ChatGPT 里的 Codex 入口，或 Codex CLI/IDE 插件），用你的 ChatGPT 账号登录。
2. 连接 GitHub：安装/授权 OpenAI 的 GitHub 应用，只勾选 `xzzyy2000418-zyy/skill-zh`
   （仓库是 Public，读权限即可；要让它直接推分支/开 PR 需要写权限）。
3. 新建一个 Task/Environment，选择这个仓库和 `main` 分支。
4. 在任务描述里写清目标和验收标准，例如：

   ```text
   目标：给 skill-zh 增加一个 `stats` 子命令，输出每个分类的技能数量。
   约束：遵守仓库根目录 AGENTS.md；只用标准库；不改变现有命令行为。
   验收：CI 通过；新增 fixture 覆盖；README/commands.md 同步更新。
   ```

5. Codex 会在云端克隆、修改、运行命令，然后给出 diff/PR。你 review 后合并，
   CI 绿了再按 AGENTS.md 的发布流程打 tag。

> 注意：不要把 GitHub token 贴进对话。权限交给 GitHub 集成管理。

## 方式二：ChatGPT（网页/项目）——不改仓库，只出方案和补丁

适合：讨论设计、写文案、生成 patch、翻译技能描述。

1. 新建一个 ChatGPT Project，名字例如 `skill-zh 开发`。
2. 上传仓库关键文件：`AGENTS.md`、`README.md`、`SKILL.md`、`scripts/skill_zh.py`、
   `references/*.md`（或直接上传 GitHub 下载的 zip）。
3. 在 Project 的自定义指令里写：

   ```text
   你在维护 skill-zh 仓库。任何代码改动都必须遵守 AGENTS.md 中的约束与验证命令。
   给出改动时请输出 unified diff（git apply 可直接应用），并说明如何验证。
   ```

4. 让它产出 patch 后，在本地执行：

   ```bash
   cd /Users/qingye/Documents/deepseek-harness/default-workspace/skill-zh-github
   git apply /path/to/change.patch
   python -m py_compile scripts/skill_zh.py
   git diff && git add -A && git commit -m "feat: ..."
   ```

5. 如果 ChatGPT 开启了 GitHub 连接器，也可以直接在对话里让它读取仓库文件，但**不要让
   网页版 GPT 尝试 push**（它没有可靠的写权限/终端），推送到本地仓库或 Codex 完成。

## 方式三：只用 GPT 做"翻译"，代码流程仍在本机

`skill-zh` 的翻译本来就是由调用方模型完成的，用 GPT 完全可行：

1. 本机运行：

   ```bash
   cd ~/.agents/skills/skill-zh
   python3 scripts/skill_zh.py init --split 2    # 生成 pending-part-a/b.json
   ```

2. 把 `references/translation-spec.md` + 一份 `pending-part-*.json` 贴给 GPT，
   要求它只返回 `{"entries":[{"name","zh"}]}` 的 JSON（每批 20–30 条，避免超长）。
3. 把返回内容保存为 `~/.skills-zh/translations/part-a.zh.json`，然后：

   ```bash
   python3 scripts/skill_zh.py check --strict ~/.skills-zh/translations/part-*.zh.json
   python3 scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json
   python3 scripts/skill_zh.py index
   python3 scripts/skill_zh.py apply --dry-run && python3 scripts/skill_zh.py apply
   python3 scripts/skill_zh.py verify
   ```

## 交接时必须告诉 GPT 的信息

- 仓库：`https://github.com/xzzyy2000418-zyy/skill-zh`
- 先读 `AGENTS.md`；验证命令与 CI 等价；发布走 tag + `release.yml`。
- 约束：只改 `description`、幂等、逐字节回滚、不提交用户状态库。
- 验收标准：`python -m py_compile` + `--help` + fixture 回滚测试 + CI 绿。

## 建议的仓库设置

- 开启 GitHub Issues（收集需求）与 Discussions（问答）。
- 用分支 + PR（Codex 默认就是 PR 流），保护 `main` 需要 CI 通过再合并。
- 发布新版本时更新 `TOOL_VERSION`、`CHANGELOG.md`，再打 `vX.Y.Z` tag。
