// Screenshot a local route at a list of viewport sizes.
//
//   node scripts/shots.mjs /              landing 1440 390
//   node scripts/shots.mjs /cases         cases   1440 768 390
import { mkdir, readFile, writeFile } from "node:fs/promises";

// The ego nodejs runtime passes neither the parent env nor extra CLI args, so
// the job arrives in scripts/.shot-job.json: { route, name, sizes: ["1440x900"] }
const job = JSON.parse(
  await readFile(
    "/Users/nayan/Documents/projects/law_saathi/scripts/.shot-job.json",
    "utf8",
  ),
);
const { route = "/", name = "page", sizes = ["1440x900"] } = job;
const BASE = "http://localhost:3000";
const OUT = "/Users/nayan/Documents/projects/law_saathi/tmp/shots";

const task = await taskSpace(6);
const page = task.page("p1");

await mkdir(OUT, { recursive: true });

for (const size of sizes) {
  const [w, h] = size.split("x").map(Number);
  await page.goto(BASE + route);
  await page.waitForTimeout(1200);
  // The viewport is set through CDP because the Page API has no setViewportSize.
  await page.cdp("Emulation.setDeviceMetricsOverride", {
    width: w,
    height: h,
    deviceScaleFactor: 1,
    mobile: w < 700,
  });
  await page.waitForTimeout(1400);

  const total = await page.evaluate(() => document.body.scrollHeight);
  const tiles = Math.min(12, Math.ceil(total / h));

  // Chromium's fullPage capture drops lazily-painted composited layers (the
  // hero artwork goes blank). Capturing one viewport per scroll position is
  // slower but renders exactly what a user sees.
  const paths: string[] = [];
  for (let i = 0; i < tiles; i += 1) {
    await page.evaluate((y) => window.scrollTo(0, y), i * h);
    // Let images in this band decode before the shot.
    await page.waitForTimeout(500);
    const p = `${OUT}/${name}-${w}-t${i}.png`;
    await page.screenshot({ path: p });
    paths.push(p);
  }

  const metrics = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
    brokenImgs: [...document.images]
      .filter((i) => !i.complete || i.naturalWidth === 0)
      .map((i) => i.currentSrc || i.src)
      .slice(0, 5),
  }));

  await writeFile(
    `${OUT}/${name}-${w}.json`,
    JSON.stringify({ route, size, total, tiles, paths, ...metrics }, null, 1),
  );

  console.log(
    JSON.stringify({
      route,
      size,
      overflow: metrics.scrollW > metrics.clientW + 1,
      scrollW: metrics.scrollW,
      clientW: metrics.clientW,
      brokenImgs: metrics.brokenImgs,
      tiles,
    }),
  );
}
await page.cdp("Emulation.clearDeviceMetricsOverride", {});