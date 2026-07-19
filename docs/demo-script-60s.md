# 60s demo video — script v1 (iterating)

Funnel-first cut: problem -> thesis -> signals -> founder/claims -> memo -> decision.
Replaces the flow in `demo.md` for the main video (that file keeps the recording
mechanics + prep checklist; read it before recording).

Cherry-pick (from DB inventory 2026-07-19): **Christiam Ipanaque -> Ipanaque Labs**.
Single subject through the whole funnel. Backup founder for the detail shot:
Vladimir Keil (rising sparkline 52.4->66.5, verified 0.89-trust claims).
Backup deal: Ticky Tech (cold-start story, bear market axis).

## The cut

| # | Time | Screen | Action | Voiceover |
|---|---|---|---|---|
| 1 | 0-8s | Home `/` | Reload page, convergence animation runs, headline fades in. No cursor movement. | "Great founders are invisible until they know the right person. Their story is scattered across GitHub, papers, launches — and by the time a fund sees them, it's late. ArgOS watches for the trail." |
| 2 | 8-15s | Settings | Thesis form already filled. Add one chip (e.g. a sector), click Save, "Saved" flashes. | "You define the thesis once. Every signal, every score, every memo is filtered through it." |
| 3 | 15-25s | Sourcing | Feed live, pre-queued discovery run flashes new cards in. Filter one type, click a card -> raw source opens in new tab, cut back fast. | "Thirteen public channels, scanned continuously. Every signal resolves to a real person — and links back to its raw source." |
| 4 | 25-38s | Founders -> Christiam Ipanaque | Open founders table, click Ipanaque. Slow scroll through claims: trust bars, supporting counts — pause on the **contradicted claim** ("Full Stack AI Engineer", red refuting count + Contradicted badge). | "Every person gets a persistent Founder Score. Per-claim trust, backed by evidence — and when sources conflict, it's flagged before it ever reaches you." |
| 5 | 38-52s | Opportunity: Ipanaque Labs | Open the deal: three axis cards — bull founder / neutral idea / improving market — pause a beat on the disagreement. TAM/SAM/SOM with reported-vs-estimated chips, scroll into memo: cited hypotheses, gaps list. | "Three independent verdicts — founder, market, idea — never averaged. The disagreement IS the signal. The memo cites every number, and flags what it doesn't know instead of inventing it." |
| 6 | 52-60s | Decision bar -> Home | Click **Track** (matches the memo's recommendation). Latency stamp appears: "first signal -> decision in ...". Cut to home funnel cards + tagline. | "From first public signal to investment decision, in one sitting. ArgOS." |

## Timing notes

- 6 beats in 60s is tight. If a beat runs long, cut beat 2 (thesis) to a 2s drive-by:
  show the chips, no edit, line becomes "Filtered through your thesis."
- Beat 6 needs the deal fully screened + memo'd BEFORE recording, decision not yet
  made — the live Pursue click + latency stamp appearing is the money shot.
- Never show a spinner longer than a beat; pre-generate the memo off camera if slow.

## Why Ipanaque -> Ipanaque Labs

- Only opportunity with all 3 axes + full memo + NO decision yet (live click works).
- Real axis disagreement: founder bull 44.5 / idea neutral 58 / market neutral 63
  improving — voiceover line "the disagreement is the signal" lands visually.
- Real sizing: TAM $30.2B (MarketsandMarkets, reported) / SAM $12.7B bottom-up /
  SOM $127M, CAGR 22.3%; memo `all_citations_resolved: true`, 11 gaps, 20 source URLs.
- Holds the DB's only contradicted claim WITH refute rationale — the trust moment.
- His claims span github / web / crunchbase signals; identity chips present.

## Keep OFF camera (blemishes on the chosen subjects)

- Ipanaque founder page: sparkline is EMPTY (0 history points) and trace timeline is
  EMPTY — do not scroll to them; stay on the claims list. Geo is inconsistent
  (city "Lima, Peru" vs Seattle claims). Signal list has filler entries
  ("Privacy policy updated") — don't linger on the timeline.
- Contradicted-claim refute rationale text ends in "(demo seed)". Verify the UI does
  not render that string anywhere visible before pointing the camera at the claim.
  If it does, show the red refuting count + badge only, collapsed.
- Memo provenance includes odd `scouts.yutori.com` URLs — don't zoom the source list.
- Founders table: sort so junk rows ("annu12340", org-as-founder "TUM.ai") are below
  the fold; Andreas Geiger (76.5) tops the table for the wide shot — fine.
- Opportunities list: duplicate NeuroForge (one rejected, one pursued) + Nimbus Edge
  (no founder linked) — go straight to Ipanaque Labs, don't dwell on the list.
- Sourcing channel sidebar: all channels show 0 yield — avoid close-up.

## Prep delta vs demo.md checklist

1. Everything in `demo.md` prep applies (prod build, backend up, browser setup).
2. Queue `curl -X POST http://localhost:8000/discovery/run` ~30s before beat 3.
3. Verify Ipanaque Labs still has screen + memo persisted and decision cleared —
   a parallel session mutates this DB; re-check axis values MINUTES before recording.
4. Check what latency stamp the Track click will produce (depends on his earliest
   signal date) — if it reads absurd (e.g. 300+ days like Ticky Tech's backdated
   signal), consider dropping the stamp from the shot and keeping only the decision.
5. Thesis form: pre-fill everything except the one chip added on camera.

## Voiceover-only (for practicing)

1. Great founders are invisible until they know the right person. Their story is
   scattered across GitHub, papers, launches — and by the time a fund sees them,
   it's late. ArgOS watches for the trail.
2. You define the thesis once. Every signal, every score, every memo is filtered
   through it.
3. Thirteen public channels, scanned continuously. Every signal resolves to a real
   person — and links back to its raw source.
4. Every person gets a persistent Founder Score. Per-claim trust, backed by
   evidence — and when sources conflict, it's flagged before it ever reaches you.
5. Three independent verdicts — founder, market, idea — never averaged. The
   disagreement IS the signal. The memo cites every number, and flags what it
   doesn't know instead of inventing it.
6. From first public signal to investment decision, in one sitting. ArgOS.

~120 words total at voiceover pace ~= 55s. Fits, barely — practice with a timer.
