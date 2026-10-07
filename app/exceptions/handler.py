from fastapi import Request
from fastapi.responses import JSONResponse


class ServiceException(Exception):
    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        instance: str = None,
        code: str | None = None,
        extra: dict | None = None,
    ):
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.instance = instance
        # Optional machine-readable reason (e.g. ACCOUNT_SUSPENDED) for clients that need
        # to tell errors apart without matching on the human-readable detail.
        self.code = code
        # Extra machine-readable fields merged into the body (e.g. a date the client shows).
        self.extra = extra or {}


async def problem_details_handler(request: Request, exc: ServiceException):
    content = {
        "type": "about:blank",
        "title": exc.title,
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": exc.instance or str(request.url.path),
    }
    if exc.code:
        content["code"] = exc.code
    content.update(exc.extra)
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        media_type="application/problem+json",
    )
