Current state:
The project has data/sample_emails/progress_report.eml.
Task:
Create app/sample_email_reader.py.
Requirements:
1. Read a local .eml file with Python's email package.
2. Extract MessageID, From, Subject, Date, and bodytext.
3. Prefer text/plain.
4. If only HTML exists, convert HTML into readable plain text.
5. Do not connect to the internet.
6. Do not print the entire email body to logs.
Return format:
{
 "message_id": "...",
 "sender": "...",
 "subject": "...",
 "date": "...",
 "bodytext": "...",
 "sourcepath": "..."
}
Acceptance tests:
- Works for text/plain email.
- Works for multipart email.
- Returns empty body_text instead of crashing if no readable body exists