"""App assembly: routers, middleware, lifespan.

Run: uvicorn hazenotes.main:app --host 0.0.0.0 --port 8123
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import config, db
from .routers import auth, notes, pages, uploads
from .ws import router as ws_router

# Ensure UTF-8 output in Windows PowerShell/cmd
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('hazenotes')


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    purged = db.purge_expired_sessions()
    logger.info('SQLite ready at %s (WAL mode); purged %d expired sessions', db.DB_PATH, purged)
    logger.info('Authentication: %s', 'ENABLED' if config.AUTH_REQUIRED else 'DISABLED')
    yield


app = FastAPI(
    title='HazeNotes',
    lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,  # not a public API product
)


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:",
    )
    return response


@app.get('/health')
async def health():
    return JSONResponse({'status': 'ok'})


app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(uploads.router)
app.include_router(ws_router)


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level='info')
