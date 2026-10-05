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

export async function askStream(
  path: string,
  body: unknown,
  handlers: StreamHandlers = {},
  timeoutMs = 300000,
): Promise<AskResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`/api/stream${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } catch {
    // No stream route at all: still answer the question.
    clearTimeout(timer);
    return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
  }

  if (!res.ok || !res.body || !res.headers.get("content-type")?.includes("text/event-stream")) {
    clearTimeout(timer);
    return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AskResult | null = null;

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
      throw new Error("The answer is taking too long. Please try again.");
    }
    // A stream that dies mid-run has already lost the answer, so retry once
    // over plain JSON rather than showing a half-sent reply.
    if (!result) return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
    throw e;
  } finally {
    clearTimeout(timer);
  }

  if (!result) return askJson(path.replace(/\/stream$/, ""), body, timeoutMs);
  handlers.onDone?.(result);
  return result;
}