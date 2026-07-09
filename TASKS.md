Task:
Create secure duplicate prevention for SchoolMail Bridge.
Files:
- app/security.py
- app/email_identity.py
- app/processed_store.py
Requirements:
1. Load EMAILFINGERPRINTSECRET from .env.
2. Build an in-memory identity using Message-ID when present.
3. Fall back to sender + subject + date only when Message-ID is absent.
4. Generate HMACSHA256 using EMAIL_FINGERPRINT_SECRET.
5. Store only:
 - fingerprint
 - processedat
 - artifactpath
6. Never store raw Message-ID in runtime/processed_emails.json.
7. Never hash or salt OAuth/access/refresh tokens. Those tokens must remain usable and are stored separately as secrets.
8. Add clear errors when the secret is absent or shorter than 32 characters.
Acceptance tests:
- Same email + same secret gives the same fingerprint.
- Same email + different secret gives a different fingerprint.
- processedemails.json contains no raw Message-ID.