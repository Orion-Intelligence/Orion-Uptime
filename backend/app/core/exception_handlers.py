from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.service.exceptions import AppException
from app.service.responses import error_response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(status_code=exc.status_code, content=error_response(message=exc.message).model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception):
        return JSONResponse(status_code=500, content=error_response(message="Internal server error.").model_dump())
