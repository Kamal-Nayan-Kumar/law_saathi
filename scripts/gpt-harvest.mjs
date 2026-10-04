// Download the generated images already sitting in the pinned ChatGPT chat.
// ChatGPT virtualises older turns away, so this works from the bottom up: take
// the newest generated <img>, save it, reload, repeat.
//
// Job file: { "space": 6, "outDir": "/abs/dir", "names": ["a","b"], "start": 0 }
// "start" is the index (newest-first) of the first name in "names".
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";

const JOB_FILE =
  "/Users/nayan/Documents/projects/law_saathi/scripts/.gpt-job.json";
const job = JSON.parse(await readFile(JOB_FILE, "utf8"));
const task = await taskSpace(Number(job.space || 6));
const page = task.page("p1");

const CHAT =
  "https://chatgpt.com/c/6ac2af42-bd9c-83ec-90d3-c562bbd6fd55";

async function generatedSrcs() {
  return page.evaluate(() =>
    [...document.querySelectorAll("img")]
      .filter((i) => /^Generated image/i.test(i.alt || ""))
      .map((i) => i.currentSrc || i.src || "")
      .filter(Boolean),
  );
}

await mkdir(job.outDir, { recursive: true });

await page.goto(CHAT);
await page.waitForTimeout(6000);

let idx = Number(job.start || 0);
for (const name of job.names) {
  const srcs = await generatedSrcs();
  const src = srcs[srcs.length - 1 - idx];
  if (!src) {
    console.error(`no image at offset ${idx} (have ${srcs.length})`);
    process.exit(2);
  }
  const out = path.join(job.outDir, `${name}.png`);
  const res = await page.fetch(src, { saveAs: out, timeout: 60000 });
  console.log(JSON.stringify({ name, out, ok: res.ok, status: res.status }));
  idx += 1;
}