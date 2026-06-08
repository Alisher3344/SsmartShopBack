import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.deps import get_current_user, require_admin
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


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


@router.post("/avatar", status_code=status.HTTP_201_CREATED)
async def upload_avatar(
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
):
    """Foydalanuvchi o'z profil rasmi (avatar) — har qanday avtorizatsiyalangan user."""
    name = file.filename or "avatar"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, "Faqat JPG, PNG, WEBP yoki GIF rasmlar")
    contents = await file.read()
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "Rasm hajmi 5 MB dan oshmasligi kerak")
    fname = f"{secrets.token_hex(16)}.{ext}"
    path = UPLOAD_DIR / fname
    path.write_bytes(contents)
    return {"url": f"/uploads/{fname}"}
