"""Notes CRUD + collaborator sharing + real-time broadcast."""
import asyncio
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import config, db
from ..security import can_edit, can_view, get_current_user
from ..ws import ws_manager

router = APIRouter()


def _unauthorized():
    return JSONResponse({'error': 'Authentication required'}, status_code=401)


@router.get('/api/notes')
async def list_notes(request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    notes = await asyncio.to_thread(db.get_user_notes, user or 'anonymous')
    return {'notes': notes}


@router.post('/api/notes')
async def create_note(request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    try:
        data = await request.json()
    except Exception:
        data = {}
    title = str(data.get('title', 'New Note'))
    if len(title) > config.MAX_TITLE_LEN:
        return JSONResponse({'error': f'Title must be at most {config.MAX_TITLE_LEN} characters'}, status_code=400)
    note_id = uuid.uuid4().hex[:16]
    note = await asyncio.to_thread(db.create_note, note_id, title, user or 'anonymous', '')
    return {'id': note['id'], 'title': note['title']}


@router.get('/api/notes/{note_id}')
async def get_note_detail(note_id: str, request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    note = await asyncio.to_thread(db.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)

    if not can_view(user, note):
        return JSONResponse({'error': 'Access denied'}, status_code=403)

    return {
        'id': note['id'],
        'title': note['title'],
        'note': note['content'],
        'created_by': note['owner'],
        'created_at': note['created_at'],
        'updated_at': note['updated_at'],
        'collaborators': note['collaborators']
    }


@router.post('/api/notes/{note_id}')
@router.put('/api/notes/{note_id}')
async def update_note(note_id: str, request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    note = await asyncio.to_thread(db.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)

    if not can_edit(user, note):
        return JSONResponse({'error': 'Permission denied'}, status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)

    title = data.get('title')
    content = data.get('note')
    if title is not None:
        title = str(title)
        if len(title) > config.MAX_TITLE_LEN:
            return JSONResponse({'error': f'Title must be at most {config.MAX_TITLE_LEN} characters'}, status_code=400)
    if content is not None:
        content = str(content)
        if len(content.encode('utf-8')) > config.MAX_NOTE_BYTES:
            return JSONResponse({'error': 'Note too large'}, status_code=413)

    await asyncio.to_thread(db.update_note, note_id, title, content)

    # Broadcast to other WebSocket subscribers in real-time
    ws_payload = {'type': 'note_update', 'note_id': note_id, 'sender': user}
    if content is not None:
        ws_payload['note'] = content
    if title is not None:
        ws_payload['title'] = title
    await ws_manager.broadcast(note_id, ws_payload)

    return {'status': 'ok'}


@router.delete('/api/notes/{note_id}')
async def delete_note(note_id: str, request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    note = await asyncio.to_thread(db.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)

    if config.AUTH_REQUIRED and user != note['owner']:
        # Collaborator: leave the note (remove self from collaborators)
        if user in note.get('collaborators', {}):
            await asyncio.to_thread(db.remove_collaborator, note_id, user)
            return {'left': True, 'note_id': note_id}
        return JSONResponse({'error': 'Access denied'}, status_code=403)

    # Owner: fully delete the note
    await asyncio.to_thread(db.delete_note, note_id)
    await ws_manager.broadcast(note_id, {'type': 'note_deleted', 'note_id': note_id})
    return {'deleted': True}


@router.post('/api/notes/{note_id}/share')
async def add_collaborator(note_id: str, request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    note = await asyncio.to_thread(db.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
    if config.AUTH_REQUIRED and user != note['owner']:
        return JSONResponse({'error': 'Only owner can share'}, status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)

    target_user = str(data.get('username', '')).strip()
    role = data.get('role', 'edit')

    if not target_user:
        return JSONResponse({'error': 'Username required'}, status_code=400)
    if target_user == note['owner']:
        return JSONResponse({'error': 'Cannot add owner as collaborator'}, status_code=400)

    success = await asyncio.to_thread(db.add_collaborator, note_id, target_user, role)
    if not success:
        return JSONResponse({'error': f'User "{target_user}" not found'}, status_code=404)

    updated = await asyncio.to_thread(db.get_note, note_id)
    return {'note': {'id': updated['id'], 'title': updated['title'], 'collaborators': updated['collaborators']}}


@router.delete('/api/notes/{note_id}/share')
async def remove_collaborator(note_id: str, request: Request):
    user = await get_current_user(request)
    if config.AUTH_REQUIRED and not user:
        return _unauthorized()
    note = await asyncio.to_thread(db.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
    if config.AUTH_REQUIRED and user != note['owner']:
        return JSONResponse({'error': 'Only owner can manage collaborators'}, status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)

    target_user = str(data.get('username', '')).strip()
    await asyncio.to_thread(db.remove_collaborator, note_id, target_user)
    return {'removed': target_user}
