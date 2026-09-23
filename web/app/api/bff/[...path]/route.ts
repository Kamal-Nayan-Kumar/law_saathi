import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth/server";

const FASTAPI = process.env.FASTAPI_URL || "http://localhost:8000";

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
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
