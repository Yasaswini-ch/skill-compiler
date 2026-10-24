---
name: complaint-resolution
description: Analyse a customer complaint and prepare a response and escalation decision.
---

# Complaint resolution

1. Extract the customer's first name.
2. Extract the order number. Write it as "#" followed by digits only.
3. Extract the product name.
4. Classify the complaint as exactly one of: shipping, quality, billing, other.
5. Classify the customer's sentiment as exactly one of: angry, neutral, happy.
6. Rate severity from 1 to 5 as a single number.
7. State the root cause of the problem in one sentence.
8. List exactly 3 resolution options, one per line.
9. Recommend one of the 3 options and give the reason in 20 words or fewer.
10. Draft an apology reply of at most 80 words. It must begin with "Dear <name>," and must not contain the word "unfortunately".
11. Decide whether to escalate. Answer "yes" if severity is 4 or higher or sentiment is angry, otherwise "no".
12. Output everything as JSON with exactly these keys: name, order, product, category, sentiment, severity, cause, recommendation, reply, escalate.
