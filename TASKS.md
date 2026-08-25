Task:
Create an offline pipeline runner for SchoolMail Bridge.
Input:
data/sample_emails/progress_report.eml
Steps:
1. Parse local email.
2. Check salted HMAC duplicate fingerprint.
3. Detect terminology from config/terms.json.
4. Use a fake translator that returns structured Chinese placeholder output.
5. Save a translated artifact to runtime/translated_messages/.
6. Render a parentfacing Markdown message.
7. Save the rendered message into runtime/pushlog.jsonl.
8. Mark the email fingerprint as processed only after artifact and local log creation succeed.
Constraints:
 No real LLM API.
 No real mailbox.
- No WeCom webhook.
- Do not expose raw Message-ID in runtime files.
Return:
- app/pipeline.py;