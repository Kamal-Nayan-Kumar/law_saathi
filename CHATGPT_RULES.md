# CHATGPT_RULES.md

Rules for generating every Law Saathi visual asset with ChatGPT image generation.

## Where

One chat only: **Build Law Saathi Landing Page**
`https://chatgpt.com/c/6ac2af42-bd9c-83ec-90d3-c562bbd6fd55`

Never open or read any other personal chat. Never start a new chat for assets.

## How

```sh
python3 scripts/gpt_job.py --out web/public/images/<name>.png "<prompt>"
```

`scripts/gpt_job.py` stages the job and runs `scripts/gpt-asset.mjs` in ego task
space 6, page `p1`. It sends the prompt, waits for the new image, and downloads it.

Every prompt starts with the literal words `Create image:` so the model routes to
the image tool.

## Palette — always name these hex values

| Role | Hex | Used for |
| --- | --- | --- |
| Deep maroon | `#6A131A` | primary strokes, silhouettes, text |
| Darker maroon | `#4A0E13` | shadow side, skyline depth |
| Marigold | `#D0792F` | gold accent, highlight word |
| Warm cream bg | `#FDF9F1` | page background |
| Soft peach | `#F8E6DD` | icon discs, pill backgrounds |
| Muted ink | `#6C6765` | body copy |

Prompt shape: `flat vector editorial illustration, warm cream #FDF9F1
background, deep maroon #6A131A and marigold #D0792F palette, clean geometric
shapes, no gradients, no text, no lettering`.

## Hard constraints

1. **No text or lettering in the image.** Every word on the page is real HTML so
   it stays selectable, translatable and responsive. Floating question chips are
   the one exception and must say exactly what the prompt specifies.
2. **Aspect ratio must match the slot.** Say `16:9`, `4:5`, `1:1` explicitly.
3. **Transparent background** for the logo mark only. Everything else gets the
   cream background so it blends into the page with no visible edge.
4. **Flat vector, no gradients, no 3D, no drop shadows** unless asked. The page
   supplies all shadows in CSS.
5. **No people holding phones with readable UI** unless it is the hero chat card,
   where the bubbles are part of the composition.
6. Generate **one concept per prompt**. Do not ask for a grid of variants.

## What GPT generates vs what I hand-build

GPT is for **illustration and logo raster art only**:

- logo mark and lockup
- hero illustration
- courthouse skyline band
- family-and-scales illustration
- login/signup side art
- chat empty state
- dashboard and courtroom art

**UI icons are hand-built SVG, never generated.** AI raster icons are blurry,
inconsistent in stroke weight and impossible to recolour with CSS. Instead
`web/components/Icon.tsx` is a single hand-written sprite on one 24px grid with
one stroke weight, so every icon matches. That is what fixes the "icons look
forcefully made" problem.

## Existing assets and what replaces them

| Old file | Verdict | Replacement |
| --- | --- | --- |
| `hero-families.png` | page-background wash, fought the layout | `hero-scene.png`, placed in its own slot |
| `auth-side.png` | photo-ish, clashed | `auth-scene.png` |
| `chat-empty.png` | circular crop looked forced | `chat-empty.png`, un-cropped, sized to slot |
| `bare-act-texture.png` | filler | dropped; acts are text chips |
| `voice-mic.png` | unplaced photo | folded into hero scene |
| root-level copies (`auth-side.png`, `center.png`, …) | duplicates | deleted |

## Post-processing

Generated art is 1254px or 1536px square. Before use:

- crop to the exact slot ratio with Pillow (`scripts/prep_assets.py`)
- for the logo, key out near-white to alpha so it sits on any background
- keep files under ~200 KB by quantising to a 64-colour palette; these are flat
  vector-style images so palette reduction is visually free