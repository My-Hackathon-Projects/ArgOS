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
| 1 | 0-7s | Home `/` | Reload page, convergence animation runs, headline fades in. No cursor movement. | "Great founders are invisible until they know the right person. Their story is scattered across hackathon participations, research papers, launches. ArgOS watches for the trail." |
| 2 | 7-12s | Settings | Drive-by: thesis chips visible (sectors/geo/stage/check), add ONE chip, Save flash. Fast. | "You set the investment thesis once — everything downstream is filtered through it." |
| 3 | 12-21s | Sourcing | Feed live, pre-queued discovery run flashes new cards in. Click a card -> raw source opens, cut back fast. | "Thirteen public channels, scanned continuously. Every signal resolves to a real person and links to its raw source." |
| 4 | 21-33s | Founders -> Christiam Ipanaque | Click Ipanaque. Scroll claims: trust bars, supporting counts — pause on the **contradicted claim** (red refuting count + Contradicted badge). | "Every person gets a persistent Founder Score. Per-claim trust, backed by evidence — and when sources conflict, it's flagged before it reaches you." |
| 5 | 33-45s | Opportunity: Ipanaque Labs | Three axis cards — bull founder / neutral idea / improving market — beat on the disagreement. TAM/SAM/SOM reported-vs-estimated chips, scroll into memo: cited hypotheses, evidenced Traction KPIs. | "Three independent verdicts. The disagreement IS the signal. And every number in the memo cites its evidence." |
| 6 | 45-53s | Opportunity: Ticky Tech memo | Cut to the contrast memo: cold-start founder, "No traction metric survives the evidence check", gaps list ("No revenue evidence"), "Not available at this stage" block. | "And when the evidence isn't there, ArgOS says so. No invented traction — flagged gaps, and still a recommendation you can act on." |
| 7 | 53-60s | Ipanaque decision bar -> Home | (Edit cut back to Ipanaque Labs.) Click **Track** — latency stamp appears. End on home funnel cards + tagline. | "From first public signal to decision, in one sitting. ArgOS." |

## Timing notes

- 7 beats in 60s is very tight — record each beat as its own clip, assemble in edit.
  If it doesn't fit: drop beat 2 (thesis) entirely before touching beats 5/6 —
  the memo contrast pair is the money shot, protect it.
- Beat 5 -> 6 is the brief's "a memo that marks its own gaps is more trustworthy"
  moment: evidenced traction (Ipanaque) vs honest empty state (Ticky Tech). Both
  memos exist and render clean, all citations resolved (conf 0.79 / 0.81).
- Beat 7 needs Ipanaque Labs screened + memo'd BEFORE recording, decision NOT yet
  made — the live Track click + latency stamp appearing closes the funnel.
- Never show a spinner longer than a beat; memos are pre-generated, don't regenerate
  on camera.

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
- Ticky Tech (beat 6): show the MEMO section only. Its decision is already recorded
  (track, ~376-day backdated latency) and status/decision may mismatch — keep the
  header/decision bar out of frame. Founder occupation is a pasted GitHub bio blob —
  don't show the founder header either.
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
   scattered across hackathon participations, research papers, launches. ArgOS watches for the trail.
2. You set the investment thesis once — everything downstream is filtered through it.
3. Thirteen public channels, scanned continuously. Every signal resolves to a real
   person and links to its raw source.
4. Every person gets a persistent Founder Score. Per-claim trust, backed by
   evidence — and when sources conflict, it's flagged before it reaches you.
5. Three independent verdicts. The disagreement IS the signal.
   And every number in the memo cites its evidence.
6. And when the evidence isn't there, ArgOS says so. No invented traction —
   flagged gaps, and still a recommendation you can act on.
7. From first public signal to decision, in one sitting. ArgOS.

~125 words at voiceover pace ~= 55-58s. Very tight — practice with a timer;
if over, cut line 2 first.
