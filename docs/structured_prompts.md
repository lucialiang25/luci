
# SchoolMail Bridge Structured Prompt Library

## Phase 0 - Environment Setup

```text
You are helping build a Python innovation project named SchoolMail Bridge.

Create a Python project structure with:
- app/
- config/
- data/sample_emails/
- runtime/translated_messages/
- runtime/logs/
- tests/

Create:
1. requirements.txt
2. .env.example
3. .gitignore
4. app/main.py that prints "SchoolMail Bridge environment ready."

Constraints:
- Do not include real credentials.
- Ignore .env and runtime/ in Git.
- Do not add MQTT, hardware, ESP32, or frontend code.
- Use Python 3.11+ compatible syntax.
```

## Phase 1 - Local .eml Dry Run

```text
Create an offline pipeline runner for SchoolMail Bridge.

Input:
data/sample_emails/progress_report.eml

Steps:
1. Parse local email.
2. Check salted HMAC duplicate fingerprint.
3. Detect terminology from config/terms.json.
4. Use a fake translator that returns structured Chinese placeholder output.
5. Save a translated artifact to runtime/translated_messages/.
6. Render a parent-facing Markdown message.
7. Save the rendered message into runtime/push_log.jsonl.
8. Mark the email fingerprint as processed only after artifact and local log creation succeed.

Constraints:
- No real LLM API.
- No real mailbox.
- No WeCom webhook.
- Do not expose raw Message-ID in runtime files.
```

## Phase 2 - Real Mail Account Retrieval

```text
Integrate one selected live email connector with app/pipeline.py.

Requirements:
1. Support two sources:
   - sample .eml file;
   - live provider email.
2. Normalize both source types into the same email object.
3. Run source -> duplicate check -> term detection -> fake translation -> local artifact -> local push log.
4. Add --source sample and --source live command-line options.
5. Add --message-id or provider message selector for live mode.
6. Do not enable real LLM or real group push in this session.
7. Never print or store OAuth/access/refresh tokens in logs or artifacts.
```

## Phase 3 - LLM Translation and Structured Extraction

```text
Create app/ai_translator.py.

Requirements:
1. Support AI_PROVIDER=fake and AI_PROVIDER=live.
2. For live mode:
   - load API key from .env;
   - use a timeout;
   - handle HTTP/API errors;
   - retry at most once for transient failure;
   - do not log API key or full raw email body.
3. Parse the LLM response as JSON.
4. Validate all required keys.
5. If JSON validation fails:
   - return review_only;
   - save a failure artifact;
   - do not allow group delivery.
```

## Phase 4 - WeCom Group Push

```text
Create app/wecom_push.py and integrate it with app/pipeline.py.

Workflow:
1. Generate validated translation artifact.
2. Check delivery_scope.
3. Render Markdown.
4. In PUSH_MODE=log, save to runtime/push_log.jsonl.
5. In PUSH_MODE=wecom_group, send only if delivery_scope == "group".
6. For private_parent or review_only, save for review and return status "not_auto_pushed".
7. Log salted email fingerprint, artifact path, delivery mode, push result, and timestamp.
8. Never log webhook secret.
```

## Phase 5 - Reliability and Final Demo

```text
Create final project documentation for SchoolMail Bridge.

Include:
1. problem statement;
2. target users;
3. system architecture;
4. privacy and security policy;
5. salted HMAC duplicate prevention;
6. real mailbox OAuth design;
7. terminology knowledge base;
8. AI translation and structured extraction;
9. delivery-scope policy;
10. WeCom test-group demonstration;
11. evaluation results;
12. limitations;
13. roadmap.

Do not include MQTT, IoT hardware, or ESP32.
```
