---
name: meeting-minutes
description: Turn a rough meeting transcript into structured minutes.
---

# Meeting minutes

1. Write the meeting title in 8 words or fewer.
2. List the attendees' first names, comma-separated, in alphabetical order.
3. Write the purpose of the meeting as one sentence of at most 25 words.
4. List every decision as a numbered list. Each decision must start with a verb.
5. List every action item as a list. Write each as "owner: task (due date)".
6. Name the single biggest open risk in 15 words or fewer.
7. Write a follow-up email subject line of at most 10 words. It must not contain the word "meeting".
8. Output everything as JSON with exactly these keys: title, attendees, purpose, decisions, actions, risk, subject.
