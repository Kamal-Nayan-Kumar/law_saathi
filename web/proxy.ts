import { auth } from "@/lib/auth/server";

export default auth.middleware({
  loginUrl: "/login",
});

// Everything behind a sign-in. /dashboard reads the user's own sessions and
// /simulator records a scored run, so both need the session server-side.
// /chat is the product itself, so both need the session server-side — not just
// on the client, where a reload would flash the page before redirecting.
export const config = {
  matcher: ["/chat/:path*", "/dashboard/:path*", "/simulator/:path*"],
};
