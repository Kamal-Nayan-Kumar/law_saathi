/**
 * Read the agent's SSE stream.
 *
 * The API reports each agent step as it happens, so the chat page can show real
 * progress instead of a spinner for 15 seconds. If the stream cannot be used
 * (an old server, a proxy that buffers, no `fetch` streaming) the caller gets
 * the plain JSON answer instead — the chat must never break because streaming
 * failed.
 *
 * Events: `step` {node, detail}, `done` {answer, citations, ...}, `error`.
 */
export type StreamStep = { node: string; detail: string };

export type AskResult = {
  answer: string;
  clarification: boolean;
  citations: string[];
  citation_sources: string[];
  provider: string;
  retries: number;
  trace: string[];
  trace_detail: StreamStep[];
  verified: boolean;
  confidence: number;
  /** The language the server actually wrote in. Authoritative. */
  lang?: string;
};

export type StreamHandlers = {
  /** Called as each agent step completes. */
  onStep?: (step: StreamStep) => void;
  /** Called once with the final answer. */
  onDone?: (result: AskResult) => void;
  /** Called when the run failed outright. */
  onError?: (message: string) => void;
};

/** Split an SSE buffer into complete `event:`/`data:` blocks. */
function parseBlocks(buffer: string) {
  const blocks: { event: string; data: string }[] = [];
  for (const raw of buffer.split("\n\n")) {
    const block = raw.trim();
    if (!block || block.startsWith(":")) continue; // comment / keepalive
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) blocks.push({ event, data: dataLines.join("\n") });
  }
  return blocks;
}

/** POST to the JSON endpoint. The fallback path, and the tests' target. */
async function askJson(path: string, body: unknown, timeoutMs: number): Promise<AskResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`/api/bff${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return (await res.json()) as AskResult;
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error("The answer is taking too long. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Ask a question, preferring the step stream.
 *
 * The one rule this function must never break: **one question, one agent run.**
 * The old version retried the whole ask over plain JSON whenever the stream
 * ended without a `done` event. But the stream carries the answer the whole
 * time — the agent persisted it before sending `done`, and the connection is
 * cut on the way out. So the "recovery" re-ran the agent, persisted a second
 * answer, and the user read the same reply twice.
 *
 * So a stream that dies is no longer retried. The answer is already saved; we
 * fetch it back from the message list. That path cannot run the agent again,
 * because it is a plain GET.
 */
export async function askStream(
  path: string,
  body: unknown,
  handlers: StreamHandlers = {},
  timeoutMs = 300000,
): Promise<AskResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  // How many steps arrived. Any step means the agent had already started, and
  // therefore already owns this question — so a later failure must not lead to
  // another run.
  let sawStep = false;
  let result: AskResult | null = null;

  let res: Response;
  try {
    res = await fetch(`/api/stream${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } catch {
    // The stream route is unreachable (old server, proxy down). Nothing has run
    // yet, so plain JSON is the correct fallback.
    clearTimeout(timer);
    return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
  }

  if (!res.ok || !res.body || !res.headers.get("content-type")?.includes("text/event-stream")) {
    clearTimeout(timer);
    // A non-200 here means the request was rejected before the agent started
    // (bad auth, missing session), so the JSON path will fail the same way and
    // there is nothing to recover. Saying so beats re-running the agent.
    if (res.status >= 400) {
      throw new Error(await readError(res, res.status));
    }
    return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const blocks = parseBlocks(buffer);
      // Keep the trailing partial block in the buffer for the next chunk.
      buffer = buffer.slice(buffer.lastIndexOf("\n\n") + 2);

      for (const { event, data } of blocks) {
        if (event === "step") {
          sawStep = true;
          handlers.onStep?.(JSON.parse(data) as StreamStep);
        } else if (event === "done") {
          result = JSON.parse(data) as AskResult;
        } else if (event === "error") {
          const { message } = JSON.parse(data) as { message: string };
          handlers.onError?.(message);
          throw new Error(message);
        }
      }
    }
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error("This is taking longer than usual. Please try again.");
    }
    // The run had started, so it has already saved an answer. Read it back
    // rather than asking again.
    if (!result && sawStep) return recoverPersisted(path);
    throw e;
  } finally {
    clearTimeout(timer);
  }

  if (result) {
    handlers.onDone?.(result);
    return result;
  }
  if (sawStep) return recoverPersisted(path);
  // Nothing streamed at all: the request never reached the agent, so JSON is
  // safe and cannot duplicate anything.
  return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
}

/** A bare status with no body is not something to show a person. */
async function readError(res: Response, status: number): Promise<string> {
  const text = (await res.text().catch(() => "")).trim();
  if (!text) return `Something went wrong (${status}). Please try again.`;
  try {
    const parsed = JSON.parse(text) as { detail?: string };
    if (parsed.detail) return parsed.detail;
  } catch {
    // Not JSON; the raw text is the best available message.
  }
  return text.slice(0, 200);
}

/**
 * Fetch the answer the agent already saved.
 *
 * `GET /sessions/{id}/messages` cannot run the agent, so this is the only way
 * to finish a run whose stream was cut — and it is the reason a dropped
 * connection no longer costs the user a second answer. Citations and the step
 * log come back with the row, so the Sources list and the Thinking panel are
 * exactly as they would have been on the streamed path.
 */
async function recoverPersisted(path: string): Promise<AskResult> {
  const sessionId = path.split("/")[2];
  // Losing the connection does not cancel the run — the agent keeps going on
  // the server and saves the answer when it finishes. So when nothing is there
  // yet, wait for it rather than telling the user to type the question again
  // while the answer they already asked for is still being written.
  for (let attempt = 0; attempt < RECOVERY_ATTEMPTS; attempt += 1) {
    const list = await fetchMessages(sessionId);
    const answer = [...list]
      .reverse()
      .find((m) => m.role === "assistant" && m.content);
    if (answer) {
      return {
        answer: answer.content,
        clarification: false,
        citations: answer.citations ?? [],
        citation_sources: answer.citation_sources ?? [],
        provider: "",
        retries: 0,
        trace: answer.trace ?? [],
        trace_detail: answer.trace_detail ?? [],
        verified: answer.verified ?? true,
        confidence: answer.confidence ?? 0,
      };
    }
    await sleep(RECOVERY_INTERVAL_MS);
  }
  throw new Error(
    "The connection dropped before the answer arrived. Please ask again.",
  );
}

// 6s, 12s, 18s, 24s — about 90 seconds in total, which covers a run that was
// already under way when the connection went.
const RECOVERY_ATTEMPTS = 10;
const RECOVERY_INTERVAL_MS = 4000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type StoredMessage = {
  role: string;
  content: string;
  citations?: string[];
  citation_sources?: string[];
  trace?: string[];
  trace_detail?: StreamStep[];
  verified?: boolean | null;
  confidence?: number | null;
};

async function fetchMessages(sessionId: string): Promise<StoredMessage[]> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch(`/api/bff/sessions/${sessionId}/messages`, {
      signal: ctrl.signal,
    });
    if (!res.ok) return [];
    return (await res.json()) as StoredMessage[];
  } catch {
    // Nothing to recover from. The caller turns this into a readable message.
    return [];
  } finally {
    clearTimeout(timer);
  }
}