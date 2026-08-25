#!/usr/bin/env bash
# Production live run: list up to 50 newest inbox messages, then translate the newest one.
# Usage (from repo root):
#   ./scripts/run_live_latest.sh
#   bash scripts/run_live_latest.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Hard cap: never list more than 50 messages.
LIST_LIMIT=50

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "==> Listing newest ${LIST_LIMIT} inbox messages..."
LIST_OUT="$("$PYTHON" -m app.pipeline --source live --list --limit "$LIST_LIMIT")"
printf '%s\n' "$LIST_OUT"

NEWEST_UID="$(
  printf '%s\n' "$LIST_OUT" \
    | awk 'NR>1 && $1 ~ /^[0-9]+$/ { print $1; exit }'
)"

if [[ -z "${NEWEST_UID}" ]]; then
  echo "ERROR: could not find a newest UID in the list output." >&2
  exit 1
fi

echo
echo "==> Translating newest message UID=${NEWEST_UID} (re-run allowed)..."
"$PYTHON" - <<PY
from pathlib import Path
import json
from dotenv import load_dotenv

load_dotenv(".env", override=True)

from app.mailbox import imap_session, fetch_message, load_imap_config
from app.email_identity import compute_fingerprint_from_email
from app.security import get_fingerprint_secret
from app import processed_store
from app.pipeline import run_pipeline_on_email, _print_result

uid = "${NEWEST_UID}"
cfg = load_imap_config()
with imap_session(cfg) as (client, c):
    email = fetch_message(client, uid, folder=c.folder)

secret = get_fingerprint_secret()
fp = compute_fingerprint_from_email(email, secret)

# Allow re-run: drop prior processed mark for this fingerprint only.
store_path = processed_store.DEFAULT_STORE_PATH
records = processed_store.all_records(store_path)
kept = [r for r in records if r.get("fingerprint") != fp]
if len(kept) != len(records):
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cleared previous processed mark for fingerprint={fp}")

result = run_pipeline_on_email(email, secret=secret)
_print_result(result)
print(f"  uid: {uid}")
print(f"  subject: {email.get('subject', '')}")
PY

echo
echo "Done. Artifacts:"
echo "  runtime/origin_messages/"
echo "  runtime/translated_messages/"
echo "  runtime/push_log.jsonl"
