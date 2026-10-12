"""API response hardening (NFR-18 ASVS headers, NFR-16 request/trace id, NFR-20 EN/ID errors).

Pure ASGI middleware so headers are added to every response, including error responses produced by
exception handlers. No request bodies or user data are read or logged here.
"""

import re
import uuid

SECURITY_HEADERS: dict[str, str] = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "cache-control": "no-store",
}
# Interactive API docs load their own scripts/styles; they get no CSP/cache override.
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

TITLE_ID: dict[str, str] = {
    "Not found": "Tidak ditemukan",
    "Invalid request": "Permintaan tidak valid",
    "Internal error": "Kesalahan internal",
    "Too many attempts": "Terlalu banyak percobaan",
    "Forbidden": "Dilarang",
    "Unauthorized": "Tidak diizinkan",
    "Method Not Allowed": "Metode tidak diizinkan",
    "Conflict": "Konflik",
}
_STATUS_TITLE_ID: dict[int, str] = {
    400: "Permintaan tidak valid", 401: "Tidak diizinkan", 403: "Dilarang", 404: "Tidak ditemukan",
    405: "Metode tidak diizinkan", 409: "Konflik", 413: "Permintaan terlalu besar",
    422: "Permintaan tidak valid", 429: "Terlalu banyak permintaan", 500: "Kesalahan internal",
    502: "Layanan hulu gagal", 503: "Layanan tidak tersedia",
}


def title_id_for(status: int, title: str) -> str:
    return TITLE_ID.get(title) or _STATUS_TITLE_ID.get(status, "Terjadi kesalahan")


def pick_request_id(provided: str | None) -> str:
    if provided and _SAFE_REQUEST_ID.fullmatch(provided):
        return provided
    return str(uuid.uuid4())


class HardeningMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        provided = None
        for k, v in scope.get("headers", []):
            if k == b"x-request-id":
                provided = v.decode("latin-1")
                break
        request_id = pick_request_id(provided)
        scope.setdefault("state", {})["request_id"] = request_id
        is_doc = scope.get("path", "").startswith(_DOC_PATHS)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in {b"x-request-id"}]
                present = {k.lower() for k, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if is_doc and name in {"content-security-policy", "cache-control"}:
                        continue
                    if name.encode() not in present:
                        headers.append((name.encode(), value.encode()))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
