# mnn_age_policy_replay_v2 data dictionary

M4.1.1 patch of Age policy replay v1. Does not overwrite v1.

## Patch

Historical `not_applicable` without M2 approved gate is **not** a comparable
Age assertion and must not become `conflict`. Display=`unknown`,
decision=`insufficient_existing_evidence`.

`not_applicable` is allowed only via M2 approved reviewed policy.

## New field

| field | values |
|---|---|
| `historical_not_applicable_without_m2_gate` | `true` / `false` |
| `age_replay_policy_version` | `age_policy_replay_v2` |

## Queues

- `*_drug_age_review.csv` — non-M2 Age contract review; new labels empty
- `*_m2_non_drug_review.csv` — confirm `not_applicable` for M2 policy only
- `*_drug_age_pilot_sample.csv` — deterministic 40-row subset of the drug queue

Queues do not overlap. Pilot is a subset of the drug queue.
