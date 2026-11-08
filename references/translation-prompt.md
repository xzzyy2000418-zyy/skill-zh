# 翻译子代理任务提示词（模板）

在「首次汉化」或「新增技能后补翻译」阶段，把下面的模板填好发给 2–3 个各自独立的
子代理/队员。**每个子代理只负责一份 `pending-part-<x>.json`，只写自己的
`part-<x>.zh.json`**，互不重叠，最后由主代理统一 `merge`。

---

## 可直接粘贴的提示词（替换 `{...}` 占位符）

```text
你是「技能汉化」翻译队员。任务：把 {COUNT} 个英文技能描述译成中文标签/检索词/
一句话说明/分类，供 DSH 中文技能目录使用。

必读文件（先全部读完再动笔）：
1. {SKILL_DIR}/references/translation-spec.md   —— 字段规则、长度上限、分类枚举、示例、质量红线
2. {SKILL_DIR}/references/glossary.md           —— 统一术语
3. {PART_FILE}                                  —— {COUNT} 条待翻译条目（name + original_description）

输出：新建 {OUT_FILE}，结构：
{"entries": [{"name": "技能名", "zh": {"label": "...", "keywords": ["...", "..."],
  "summary": "...", "category": "..."}}]}
只输出这 {COUNT} 个技能，只包含 name 和 zh 两个键。
label ≤36 字（不含【】）、keywords 2–8 个且每个 ≤16 字、summary ≤90 字、
category 必须从 13 类枚举里原样选。

自检（必须跑到 0 问题）：
python3 {SKILL_DIR}/scripts/skill_zh.py check --strict {OUT_FILE}

纪律：
- 只写 {OUT_FILE} 这一个文件；不要改 pending 输入、state.json、索引或其他人的文件；
  不要运行 scan / merge / apply / revert。
- 中文简体；专有名词/软件/文件格式保留英文；不要编造英文描述里没有的功能。
- {COUNT} 条要全部完成。若上下文紧张，可先写临时文件分批，但最终必须产出完整且
  通过 check --strict 的 {OUT_FILE}。
- 完成后回复：条目数、check --strict 结果、覆盖的技能名（前 5 + 总数）。
```

## 占位符怎么填

```text
SKILL_DIR  = 技能所在目录，例如 ~/.agents/skills/skill-zh
PART_FILE  = ~/.skills-zh/translations/pending-part-a.json
OUT_FILE   = ~/.skills-zh/translations/part-a.zh.json
COUNT      = 该 part 文件里的条目数（看 JSON 的 count 字段）
```

`init` / `pending --split 3` 会打印实际路径与每份的大小，直接复制即可。

## 分批建议

- 每批 **≤ 60 条**；技能很多（>120）时拆 3–4 份并行。
- 全量翻译通常 10–20 分钟；子代理之间不要共享文件。
- 如果某个技能描述特别长或领域很偏，按英文原文直译，不要扩展功能。

## 主代理合并时的检查

```bash
# 1) 逐份自检（子代理应已完成；主代理再抽查一遍）
python3 {SKILL_DIR}/scripts/skill_zh.py check --strict ~/.skills-zh/translations/part-*.zh.json

# 2) 合并（校验不通过会列出问题，不写坏状态）
python3 {SKILL_DIR}/scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json

# 3) 重建索引 / 预览标注 / 写入 / 验收
python3 {SKILL_DIR}/scripts/skill_zh.py index
python3 {SKILL_DIR}/scripts/skill_zh.py apply --dry-run
python3 {SKILL_DIR}/scripts/skill_zh.py apply
python3 {SKILL_DIR}/scripts/skill_zh.py verify
```

## 常见问题

- **子代理把英文原文抄进 summary**：要求重做该条，`summary` 必须是中文一句话。
- **label 重复或太泛**：让同一领域内的技能标签互相可区分（如 `Word 文档 · 读写与制作`
  与 `office-docx · 读写与校验`）。
- **keywords 只是把 label 拆词**：要求补用户口语说法、同义词、对象名、常见缩写。
- **领域不熟**：严格照英文描述直译，宁可不加细节，也不要猜测扩展。
