import { NextRequest, NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";
import { auth } from "@/lib/auth/server";

export async function POST(req: NextRequest) {
  // 1. Authenticate user session
  const { data: session } = await auth.getSession();
  const userId = session?.user?.id || `guest-${Math.random().toString(36).slice(2, 8)}`;
  const userName = session?.user?.name || "Participant";

  const body = await req.json().catch(() => ({}));
  const roomName = body.room || `law-saathi-${userId}`;

  const apiKey = process.env.LIVEKIT_API_KEY || "devkey";
  const apiSecret = process.env.LIVEKIT_API_SECRET || "secret";
  const livekitUrl = process.env.LIVEKIT_URL || "ws://127.0.0.1:7880";

  // 2. Generate AccessToken with audio and room join grants
  const at = new AccessToken(apiKey, apiSecret, {
    identity: userId,
    name: userName,
  });

  at.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
  });

  const token = await at.toJwt();

  return NextResponse.json({
    token,
    url: livekitUrl,
    room: roomName,
  });
}
