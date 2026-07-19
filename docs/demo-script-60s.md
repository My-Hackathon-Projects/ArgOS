# 60s demo video — script v1 (iterating)

Funnel-first cut: problem -> thesis -> signals -> founder/claims -> memo -> decision.
Replaces the flow in `demo.md` for the main video (that file keeps the recording
mechanics + prep checklist; read it before recording).

Cherry-pick slots marked `[TBD]` — fill after picking the demo founder + opportunity.

## The cut

| # | Time | Screen | Action | Voiceover |
|---|---|---|---|---|
| 1 | 0-8s | Home `/` | Reload page, convergence animation runs, headline fades in. No cursor movement. | "Great founders are invisible until they know the right person. Their story is scattered across GitHub, papers, launches — and by the time a fund sees them, it's late. ArgOS watches for the trail." |
| 2 | 8-15s | Settings | Thesis form already filled. Add one chip (e.g. a sector), click Save, "Saved" flashes. | "You define the thesis once. Every signal, every score, every memo is filtered through it." |
| 3 | 15-25s | Sourcing | Feed live, pre-queued discovery run flashes new cards in. Filter one type, click a card -> raw source opens in new tab, cut back fast. | "Thirteen public channels, scanned continuously. Every signal resolves to a real person — and links back to its raw source." |
| 4 | 25-38s | Founders -> `[TBD founder]` | Open founders table, click `[TBD founder]`. Slow scroll: Founder Score + sparkline, claims with trust bars + supporting/refuting counts, reasoning trace. | "Every person gets a persistent Founder Score. Per-claim trust, backed by evidence — it follows them across startups and never resets." |
| 5 | 38-52s | Opportunity `[TBD deal]` | Open the screened deal: three axis cards (pause on disagreement if we have one), TAM/SAM/SOM with reported-vs-estimated chips, scroll into memo: cited hypotheses, flagged gaps. | "Three independent verdicts — founder, market, idea — never averaged. The memo cites every number, and flags what it doesn't know instead of inventing it." |
| 6 | 52-60s | Decision bar -> Home | Click Pursue. Latency stamp appears: "first signal -> decision in ...". Cut to home funnel cards + tagline. | "From first public signal to investment decision, in one sitting. ArgOS." |

## Timing notes

- 6 beats in 60s is tight. If a beat runs long, cut beat 2 (thesis) to a 2s drive-by:
  show the chips, no edit, line becomes "Filtered through your thesis."
- Beat 6 needs the deal fully screened + memo'd BEFORE recording, decision not yet
  made — the live Pursue click + latency stamp appearing is the money shot.
- Never show a spinner longer than a beat; pre-generate the memo off camera if slow.

## Cherry-pick criteria (for choosing `[TBD]`)

Founder: high score, >=6 claims with varied trust, >=2 score_history points
(sparkline needs 2+), diverse signal sources, clean name/story, no "unknown" fields.
Bonus: a refuting count or "needs review" badge visible — shows the trust layer.

Opportunity: all 3 axes screened, ideally disagreement (strong founder + neutral/bear
market), realistic TAM/SAM/SOM with basis chips, memo with resolved citations + gaps
list, NO decision recorded yet (we click it on camera).

## Prep delta vs demo.md checklist

1. Everything in `demo.md` prep applies (prod build, backend up, browser setup).
2. Queue `curl -X POST http://localhost:8000/discovery/run` ~30s before beat 3.
3. Verify `[TBD deal]` has screen + memo persisted, decision cleared.
4. Thesis form: pre-fill everything except the one chip added on camera.

## Voiceover-only (for practicing)

1. Great founders are invisible until they know the right person. Their story is
   scattered across GitHub, papers, launches — and by the time a fund sees them,
   it's late. ArgOS watches for the trail.
2. You define the thesis once. Every signal, every score, every memo is filtered
   through it.
3. Thirteen public channels, scanned continuously. Every signal resolves to a real
   person — and links back to its raw source.
4. Every person gets a persistent Founder Score. Per-claim trust, backed by
   evidence — it follows them across startups and never resets.
5. Three independent verdicts — founder, market, idea — never averaged. The memo
   cites every number, and flags what it doesn't know instead of inventing it.
6. From first public signal to investment decision, in one sitting. ArgOS.

~120 words total at voiceover pace ~= 55s. Fits, barely — practice with a timer.
