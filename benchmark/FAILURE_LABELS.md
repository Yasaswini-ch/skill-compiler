# Failure labels

Every failure in the dataset carries exactly one of these 7 labels. The definitions are from Section 2.5 of the team work-split document.

The scorer sets a label automatically (the label written on the first failed check of the task). A person then reviews each failure and can override it in `label_overrides.json`. The label in `failures.json` is the reviewed one; the scorer's own label is kept in `results.json` as `scorer_label` when it was changed.

Examples below come only from real failures in `output/failures.json` (the official run 1). Where none was observed, it says so.

| Label | Meaning | Real example |
|---|---|---|
| `skipped_step` | A required step's output is missing. | No real example observed yet. |
| `wrong_format` | Output is not in the required format (invalid JSON, wrong allowed value, wrong structure). | **f001**, task t03, harness: the skill says to answer `"yes"` or `"no"`, the output has `"meets_minimum": false` (a boolean). **f004**, task t08, plain: the beef row is `\| beef mince \| 1000 g \| 0.3 kg \|`; the 1000 g to kg rule was applied to 250 g, and the expected cell is `250.0 g`. |
| `lost_track` | Later steps contradict or forget earlier steps' results. | No real example observed yet. |
| `merged_steps` | Two steps were blended into one output. | No real example observed yet. |
| `hallucinated_step` | The model added a step or content that the skill never asked for. | No real example observed yet. |
| `ignored_constraint` | A limit or rule was broken (word count, required phrase, forbidden word). | No real example observed yet. |
| `other` | Anything else. Review these by hand. | **f002**, task t04, plain: `"subtotal": "157.75"` where the correct value is 150.75, and tax and total follow the wrong subtotal. **f003**, task t05, plain: `"subtotal": "462.78"` where the correct value is 485.98. Both are arithmetic errors, which have no label of their own. |

## Notes

- The scorer first labelled f001, f002 and f003 `lost_track`. After hand review they became `wrong_format` (f001) and `other` (f002, f003), because the model made an arithmetic or format mistake rather than forgetting an earlier step. So `lost_track` still has no real example.
- Five of the seven labels have no real example yet. The 10 tasks are a small sample, and this list will change if more failures are collected (for example from the generated tasks or from submitted failures).
- A label describes the first problem found, not everything that went wrong. See `what_went_wrong` and `failed_checks` in each failure for the full detail.
