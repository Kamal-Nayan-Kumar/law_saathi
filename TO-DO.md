# TO-DO.md — Law Saathi frontend rebuild

Design source of truth: `Law Saathi_ Family Law Guidance.png`.
Asset rules: `CHATGPT_RULES.md`. Colour tokens: `web/app/globals.css`.

Legend: `[x]` done · `[~]` in progress · `[ ]` pending

---

## 0. Groundwork

- [x] Read the reference image and sample its actual pixel colours
- [x] Read current `web/` (landing, chat, login, admin, globals.css, Nav)
- [x] Map existing API surface (`routers_chat.py`) so the new pages only call real endpoints
- [x] Build the ChatGPT asset pipeline (`scripts/gpt_job.py`, `scripts/gpt-asset.mjs`)
- [x] Prove the pipeline end to end on a throwaway logo
- [x] Write `CHATGPT_RULES.md`
- [x] Write this file

## 1. Design tokens extracted from the reference

Sampled, not guessed:

| Token | Value | Where it came from |
| --- | --- | --- |
| `--bg` | `#FDF9F1` | dominant page pixel |
| `--maroon` | `#6A131A` | CTA band + primary buttons |
| `--maroon-deep` | `#4A0E13` | skyline shadow |
| `--gold` | `#D0792F` | the gold words in the h1 |
| `--peach` | `#F8E6DD` | feature icon discs |
| `--ink` | `#2F313F` | feature titles |
| `--muted` | `#6C6765` | body copy |
| `--line` | `#EADFD2` | card hairlines |
| `--cream-2` | `#FCF5EC` | stats strip, icon wells |

- [ ] Typography: display serif (Playfair Display) for headings, humanist sans
      (Plus Jakarta Sans) for body — matches the reference's serif/grotesque pair
- [ ] Single 8px spacing scale, single radius scale
- [ ] One focus ring, one shadow ladder

## 2. Proprietary icon + logo system

- [ ] `web/components/Icon.tsx` — hand-built SVG sprite, one 24px grid, one
      stroke weight, `currentColor` so icons recolour with context
- [ ] Every icon the site needs, on that one grid: scales, shield-check,
      document, users, mic, sparkle, globe, book, play, arrow, menu, close,
      chart, gavel, folder, check, lock, mail, eye, send, clock, target, flame
- [ ] `web/components/IconDisc.tsx` — the peach circular well the reference puts
      behind every icon, with the four colour variants it actually uses
- [ ] Logo mark generated from the reference (`logo-mark.png`) keyed to alpha
- [ ] Logo lockup component using the mark + the same two-tone wordmark
- [ ] Document the icon set in `web/components/Icon.tsx` header

Why hand-built icons and not generated: raster icons cannot be recoloured, scale
crisp, or share a stroke weight, which is exactly the "forcefully made" look.

## 3. Assets from ChatGPT

Generated in the pinned chat via `scripts/gpt_job.py`, then cropped and
compressed by `scripts/prep_assets.py`.

- [ ] `logo-mark.png` — scales mark, transparent
- [ ] `hero-scene.png` — hero illustration, woman at a laptop with a floating
      chat card, courthouse dome behind, 4:5
- [ ] `skyline.png` — courthouse skyline band, deep maroon silhouette on cream, 21:9
- [ ] `family-scales.png` — family of three from behind facing scales of justice,
      warm gold sun behind, 1:1
- [ ] `auth-scene.png` — login/signup side panel, 3:4
- [ ] `chat-empty.png` — chat empty state, scales + speech bubble, 1:1
- [ ] `dashboard-hero.png` — dashboard banner, 16:9
- [ ] `courtroom.png` — courtroom scene for the simulator, 16:9
- [ ] Delete loose root copies (`auth-side.png`, `center.png`, `voice-mic.png`, …)
- [ ] Delete `bare-act-texture.png` — filler with no slot
- [ ] Delete `docs/design/*.png` duplicates, keep the reference itself

## 4. Shared layout

- [ ] `web/app/Nav.tsx` — reference nav: logo left, 5 centred links, maroon pill
      CTA right, mobile hamburger sheet
- [ ] `web/app/Footer.tsx` — two rows: brand + links + socials, then copyright
      and legal links, hairline separated, exactly like the reference
- [ ] `web/components/Shell.tsx` — page width + rhythm wrapper so every page
      shares one container and one section spacing
- [ ] `web/components/Section.tsx` — eyebrow + serif h2 + lede, centred option
- [ ] `web/app/layout.tsx` — fonts, metadata, icon, Nav + Footer everywhere
      except `/chat`, `/dashboard`, `/simulator`, `/admin` which own their shell

## 5. Landing page — rebuilt to the reference

Section by section, in the reference's order:

- [ ] Hero: peach pill eyebrow, 3-line serif h1 with the gold phrase, lede,
      3 language pills (active = maroon), 2 buttons, illustration right
- [ ] Skyline band full-bleed under the hero
- [ ] 4 feature columns, peach icon disc + title + 2-line body, icon on top and
      title/body centred under it (reference alignment)
- [ ] Two-up: illustration left with floating question chips, copy right with a
      gold "WHY LAW SAATHI" eyebrow, serif h2, lede, 3 gold-tick checks
- [ ] Stats strip: 4 icon + value + label cells, hairline dividers
- [ ] How it works: centred eyebrow + h2, 4 steps on a dotted connector line,
      icon discs in 4 different pastel tints
- [ ] CTA band: deep maroon, serif headline, one white pill button, corner flourishes
- [ ] Footer

Also:
- [ ] Equal-height columns everywhere (`align-items: stretch`, flex column,
      `margin-top: auto` on the body text) so titles align on one baseline row
- [ ] Consistent 24px gap between icon disc and title in every card row
- [ ] Every illustration in a real slot with a fixed aspect ratio and
      `object-fit`, not just dropped in

## 6. Login / signup

- [ ] Split card: art left in a cream panel, form right
- [ ] Serif h2, muted sub, labelled fields (not bare placeholders)
- [ ] Language choice on signup (EN / HI / KN) — it drives the whole product
- [ ] Show/hide password with the house eye icon, 44px tap target
- [ ] Busy state, error state, mode switch that keeps `?mode=`
- [ ] Mobile: art becomes a short banner above the form

## 7. Dashboard — past performance

- [ ] `web/app/dashboard/page.tsx`
- [ ] Greeting header with the user's saved name and preferred language
- [ ] 4 stat tiles: questions asked, answers verified, topics covered, streak
- [ ] Line/area chart of questions asked per day, last 14 days (hand-built SVG)
- [ ] Horizontal bar chart of topics by share of questions
- [ ] Donut of language mix
- [ ] Written summary: a plain-English paragraph that reads the numbers out
- [ ] Recent activity list from real sessions
- [ ] Empty state when there is no data yet, with a link to `/chat`
- [ ] Responsive: 4 tiles → 2 → 1; charts stack

All charts hand-built SVG (`web/components/Charts.tsx`) so they use the house
palette and need no chart dependency.

## 8. Cases list

- [ ] `web/app/cases/page.tsx`
- [ ] Case cards: title, area tag, difficulty, duration, what it tests
- [ ] Filter by family-law area (divorce, custody, maintenance, DV, adoption,
      succession) and by difficulty
- [ ] Search box
- [ ] Each card links into preparation for that case
- [ ] Empty state when filters match nothing

## 9. Courtroom preparation

- [ ] `web/app/cases/[id]/page.tsx`
- [ ] Case brief: the facts, the parties, the legal issue in one sentence
- [ ] Applicable acts and sections for that case, as chips
- [ ] Key arguments for each side, with the citation behind each
- [ ] Documents checklist
- [ ] Likely judge questions
- [ ] "Start simulator" CTA
- [ ] Data in one typed file `web/lib/cases.ts` so the list and the detail page
      can never disagree

## 10. Courtroom simulator

- [ ] `web/app/simulator/page.tsx`
- [ ] Three columns exactly as asked: left = case info, centre = court, right =
      chat stream
- [ ] Centre: courtroom art, judge/parties, a live "round" indicator, and a
      running transcript of what has been said in court
- [ ] Left: case facts, applicable sections, a score panel
- [ ] Right: chat stream against the judge/AI, composer at the bottom
- [ ] Answer scoring: groundedness, citation, clarity — computed from the reply
      against the case's expected sections
- [ ] Session score summary at the end
- [ ] Responsive: 3 columns → stacked with tabs under 1100px; centre stays on top
- [ ] Persists the run so a reload does not lose it

## 11. Chat page — restyled, behaviour untouched

- [ ] Keep every existing behaviour: history sidebar, language detection,
      Thinking steps, Sources with tags, inline citation links, sign out
- [ ] Restyle to the new tokens: serif headings, peach discs, house icon set
- [ ] Empty state uses the new `chat-empty.png` in a proper slot
- [ ] Composer keeps the arrow-inside-pill pattern
- [ ] Mobile: off-canvas sidebar, 44px targets, no clipped wordmark

## 12. Responsive verification in a real browser

Checked in ego-browser at each width, screenshots compared to the reference.

- [ ] 360 × 740 (small phone)
- [ ] 390 × 844 (phone)
- [ ] 768 × 1024 (tablet)
- [ ] 1024 × 768 (small laptop)
- [ ] 1440 × 900 (laptop)
- [ ] 1920 × 1080 (big screen)
- [ ] 2560 × 1440 (ultra-wide)
- [ ] Landing: no horizontal scroll, columns collapse in the right order
- [ ] Login: art and form stack cleanly
- [ ] Dashboard: tiles and charts reflow
- [ ] Cases: filters wrap, cards go single column
- [ ] Simulator: three columns → tabs
- [ ] Chat: sidebar, composer, no overflow
- [ ] Nav collapses to a sheet on mobile

## 13. Cleanup

- [ ] Delete the "Legacy compat" CSS block and every class it kept alive
- [ ] Delete unused images
- [ ] Delete `.board` / `.dotgrid` / `hero-banner` / `acts-banner` leftovers
- [ ] `npm run typecheck` clean
- [ ] `npm run build` clean
- [ ] `docs/design.md` — where every asset came from and how to regenerate it
- [ ] Commit after each section

---

## Order of work

1. Tokens and icon system → 2. Assets → 3. Nav/Footer → 4. Landing →
   5. Login → 6. Chat restyle → 7. Dashboard → 8. Cases → 9. Prep →
   10. Simulator → 11. Responsive sweep → 12. Cleanup and commits

## Notes for future sessions

- Assets are generated through `scripts/gpt_job.py`, never by hand-copying from
  a browser. Do not open other ChatGPT chats.
- Charts are hand-built SVG on purpose. Do not add Recharts.
- `web/lib/cases.ts` is the single source for case data. Add a case there and it
  shows up in the list, the prep page and the simulator at once.