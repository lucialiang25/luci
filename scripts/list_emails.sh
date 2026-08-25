#!/usr/bin/env bash
# List newest inbox messages (UID + date + subject).
#
# Usage (from repo root):
#   ./scripts/list_emails.sh           # default: 20
#   ./scripts/list_emails.sh 10        # list newest 10
#   ./scripts/list_emails.sh 50        # list newest 50 (hard max)
#
# Also writes a copy to: runtime/email_list_latest.txt

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MAX_LIMIT=50
LIMIT="${1:-20}"

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [[ "$LIMIT" -lt 1 ]]; then
  echo "ERROR: limit must be a positive integer (got: ${LIMIT})" >&2
  echo "Usage: $0 [limit]" >&2
  exit 1
fi

if [[ "$LIMIT" -gt "$MAX_LIMIT" ]]; then
  echo "WARN: requested ${LIMIT}, capped to hard max ${MAX_LIMIT}." >&2
  LIMIT="$MAX_LIMIT"
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p runtime
OUT_FILE="runtime/email_list_latest.txt"

echo "==> Listing newest ${LIMIT} inbox messages..."
LIST_OUT="$("$PYTHON" -m app.pipeline --source live --list --limit "$LIMIT")"
printf '%s\n' "$LIST_OUT" | tee "$OUT_FILE"

echo
echo "Saved list to ${OUT_FILE}"
echo "Next: pick a UID from the list, then run:"
echo "  ./scripts/translate_uid.sh <UID>"
