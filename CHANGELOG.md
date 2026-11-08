# Changelog

## [1.0.0] - 2026-11-08

首个公开版本。

### Added

- `doctor`：环境自检（Python/PyYAML/项目根/技能根目录/内置目录/状态库），缺依赖也能运行。
- `init`：首次初始化，扫描本机技能、生成待翻译清单（可拆分并行）、生成中文索引预览。
- `scan` / `status`：技能发现与覆盖率统计；按 DSH 的 project/custom/user/bundled 优先级去重。
- `pending` / `check` / `merge`：译文导出、校验、合并；增量只翻译未译或描述变了的技能。
- `index`：生成中文技能目录（13 类分组，含中文名/一句话说明/关键词/状态）。
- `apply`：把 `【中文名 · 关键词】` 写到 `description` 最前面；幂等、写前备份、写后校验。
- `revert`：用原始 frontmatter 备份逐字节回滚；支持 `--only` / `--force` / `--dry-run`。
- `lookup`：中文口语查询 → 精确英文技能名（供 `skill` 工具加载）。
- `verify`：YAML 可解析、标签/原文一致、备份存在、索引覆盖全部技能。
- `ingest`：整理下载的目录/单个 `SKILL.md`/zip 并安装到用户技能根目录。
- `pull-bundled`：把内置只读技能复制到用户目录后再汉化。
- 翻译配套：`references/translation-spec.md`（字段与质量规范）、`glossary.md`（术语表）、
  `translation-prompt.md`（可直接粘贴给翻译子代理的提示词模板）。
- GitHub Actions：打 `v*` tag 自动构建 `skill-zh-<version>.zip` 并创建 Release。

### Notes

- 状态库默认 `~/.skills-zh/`，可用 `SKILL_ZH_HOME` 覆盖；不随仓库分发。
- 已在 macOS（Python 3.9.6 / 3.14）从零安装并跑通首次汉化闭环；Windows 未实测。
