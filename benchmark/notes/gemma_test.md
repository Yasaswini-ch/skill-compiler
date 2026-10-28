# Gemma 4 manual test (Google AI Studio)

Written from what was actually seen in Google AI Studio on 28 Oct 2026. Tested by Likhitha.

| Field | Value |
|---|---|
| Date | 28 Oct 2026 |
| Model name (exact, as shown in AI Studio) | gemma-4-26b-a4b-it (Gemma 4 26B A4B IT) |
| Settings | Temperature 1. Thinking level: High. Grounding with Google Search: on. No other tools. This differs from the benchmark setup (MINIMAL thinking, no grounding), so these notes are an early look, not comparable to the measured results. |
| Number of runs | 4 |
| Prompt used | The 6-step support-ticket prompt from the team doc, Section 4. Run 1 used it exactly. In runs 2 to 4, step 4 read `Hi ,` instead of `Hi <name>,` because the `<name>` placeholder was lost when pasting. |
| Different tickets used | No. All 4 runs used the same ticket text (double charge plus can't log in). Only the name, order number and date changed (Ravi #4411, sita #0001, likks #0211, Mark #0411). |

## Per-run notes

### Run 1 (4:30 PM)

- Ticket used: Ravi, order #4411, 12 Oct (the exact Section 4 ticket)
- Skipped steps: none
- Merged steps: none
- Over a limit (word count etc.): none (reply 47 words, internal note 8 words)
- Wrong format (invalid JSON, wrong keys, wrong allowed value): output had an extra key, "urgency_reason", so it did not have exactly the five required keys
- Other: the internal_note value does not start with "Internal note:" (the prompt is ambiguous about this)

### Run 2 (4:40 PM)

- Ticket used: sita, order #0001, 1 Oct (same ticket text, step 4 altered as noted above)
- Skipped steps: none
- Merged steps: the urgency rating and its reason were put into one string field ("5 - Customer is facing double charges and card limit issues.")
- Over a limit (word count etc.): none (reply 41 words, internal note 8 words)
- Wrong format (invalid JSON, wrong keys, wrong allowed value): none clearly. Exactly the five required keys were present, and the category was "billing"
- Other: the internal_note value does not start with "Internal note:"

### Run 3 (4:42 PM)

- Ticket used: likks, order #0211, 2 July (same ticket text, step 4 altered as noted above)
- Skipped steps: none
- Merged steps: urgency rating and reason in one string field (same as run 2)
- Over a limit (word count etc.): none (reply 43 words, internal note 8 words)
- Wrong format (invalid JSON, wrong keys, wrong allowed value): none clearly. Exactly the five required keys were present
- Other: the internal_note value does not start with "Internal note:"

### Run 4 (4:45 PM)

- Ticket used: Mark, order #0411, 5 Sept (same ticket text, step 4 altered as noted above)
- Skipped steps: none
- Merged steps: urgency rating and reason in one string field (same as runs 2 and 3)
- Over a limit (word count etc.): none (reply 45 words, internal note 8 words)
- Wrong format (invalid JSON, wrong keys, wrong allowed value): none clearly. Exactly the five required keys were present
- Other: the internal_note value does not start with "Internal note:"

(Copy the block for more runs.)

## Summary

In 4 runs on one ticket type, Gemma 4 26B respected every length limit and always picked a valid category. The greeting rule ("Hi <name>,") was tested only in run 1; in runs 2 to 4 the prompt read "Hi ," so greeting compliance was not tested there (the replies still began with "Hi <name>,"). Run 1 added an extra "urgency_reason" key, and runs 2 to 4 merged the urgency rating and its reason into one string. This is an early look at a single ticket type, not a measured result. The measured benchmark numbers are in benchmark/RESULTS_NOTE.md.