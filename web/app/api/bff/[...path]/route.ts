import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth/server";

const FASTAPI = process.env.FASTAPI_URL || "http://localhost:8000";

// A single agent run is 60-90s. This proxy fronts both the cheap reads and that
// one long call, so it needs the same raised ceiling as the stream route —
// otherwise the function is killed mid-run and the browser gets a bare 500 with
// no body, which is exactly what a user sees as "500" under their answer.
export const maxDuration = 300;

async function proxy(req: NextRequest, path: string[]) {
  const { data: session } = await auth.getSession();
  if (!session?.user) {
    return NextResponse.json({ detail: "Login required" }, { status: 401 });
  }
  const url = `${FASTAPI}/${path.join("/")}${req.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(url, {
    method: req.method,
    headers: {
      "Content-Type": "application/json",
      "x-internal-secret": process.env.INTERNAL_API_SECRET!,
      "x-user-id": session.user.id,
      "x-user-email": session.user.email ?? "",
    },
    body: hasBody ? await req.arrayBuffer() : undefined,
  });
  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
