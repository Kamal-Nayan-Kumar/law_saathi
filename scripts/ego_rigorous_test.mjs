import { promises as fs } from "node:fs";
import path from "node:path";

const QUESTIONS = [
  {
    id: 1,
    category: "Edge Case - Identity / Capabilities",
    lang: "hinglish",
    prompt: "Aap kaun hain aur aap meri kya madad kar sakte hain?",
    description: "Who are you and how can you help me? (Should give warm Law Saathi intro, covered topics, multilingual text/voice, citations, disclaimer)."
  },
  {
    id: 2,
    category: "Edge Case - Out of Scope",
    lang: "hinglish",
    prompt: "Mera padosi meri zameen par kabza kar raha hai aur dhamki de raha hai, kya police complaint karun?",
    description: "Land encroachment & criminal intimidation. Must identify as out-of-scope property/criminal law and redirect politely to family law."
  },
  {
    id: 3,
    category: "Edge Case - Web Search / Recent Legal Ruling",
    lang: "english",
    prompt: "Can the 6-month statutory waiting period for mutual consent divorce under Section 13B(2) of the Hindu Marriage Act be waived by courts? What does recent Supreme Court ruling say?",
    description: "Requires web search / recent Supreme Court jurisprudence (e.g. Article 142 waiver, Amardeep Singh 2017 / Shilpa Sailesh 2023)."
  },
  {
    id: 4,
    category: "Edge Case - Low Information / Initial Query",
    lang: "hinglish",
    prompt: "Mujhe apne pati se divorce chahiye, mujhe kya karna hoga?",
    description: "Vague initial query. Should offer constructive overview of mutual consent vs contested grounds and actionable next steps."
  },
  {
    id: 5,
    category: "Family Law - Muslim Maintenance",
    lang: "hindi",
    prompt: "क्या एक मुस्लिम तलाकशुदा महिला अपने पूर्व पति से भरण-पोषण (maintenance) मांग सकती है? सुप्रीम कोर्ट का नया फैसला क्या कहता है?",
    description: "Divorced Muslim woman maintenance rights under BNSS s.144 / CrPC s.125 & recent Supreme Court Mohd. Abdul Samad 2024 verdict."
  },
  {
    id: 6,
    category: "Family Law - Domestic Violence & Residence",
    lang: "kannada",
    prompt: "ನನ್ನ ಗಂಡ ಮತ್ತು ಅತ್ತೆ ನನಗೆ ಮನೆಯಲ್ಲಿ ಮಾನಸಿಕ ಮತ್ತು ದೈಹಿಕ ಹಿಂಸೆ ನೀಡುತ್ತಿದ್ದಾರೆ, ನನ್ನನ್ನು ಮನೆಯಿಂದ ಹೊರಹಾಕದಂತೆ ನ್ಯಾಯಾಲಯದಿಂದ ಯಾವ ಆದೇಶ ಪಡೆಯಬಹುದು?",
    description: "Protection of Women from Domestic Violence Act 2005: Protection order s.18 & Residence order s.19, right to reside in shared household."
  },
  {
    id: 7,
    category: "Family Law - Child Custody",
    lang: "kannada",
    prompt: "ಮಗುವಿಗೆ 3 ವರ್ಷ ವಯಸ್ಸಾಗಿದೆ, ತಂದೆ ಮಗುವನ್ನು ಕಸಿದುಕೊಳ್ಳಲು ಬೆದರಿಕೆ ಹಾಕುತ್ತಿದ್ದಾನೆ. ಮಗುವಿನ ಕಸ್ಟಡಿ ತಾಯಿಗೆ ಸಿಗುತ್ತದೆಯೇ ಅಥವಾ ತಂದೆಗೆ ಸಿಗುತ್ತದೆಯೇ?",
    description: "Custody of minor under 5 years: Hindu Minority & Guardianship Act s.6(a) (usually with mother) & paramount welfare of child."
  },
  {
    id: 8,
    category: "Family Law - Mutual Consent Divorce",
    lang: "hindi",
    prompt: "आपसी सहमति से तलाक (Mutual Consent Divorce) के नियम क्या हैं? क्या दोनों को अलग रहना ज़रूरी है और इसमें कितना समय लगता है?",
    description: "HMA Section 13B conditions: 1 year separation, joint petition, cooling-off period (6-18 months), final decree."
  },
  {
    id: 9,
    category: "Family Law - Succession & Daughter Rights",
    lang: "hindi",
    prompt: "क्या शादीशुदा बेटी का अपने पिता की पैतृक संपत्ति (ancestral property) में बेटों के बराबर अधिकार है? हिंदू उत्तराधिकार कानून क्या कहता है?",
    description: "Hindu Succession Act s.6 post-2005 amendment: daughter as coparcener by birth, Vineeta Sharma v. Rakesh Sharma 2020 landmark SC ruling."
  },
  {
    id: 10,
    category: "Family Law - Senior Citizens Maintenance",
    lang: "english",
    prompt: "My elderly parents gifted their house to my brother, but now he is neglecting and ill-treating them. Can they get their house back and claim maintenance under the law?",
    description: "Maintenance and Welfare of Parents and Senior Citizens Act 2007: Section 23 revocation of gift transfer + Section 4/9 maintenance tribunal."
  }
];

export async function run() {
  const task = await taskSpace(34);
  const page = task.page("p1");

  console.log("Starting Rigorous Testing of Law Saathi across 10 questions...");
  const results = [];

  for (let i = 0; i < QUESTIONS.length; i++) {
    const q = QUESTIONS[i];
    console.log(`\n======================================================`);
    console.log(`[Q${q.id}/10] [${q.lang.toUpperCase()}] ${q.category}`);
    console.log(`Prompt: "${q.prompt}"`);

    // Inter-query pacing to maintain smooth rate limit headroom
    if (i > 0) {
      await page.waitForTimeout(4000);
    }

    // Reset to new chat
    try {
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll("button"));
        const b = btns.find(el => el.textContent && (
          el.textContent.includes("New chat") ||
          el.textContent.includes("नई बातचीत") ||
          el.textContent.includes("ಹೊಸ ಸಂಭಾಷಣೆ")
        ));
        if (b) b.click();
      });
      await page.waitForTimeout(2000);
    } catch (e) {
      console.warn("Could not click new chat:", e.message);
    }

    // Wait until composer input is actionable
    const inputSelector = "input[aria-label='Question'], input[placeholder*='question'], input[placeholder*='पारिवारिक'], input[placeholder*='ಕುಟುಂಬ']";
    await page.waitForSelector(inputSelector);
    await page.fill(inputSelector, q.prompt);

    // Wait for Send button to be enabled
    await page.waitForFunction(() => {
      const btn = document.querySelector("button[aria-label='Send question']");
      return btn && !btn.disabled;
    });

    const sendSelector = "button[aria-label='Send question']";
    const t0 = Date.now();
    await page.click(sendSelector);

    // Poll until response completes
    let finished = false;
    let elapsed = 0;
    const maxWaitMs = 90000;

    while (!finished && (Date.now() - t0) < maxWaitMs) {
      await page.waitForTimeout(2000);
      elapsed = (Date.now() - t0) / 1000;
      
      const status = await page.evaluate(() => {
        const ansCard = document.querySelector(".ans-card");
        const readAloud = document.querySelector("button[aria-label='Read aloud'], button[aria-label='पढ़कर सुनाएँ'], button[aria-label='ಓದಿ ಕೇಳಿಸಿ']");
        const text = ansCard ? ansCard.innerText : "";
        const isStreaming = !!document.querySelector("[data-streaming='true'], .streaming, .warmup");
        return {
          hasCard: !!ansCard,
          hasReadAloud: !!readAloud,
          isStreaming,
          length: text.length
        };
      });

      if (status.hasReadAloud || (status.hasCard && !status.isStreaming && status.length > 80)) {
        // Wait another 1.5s for any DOM settles
        await page.waitForTimeout(1500);
        finished = true;
        break;
      }
      process.stdout.write(`.`);
    }
    console.log(`\nCompleted in ${elapsed.toFixed(1)}s (finished=${finished})`);

    // Click "How Saathi worked this out" toggle if present to expand steps
    try {
      await page.evaluate(() => {
        const toggle = document.querySelector(".think-toggle");
        if (toggle && !toggle.closest(".think")?.getAttribute("data-open")) {
          toggle.click();
        }
      });
      await page.waitForTimeout(1000);
    } catch (e) {}

    // Extract content
    const extraction = await page.evaluate(() => {
      const ansCard = document.querySelector(".ans-card");
      const fullText = ansCard ? ansCard.innerText : "";
      
      // Extract steps from .think
      const thinkSteps = Array.from(document.querySelectorAll(".think ol li, .think li, .think-steps li")).map(li => li.innerText.trim());
      
      // Extract sources
      const sourceItems = Array.from(document.querySelectorAll(".src-item, .src-list li, .sources li")).map(el => el.innerText.trim());

      return {
        fullText,
        steps: thinkSteps,
        sources: sourceItems
      };
    });

    const record = {
      id: q.id,
      category: q.category,
      lang: q.lang,
      prompt: q.prompt,
      description: q.description,
      responseTimeSec: parseFloat(elapsed.toFixed(1)),
      completed: finished,
      extractedSteps: extraction.steps,
      extractedSources: extraction.sources,
      answerText: extraction.fullText
    };

    results.push(record);
    console.log(`Preview of answer (${record.answerText.length} chars):`);
    console.log(record.answerText.slice(0, 300) + (record.answerText.length > 300 ? "..." : ""));
    console.log(`Steps (${record.extractedSteps.length}):`, record.extractedSteps);
    console.log(`Sources (${record.extractedSources.length}):`, record.extractedSources);
  }

  const outPath = path.resolve("tmp/ego_test_results.json");
  await fs.writeFile(outPath, JSON.stringify(results, null, 2), "utf8");
  console.log(`\nAll 10 tests completed successfully! Saved to ${outPath}`);
}

await run();
