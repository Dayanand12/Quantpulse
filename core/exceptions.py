"""Global exception hierarchy.

Every module raises one of these instead of a bare Exception, and the API
layer maps them to HTTP responses in ONE place (register_exception_handlers)
instead of every route carrying its own try/except. Business logic never
imports FastAPI here — only the registration function at the bottom does,
keeping the hierarchy itself transport-agnostic (usable from a future CLI,
scheduler, or desktop app just as well as from the web API).
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error raised by application/domain code."""


class ValidationError(DomainError):
    """Input or business-rule validation failed."""


class NotFoundError(DomainError):
    """A requested entity does not exist."""


class InfrastructureError(DomainError):
    """An external dependency (broker API, database, network) failed."""


def register_exception_handlers(app) -> None:
    """Wire the hierarchy above to HTTP responses on a FastAPI app.

    Imported lazily inside the function so this module has zero hard
    dependency on FastAPI for callers that don't need it.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(ValidationError)
    async def _validation_error_handler(request: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InfrastructureError)
    async def _infrastructure_error_handler(request: Request, exc: InfrastructureError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})
