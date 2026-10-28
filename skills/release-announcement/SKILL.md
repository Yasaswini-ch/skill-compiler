---
name: release-announcement
description: Write a short product announcement from a product name, a release date and three features.
---

# Release announcement

1. Extract the product name.
2. Extract the three main features from the input.
3. Write a headline of at most 8 words. It must begin with "Meet the" and must not contain the word "revolutionary".
4. Write a one-sentence summary of at most 25 words. Do not use the words "revolutionary", "game-changing" or "cutting-edge".
5. Write exactly 3 bullet points, one per feature, each at most 10 words.
6. Write a closing line that begins with "Available" and contains the release date written as DD/MM/YYYY.
7. Write exactly 2 hashtags in lowercase, separated by one space, each starting with "#".
8. Output JSON with exactly these keys: headline, summary, bullets, closing, hashtags. The value of "bullets" is an array of 3 strings and the value of "hashtags" is one string.
