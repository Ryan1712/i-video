import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // NEVER match /api (proxied to FastAPI by the rewrite), _next, or static files.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
