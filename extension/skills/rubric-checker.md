---
name: rubric-checker
description: Check a short piece of writing against a simple four-point rubric and say what to fix.
---

# Rubric checker

1. Count the words in the text and write the number.
2. Write the main point of the text in one sentence of at most 20 words. If there is no clear main point, write "no clear main point".
3. Answer yes or no: does the text give at least one concrete example, number or name?
4. Answer yes or no: does the text end with a clear next step or conclusion?
5. Write one sentence of at most 25 words saying the most important thing to fix. If the text meets both yes/no points, write "nothing to fix".
6. Output JSON with exactly these keys: "word_count" (a number), "main_point", "has_example" ("yes" or "no"), "has_ending" ("yes" or "no"), "fix".
