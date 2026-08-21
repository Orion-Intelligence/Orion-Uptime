from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ANGULAR_BUILD_DIR = (BASE_DIR / "build").resolve()

router = APIRouter()


def _frontend_index_response() -> HTMLResponse:
    index_path = ANGULAR_BUILD_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@router.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    user_path = Path(full_path)
    if user_path.is_absolute() or ".." in user_path.parts:
        raise HTTPException(status_code=404, detail="Frontend not found")

    safe_relative_path = Path(*[part for part in user_path.parts if part not in ("", ".")])
    requested_path = (ANGULAR_BUILD_DIR / safe_relative_path).resolve()
    if requested_path == ANGULAR_BUILD_DIR / "index.html":
        return _frontend_index_response()
    if requested_path.is_relative_to(ANGULAR_BUILD_DIR) and requested_path.is_file():
        return FileResponse(requested_path)

    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API route not found")

    return _frontend_index_response()
