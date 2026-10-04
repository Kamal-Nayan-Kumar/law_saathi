#!/usr/bin/env bash
# Generate the remaining Law Saathi assets, one at a time, in the pinned
# ChatGPT chat. Serial on purpose: they all share ego page p1.
set -uo pipefail
cd "$(dirname "$0")/.."
RAW=/Users/nayan/Documents/projects/law_saathi/tmp/raw
mkdir -p "$RAW"

gen() {
  local name="$1"; shift
  echo "=== $name"
  python3 scripts/gpt_job.py --out "$RAW/$name.png" "$1" || echo "FAILED $name"
}

gen logo-mark "Create image: a minimal flat vector logo mark of balanced scales of justice drawn as clean line art. Deep maroon #6A131A strokes with marigold gold #D0792F accent on one pan. Perfectly centered, symmetrical, thick even rounded strokes, generous negative space, no fill shapes, no shading, no text, no background, plain white background. Simple, modern, memorable, app icon quality."

gen skyline "Create image: a wide horizontal silhouette band of Indian courthouse architecture in solid deep maroon #6A131A on a plain warm cream #FDF9F1 background. Left to right: a domed colonial court building with columns and a flag, a tall tiered temple-like courthouse tower, a long colonnaded wing, a smaller dome with a spire. Flat solid silhouette, no outlines, no gradients, no shading, no people, no text, no lettering, no words. The buildings sit on a common baseline along the bottom edge with plain cream sky above. Aspect ratio 21:9, very wide letterbox composition."

gen family-scales "Create image: flat vector editorial illustration, warm cream #FDF9F1 background. Seen from behind, an Indian family of three — a father in a light shirt, a mother in a coral and gold saree with long dark hair, and a young child in a mustard shirt between them — stand together looking at a large golden scales of justice silhouette. Behind the scales is a big warm gold sun disc. Gold and olive leafy branches frame the left and right edges. Flat geometric shapes, no gradients, no shadows, no text, no lettering, no words. Aspect ratio 1:1, square composition."

gen auth-scene "Create image: flat vector editorial illustration, warm cream #FDF9F1 background. A young Indian woman in a maroon kurta sits on a floor cushion holding a phone, smiling gently, with a soft peach circle behind her. Floating beside her are three small rounded cards containing simple icons: a scales of justice, a speech bubble, and a document. Gold leafy branch in the lower left corner, a small deep maroon courthouse dome silhouette in the upper right. Flat geometric shapes, no gradients, no shadows, no text, no lettering, no words. Aspect ratio 3:4, tall vertical composition."

gen chat-empty "Create image: flat vector editorial illustration, warm cream #FDF9F1 background. A simple friendly scales of justice in deep maroon #6A131A line art with marigold gold #D0792F pans, sitting inside a large soft peach circle, with two small rounded chat bubbles floating beside it, one blank. Gold leafy sprig at the bottom. Flat geometric shapes, thick even rounded strokes, no gradients, no shadows, no text, no lettering, no words. Aspect ratio 1:1, square composition, generous empty margins."

gen dashboard-hero "Create image: flat vector editorial illustration, warm cream #FDF9F1 background. A wide scene of a rising bar chart drawn in deep maroon #6A131A with one bar highlighted in marigold gold #D0792F, a rising trend line arcing above it, and a small trophy-like scales of justice at the top of the line. A deep maroon courthouse dome silhouette sits far in the background on the right, gold leafy branches at both edges. Flat geometric shapes, no gradients, no shadows, no people, no text, no lettering, no numbers. Aspect ratio 16:9, wide horizontal composition."

gen courtroom "Create image: flat vector editorial illustration, warm cream #FDF9F1 background. Interior of an Indian courtroom seen from the judge's bench looking out: a raised wooden bench in deep maroon #6A131A at the top with an empty chair, a national emblem circle in marigold gold #D0792F on the wall behind it, two lawyer tables with simple geometric figures seated at them in the lower half, a wooden railing across the front. Warm gold walls, high arched window shapes. Flat geometric shapes, no gradients, no shadows, no text, no lettering, no words. Aspect ratio 16:9, wide horizontal composition, symmetrical."

echo "=== batch done"
ls -la "$RAW"