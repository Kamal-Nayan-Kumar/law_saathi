// Generate one image in a fixed ChatGPT chat, then download it.
//
// Generate one image in a fixed ChatGPT chat, then download it.
//
// The ego nodejs runtime inherits neither the parent environment nor extra CLI
// arguments, so the job is read from a fixed path: JOB_FILE holds
// { space, out, prompt, waitMs }.
//
//   printf '%s' '{"out":"/abs/a.png","prompt":"..."}' > scripts/.gpt-job.json
//   ego-browser nodejs < scripts/gpt-asset.mjs
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";

// import.meta.url is not the script path when the script arrives on stdin, so
// the repo location is spelled out. scripts/gpt_job.py writes the same path.
const JOB_FILE = "/Users/nayan/Documents/projects/law_saathi/scripts/.gpt-job.json";
const job = JSON.parse(await readFile(JOB_FILE, "utf8"));
const SPACE = Number(job.space || 6);
const out = job.out;
const prompt = job.prompt;
const waitMs = Number(job.waitMs || 180000);

const task = await taskSpace(SPACE);
const page = task.page("p1");

// Count images already in the chat so we can tell which one is new.
async function countImages() {
  return page.evaluate(
    () => document.querySelectorAll('button[aria-label^="Generated image"]').length,
  );
}

const before = await countImages();

await page.fill('textarea[name="prompt"], div[contenteditable="true"][role="textbox"]', prompt);
await page.keyboard.press("Enter");

// Generation takes 30-90s. Wait until a new image button appears.
const deadline = Date.now() + waitMs;
let after = before;
while (Date.now() < deadline) {
  await page.waitForTimeout(4000);
  const busy = await page.evaluate(() => {
    const b = document.querySelector('button[aria-label="Stop generating"]');
    return !!b;
  });
  after = await countImages();
  if (after > before && !busy) break;
  if (after > before && busy) {
    // keep waiting for streaming to settle
    continue;
  }
}
if (after <= before) {
  console.error("TIMEOUT: no new image appeared");
  process.exit(2);
}

await page.waitForTimeout(3000);
// The Nth generated-image button is the newest.
const idx = after - 1;
const buttons = await page.evaluate(() =>
  [...document.querySelectorAll('button[aria-label^="Generated image"]')].map((b) => {
    const img = b.querySelector("img");
    return { alt: img?.getAttribute("alt") || "", src: img?.currentSrc || img?.src || "" };
  }),
);
const target = buttons[idx];
if (!target?.src) {
  console.error("could not read image src", JSON.stringify(buttons.slice(-2)));
  process.exit(3);
}

await mkdir(path.dirname(out), { recursive: true });
const res = await page.fetch(target.src, { saveAs: out, timeout: 60000 });
console.log(JSON.stringify({ out, ok: res.ok, status: res.status, total: after }));