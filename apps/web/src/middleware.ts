import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // CSP: restrict to self, inline styles (Tailwind), and the API origin.
  // No external scripts, no eval, no cloud telemetry endpoints.
  response.headers.set(
    "Content-Security-Policy",
    [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self'",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  );

  // Prevent MIME-type sniffing
  response.headers.set("X-Content-Type-Options", "nosniff");

  // Prevent framing (defense-in-depth with CSP frame-ancestors)
  response.headers.set("X-Frame-Options", "DENY");

  // Referrer: send origin only to same-origin requests
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  // Permissions policy: disable camera, microphone, geolocation, etc.
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=()",
  );

  return response;
}

export const config = {
  matcher: [
    // Apply to all routes except _next/static, _next/image, favicon
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
