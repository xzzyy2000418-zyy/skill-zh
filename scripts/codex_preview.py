#!/usr/bin/env python3
"""Read-only skill catalog for the Codex desktop plugin."""

import argparse
import json
import os
import sys
from pathlib import Path

import skill_zh

HTML_FILE = Path(__file__).resolve().parent.parent / "preview" / "catalog.html"
URI = "ui://skill-zh/catalog"
MIME_TYPE = "text/html;profile=mcp-app"
TOOL_NAME = "open_skill_catalog"
TOOL = {
    "name": TOOL_NAME,
    "title": "打开中文技能目录",
    "description": "打开本机中文技能目录，浏览和搜索技能。只读取技能说明和已有的汉化记录。",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
    "_meta": {
        "ui": {"resourceUri": URI},
        "openai/ui": {"entrypoints": [{"type": "global"}, {"type": "thread"}]},
    },
}
RESOURCE = {"uri": URI, "name": "中文技能目录", "mimeType": MIME_TYPE}
PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}


def read_index():
    try:
        data = json.loads(skill_zh.INDEX_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError):
        return {}, "已有索引无法读取。可在本地 Agent 中重新生成中文索引。"
    if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
        return {}, "已有索引格式有误。可在本地 Agent 中重新生成中文索引。"
    return data["categories"], ""


def local_catalog():
    categories, notice = read_index()
    entries = {}
    for category, items in categories.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            path = item.get("path")
            if isinstance(path, str) and not Path(path).is_file():
                continue
            entries[item["name"]] = {
                "name": item["name"],
                "label": item.get("label") or "",
                "summary": item.get("summary") or "",
                "keywords": item.get("keywords") or [],
                "status": item.get("status") or "",
                "category": category,
            }

    if skill_zh.yaml is not None:
        home = Path.home()
        codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser()
        claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser()
        extra_roots = [str(root / "skills") for root in (codex_home, claude_home, home / ".cursor")]
        # Anchor the discovery at the user's home. Codex can launch the server from its cache.
        scan = skill_zh.scan_skills(home, extra_roots)
        for name, item in scan["skills"].items():
            description, label = skill_zh.strip_label(item["description"])
            entry = entries.setdefault(name, {
                "name": name, "label": "", "summary": "", "keywords": [],
                "category": "未分类", "status": "",
            })
            if not entry["label"]:
                entry["label"] = label or ""
            if not entry["summary"]:
                entry["summary"] = description[:240]
            if not entry["status"]:
                entry["status"] = "已是中文" if label else "待翻译"
                if not item["writable"]:
                    entry["status"] = "内置只读" if item["source"] == "bundled" else "只读"
    elif not entries and not notice:
        notice = "首次扫描需要 PyYAML。安装后可刷新目录，也可以从已有的中文索引打开。"

    return {"skills": sorted(entries.values(), key=lambda item: item["name"]), "notice": notice}


def export_html(path):
    catalog = json.dumps(local_catalog(), ensure_ascii=False).replace("<", "\\u003c")
    html = HTML_FILE.read_text(encoding="utf-8").replace(
        '<script type="application/json" id="snapshot"></script>',
        '<script type="application/json" id="snapshot">' + catalog + "</script>",
        1,
    )
    # Avoid replacing an existing file, including a previous export.
    with path.open("x", encoding="utf-8") as output:
        output.write(html)
    print(path.resolve())


def reply(request):
    method = request.get("method")
    params = request.get("params") or {}
    if method == "initialize":
        version = params.get("protocolVersion")
        return {
            "protocolVersion": version if version in PROTOCOL_VERSIONS else "2025-11-25",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "skill-zh-catalog", "version": "1.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "resources/list":
        return {"resources": [RESOURCE]}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "resources/read" and params.get("uri") == URI:
        return {"contents": [{
            "uri": URI, "mimeType": MIME_TYPE, "text": HTML_FILE.read_text(encoding="utf-8"),
        }]}
    if method == "tools/call" and params.get("name") == TOOL_NAME:
        catalog = local_catalog()
        summary = "中文技能目录共收录 {} 个技能。".format(len(catalog["skills"]))
        return {
            "content": [{"type": "text", "text": " ".join(filter(None, [summary, catalog["notice"]]))}],
            # Catalog details are for the viewer. The model only needs the summary.
            "_meta": {"catalog": catalog},
        }
    if method in {"resources/read", "tools/call"}:
        return None
    raise NotImplementedError


def serve():
    for line in sys.stdin.buffer:
        response = {"jsonrpc": "2.0", "id": None}
        try:
            request = json.loads(line)
        except ValueError:
            response["error"] = {"code": -32700, "message": "Parse error"}
        else:
            if not isinstance(request, dict) or "method" not in request:
                response["error"] = {"code": -32600, "message": "Invalid request"}
            elif "id" not in request:
                continue
            else:
                response["id"] = request["id"]
                try:
                    result = reply(request)
                    if result is None:
                        response["error"] = {"code": -32602, "message": "Invalid params"}
                    else:
                        response["result"] = result
                except NotImplementedError:
                    response["error"] = {"code": -32601, "message": "Method not found"}
                except (AttributeError, TypeError, ValueError):
                    response["error"] = {"code": -32602, "message": "Invalid params"}
                except OSError:
                    response["error"] = {"code": -32603, "message": "Cannot read catalog"}
        # ASCII JSON keeps stdout portable on Windows even without PYTHONUTF8.
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, metavar="NEW_FILE", help="导出可离线打开的目录")
    options = parser.parse_args()
    if options.html:
        export_html(options.html)
    else:
        serve()
