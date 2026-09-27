Task:
Connect Gmail IMAP and run live list + one local translation.
Files:
- app/mailbox.py
- app/pipeline.py
- app/sample_email_reader.py
Commands:
0. python -m app.gmail_oauth   (one-time browser authorization)
1. python -m app.pipeline --source live --list
2. python -m app.pipeline --source live --uid <UID>
Constraints:
- Log in with Gmail OAuth 2.0 (IMAP XOAUTH2); never the account password.
- Keep the OAuth client file and refresh token in .secrets/ (gitignored), never in runtime/.
- Fake translator only — no real LLM / WeCom.
- Never store raw Message-ID or app password in runtime artifacts.
