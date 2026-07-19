# Demo guide: the 60-second UI/UX video

How to record the demo video so the product flow carries the story. The target is the
UI/UX showcase video: user experience and product flow, 60 seconds.

## Prep checklist (10 minutes before recording)

1. **Run the production build, not the dev server.** The dev server shows the Next.js
   dev-tools badge in the corner and is slower on first paint.

   ```bash
   cd frontend
   npm run build
   npm start          # serves :3000 without the dev overlay
   ```

2. **Backend up with real data.** From the repo root: `docker compose up -d`, then from
   `backend/`: `uv run python -m uvicorn app.main:app`. Check <http://localhost:8000/health>
   shows a few hundred signals. The founders table and both market analyses
   (OpenDriveLab, Nimbus Edge) should already be in the DB.

3. **Queue fresh signals for the live moment.** The feed polls every 5 seconds and flashes
   new arrivals. About 30 seconds before you record the sourcing segment, trigger:

   ```bash
   curl -X POST http://localhost:8000/discovery/run
   ```

   The run takes 30 to 60 seconds, so cards will flash in on camera while you talk.

4. **Browser setup.** Fresh window, hidden bookmarks bar, 1280x800 or larger recording
   region, 100 percent zoom. Close other tabs. macOS: hide the dock if it clips.

5. **The intro animation replays on every load of `/`.** Each take starts by reloading the
   home page; the convergence animation runs for about 4 seconds, then the canvas fades.

## The 60-second cut

| Time | Screen | Action and voiceover |
|---|---|---|
| 0-6s | Home `/` | Page loads, signal particles converge into the hero, headline fades in. Voiceover: "Great founders leave a public trail long before they raise. VC Brain watches for it." |
| 6-18s | Sourcing | Show the live heartbeat and the feed. New signals flash in (from the discovery run you queued). Filter to Funding, click a card: it opens the real source. "Thirteen public channels, resolved to real people, every signal traceable to its source." |
| 18-30s | Founders | Search "max planck", sort by Signals, open a founder. Point at education, identity links, the timeline, discovery confidence. "Every person gets a resolved profile and an auditable confidence score." |
| 30-45s | Market Research | Switch opportunities with the picker. Show the axis score, TAM/SAM/SOM cards with reported versus estimated chips, then the flagged gaps card. "The research agent cites every number, and flags what it does not know instead of inventing it." |
| 45-55s | Any page, narrow window | Drag the window narrow or show a phone frame: nav collapses to the menu, table becomes cards. "The whole funnel, on any screen." |
| 55-60s | Home `/` | End on the funnel cards and the tagline. "Sourcing to decision. VC Brain." |

## Recording mechanics

- Slow, deliberate cursor. One action per sentence of voiceover.
- Record more than you need and cut dead time; never show a loading spinner longer
  than a beat.
- The page transitions and the sort/filter animations read best at normal speed; do not
  speed-ramp the UI segments.
- Record the sourcing segment first if you are worried about discovery timing, then film
  the rest; order the clips in the edit.

## Where the demo-critical pieces live

- Intro animation: `frontend/src/components/home/convergence-hero.tsx` (canvas swarm,
  colors from `lib/source-style.ts`, respects reduced motion, `RUN_MS` sets duration).
- Live feed flash-in: `frontend/src/components/sourcing/signal-feed.tsx` (5s poll).
- Filters, search, sort: `sourcing/type-filter.tsx`, `founders/founder-toolbar.tsx`,
  `founders/sort.ts`.
- Basis chips and gap flags: `frontend/src/components/market/meta.tsx`, `gaps-card.tsx`.

## The other two videos

- **Tech video**: walk the pipeline in data-flow order using `docs/claims-layer.md` and
  `docs/market-layer.md`; show the FE/BE contract (`openapi.json` to generated hooks) as
  the engineering highlight.
- **Team video**: the About Us section on the home page mirrors it: three founding
  engineers, names, LinkedIn.
