from fastapi import FastAPI, Request

from orion.constants.constant import SecurityHeaders
from orion.services.auth.authorization import development_environment


def register_security_headers(app: FastAPI) -> None:
    headers = dict(SecurityHeaders.DEFAULTS)
    if not development_environment():
        headers["Strict-Transport-Security"] = SecurityHeaders.STRICT_TRANSPORT_SECURITY

    @app.middleware("http")
    async def apply_security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in headers.items():
            response.headers[header] = value
        return response
