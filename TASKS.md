Current state:
I have normalized email dictionaries from sample_email_reader.py.
Task:
Create:
1. config/terms.json
2. app/term_store.py
3. app/termdetector.py
terms.json fields:
 term
 zh
 explanation
 category
- priority
Detection requirements:
 Search both email subject and bodytext.
- Case-insensitive matching.
- Avoid duplicate term results.
- Return the complete matched terminology objects.
 Do not use an LLM for this step.
Include initial terminology:
PowerSchool, Progress Report, Counselor, PSAT, GPA, AP, Transcript, Advisory, Block Schedule, Late Start.
Acceptance tests:
- "Progress Report Available on PowerSchool" returns both Progress Report and PowerSchool.
- "AP" should not accidentally match letters inside "application
