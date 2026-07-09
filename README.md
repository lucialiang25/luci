# SchoolMail Bridge Kickoff Process Pack

This package contains the complete kickoff workflow for SchoolMail Bridge:

1. local mail file parse dry-run;
2. real mailbox retrieval planning;
3. terminology extraction with `config/terms.json`;
4. LLM English-to-Simplified-Chinese translation and structured extraction;
5. translated artifact storage;
6. WeCom/WeChat group push preparation;
7. security baseline using salted HMAC email fingerprints.

## Included files

```text
docs/SchoolMailBridge_Kickoff_Process_Guide.docx
docs/SchoolMailBridge_Kickoff_Process_Guide.pdf
docs/structured_prompts.md
config/terms.json
config/terms.sample.json
config/term.json
data/sample_emails/*.eml
templates/TASKS_TEMPLATE.md
TASKS.md
.env.example
requirements.txt
.gitignore
```

## First milestone

```text
local .eml file
-> parse email
-> detect school terms
-> fake Chinese translation
-> save translated artifact
-> write local push log
```

Do not connect the real mailbox, real LLM, or real WeCom group until the local dry-run works.
