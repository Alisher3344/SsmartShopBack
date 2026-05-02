import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.deps import require_admin

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/image",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def upload_image(file: UploadFile = File(...)):
    name = file.filename or "image"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
    contents = await file.read()
    fname = f"{secrets.token_hex(16)}.{ext}"
    path = UPLOAD_DIR / fname
    path.write_bytes(contents)
    return {"url": f"/uploads/{fname}"}
