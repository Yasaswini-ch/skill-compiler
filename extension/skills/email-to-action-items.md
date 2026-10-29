---
name: email-to-action-items
description: Turn a pasted email or message into a short list of action items with owners and dates.
---

# Email to action items

1. Write the sender's name exactly as it appears in the text. If no name appears, write "unknown".
2. Write a one-sentence summary of at most 20 words. Say what the sender wants.
3. List every task the text asks someone to do, one per line, each starting with "- ". If there are none, write "- none".
4. For each task, add the person responsible in brackets, for example "[Priya]". If the text does not say who, write "[unassigned]".
5. For each task, add the due date or deadline exactly as written, for example "(by Friday)". If the text gives none, write "(no date)".
6. Output JSON with exactly these keys: "sender", "summary", "tasks". The value of "tasks" is a list of strings, one per task, each with its owner and date.
