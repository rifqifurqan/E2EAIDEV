"""One error format: RFC 9457 problem details (NFR-20). Clients never see stack traces or internal names."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .http_hardening import title_id_for

log = logging.getLogger("e2eai")
PROBLEM = "application/problem+json"


class AppError(Exception):
    def __init__(self, status: int, title: str, detail: str = "", code: str = "about:blank",
                 headers: dict[str, str] | None = None):
        super().__init__(title)
        self.status, self.title, self.detail, self.code = status, title, detail, code
        self.headers = headers or {}


def problem(request: Request, status: int, title: str, detail: str = "", code: str = "about:blank") -> JSONResponse:
    body = {"type": code, "title": title, "title_id": title_id_for(status, title), "status": status,
            "detail": detail, "instance": request.url.path}
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        resp = problem(request, exc.status, exc.title, exc.detail, exc.code)
        for k, v in exc.headers.items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        title = {404: "Not found", 405: "Method Not Allowed"}.get(exc.status_code, "Request failed")
        detail = exc.detail if isinstance(exc.detail, str) and exc.status_code not in (404, 405) else ""
        resp = problem(request, exc.status_code, title, detail)
        for k, v in (getattr(exc, "headers", None) or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
        return problem(request, 422, "Invalid request", f"Check these fields: {fields}")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return problem(request, 500, "Internal error", "Something went wrong. The error was logged.")
