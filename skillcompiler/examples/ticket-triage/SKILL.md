---
name: ticket-triage
description: Triage a customer support ticket and draft a reply.
---

# Ticket triage

1. Extract the customer's first name from the ticket.
2. Classify the ticket as exactly one of: billing, technical, account.
3. Rate urgency from 1 to 5 and give a reason in one sentence.
4. Draft a reply of at most 60 words. It must begin with "Hi <name>,".
5. Write an internal note that summarizes the issue in 10 words or fewer. It must start with "Internal note:".
6. Output everything as JSON with exactly these keys: name, category, urgency, reply, internal_note.
