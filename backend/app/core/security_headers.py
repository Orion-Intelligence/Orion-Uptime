from fastapi import FastAPI, Request

from app.service.authorization import development_environment

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "manifest-src 'self'",
    "media-src 'none'",
    "object-src 'none'",
    "frame-src 'none'",
    "worker-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
}


STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains"


def register_security_headers(app: FastAPI) -> None:
    headers = dict(SECURITY_HEADERS)
    if not development_environment():
        headers["Strict-Transport-Security"] = STRICT_TRANSPORT_SECURITY

    @app.middleware("http")
    async def apply_security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in headers.items():
            response.headers[header] = value
        return response
