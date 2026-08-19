#!/usr/bin/env bash
# HGF CI 逻辑本地演练（V3.2.8）
# 模拟 .github/workflows/hgf-gates.yml 的核心步骤：
#   1. 取变更文件（相对 BASE_REF 的 git 差异）
#   2. 跑 workflow_cli --execute（门禁，退出码=门禁结果）
# 本地跑通即证明 CI 逻辑正确；推送到 GitHub 后由 Actions 触发。
#
# 用法: bash scripts/ci_simulate.sh [BASE_REF=HEAD~1] [--dir 工作目录]
set -euo pipefail

cd "$(dirname "$0")/.."
BASE_REF="${1:-HEAD~1}"
WD="."
PY="${PYTHON:-python}"

echo "== [CI 演练] 变更文件（$BASE_REF..HEAD）=="
FILES=$(git diff --name-only "$BASE_REF" -- '*.py' | tr '\n' ',' | sed 's/,$//')
if [ -z "$FILES" ]; then
  echo "changed files: (无 Python 变更，跳过门禁)"
  exit 0
fi
echo "changed files: $FILES"

echo "== [CI 演练] 运行 HGF 门禁 =="
OUT=$($PY workflow_cli.py --task "CI simulate" --files "$FILES" --lines 0 --dir "$WD" --execute --json 2>/dev/null)
RC=$?
echo "gate exit code: $RC"
echo "== 门禁摘要 =="
echo "$OUT" | grep -E '"success"|"level"|"passed"|"failed"' | head -4
exit $RC
