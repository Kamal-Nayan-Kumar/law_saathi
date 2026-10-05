import { NextRequest } from "next/server";
import { auth } from "@/lib/auth/server";

const FASTAPI = process.env.FASTAPI_URL || "http://localhost:8000";

/**
 * BFF proxy for the agent's server-sent events.
 *
 * A plain `fetch` to FastAPI would buffer the whole response before returning,
 * which throws away the entire point: the browser must receive each step as it
 * happens. So the upstream body is streamed through untouched.
 *
 * A cookie session is added rather than forwarding the browser's cookies: the
 * upstream FastAPI trusts `x-user-id` plus the internal secret, and the browser
 * has no business holding either.
 */
export const dynamic = "force-dynamic";

// An agent run takes 60-90s. Without this the function is killed at Vercel's
// default limit, the SSE body is cut mid-answer, and the browser sees a stream
// that ends cleanly with no `done` event — which the client then "recovers" by
// running the whole agent a second time over plain JSON. That is what produced
// two answers to one question.
export const maxDuration = 300;

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { data: session } = await auth.getSession();
  if (!session?.user) {
    return new Response(JSON.stringify({ detail: "Login required" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { path } = await ctx.params;
  const upstream = await fetch(`${FASTAPI}/${path.join("/")}${req.nextUrl.search}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "x-internal-secret": process.env.INTERNAL_API_SECRET!,
      "x-user-id": session.user.id,
      "x-user-email": session.user.email ?? "",
    },
    body: await req.arrayBuffer(),
    // The agent run is long; the default 30s fetch timeout would abort it.
    signal: AbortSignal.timeout(300000),
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text || `upstream ${upstream.status}`, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Without these, Vercel's proxy and nginx buffer the stream and the user
      // is back to waiting for the whole answer.
      "X-Accel-Buffering": "no",
      "X-Content-Type-Options": "nosniff",
    },
  });
}