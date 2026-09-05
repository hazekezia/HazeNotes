"""Image upload (magic-byte validated, size capped) and serving."""
import asyncio
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import config
from ..security import get_current_user

router = APIRouter()


def _detect_ext(data: bytes) -> Optional[str]:
    """Magic-byte sniffing; SVG intentionally rejected (can carry scripts)."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if data.startswith(b'BM'):
        return '.bmp'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    return None


@router.post('/api/upload')
@router.put('/api/upload')
async def upload_image(request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)

    # Stream with a hard cap so oversized bodies never buffer fully in memory.
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            return JSONResponse({'error': 'File too large'}, status_code=413)
        chunks.append(chunk)
    data = b''.join(chunks)
    if not data:
        return JSONResponse({'error': 'No file content received'}, status_code=400)

    ext = _detect_ext(data)
    if not ext:
        return JSONResponse({'error': 'Unsupported image type (PNG, JPEG, GIF, WebP, BMP only)'}, status_code=400)

    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    filename = uuid.uuid4().hex + ext

    def _write():
        with open(os.path.join(config.IMAGES_DIR, filename), 'wb') as f:
            f.write(data)

    await asyncio.to_thread(_write)
    return {'url': f'/images/{filename}'}


@router.get('/images/{filename}')
async def serve_image(filename: str):
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(config.IMAGES_DIR, safe_filename)
    if not os.path.isfile(filepath):
        return JSONResponse({'error': 'Image not found'}, status_code=404)
    return FileResponse(filepath)
