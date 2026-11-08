# 技能汉化翻译规范（skill-zh）

这份规范给「翻译队员」使用：把每个技能的英文 `description` 压缩成中文标签、检索词、
一句话说明和分类，供 `skill_zh.py merge` 写入翻译库，并最终标注到 SKILL.md 的
描述前面，让中文提问能精准命中技能。

## 1. 输入与输出

- 输入：`~/.skills-zh/translations/pending-part-<x>.json`
  ```json
  {"count": 60, "entries": [
    {"name": "diffdock", "path": "...", "original_description": "DiffDock and DiffDock-L ...", "zh": {"label": "", "keywords": [], "summary": "", "category": ""}}
  ]}
  ```
- 输出：`~/.skills-zh/translations/part-<x>.zh.json`（新建文件，不要改输入文件）
  ```json
  {"entries": [
    {"name": "diffdock",
     "zh": {"label": "分子对接 · 蛋白-配体结合位姿",
            "keywords": ["分子对接", "蛋白配体", "结合位姿", "虚拟筛选", "DiffDock"],
            "summary": "用扩散模型预测小分子在蛋白口袋中的结合位姿，支持批量对接与虚拟筛选。",
            "category": "分子与药物发现"}}
  ]}
  ```
- 自检（必须做，直到 0 问题；`<技能目录>` 指本技能安装目录，用户级通常是
  `~/.agents/skills/skill-zh`）：
  ```bash
  python3 <技能目录>/scripts/skill_zh.py check --strict ~/.skills-zh/translations/part-<x>.zh.json
  ```
- 只允许写自己的 `part-<x>.zh.json`。不要改 `pending-*.json`、`state.json`、索引或其他队员的文件。

## 2. 字段规则

| 字段 | 规则 |
| --- | --- |
| `label` | 中文名/标签，**≤ 36 字**，不要带 `【】`。格式建议「领域 · 用途短语」，例如 `分子对接 · 蛋白-配体结合位姿`。同领域技能必须能互相区分。 |
| `keywords` | **2–8 个**中文检索词，每个 **≤ 16 字**。覆盖用户口语、同义词、对象名、常见缩写的中文说法（如「做PPT」「幻灯片」「演示文稿」）。不要只是把 label 拆成词。 |
| `summary` | 一句话，**≤ 90 字**：做什么 + 什么时候用。忠实原文，不夸张、不加功能。 |
| `category` | 必须从下面 13 类中原样选一个。 |

## 3. 分类枚举（只能选这 13 个）

1. `学术写作与投稿`
2. `文献检索与综述`
3. `数据统计与分析`
4. `生物信息与组学`
5. `分子与药物发现`
6. `结构与分子模拟`
7. `医学与临床`
8. `科研绘图与幻灯片`
9. `文档与办公`
10. `实验室与仪器自动化`
11. `云平台与工程化`
12. `物理化学与数学计算`
13. `综合工具与效率`

判断不准时的默认顺序：先看领域（医学/生物/化学/物理），再看交付物（文档/图/PPT/代码），
最后看平台（云/机器人/仪器）；都不明显就放 `综合工具与效率`。

## 4. 风格与术语

- 专有名词、软件名、模型名、文件格式、API 保留英文：`DiffDock`、`PyDESeq2`、`AlphaFold`、
  `SPR`、`BAM`、`FASTQ`、`SDF`、`SMILES`、`README`、`Docker`。
- 通用概念用中文：分子对接、差异表达、单细胞、虚拟筛选、读数、质控、剂量、通路富集。
- 中文标点（、，。：·），动宾或名词短语，不用「本技能」「该技能」「可以…」这类空话。
- 不要补充英文描述里没有的功能；原文有明确的「Not for…」边界时，`summary` 里保留该边界。
- 面向「用户会怎么说」选关键词，而不是「作者怎么命名」。

## 5. 示例（真实技能）

```json
{"name": "diffdock",
 "zh": {"label": "分子对接 · 蛋白-配体结合位姿",
        "keywords": ["分子对接", "蛋白配体", "结合位姿", "虚拟筛选", "DiffDock"],
        "summary": "用扩散模型预测小分子在蛋白口袋中的结合位姿，支持批量对接与虚拟筛选，不做结合亲和力预测。",
        "category": "分子与药物发现"}}

{"name": "scanpy",
 "zh": {"label": "单细胞分析 · 标准流程",
        "keywords": ["单细胞", "单细胞RNA", "单细胞测序", "聚类", "UMAP", "差异表达"],
        "summary": "单细胞 RNA-seq 标准分析：质控、归一化、降维、聚类、差异表达与可视化。",
        "category": "生物信息与组学"}}

{"name": "docx",
 "zh": {"label": "Word 文档 · 读写与制作",
        "keywords": ["Word", "docx", "写文档", "合同", "报告排版", "文档编辑"],
        "summary": "创建、读取、编辑和校验 Word 文档（.docx/.dotx），支持目录、页眉页脚、查找替换与模板。",
        "category": "文档与办公"}}

{"name": "nextflow",
 "zh": {"label": "Nextflow 流程 · 编写与运行",
        "keywords": ["Nextflow", "nf-core", "流程编排", "生信流水线", "HPC", "容器"],
        "summary": "编写、运行和调试 Nextflow/nf-core 数据流水线，含执行器、容器与调度器配置。",
        "category": "云平台与工程化"}}
```

## 6. 质量红线

- 长度超限、分类不在枚举、关键字数量不对 → `check --strict` 会报错，必须修到通过。
- `label` 里出现 `【】`、换行、英文长句 → 不合格。
- 把英文原文整句塞进 `summary` → 不合格。
- 对不熟悉领域的技能：严格按英文描述直译，不要猜测扩展功能。
