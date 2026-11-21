"""One error envelope for the campaign API: ``{error: {code, message}}``."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_HTTP_CODES = {
    401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
    409: "conflict", 422: "validation_error",
}  # fmt: skip


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        self.status, self.code, self.message, self.extra = status, code, message, extra


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message, **exc.extra}
        return JSONResponse({"error": body}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error")
        body = {"code": code, "message": str(exc.detail)}
        return JSONResponse({"error": body}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {
            ".".join(str(p) for p in e["loc"][1:]): str(e["msg"]) for e in exc.errors()
        }
        body = {"code": "validation_error", "message": "Check your input", "fields": fields}
        return JSONResponse({"error": body}, status_code=422)
