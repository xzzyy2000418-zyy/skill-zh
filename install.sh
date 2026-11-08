#!/usr/bin/env bash
# 可选的本地安装脚本。
#
# 用法：
#   ./install.sh                    # 安装到 ~/.agents/skills/skill-zh
#   ./install.sh /path/to/skills    # 安装到指定技能根目录下的 skill-zh/
#
# 说明：如果已经 `git clone ... ~/.agents/skills/skill-zh`，则不需要运行本脚本。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$HOME/.agents/skills}"
DEST="$ROOT/skill-zh"

echo "源目录：$SRC"
echo "目标：  $DEST"

if [ "$SRC" = "$DEST" ]; then
  echo "已经在目标位置，无需安装。"
else
  mkdir -p "$ROOT"
  if [ -e "$DEST" ]; then
    BACKUP="$ROOT/skill-zh.backup-$(date +%Y%m%d-%H%M%S)"
    mv "$DEST" "$BACKUP"
    echo "已备份旧版本到：$BACKUP"
  fi
  mkdir -p "$DEST"
  tar -C "$SRC" --exclude='.git' --exclude='dist' --exclude='__pycache__' \
    -cf - . | tar -C "$DEST" -xf -
  echo "已复制到：$DEST"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import yaml' >/dev/null 2>&1; then
    echo "PyYAML 已就绪"
  else
    echo "提示：请安装 PyYAML：python3 -m pip install pyyaml"
  fi
  echo
  echo "下一步："
  echo "  cd \"$DEST\""
  echo "  python3 scripts/skill_zh.py doctor"
  echo "  python3 scripts/skill_zh.py init"
else
  echo "未找到 python3，请先安装 Python 3.8+。"
fi
