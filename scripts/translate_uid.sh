#!/usr/bin/env bash
# Translate one live inbox message by IMAP UID (from a prior list).
#
# Usage (from repo root):
#   ./scripts/translate_uid.sh 10041
#
# Tip: get UIDs first with:
#   ./scripts/list_emails.sh 20
#
# Writes:
#   runtime/origin_messages/<fingerprint>.json
#   runtime/translated_messages/<fingerprint>.json
#   runtime/push_log.jsonl

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UID_ARG="${1:-}"
if [[ -z "$UID_ARG" ]]; then
  echo "ERROR: missing UID." >&2
  echo "Usage: $0 <imap-uid>" >&2
  echo "Example: $0 10041" >&2
  if [[ -f runtime/email_list_latest.txt ]]; then
    echo >&2
    echo "Latest saved list (runtime/email_list_latest.txt):" >&2
    sed -n '1,15p' runtime/email_list_latest.txt >&2
  fi
  exit 1
fi

if ! [[ "$UID_ARG" =~ ^[0-9]+$ ]]; then
  echo "ERROR: UID must be numeric (got: ${UID_ARG})" >&2
  exit 1
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "==> Translating UID=${UID_ARG} ..."
"$PYTHON" -m app.pipeline --source live --uid "$UID_ARG"

echo
echo "Done. Check:"
echo "  runtime/origin_messages/"
echo "  runtime/translated_messages/"
echo "  runtime/push_log.jsonl"
