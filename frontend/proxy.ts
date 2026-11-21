// Optimistic check only: no cookie -> sign-in. The real check (signature, account
// state, session version) runs in requireSession() on the server for every page.
import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "hh_session";

export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Everything except sign-in, Next internals and static files.
  // "\\." = a literal dot in the regex (a single "\." in a JS string is just ".", which matched every path).
  matcher: ["/((?!sign-in|_next/static|_next/image|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
