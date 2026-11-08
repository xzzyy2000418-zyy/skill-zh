#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_zh.py — 技能汉化管家 / skill-zh toolkit.

扫描本机 DSH 会加载的全部技能根目录，维护一份「英文技能 -> 中文名/关键词」的
翻译库，给每个 SKILL.md 的描述前面加上中文标签（【中文名 · 关键词】），生成
中文索引，并提供中文查询 -> 精确技能名的检索。

设计原则
- 不破坏原文件：只改 description 一行，写前备份、写后校验，支持精确回滚。
- 幂等：重复 scan / apply / revert 不会叠加标签。
- 状态外置：翻译库、索引、备份都放在 ~/.skills-zh（不在技能扫描根目录内，
  避免被当成技能加载）。可用环境变量 SKILL_ZH_HOME 覆盖。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 允许 doctor/check 在缺依赖时仍可运行
    yaml = None


def require_yaml() -> None:
    if yaml is None:
        die(
            "缺少 PyYAML。请先安装：python3 -m pip install pyyaml\n"
            "（Windows 用 python -m pip install pyyaml；安装后重新运行即可）"
        )


# ---------------------------------------------------------------------------
# 常量与路径
# ---------------------------------------------------------------------------

SKILL_ZH_HOME = Path(
    os.environ.get("SKILL_ZH_HOME", str(Path.home() / ".skills-zh"))
).expanduser()
STATE_FILE = SKILL_ZH_HOME / "state.json"
INDEX_MD = SKILL_ZH_HOME / "index.md"
INDEX_JSON = SKILL_ZH_HOME / "index.json"
PENDING_FILE = SKILL_ZH_HOME / "pending.json"
TRANS_DIR = SKILL_ZH_HOME / "translations"
BACKUP_DIR = SKILL_ZH_HOME / "backups"
REPORT_DIR = SKILL_ZH_HOME / "reports"

STATE_VERSION = 1
TOOL_VERSION = "1.0.0"

LABEL_OPEN = "【"
LABEL_CLOSE = "】"
LABEL_RE = re.compile(r"^【([^】]{1,80})】")

# 中文分类枚举（翻译队员只能从这里选；索引按这个顺序分组）
CATEGORIES = [
    "学术写作与投稿",
    "文献检索与综述",
    "数据统计与分析",
    "生物信息与组学",
    "分子与药物发现",
    "结构与分子模拟",
    "医学与临床",
    "科研绘图与幻灯片",
    "文档与办公",
    "实验室与仪器自动化",
    "云平台与工程化",
    "物理化学与数学计算",
    "综合工具与效率",
]

# 这些长度限制同时被 merge 校验和 verify 使用
LIMITS = {
    "label": 36,        # 中文名/标签内部文本（不含【】）
    "summary": 90,      # 一句话中文说明
    "keyword": 16,      # 单个中文关键词
    "keywords_min": 2,
    "keywords_max": 8,
}

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
DESC_KEY_RE = re.compile(r"^description[ \t]*:[ \t]*(.*)$")
BLOCK_IND_RE = re.compile(r"^(?:[>|][+-]?[0-9]?)(?:[ \t]+#.*)?$")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def die(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


def ensure_dirs() -> None:
    for d in (SKILL_ZH_HOME, TRANS_DIR, BACKUP_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def find_project_root(start: Path) -> Path:
    """与 DSH 一致：最近的含 .git 的祖先目录，没有则用 cwd。"""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh"))).expanduser()


def agents_home() -> Path:
    return Path(os.environ.get("DSH_AGENTS_HOME", str(Path.home() / ".agents"))).expanduser()


def bundled_skill_dir() -> Path | None:
    """内置技能目录（只读）。优先环境变量，其次 macOS app 资源路径。"""
    for env_name in ("DSH_BUNDLED_SKILL_DIR", "DSH_BUNDLED_OFFICE_SKILLS"):
        env = os.environ.get(env_name)
        if env and Path(env).expanduser().is_dir():
            return Path(env).expanduser()
    for base in (
        Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/office-skills"),
        Path("/Applications/DeepSeek Harness.app/Contents/Resources/app.asar.unpacked/runtime/office-skills"),
    ):
        if base.is_dir():
            return base
    return None


# ---------------------------------------------------------------------------
# 技能根目录发现（与 DSH dsh-skill-filesystem 的 rank 一致）
# ---------------------------------------------------------------------------

ROOT_SPEC = [
    (100, "project-dsh"),
    (200, "project-agents"),
    (400, "user-dsh"),
    (500, "user-agents"),
    (600, "bundled"),
]


def discover_roots(cwd: Path, extra_roots: list[str] | None = None) -> list[dict]:
    """返回按优先级（rank 升序）排列的技能根目录。"""
    project = find_project_root(cwd)
    candidates: list[tuple[int, str, Path]] = [
        (100, "project-dsh", project / ".dsh" / "skills"),
        (200, "project-agents", project / ".agents" / "skills"),
    ]

    custom_env = os.environ.get("DSH_CUSTOM_SKILL_DIRS", "")
    custom = [p for p in custom_env.split(os.pathsep) if p.strip()]
    custom += list(extra_roots or [])
    for idx, raw in enumerate(custom):
        candidates.append((300 + idx, "custom", Path(raw).expanduser()))

    candidates.append((400, "user-dsh", dsh_home() / "skills"))
    candidates.append((500, "user-agents", agents_home() / "skills"))
    bundled = bundled_skill_dir()
    if bundled:
        candidates.append((600, "bundled", bundled))

    roots = []
    for rank, source, path in candidates:
        path = Path(path)
        if not path.is_dir():
            continue
        writable = source != "bundled" and os.access(path, os.W_OK)
        roots.append(
            {
                "rank": rank,
                "source": source,
                "path": str(path.resolve()),
                "writable": bool(writable),
            }
        )
    roots.sort(key=lambda r: r["rank"])
    return roots


# ---------------------------------------------------------------------------
# frontmatter 解析 / 改写（文本级，不重排其它字段）
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[str, str, re.Match] | None:
    m = FM_RE.match(text)
    if not m:
        return None
    return m.group(1), text[m.end():], m


def parse_skill_text(text: str) -> dict:
    require_yaml()
    parts = split_frontmatter(text)
    if parts is None:
        return {"error": "missing frontmatter"}
    block, body, match = parts
    try:
        data = yaml.safe_load(block)
    except Exception as exc:  # noqa: BLE001 - YAML 报错要原样透出
        return {"error": f"invalid YAML frontmatter: {exc}"}
    if not isinstance(data, dict):
        return {"error": "frontmatter is not a mapping"}
    return {"block": block, "body": body, "match": match, "data": data}


def parse_skill_file(path: Path) -> dict:
    try:
        text = read_text(path)
    except OSError as exc:
        return {"error": f"read failed: {exc}"}
    info = parse_skill_text(text)
    if "error" in info:
        return info
    info["text"] = text
    return info


def locate_description(block: str) -> tuple[int, int, str] | None:
    """返回 block 中 description 值的行区间 [i, j) 与类型。"""
    lines = block.split("\n")
    for i, line in enumerate(lines):
        m = DESC_KEY_RE.match(line)
        if not m:
            continue
        rest = m.group(1).strip()
        if BLOCK_IND_RE.match(rest):
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() == "" or nxt[:1] in (" ", "\t"):
                    j += 1
                else:
                    break
            return i, j, "block"
        j = i + 1
        while j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].strip():
            j += 1
        return i, j, "inline"
    return None


def replace_description(block: str, value: str) -> str:
    loc = locate_description(block)
    if loc is None:
        raise ValueError("frontmatter has no description key")
    i, j, _kind = loc
    lines = block.split("\n")
    quoted = json.dumps(value, ensure_ascii=False)
    return "\n".join(lines[:i] + ["description: " + quoted] + lines[j:])


def rebuild_text(text: str, match: re.Match, new_block: str) -> str:
    eol = "\r\n" if "\r\n" in text[: match.end()] else "\n"
    head = text[: match.start()]
    tail = text[match.end():]
    return head + "---" + eol + new_block + eol + "---" + eol + tail


def rebuild_text_with_block(text: str, match: re.Match, new_block: str) -> str:
    """用于回滚：把整段 frontmatter 换成备份内容，保证与原文逐字节一致。"""
    eol = "\r\n" if "\r\n" in text[: match.end()] else "\n"
    return "---" + eol + new_block + eol + "---" + eol + text[match.end():]


def full_label(zh: dict) -> str:
    return LABEL_OPEN + zh["label"].strip() + LABEL_CLOSE


def strip_label(description: str) -> tuple[str, str | None]:
    m = LABEL_RE.match(description)
    if not m:
        return description, None
    return description[m.end():], m.group(1)


# ---------------------------------------------------------------------------
# 状态读写
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {"version": STATE_VERSION, "created_at": now_iso(), "skills": {}}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"状态文件损坏：{STATE_FILE}\n{exc}")
    if not isinstance(state, dict) or not isinstance(state.get("skills"), dict):
        die(f"状态文件格式不对：{STATE_FILE}")
    state.setdefault("version", STATE_VERSION)
    return state


def save_state(state: dict) -> None:
    ensure_dirs()
    state["updated_at"] = now_iso()
    write_text(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# scan：发现技能并刷新状态
# ---------------------------------------------------------------------------

def iter_root_children(root_path: Path) -> list[tuple[str, Path, str]]:
    """列出一个技能根的「直接子项」，与 DSH 一致：<name>/SKILL.md 或 <name>.md。"""
    found = []
    try:
        children = sorted(root_path.iterdir(), key=lambda p: p.name)
    except OSError:
        return found
    for child in children:
        if child.name.startswith("."):
            continue  # 跳过 .system 等隐藏目录
        if child.is_dir():
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                found.append((child.name, skill_file, "dir"))
        elif child.is_file() and child.suffix == ".md":
            if child.name == "SKILL.md":
                continue
            found.append((child.stem, child, "flat"))
    return found


def scan_skills(cwd: Path, extra_roots: list[str] | None = None) -> dict:
    roots = discover_roots(cwd, extra_roots)
    winners: dict[str, dict] = {}
    shadowed: list[dict] = []
    skipped: list[dict] = []
    all_entries: list[dict] = []

    for root in roots:
        root_path = Path(root["path"])
        for dir_name, skill_path, kind in iter_root_children(root_path):
            info = parse_skill_file(skill_path)
            if "error" in info:
                skipped.append({"path": str(skill_path), "reason": info["error"]})
                continue
            data = info["data"]
            name = str(data.get("name") or dir_name)
            description = data.get("description")
            if not isinstance(description, str) or not description.strip():
                skipped.append({"path": str(skill_path), "reason": "empty description"})
                continue
            if not NAME_RE.match(name):
                skipped.append({"path": str(skill_path), "reason": f"invalid skill name {name!r}"})
                continue
            entry = {
                "name": name,
                "path": str(skill_path.resolve()),
                "block_sha": sha256(info["block"]),
                "root": root["path"],
                "kind": kind,
                "rank": root["rank"],
                "source": root["source"],
                "writable": root["writable"],
                "description": description,
                "dir": str(skill_path.parent.resolve()),
            }
            all_entries.append(entry)
            if name in winners:
                shadowed.append({"name": name, "path": entry["path"], "root": entry["root"],
                                 "rank": entry["rank"], "winner": winners[name]["path"]})
            else:
                winners[name] = entry

    return {"roots": roots, "skills": winners, "shadowed": shadowed,
            "skipped": skipped, "all_entries": all_entries}


def refresh_state(state: dict, scan: dict) -> dict:
    """用扫描结果刷新状态，保留已有译文/标注记录。"""
    old_skills = state.get("skills", {})
    now = now_iso()
    new_skills: dict[str, dict] = {}

    for name, entry in scan["skills"].items():
        prev = old_skills.get(name) or {}
        description = entry["description"]
        apply_info = prev.get("apply") if isinstance(prev.get("apply"), dict) else None

        if apply_info:
            label = apply_info.get("label") or ""
            if label and description.startswith(label):
                original = description[len(label):]
                applied = True
            else:
                original = description
                applied = False
                apply_info = None
        else:
            original = description
            applied = False

        zh = prev.get("zh") if isinstance(prev.get("zh"), dict) else None
        source_hash = sha256(original)
        if zh and original.lstrip().startswith(LABEL_OPEN):
            zh["source_hash"] = source_hash
        original_block_sha = entry.get("block_sha") if not applied else prev.get("original_block_sha")

        new_skills[name] = {
            "name": name,
            "path": entry["path"],
            "dir": entry["dir"],
            "root": entry["root"],
            "kind": entry["kind"],
            "rank": entry["rank"],
            "source": entry["source"],
            "writable": entry["writable"],
            "original_description": original,
            "source_hash": source_hash,
            "original_block_sha": original_block_sha,
            "description_length": len(description),
            "zh": zh,
            "apply": apply_info if applied else None,
            "first_seen": prev.get("first_seen") or now,
            "updated_at": now,
        }

    removed = sorted(set(old_skills) - set(new_skills))
    state["skills"] = new_skills
    state["roots"] = scan["roots"]
    state["shadowed"] = scan["shadowed"]
    state["skipped"] = scan["skipped"]
    state["last_scan"] = now
    state["removed_since_last_scan"] = removed
    return state


def cmd_scan(args) -> int:
    ensure_dirs()
    scan = scan_skills(Path(args.cwd).expanduser().resolve(), args.extra_root)
    if not scan["skills"]:
        print("没有发现技能。DSH 默认扫描项目 .agents/skills、~/.agents/skills、~/.dsh/skills；"
              "可用 --extra-root 指定目录。")
    state = refresh_state(load_state(), scan)
    save_state(state)

    skills = state["skills"]
    writable = [s for s in skills.values() if s["writable"]]
    translated = [s for s in skills.values() if s.get("zh")]
    applied = [s for s in skills.values() if s.get("apply")]

    print(f"技能根目录（按 DSH 优先级）：")
    for root in state["roots"]:
        mark = "可写" if root["writable"] else "只读"
        print(f"  [{root['rank']:>3}] {root['source']:<14} {root['path']}  ({mark})")
    print()
    print(f"共发现 {len(skills)} 个技能（可写 {len(writable)}，只读 {len(skills) - len(writable)}）")
    print(f"已翻译 {len(translated)}，已加中文标签 {len(applied)}")
    if state["shadowed"]:
        print(f"同名低优先级副本（不会重复标注）：{len(state['shadowed'])} 个")
    if state["skipped"]:
        print(f"跳过（frontmatter 无效）：{len(state['skipped'])} 个")
        for sk in state["skipped"][:5]:
            print(f"  - {sk['path']}: {sk['reason']}")
    if args.json:
        print(json.dumps({"roots": state["roots"], "counts": {
            "total": len(skills), "writable": len(writable),
            "translated": len(translated), "applied": len(applied),
        }, "shadowed": state["shadowed"], "skipped": state["skipped"]},
            ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# pending：生成待翻译清单（可拆分为多个文件交给并行翻译）
# ---------------------------------------------------------------------------

def is_pending(entry: dict) -> bool:
    if not entry.get("writable"):
        return False
    if (entry.get("original_description") or "").lstrip().startswith(LABEL_OPEN):
        return False  # 描述本来就是中文（如 skill-zh 自己），无需翻译
    zh = entry.get("zh")
    if not isinstance(zh, dict) or not zh.get("label"):
        return True
    return zh.get("source_hash") != entry.get("source_hash")


def pending_items(state: dict) -> list[dict]:
    items = []
    for name, entry in sorted(state["skills"].items()):
        if not is_pending(entry):
            continue
        items.append(
            {
                "name": name,
                "root": entry["root"],
                "path": entry["path"],
                "original_description": entry["original_description"],
                "zh": {"label": "", "keywords": [], "summary": "", "category": ""},
            }
        )
    return items


PENDING_INSTRUCTIONS = (
    "按 references/translation-spec.md 为每个条目补全 zh 字段；只填 zh，不要改其它键。"
    "完成后运行 check --strict 自检到 0 问题。"
)


def write_pending_parts(pending: list[dict], split: int,
                        out_dir: Path | None = None) -> list[Path]:
    """把待翻译条目写成 1..N 份 JSON，供并行翻译使用。"""
    out_dir = out_dir or TRANS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清理上一轮的分片，避免旧条目误导翻译（不动 part-*.zh.json 产出）
    for stale in out_dir.glob("pending-part-*.json"):
        stale.unlink()
    split = max(1, split)
    letters = "abcdefghijklmnopqrstuvwxyz"
    chunks: list[list[dict]] = [[] for _ in range(split)]
    for idx, item in enumerate(pending):
        chunks[idx % split].append(item)
    paths: list[Path] = []
    for idx, chunk in enumerate(chunks):
        if not chunk:
            continue
        path = out_dir / f"pending-part-{letters[idx]}.json"
        write_text(
            path,
            json.dumps(
                {
                    "generated_at": now_iso(),
                    "count": len(chunk),
                    "instructions": PENDING_INSTRUCTIONS,
                    "entries": chunk,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
        )
        paths.append(path)
    write_text(
        PENDING_FILE,
        json.dumps(
            {
                "generated_at": now_iso(),
                "instructions": PENDING_INSTRUCTIONS,
                "count": len(pending),
                "entries": pending,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )
    return paths


def cmd_pending(args) -> int:
    ensure_dirs()
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan（或 init）")

    pending = pending_items(state)
    if not pending:
        print("没有待翻译技能：所有可写技能都已有中文翻译（或描述本来就是中文）。")
        return 0
    if args.split and args.split > 1:
        out_dir = Path(args.outdir).expanduser() if args.outdir else TRANS_DIR
        paths = write_pending_parts(pending, args.split, out_dir)
        print(f"共 {len(pending)} 个待翻译技能，已拆成 {len(paths)} 份：")
        for path in paths:
            print(f"  {path}")
        print("下一步：按 references/translation-prompt.md 启动翻译子代理。")
        return 0
    write_pending_parts(pending, 1)
    print(f"待翻译 {len(pending)} 个技能 -> {PENDING_FILE}")
    for item in pending[:10]:
        print(f"  - {item['name']}")
    if len(pending) > 10:
        print(f"  ... 其余 {len(pending) - 10} 个见文件")
    return 0


def write_index(state: dict) -> None:
    groups = build_index(state)
    ensure_dirs()
    write_text(INDEX_MD, render_index_md(groups, state))
    write_text(
        INDEX_JSON,
        json.dumps(
            {
                "generated_at": now_iso(),
                "total": sum(len(v) for v in groups.values()),
                "categories": {cat: items for cat, items in groups.items() if items},
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )


def print_next_steps(pending_count: int) -> None:
    print()
    if pending_count:
        print("下一步（把英文技能变成中文可调用）：")
        print("  1. 按 references/translation-prompt.md 启动 2–3 个翻译子代理，")
        print("     每个子代理负责一份 ~/.skills-zh/translations/pending-part-<x>.json；")
        print("  2. 子代理产出 part-<x>.zh.json 后自检：")
        print("     python3 scripts/skill_zh.py check --strict <file>")
        print("  3. 合并、重建索引、加标签、验收：")
        print("     python3 scripts/skill_zh.py merge ~/.skills-zh/translations/part-*.zh.json")
        print("     python3 scripts/skill_zh.py index")
        print("     python3 scripts/skill_zh.py apply --dry-run   # 先预览改动")
        print("     python3 scripts/skill_zh.py apply")
        print("     python3 scripts/skill_zh.py verify")
    else:
        print("所有可写技能都已有中文翻译。需要时运行：index / apply / verify")
        print("用户用中文提问时，模型会直接按中文标签命中技能；也可用 lookup 查精确技能名。")


def cmd_init(args) -> int:
    ensure_dirs()
    if yaml is None:
        die("缺少 PyYAML。请先安装：python3 -m pip install pyyaml\n"
            "（Windows 用 python -m pip install pyyaml）", code=2)
    print(f"skill-zh {TOOL_VERSION} · 初始化：扫描本机技能并准备中文翻译")
    cwd = Path(args.cwd).expanduser().resolve()
    scan = scan_skills(cwd, args.extra_root)
    if not scan["roots"]:
        print("没有发现技能根目录。DSH 默认扫描项目 .agents/skills、~/.agents/skills、~/.dsh/skills；")
        print("如果技能在别处，用 --extra-root /path/to/skills 指定。")
    if not scan["skills"]:
        print("没有发现任何技能，初始化结束（没有可汉化的内容）。")
        return 1

    state = refresh_state(load_state(), scan)
    save_state(state)
    write_index(state)

    skills = state["skills"]
    writable = sum(1 for s in skills.values() if s["writable"])
    translated = sum(1 for s in skills.values() if s.get("zh"))
    applied = sum(1 for s in skills.values() if s.get("apply"))
    pending = pending_items(state)

    print()
    print(f"发现 {len(skills)} 个技能（可写 {writable}）；已翻译 {translated}，已标注 {applied}，"
          f"待翻译 {len(pending)}。")
    print(f"中文目录预览：{INDEX_MD}")
    if pending:
        split = max(1, args.split or 3)
        paths = write_pending_parts(pending, split)
        print(f"已生成 {len(paths)} 个待翻译文件：")
        for path in paths:
            print(f"  {path}")
    print_next_steps(len(pending))
    return 0


def cmd_doctor(args) -> int:
    print(f"skill-zh {TOOL_VERSION} 环境自检")
    print(f"  Python：{sys.version.split()[0]}（{sys.platform}）")
    print(f"  PyYAML：{getattr(yaml, '__version__', '缺失')}")
    print(f"  状态目录：{SKILL_ZH_HOME}（{'存在' if SKILL_ZH_HOME.exists() else '不存在，init 会创建'}）")
    if yaml is None:
        print("  ! 缺少 PyYAML：请运行 python3 -m pip install pyyaml 后重试")
        return 2

    cwd = Path(args.cwd).expanduser().resolve()
    scan = scan_skills(cwd, args.extra_root)
    print(f"  项目根：{find_project_root(cwd)}")
    print("  技能根目录（按 DSH 优先级）：")
    for root in scan["roots"]:
        count = sum(1 for e in scan["all_entries"] if e["root"] == root["path"])
        mark = "可写" if root["writable"] else "只读"
        print(f"    [{root['rank']:>3}] {root['source']:<14} {root['path']}  技能 {count} 个（{mark}）")
    print(f"  发现技能 {len(scan['skills'])} 个（低优先级副本 {len(scan['shadowed'])}，"
          f"跳过 {len(scan['skipped'])}）")
    print(f"  内置技能目录：{bundled_skill_dir() or '未找到（可用 DSH_BUNDLED_OFFICE_SKILLS 指定）'}")
    if STATE_FILE.is_file():
        state = load_state()
        pending = len(pending_items(state))
        translated = sum(1 for s in state["skills"].values() if s.get("zh"))
        applied = sum(1 for s in state["skills"].values() if s.get("apply"))
        print(f"  状态库：{len(state['skills'])} 技能，已翻译 {translated}，已标注 {applied}，待翻译 {pending}")
    else:
        print("  状态库：尚未初始化（运行 init）")
    return 0


# ---------------------------------------------------------------------------
# merge：合并翻译结果
# ---------------------------------------------------------------------------

def load_entry_file(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"无法读取译文文件 {path}: {exc}")
    if isinstance(data, dict):
        data = data.get("entries", [])
    if not isinstance(data, list):
        die(f"译文文件格式应为列表或含 entries 列表的对象：{path}")
    return data


def validate_zh(entry: dict) -> list[str]:
    problems: list[str] = []
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return ["缺少 name"]
    zh = entry.get("zh")
    if not isinstance(zh, dict):
        return [f"{name}: 缺少 zh 对象"]
    label = zh.get("label")
    keywords = zh.get("keywords")
    summary = zh.get("summary")
    category = zh.get("category")

    if not isinstance(label, str) or not label.strip():
        problems.append(f"{name}: zh.label 不能为空")
    else:
        label = label.strip()
        if "【" in label or "】" in label:
            problems.append(f"{name}: zh.label 不要包含【】")
        if len(label) > LIMITS["label"]:
            problems.append(f"{name}: zh.label 超过 {LIMITS['label']} 字（{len(label)}）")
    if not isinstance(keywords, list) or not all(isinstance(k, str) and k.strip() for k in keywords):
        problems.append(f"{name}: zh.keywords 必须是字符串列表")
    else:
        if not (LIMITS["keywords_min"] <= len(keywords) <= LIMITS["keywords_max"]):
            problems.append(f"{name}: zh.keywords 数量应为 {LIMITS['keywords_min']}-{LIMITS['keywords_max']}")
        for keyword in keywords:
            if len(keyword.strip()) > LIMITS["keyword"]:
                problems.append(f"{name}: 关键词「{keyword}」超过 {LIMITS['keyword']} 字")
    if not isinstance(summary, str) or not summary.strip():
        problems.append(f"{name}: zh.summary 不能为空")
    elif len(summary.strip()) > LIMITS["summary"]:
        problems.append(f"{name}: zh.summary 超过 {LIMITS['summary']} 字（{len(summary)}）")
    if category not in CATEGORIES:
        problems.append(f"{name}: category 必须是 {CATEGORIES} 之一（当前 {category!r}）")
    return problems


def cmd_check(args) -> int:
    """只校验译文 JSON，不写状态（供翻译队员自检 / Lead 预检）。"""
    state = load_state() if args.strict else None
    if args.strict and (state is None or not state.get("skills")):
        die("--strict 需要先 scan 生成状态")
    paths = [Path(p).expanduser() for p in args.files]
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            die(f"找不到译文文件：{path}")
    if not files:
        die("没有找到任何译文文件（*.json）")

    total = 0
    ok = 0
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in files:
        for entry in load_entry_file(path):
            total += 1
            issues = validate_zh(entry) if isinstance(entry, dict) else ["条目不是对象"]
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                name = entry["name"]
                if name in seen:
                    issues.append(f"{name}: 在多个文件重复出现（{seen[name]} / {path.name}）")
                seen[name] = path.name
                if args.strict and name not in state["skills"]:
                    issues.append(f"{name}: 不是已发现的技能名（拼写错误？）")
            if issues:
                problems.extend(issues)
            else:
                ok += 1
    print(f"校验 {total} 条：通过 {ok}，问题 {len(problems)}")
    for problem in problems[:50]:
        print(f"  - {problem}")
    if len(problems) > 50:
        print(f"  ... 共 {len(problems)} 条")
    return 1 if problems else 0


def cmd_merge(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")

    paths = [Path(p).expanduser() for p in args.files]
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            found = sorted(path.glob("*.zh.json"))
            if not found:
                found = [p for p in sorted(path.glob("*.json"))
                         if not p.name.startswith("pending-")]
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            die(f"找不到译文文件：{path}")
    if not files:
        die("没有找到任何译文文件（*.json 或 *.zh.json）")

    merged = 0
    all_problems: list[str] = []
    seen: set[str] = set()
    for path in files:
        for entry in load_entry_file(path):
            name = entry.get("name") if isinstance(entry, dict) else None
            problems = validate_zh(entry) if isinstance(entry, dict) else ["条目不是对象"]
            if problems:
                all_problems.extend(problems)
                continue
            target = state["skills"].get(name)
            if target is None:
                all_problems.append(f"{name}: 状态里没有这个技能（可能改名或被删），请先 scan")
                continue
            zh = {
                "label": entry["zh"]["label"].strip(),
                "keywords": [k.strip() for k in entry["zh"]["keywords"]],
                "summary": entry["zh"]["summary"].strip(),
                "category": entry["zh"]["category"],
                "source_hash": target["source_hash"],
                "translated_at": now_iso(),
            }
            target["zh"] = zh
            merged += 1
            seen.add(name)

    save_state(state)
    if all_problems:
        print(f"校验失败 {len(all_problems)} 条：")
        for problem in all_problems[:40]:
            print(f"  - {problem}")
        if len(all_problems) > 40:
            print(f"  ... 共 {len(all_problems)} 条")
        print()
    print(f"已合并 {merged} 条译文（来自 {len(files)} 个文件）")
    translated = sum(1 for s in state["skills"].values() if s.get("zh"))
    translatable = sum(
        1
        for s in state["skills"].values()
        if s["writable"] and not (s.get("original_description") or "").lstrip().startswith(LABEL_OPEN)
    )
    print(f"翻译覆盖：{translated}/{translatable} 个需要翻译的技能（原生中文描述不计入）")
    return 1 if all_problems else 0


# ---------------------------------------------------------------------------
# index：生成中文索引
# ---------------------------------------------------------------------------

def status_of(entry: dict) -> str:
    if not entry.get("writable"):
        return "内置只读"
    if (entry.get("original_description") or "").lstrip().startswith(LABEL_OPEN):
        return "已是中文"
    if entry.get("apply"):
        return "已标注"
    if entry.get("zh"):
        if entry["zh"].get("source_hash") != entry.get("source_hash"):
            return "需重译"
        return "已翻译未标注"
    return "待翻译"


STATUS_ICON = {
    "内置只读": "🔒",
    "已标注": "✅",
    "已翻译未标注": "🟡",
    "需重译": "⚠️",
    "待翻译": "⏳",
    "已是中文": "🈶",
}


def build_index(state: dict) -> dict:
    groups: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}
    for name, entry in sorted(state["skills"].items()):
        zh = entry.get("zh") or {}
        category = zh.get("category") or "综合工具与效率"
        if category not in groups:
            category = "综合工具与效率"
        groups[category].append(
            {
                "name": name,
                "label": zh.get("label") or "",
                "keywords": zh.get("keywords") or [],
                "summary": zh.get("summary") or "",
                "status": status_of(entry),
                "source": entry.get("source"),
                "root": entry.get("root"),
                "path": entry.get("path"),
                "rank": entry.get("rank"),
                "writable": entry.get("writable"),
                "applied": bool(entry.get("apply")),
            }
        )
    return groups


def render_index_md(groups: dict, state: dict) -> str:
    total = sum(len(v) for v in groups.values())
    counts: dict[str, int] = {}
    for items in groups.values():
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
    writable = sum(1 for s in state["skills"].values() if s["writable"])
    translated = sum(1 for s in state["skills"].values() if s.get("zh"))
    applied = sum(1 for s in state["skills"].values() if s.get("apply"))

    lines = [
        "# 中文技能目录（skill-zh）",
        "",
        f"> 生成时间：{now_iso()}　共 {total} 个技能；可写 {writable}，已翻译 {translated}，已加中文标签 {applied}。",
        "> 用法：模型按中文描述直接路由；也可让 skill-zh 查表后用 `skill` 工具加载精确技能名。",
        "> 状态：✅ 已标注　🈶 已是中文（原生中文描述）　🟡 已翻译未标注　⏳ 待翻译　⚠️ 需重译　🔒 内置只读（不修改系统文件）",
        "",
    ]
    for category in CATEGORIES:
        items = groups.get(category) or []
        if not items:
            continue
        lines.append(f"## {category}（{len(items)}）")
        lines.append("")
        lines.append("| 中文名 | 技能 ID | 一句话说明 | 关键词 | 状态 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in items:
            label = item["label"] or "—"
            summary = (item["summary"] or "").replace("|", "\\|")
            keywords = "、".join(item["keywords"]) if item["keywords"] else "—"
            keywords = keywords.replace("|", "\\|")
            icon = STATUS_ICON.get(item["status"], "")
            lines.append(
                f"| {label} | `{item['name']}` | {summary} | {keywords} | {icon} {item['status']} |"
            )
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("技能 ID 用于 `skill` 工具加载；同名技能按 DSH 优先级（project > custom > user）去重。")
    return "\n".join(lines) + "\n"


def cmd_index(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    groups = build_index(state)
    markdown = render_index_md(groups, state)
    ensure_dirs()
    write_text(INDEX_MD, markdown)

    index_json = {
        "generated_at": now_iso(),
        "total": sum(len(v) for v in groups.values()),
        "categories": {cat: items for cat, items in groups.items() if items},
    }
    write_text(INDEX_JSON, json.dumps(index_json, ensure_ascii=False, indent=2) + "\n")
    if args.out:
        out = Path(args.out).expanduser()
        write_text(out, markdown)
    print(f"中文索引已生成：{INDEX_MD}")
    print(f"机器可读版本：{INDEX_JSON}")
    for cat, items in groups.items():
        if items:
            print(f"  {cat}: {len(items)}")
    return 0


# ---------------------------------------------------------------------------
# apply / revert：给 SKILL.md 描述加中文标签
# ---------------------------------------------------------------------------

APPLY_EXPECTED_KEYS = ("name", "description")


def preview_label_length(entry: dict) -> int:
    zh = entry.get("zh") or {}
    return len(full_label(zh)) if zh.get("label") else 0


def apply_skill(entry: dict, dry: bool = False) -> tuple[str, str]:
    """返回 (状态, 说明)。状态：applied / already / skipped / error。"""
    if not entry.get("writable"):
        return "skipped", "内置/只读根目录"
    zh = entry.get("zh")
    if not isinstance(zh, dict) or not zh.get("label"):
        return "skipped", "还没有中文标签"
    if zh.get("source_hash") != entry.get("source_hash"):
        return "skipped", "描述已变更，需要重新翻译"

    path = Path(entry["path"])
    info = parse_skill_file(path)
    if "error" in info:
        return "error", f"无法解析：{info['error']}"
    data = info["data"]
    description = data.get("description")
    if not isinstance(description, str):
        return "error", "description 缺失"

    label = full_label(zh)
    if description.startswith(label):
        entry["apply"] = {
            "label": label,
            "applied_at": (entry.get("apply") or {}).get("applied_at") or now_iso(),
            "block_sha": sha256(info["block"]),
        }
        return "already", "已有中文标签"

    original = entry.get("original_description") or description
    if original.lstrip().startswith(LABEL_OPEN):
        return "already", "描述本来就是中文，无需加标签"
    if description != original:
        # 扫描后文件被改过：以当前内容为新的原文基础
        stripped, _ = strip_label(description)
        original = stripped
        entry["original_description"] = original
        entry["source_hash"] = sha256(original)
        if zh.get("source_hash") != entry["source_hash"]:
            return "error", "描述在扫描后有变动，请先 scan + 重新翻译"

    new_description = label + original
    try:
        new_block = replace_description(info["block"], new_description)
    except ValueError as exc:
        return "error", str(exc)

    new_text = rebuild_text(info["text"], info["match"], new_block)
    check = parse_skill_text(new_text)
    if "error" in check:
        return "error", f"改写后 frontmatter 不合法：{check['error']}"
    check_data = check["data"]
    if check_data.get("name") != data.get("name"):
        return "error", "改写改变了 name 字段"
    if check_data.get("description") != new_description:
        return "error", "改写后 description 校验失败"

    if dry:
        return "applied", f"[dry-run] 将加标签：{label}"

    backup = BACKUP_DIR / f"{entry['name']}.frontmatter"
    current_block_sha = sha256(info["block"])
    if not backup.is_file() or entry.get("original_block_sha") != current_block_sha:
        write_text(backup, info["block"])
    entry["original_block_sha"] = current_block_sha
    write_text(path, new_text)

    entry["apply"] = {
        "label": label,
        "applied_at": now_iso(),
        "block_sha": sha256(new_block),
        "backup": str(backup),
    }
    return "applied", f"+ {label}"


def cmd_apply(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    only = set(args.only) if args.only else None
    counts = {"applied": 0, "already": 0, "skipped": 0, "error": 0}
    messages: list[str] = []
    for name, entry in sorted(state["skills"].items()):
        if only is not None and name not in only:
            continue
        status, note = apply_skill(entry, dry=args.dry_run)
        if status == "skipped" and not entry.get("zh"):
            continue
        counts[status] = counts.get(status, 0) + 1
        if status == "applied":
            messages.append(f"  {name}: {note}")
        elif status == "error":
            messages.append(f"  ! {name}: {note}")
    if not args.dry_run:
        save_state(state)
        write_index(state)  # 让索引里的状态与覆盖率保持最新
    print(f"加中文标签：新增 {counts['applied']}，已存在 {counts['already']}，"
          f"跳过 {counts['skipped']}，失败 {counts['error']}")
    for message in messages[:30]:
        print(message)
    if len(messages) > 30:
        print(f"  ... 共 {len(messages)} 条")
    if args.dry_run:
        print("（dry-run，未写入任何文件）")
    return 1 if counts["error"] else 0


def cmd_revert(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    only = set(args.only) if args.only else None
    reverted = 0
    problems: list[str] = []
    for name, entry in sorted(state["skills"].items()):
        if only is not None and name not in only:
            continue
        apply_info = entry.get("apply")
        if not apply_info:
            continue
        path = Path(entry["path"])
        info = parse_skill_file(path)
        if "error" in info:
            problems.append(f"{name}: {info['error']}")
            continue
        description = info["data"].get("description") or ""
        label = apply_info.get("label") or ""
        if not label or not description.startswith(label):
            entry["apply"] = None
            problems.append(f"{name}: 文件里已没有标签，已清理状态")
            continue
        expected_block_sha = apply_info.get("block_sha")
        untouched = bool(expected_block_sha) and sha256(info["block"]) == expected_block_sha
        if expected_block_sha and not untouched and not args.force:
            problems.append(f"{name}: 标注后文件又被改过，跳过（--force 可强制回滚）")
            continue
        original = entry.get("original_description") or ""
        if not original:
            problems.append(f"{name}: 缺少原文备份")
            continue
        backup = BACKUP_DIR / f"{name}.frontmatter"
        if untouched and backup.is_file():
            # 优先用原始 frontmatter 备份，保证回滚后逐字节一致
            new_text = rebuild_text_with_block(info["text"], info["match"],
                                               backup.read_text(encoding="utf-8"))
            new_block = None
        else:
            new_block = replace_description(info["block"], original)
            new_text = rebuild_text(info["text"], info["match"], new_block)
        check = parse_skill_text(new_text)
        if "error" in check or check["data"].get("description") != original:
            problems.append(f"{name}: 回滚校验失败")
            continue
        if not args.dry_run:
            write_text(path, new_text)
        entry["apply"] = None
        entry["source_hash"] = sha256(original)
        if entry.get("zh"):
            entry["zh"]["source_hash"] = entry["source_hash"]
        reverted += 1
    if not args.dry_run:
        save_state(state)
        # 回滚后重新扫描，保证状态与磁盘一致
        scan = scan_skills(Path(args.cwd).expanduser().resolve(), args.extra_root)
        state = refresh_state(load_state(), scan)
        save_state(state)
        write_index(state)
    if args.dry_run:
        print(f"[dry-run] 将回滚 {reverted} 个技能的中文标签（未写入任何文件）")
    else:
        print(f"已回滚 {reverted} 个技能的中文标签")
    for problem in problems[:20]:
        print(f"  - {problem}")
    return 0


# ---------------------------------------------------------------------------
# lookup：中文查询 -> 技能名
# ---------------------------------------------------------------------------

CJK_RE = re.compile(r"[\u3400-\u9fff]")
WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def bigrams(text: str) -> set[str]:
    chars = [c for c in text if CJK_RE.match(c)] if CJK_RE.search(text) else []
    if len(chars) < 2:
        return set(chars)
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def score_skill(query: str, entry: dict) -> float:
    zh = entry.get("zh") or {}
    label = (zh.get("label") or "")
    keywords = zh.get("keywords") or []
    summary = (zh.get("summary") or "")
    name = entry.get("name") or ""
    english = (entry.get("original_description") or "").lower()
    q = query.strip().lower()
    q_norm = re.sub(r"\s+", "", q)
    score = 0.0

    if not q_norm:
        return 0.0
    label_norm = re.sub(r"\s+", "", label).lower()
    if label_norm and (q_norm == label_norm):
        score += 40
    elif label_norm and (label_norm in q_norm):
        score += 24
    elif label_norm and (q_norm in label_norm):
        score += 16

    for keyword in keywords:
        k = keyword.strip()
        if not k:
            continue
        kn = re.sub(r"\s+", "", k).lower()
        if kn and kn in q_norm:
            score += 14 + min(len(kn), 6)
        elif q_norm in kn and len(q_norm) >= 2:
            score += 8

    q_grams = bigrams(q_norm)
    if q_grams:
        pool = bigrams(label_norm + summary)
        overlap = len(q_grams & pool)
        score += overlap * 2.0

    q_words = set(WORD_RE.findall(q))
    if q_words:
        name_words = set(name.replace("-", " ").split())
        score += len(q_words & name_words) * 6
        score += len(q_words & set(WORD_RE.findall(english))) * 1.0

    return score


def cmd_lookup(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    query = " ".join(args.query).strip()
    if not query:
        die("请给出中文查询，例如：skill_zh.py lookup 分子对接")
    scored = []
    for name, entry in state["skills"].items():
        s = score_skill(query, entry)
        if s > 0:
            scored.append((s, name, entry))
    scored.sort(key=lambda item: (-item[0], item[1]))
    scored = scored[: args.limit]
    if not scored:
        print(f"没有匹配「{query}」的技能。可以运行 skill_zh.py index 查看全部中文目录。")
        return 0
    if args.json:
        print(json.dumps([
            {"name": name, "score": round(s, 1),
             "label": (entry.get("zh") or {}).get("label"),
             "summary": (entry.get("zh") or {}).get("summary"),
             "path": entry.get("path")}
            for s, name, entry in scored
        ], ensure_ascii=False, indent=2))
        return 0
    if scored and scored[0][0] < 4:
        print(f"提示：没有高置信匹配（最高分 {scored[0][0]:.1f}），以下候选可能只是字面重合；"
              f"建议先浏览 ~/.skills-zh/index.md 或改用英文技能名/更具体的中文说法。")
    print(f"中文查询「{query}」的候选技能：")
    for idx, (s, name, entry) in enumerate(scored, 1):
        zh = entry.get("zh") or {}
        label = zh.get("label") or "（未翻译）"
        summary = zh.get("summary") or ""
        print(f"{idx}. {name}  【{label}】 score={s:.1f}")
        if summary:
            print(f"   {summary}")
        print(f"   加载：skill(name=\"{name}\")")
    return 0


# ---------------------------------------------------------------------------
# ingest：整理下载/散落的技能包
# ---------------------------------------------------------------------------

def discover_bundle_files(base: Path) -> list[Path]:
    if base.is_file() and base.name == "SKILL.md":
        return [base]
    if base.is_file() and base.suffix == ".md":
        return [base]
    return sorted(base.rglob("SKILL.md"))


def cmd_ingest(args) -> int:
    src = Path(args.path).expanduser()
    if not src.exists():
        die(f"路径不存在：{src}")
    temp_dir = None
    if src.is_file() and src.suffix.lower() == ".zip":
        temp_dir = Path(tempfile.mkdtemp(prefix="skill-zh-ingest-"))
        with zipfile.ZipFile(src) as zf:
            zf.extractall(temp_dir)
        src = temp_dir
    target = Path(args.target).expanduser() if args.target else (agents_home() / "skills")
    target.mkdir(parents=True, exist_ok=True)

    files = discover_bundle_files(src)
    if not files:
        die(f"没有在 {src} 下找到 SKILL.md")

    installed, skipped, conflicts = [], [], []
    for skill_file in files:
        info = parse_skill_file(skill_file)
        if "error" in info:
            skipped.append((skill_file, info["error"]))
            continue
        data = info["data"]
        name = data.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            skipped.append((skill_file, f"name 不是 kebab-case：{name!r}"))
            continue
        bundle_dir = skill_file.parent
        destination = target / name
        if destination.exists() and not args.force:
            conflicts.append((name, destination))
            continue
        if args.dry_run:
            installed.append((name, str(destination), "dry-run"))
            continue
        if destination.exists():
            shutil.rmtree(destination)
        if bundle_dir.name == "SKILL.md":  # 理论上不会发生
            continue
        shutil.copytree(bundle_dir, destination)
        (destination / ".skill-zh-origin").write_text(
            f"imported-from: {bundle_dir}\nimported-at: {now_iso()}\n", encoding="utf-8"
        )
        installed.append((name, str(destination), "copied"))

    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"整理技能包：{src}")
    print(f"  安装到：{target}")
    print(f"  新增 {len(installed)}，跳过 {len(skipped)}，冲突 {len(conflicts)}")
    for name, path, note in installed:
        print(f"  + {name} ({note}) {path if args.verbose else ''}")
    for path, reason in skipped[:10]:
        print(f"  - 跳过 {path}: {reason}")
    for name, destination in conflicts[:10]:
        print(f"  ! 已存在 {name} -> {destination}（--force 覆盖）")
    if installed and not args.dry_run:
        print("提示：新技能会被 DSH 自动发现；接着跑 `skill_zh.py scan` 纳入中文翻译流程。")
    return 1 if (skipped or conflicts) else 0


def cmd_pull_bundled(args) -> int:
    bundled = bundled_skill_dir()
    if bundled is None:
        die("没有找到内置技能目录（可通过 DSH_BUNDLED_OFFICE_SKILLS 指定）")
    target = Path(args.target).expanduser() if args.target else (agents_home() / "skills")
    target.mkdir(parents=True, exist_ok=True)
    installed, conflicts = [], []
    for dir_name, skill_file, kind in iter_root_children(bundled):
        destination = target / dir_name
        if destination.exists() and not args.force:
            conflicts.append(dir_name)
            continue
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(skill_file.parent, destination)
        (destination / ".skill-zh-origin").write_text(
            f"bundled-copy-from: {skill_file.parent}\nimported-at: {now_iso()}\n",
            encoding="utf-8",
        )
        installed.append(dir_name)
    print(f"内置技能复制到 {target}：新增 {len(installed)}，已存在 {len(conflicts)}")
    for name in installed:
        print(f"  + {name}")
    if conflicts:
        print(f"  已存在（保持原样）：{', '.join(conflicts)}")
    print("提示：副本会按 user-agents 优先级覆盖内置版本，之后请运行 scan。")
    return 0


# ---------------------------------------------------------------------------
# status / verify
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    skills = state["skills"]
    writable = [s for s in skills.values() if s["writable"]]
    translated = [s for s in skills.values() if s.get("zh")]
    applied = [s for s in skills.values() if s.get("apply")]
    pending = pending_items(state)
    stale = [
        s
        for s in writable
        if s.get("zh")
        and s["zh"].get("source_hash") != s["source_hash"]
        and not (s.get("original_description") or "").lstrip().startswith(LABEL_OPEN)
    ]
    print(f"状态目录：{SKILL_ZH_HOME}")
    print(f"技能总数：{len(skills)}（可写 {len(writable)}，只读 {len(skills) - len(writable)}）")
    print(f"已翻译：{len(translated)}　已标注：{len(applied)}　待翻译：{len(pending)}　需重译：{len(stale)}")
    print(f"索引：{INDEX_MD} ({'存在' if INDEX_MD.is_file() else '未生成'})")
    print(f"上次扫描：{state.get('last_scan', '未知')}")
    if state.get("removed_since_last_scan"):
        print(f"扫描间消失的技能：{', '.join(state['removed_since_last_scan'])}")
    if args.json:
        print(json.dumps({"total": len(skills), "writable": len(writable),
                          "translated": len(translated), "applied": len(applied),
                          "pending": len(pending), "stale": len(stale)},
                         ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args) -> int:
    state = load_state()
    if not state.get("skills"):
        die("还没有扫描结果，请先运行：skill_zh.py scan")
    failures: list[str] = []
    checks = 0

    for name, entry in sorted(state["skills"].items()):
        checks += 1
        path = Path(entry["path"])
        if not path.is_file():
            failures.append(f"{name}: 文件不存在 {path}")
            continue
        info = parse_skill_file(path)
        if "error" in info:
            failures.append(f"{name}: frontmatter 解析失败：{info['error']}")
            continue
        data = info["data"]
        if data.get("name") != name:
            failures.append(f"{name}: 文件里的 name 变成了 {data.get('name')!r}")
        description = data.get("description")
        if not isinstance(description, str):
            failures.append(f"{name}: description 不是字符串")
            continue
        if entry.get("apply"):
            label = entry["apply"].get("label") or ""
            if not description.startswith(label):
                failures.append(f"{name}: 状态记为已标注，但描述缺少标签 {label!r}")
            elif description[len(label):] != entry["original_description"]:
                failures.append(f"{name}: 标签后的原文与状态记录不一致")
            backup = BACKUP_DIR / f"{name}.frontmatter"
            if not backup.is_file():
                failures.append(f"{name}: 缺少原文备份 {backup}")
        else:
            if description != entry["original_description"]:
                failures.append(f"{name}: 未标注，但描述与记录不一致（可能被手动改过，请 scan）")
        if entry.get("zh"):
            problems = validate_zh({"name": name, "zh": entry["zh"]})
            failures.extend(problems)
        if not entry.get("writable") and entry.get("apply"):
            failures.append(f"{name}: 只读技能不应被标注")

    # 索引与状态一致性
    if INDEX_MD.is_file():
        index_text = INDEX_MD.read_text(encoding="utf-8")
        missing = [n for n in state["skills"] if f"`{n}`" not in index_text]
        if missing:
            failures.append(f"索引缺少 {len(missing)} 个技能（建议重新 index）：{missing[:5]}")
    else:
        failures.append("索引 index.md 不存在")

    report = {
        "checked_at": now_iso(),
        "checks": checks,
        "failures": failures,
    }
    ensure_dirs()
    report_path = REPORT_DIR / f"verify-{time.strftime('%Y%m%d-%H%M%S')}.json"
    write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"校验了 {checks} 个技能，发现 {len(failures)} 个问题。报告：{report_path}")
    for failure in failures[:30]:
        print(f"  - {failure}")
    if len(failures) > 30:
        print(f"  ... 共 {len(failures)} 条")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_zh.py",
        description="技能汉化管家：扫描技能、翻译中文名、给描述加中文标签、生成中文索引、中文检索。",
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="用于定位项目级技能根目录（默认当前目录）")
    parser.add_argument("--extra-root", action="append", default=[],
                        help="额外的技能根目录（可重复，优先级在 user 根之前）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="首次初始化：扫描本机技能、生成待翻译清单与中文索引预览")
    p_init.add_argument("--split", type=int, default=3, help="待翻译清单拆分份数（默认 3）")
    p_init.set_defaults(func=cmd_init)

    p_doctor = sub.add_parser("doctor", help="环境与技能根目录自检（缺依赖时也能运行）")
    p_doctor.set_defaults(func=cmd_doctor)

    p_scan = sub.add_parser("scan", help="扫描全部技能根目录并更新状态")
    p_scan.add_argument("--json", action="store_true", help="同时输出 JSON 统计")
    p_scan.set_defaults(func=cmd_scan)

    p_pending = sub.add_parser("pending", help="导出待翻译清单")
    p_pending.add_argument("--split", type=int, default=0, help="拆分成 N 个文件（并行翻译用）")
    p_pending.add_argument("--outdir", default="", help="拆分文件输出目录（默认 ~/.skills-zh/translations）")
    p_pending.set_defaults(func=cmd_pending)

    p_check = sub.add_parser("check", help="只校验译文 JSON，不写状态")
    p_check.add_argument("files", nargs="+", help="译文文件或目录")
    p_check.add_argument("--strict", action="store_true", help="同时校验技能名确实存在于已扫描结果中")
    p_check.set_defaults(func=cmd_check)

    p_merge = sub.add_parser("merge", help="合并译文 JSON（文件或目录）")
    p_merge.add_argument("files", nargs="+", help="译文文件或目录")
    p_merge.set_defaults(func=cmd_merge)

    p_index = sub.add_parser("index", help="生成中文索引 index.md / index.json")
    p_index.add_argument("--out", default="", help="额外导出一份 markdown 到指定路径")
    p_index.set_defaults(func=cmd_index)

    p_apply = sub.add_parser("apply", help="给技能描述加中文标签")
    p_apply.add_argument("--dry-run", action="store_true", help="只演示，不写文件")
    p_apply.add_argument("--only", action="append", help="只处理指定技能名（可重复）")
    p_apply.set_defaults(func=cmd_apply)

    p_revert = sub.add_parser("revert", help="回滚中文标签")
    p_revert.add_argument("--dry-run", action="store_true", help="只演示，不写文件")
    p_revert.add_argument("--only", action="append", help="只处理指定技能名（可重复）")
    p_revert.add_argument("--force", action="store_true", help="即使标注后文件被改过也强制回滚")
    p_revert.set_defaults(func=cmd_revert)

    p_lookup = sub.add_parser("lookup", help="中文查询 -> 候选技能名")
    p_lookup.add_argument("query", nargs="+", help="中文/英文查询，例如：分子对接")
    p_lookup.add_argument("--limit", type=int, default=6, help="返回数量（默认 6）")
    p_lookup.add_argument("--json", action="store_true", help="输出 JSON")
    p_lookup.set_defaults(func=cmd_lookup)

    p_status = sub.add_parser("status", help="查看统计与健康状态")
    p_status.add_argument("--json", action="store_true", help="输出 JSON")
    p_status.set_defaults(func=cmd_status)

    p_verify = sub.add_parser("verify", help="校验标注/备份/索引一致性")
    p_verify.set_defaults(func=cmd_verify)

    p_ingest = sub.add_parser("ingest", help="整理下载或散落的技能包（支持 zip / 目录）")
    p_ingest.add_argument("path", help="技能包目录、SKILL.md 或 zip 文件")
    p_ingest.add_argument("--target", default="", help="安装目标根目录（默认 ~/.agents/skills）")
    p_ingest.add_argument("--force", action="store_true", help="覆盖同名技能")
    p_ingest.add_argument("--dry-run", action="store_true", help="只列出，不复制")
    p_ingest.add_argument("--verbose", action="store_true", help="打印目标路径")
    p_ingest.set_defaults(func=cmd_ingest)

    p_bundled = sub.add_parser("pull-bundled", help="把内置（只读）技能复制到用户根目录以便汉化")
    p_bundled.add_argument("--target", default="", help="目标根目录（默认 ~/.agents/skills）")
    p_bundled.add_argument("--force", action="store_true", help="覆盖已存在的同名副本")
    p_bundled.set_defaults(func=cmd_pull_bundled)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
