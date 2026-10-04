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

// The newest generated image is the last generated <img> in the thread. Older
// turns get virtualised out of the DOM as the thread grows, so counting them is
// unreliable — comparing the tail src is not. The src is a blob: URL, so it can
// only be fetched from inside the page.
async function lastSrc() {
  return page.evaluate(() => {
    const imgs = [...document.querySelectorAll("img")].filter((i) =>
      /^Generated image/i.test(i.alt || ""),
    );
    const last = imgs[imgs.length - 1];
    return last ? last.currentSrc || last.src || "" : "";
  });
}

const before = await lastSrc();

await page.fill('textarea[name="prompt"], div[contenteditable="true"][role="textbox"]', prompt);
await page.keyboard.press("Enter");

// Generation takes 30-90s. Wait for the tail image src to change, then for the
// stream to settle.
const deadline = Date.now() + waitMs;
let src = "";
while (Date.now() < deadline) {
  await page.waitForTimeout(4000);
  const busy = await page.evaluate(() =>
    !!document.querySelector('button[aria-label="Stop generating"]'),
  );
  const now = await lastSrc();
  if (now && now !== before) {
    if (!busy) {
      src = now;
      break;
    }
    src = now;
  }
}
if (!src) {
  console.error("TIMEOUT: no new image appeared");
  process.exit(2);
}

// Let the image finish loading at full resolution before reading its src again.
await page.waitForTimeout(2500);
const finalSrc = (await lastSrc()) || src;

await mkdir(path.dirname(out), { recursive: true });
const res = await page.fetch(finalSrc, { saveAs: out, timeout: 60000 });
console.log(JSON.stringify({ out, ok: res.ok, status: res.status }));