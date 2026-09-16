# Scoring model

Prototype heuristic only. Weights are **not medically validated**.

Similarity = resemblance among available comparable fields.

Coverage = how much of the intended comparison model had usable data.

These are different concepts. Coverage is never mixed into the similarity score.

## Candidate pool vs scored fields

Alzheimer's disease and Phase III define the candidate pool. They are not similarity features.

Not scored: `study_span_months`, `outcome_class`, provenance (`amass_id`, `registry_id`, `source_registry`, `source_url`).

## Scored fields and weights

Relative weights from the original prototype after dropping disease (0.15) and phase (0.10), renormalized so remaining mass (0.75) sums to 1.0.

| Field | Weight | Type |
| --- | ---: | --- |
| Disease stage | 4/15 ≈ 0.2667 | Categorical |
| Biomarker strategy | 4/15 ≈ 0.2667 | Categorical |
| Primary endpoint | 3/15 = 0.2000 | Categorical |
| Duration (months) | 2/15 ≈ 0.1333 | Numeric (scale 18) |
| Sample size | 1/15 ≈ 0.0667 | Numeric (scale 2000) |
| Intervention | 1/15 ≈ 0.0667 | Categorical |

`intervention` remains a small leftover weight from the original target slot. It is a named product/compound/tracer, not a mapped biological target.

## Unknown handling

Missing, empty, `"unknown"`, or `"ambiguous: …"` on either side → status **unknown**. That field is excluded from the similarity denominator (not treated as a mismatch).

## Numeric similarity

`max(0, 1 − |protocol − historical| / scale)`

Duration is compared only when a semantically equivalent historical protocol/follow-up duration exists. Live TrialCore records leave `duration_months` empty; start/completion dates become `study_span_months` (evidence only).

## Aggregation

For comparable (non-unknown) fields:

`similarity = Σ (weight_i / Σ comparable weights) × field_score_i`

Rank order: similarity descending, then `trial_id` ascending.

## Coverage

```
comparison_coverage = sum(weights of comparable fields) / sum(weights of all similarity fields)
```

`comparable_feature_count` / `total_feature_count` is the unweighted field count (6 intended features).

Prototype low-coverage warning: `comparison_coverage < 0.50`.

## Endpoint canonicalization

Deterministic rules in `trialtwin/endpoints.py`. No LLM, embeddings, or fuzzy match.

Recognized families: CDR-SB, ADAS-Cog, MMSE, ADCS-ADL.

Unrecognized strings become `other: <original>`. Multiple distinct families stay `ambiguous:`.

The engine compares canonical `primary_endpoint`. Evidence shows `primary_endpoint_raw` when present.

## Live vs demo outcomes

Live TrialCore: outcome class is always `unknown` and is hidden in the UI.

Local JSON: demo outcome labels may be shown, marked as synthetic.
