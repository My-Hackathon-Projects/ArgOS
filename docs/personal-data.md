# Personal data in ArgOS — what we hold, and why erasure does not work yet

ArgOS builds a persistent, per-person Founder Score from public footprint. That is the product,
and it is also the reason this document exists: the system stores identifiable information about
living people who never applied to us, and it is designed so that record *never resets*.

**Status: documented, not implemented.** No erasure path is built. This is the map of what would
have to be decided first — the decisions are the human's, not the agent's.

## What is stored, and where it came from

| Table | Personal data | Origin |
|---|---|---|
| `founder` | name, city + resolved place, occupation, employer, education history | outbound discovery (agent search), or an inbound deck |
| `identity` | GitHub / LinkedIn / Twitter / ORCID / website / email | extracted from public profiles and pages |
| `founder_alias` | every name spelling ever seen for the person | resolution |
| `signal` | the artifact itself — URL, title, summary, and `raw`, the **full source payload** | connectors |
| `claim` + `claim_evidence` | assertions about the person, each with cited evidence | claims engine |
| `score_history` | the Founder Score time series | scoring |
| `trace_step` | what each agent node did with this person's data | screening/memo |
| `founder_resolution_review` | that this mention was held apart from another person, and why | resolver |
| `entity_merge` | that two rows were judged one human | reconciliation |

3,322 of 3,323 `signal` rows carry a non-null `raw`.

Two legal bases are in play and they are not the same. An **inbound** founder sent us a deck: that
is a relationship they initiated. An **outbound** founder was discovered by an agent and has no
idea the record exists — no notice, no consent, and (Art. 14 GDPR) a notification duty we do not
currently discharge. `opportunity.source` distinguishes the two.

## Why "delete the founder" does not work

Every FK into `founder`, as it stands:

```
CASCADE   claim, founder_alias, founder_company, founder_signal, identity,
          score_history, trace_step, founder_resolution_review.founder_id
SET NULL  entity_merge.canonical_founder_id, entity_merge.merged_founder_id,
          founder_resolution_review.counterpart_founder_id
RESTRICT  opportunity.founder_id
```

**A founder with a deal cannot be deleted at all.** `opportunity.founder_id` is `RESTRICT`, and
deliberately so — ArgOS is founder-first and a founderless opportunity is not a thing the schema
permits. So the erasure path for exactly the people we know best is blocked by the invariant that
makes the product work.

**The obvious fix destroys the fund's own record.** Switching that FK to CASCADE takes the
opportunity with the founder, and `claim`, `three_axis`, `memo` and `trace_step` all cascade off
the opportunity in turn. That deletes the investment memo, the three-axis verdict and the decision
— the fund's own work product and, where a deal was rejected, its record of *why*. A memo is not
the founder's personal data merely because it is about them.

**`signal.raw` has no retention policy.** It is the full source payload, kept for provenance and
re-extraction. Nothing ages it out and nothing distinguishes the part that is evidence from the
part that is incidental personal data about third parties named in the same page. A signal is also
shared: `founder_signal` is many-to-many by design, so one artifact can be evidence about several
founders and deleting it on one person's request removes another person's evidence.

**Erasure leaks through the audit trail.** `entity_merge` and `founder_resolution_review` are
deliberately append-only — that is the point of `merged_founder_ref` and `canonical_founder_ref`,
which survive the FK being nulled. They are how a wrong merge is discovered and reversed. They are
also a durable record that a specific person existed in the system, surviving their deletion.

**Handles reach the logs.** `app/maintenance/audit_identity.py` prints offending rows, which
includes GitHub/LinkedIn/Twitter handles and founder ids, into whatever captures cron output. So
does the new per-merge log line in `reconcile.merge_founders`, which names both people. Log
retention is not managed anywhere in this repo.

## The decisions that have to be made first

1. **Erasure vs. anonymisation.** Deleting the person destroys the fund's memos; anonymising in
   place (drop `identity`, `founder_alias`, name, city; keep the row and its scores under an
   opaque id) preserves them but keeps a profile that is arguably still personal data given how
   few people match "PhD, robotics, Munich, 2024".
2. **Tombstones.** Erasure without a record of it means the next discovery run re-creates the
   person from the same public sources. A suppression list is the only thing that prevents that —
   and it is itself a permanent record of the person, which needs its own justification.
3. **`signal.raw` retention.** A TTL, or a "keep the extract, drop the payload" rule after claims
   are minted. Neither exists.
4. **Notice for outbound founders.** Whether Art. 14 notification is discharged, deferred under an
   exemption, or the outbound funnel is restricted to sources where it does not apply.
5. **Log hygiene.** Whether the audit and merge logs may carry handles at all, or must emit ids
   only, with the values available on demand.

Until (1) is decided nothing else can be built: every other item depends on whether a founder row
is destroyed or emptied.
