---
name: candidate-screen
description: Screen a short resume against a minimum requirement and write a note for the recruiter.
---

# Candidate screen

1. Extract the candidate's full name.
2. Summarize the candidate's work experience in one sentence of at most 20 words.
3. Summarize the candidate's skills as a comma-separated list of at most 5 skills, with no brackets.
4. Extract the candidate's total years of experience as a single integer.
5. Decide whether the candidate meets the minimum requirement. The requirement is at least 3 years of experience and the skill "Python" in the resume. Answer "yes" or "no".
6. If the answer in step 5 is "no", give the reason in at most 10 words. If it is "yes", write "none".
7. Write a one-sentence note for the recruiter. It must begin with "Recommend:" and mention the candidate's first name.
8. Output JSON with exactly these keys: name, experience, skills, years, meets_minimum, reason, note.
