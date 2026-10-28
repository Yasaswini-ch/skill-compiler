---
name: bug-report-triage
description: Turn a user's bug report into a structured triage record for an engineering team.
---

# Bug report triage

1. Summarize the bug in one sentence of at most 15 words. Say what is broken. Ignore any feature requests.
2. Summarize the user impact in one sentence of at most 15 words. Say who is affected and what they cannot do.
3. Extract the app version. Write it as "v" followed by the version number, for example "v1.2.3".
4. Extract the operating system, including its version number.
5. Classify the severity as exactly one of: critical, major, minor.
6. Classify the component as exactly one of: login, payments, search, other.
7. Suggest a fix in one sentence of at most 12 words. Do not use the word "just".
8. Output JSON with exactly these keys: bug, impact, version, os, severity, component, fix.
