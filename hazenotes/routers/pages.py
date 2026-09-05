"""HTML pages + favicon serving."""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from .. import config
from ..security import get_current_user

router = APIRouter()

_BASE_DIR = Path(__file__).resolve().parent.parent
_template_cache = {}


def _load_template(name: str) -> str:
    # ponytail: templates cached at first use; restart to pick up edits. Fine for prod.
    if name not in _template_cache:
        _template_cache[name] = (_BASE_DIR / 'templates' / name).read_text(encoding='utf-8')
    return _template_cache[name]


@router.get('/favicon.png')
async def serve_favicon():
    return FileResponse(_BASE_DIR / 'static' / 'favicon.png', media_type='image/png')


@router.get('/', response_class=HTMLResponse)
@router.get('/index.html', response_class=HTMLResponse)
async def serve_index(request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return HTMLResponse(_load_template('login.html'))
    return HTMLResponse(_render_editor_page(user))


def _render_editor_page(current_user: Optional[str]) -> str:
    user_display = current_user if current_user and current_user != 'anonymous' else ''
    user_info_style = 'inline' if user_display else 'none'
    logout_btn = '<button id="logoutBtn" type="button" title="Logout">🚪</button>' if user_display else ''
    logout_script = ''
    if user_display:
        logout_script = 'document.getElementById("logoutBtn").onclick = () => { fetch("/api/auth/logout", {method: "POST"}).then(() => window.location.reload()); };'

    html = _load_template('editor.html').replace('USER_INFO_STYLE_PLACEHOLDER_', user_info_style)
    html = html.replace('{CURRENT_USER_DISPLAY}', user_display)
    html = html.replace('[LOGOUT_BUTTON_PLACEHOLDER]', logout_btn)
    # json.dumps escapes quotes; "<\\/" also neutralizes </script> breakouts.
    html = html.replace('CURRENT_USER_PLACEHOLDER_', json.dumps(current_user or 'anonymous').replace('</', '<\\/'))
    html = html.replace('LOGOUT_SCRIPT_PLACEHOLDER', logout_script)
    return html
