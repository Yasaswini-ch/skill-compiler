# tasks.json is frozen

| | |
|---|---|
| File | `benchmark/tasks.json` (10 tasks) |
| Current SHA-256 | `53351f62f15b026cb6c653e43c591c60ce1b4877ba9f3522b1c6fba1f427bfd2` |
| Original freeze | 2026-10-28 12:02:44 +0530 (IST), SHA-256 `b0e7a62810f7fb07343fd816c453dde898d0c41becdff2de1a787561ee506adb` |
| Original note | **No plain run before this freeze.** |

The hash is of the file with LF line endings (`benchmark/.gitattributes` forces LF on every platform).
Verify with:

    python -c "import hashlib;print(hashlib.sha256(open('benchmark/tasks.json','rb').read()).hexdigest())"

Rule: do not edit, add or drop tasks after seeing plain's score. If a check is later found broken and is
fixed, record it below and in the dataset card, and update the hash with the date.

## Changes after the freeze

### 1. t06 eggs row (check c4), 2026-10-28 12:13:18 +0530 (IST)

| | |
|---|---|
| Old SHA-256 | `b0e7a62810f7fb07343fd816c453dde898d0c41becdff2de1a787561ee506adb` |
| New SHA-256 | `53351f62f15b026cb6c653e43c591c60ce1b4877ba9f3522b1c6fba1f427bfd2` |
| Change | One line. The eggs-row regex now accepts an optional trailing "eggs" in both columns: `2` or `2 eggs`, `7.0` or `7.0 eggs`. Nothing else in the file changed. |
| Tests | Both accepted forms pass; `7 eggs`, `8.0 eggs`, `3 eggs` and extra text still fail. |

**Baseline was seen before this fix. The check was over-strict (the skill says to keep the original quantity exactly as written). The fix applies equally to plain and harness.**

Effect: plain's t06 output (`| eggs | 2 eggs | 7.0 eggs |`) now passes. The baseline file was re-scored offline with the fixed check; no new API calls.
