Task:
Connect Gmail IMAP and run live list + one local translation.
Files:
- app/mailbox.py
- app/pipeline.py
- app/sample_email_reader.py
Commands:
1. python -m app.pipeline --source live --list
2. python -m app.pipeline --source live --uid <UID>
Constraints:
- Use Gmail App Password (not account password).
- Fake translator only — no real LLM / WeCom.
- Never store raw Message-ID or app password in runtime artifacts.
