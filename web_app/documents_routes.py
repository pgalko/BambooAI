"""Documents attached to a thread (docs/DOCUMENTS_DESIGN.md): the routes the page
calls. Upload parses the file and stores it under storage/<user>/documents/<thread_id>/ through
bambooai.documents; the list, the map and the text feed the Documents pill and tab; remove deletes the
document and the kernel's copy. When the page has no thread yet - nothing asked - the upload mints one,
as a first question does, and the page adopts the id this returns. The refusals come back
as 400 with the sentence to show. The kernel's copy is otherwise kept in step by the engine at every
chain start; the Flask routes are thin on purpose - the logic lives in the library and is
tested there."""
import os
import re
import tempfile

from flask import Blueprint, request, jsonify, session
from auth import requires_auth
from logger_config import get_logger
from bambooai import documents as docs
from bambooai import utils

logger = get_logger(__name__)
documents_bp = Blueprint('documents', __name__)

_THREAD_RE = re.compile(r'^\d{1,20}$')
_DOC_RE = re.compile(r'^D\d{1,6}$')


def _tdir(thread_id):
    from app import user_path
    return user_path('storage', 'documents', str(thread_id))


def _instance():
    from app import bamboo_ai_instances
    session_id = session.get('session_id')
    return bamboo_ai_instances.get(session_id) if session_id else None



def _listing(thread_id):
    return {'thread_id': str(thread_id), 'documents': docs.load_manifest(_tdir(thread_id)).get('documents', []),
            'max': docs.MAX_DOCS}


@documents_bp.route('/documents/upload', methods=['POST'])
@requires_auth
def upload_document():
    from app import user_path
    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'message': 'No file selected.'}), 400
    f = request.files['file']
    thread_id = (request.form.get('thread_id') or '').strip() or None
    if thread_id is None:
        thread_id = str(utils.next_thread_id())                 # the upload starts the thread
    if not _THREAD_RE.match(thread_id):
        return jsonify({'message': 'Invalid thread id.'}), 400
    tdir = _tdir(thread_id)
    tmp_dir = user_path('temp')
    os.makedirs(tmp_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='doc_', suffix=os.path.splitext(f.filename)[1].lower(), dir=tmp_dir)
    os.close(fd)
    try:
        f.save(tmp)
        entry = docs.attach(tdir, tmp, os.path.basename(f.filename))
    except docs.Refused as exc:
        return jsonify({'message': str(exc), 'thread_id': thread_id}), 400
    except Exception as exc:                                    # noqa: BLE001
        logger.error(f"Document upload of {f.filename!r} failed: {exc}", exc_info=True)
        return jsonify({'message': f'The document could not be processed: {exc}', 'thread_id': thread_id}), 500
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    inst = _instance()
    if inst is not None and str(getattr(inst, 'thread_id', '')) == thread_id:
        inst._sync_documents("upload")                          # the running thread's kernel sees it at once
    out = _listing(thread_id)
    out['document'] = entry
    out['message'] = f"{entry['file']} attached as {entry['id']}."
    return jsonify(out), 200


@documents_bp.route('/documents/<thread_id>', methods=['GET'])
@requires_auth
def list_documents(thread_id):
    if not _THREAD_RE.match(thread_id):
        return jsonify({'message': 'Invalid thread id.'}), 400
    return jsonify(_listing(thread_id)), 200


@documents_bp.route('/documents/<thread_id>/<doc_id>/map', methods=['GET'])
@requires_auth
def document_map(thread_id, doc_id):
    if not (_THREAD_RE.match(thread_id) and _DOC_RE.match(doc_id)):
        return jsonify({'message': 'Invalid id.'}), 400
    try:
        return jsonify({'thread_id': thread_id, 'id': doc_id, 'map': docs.read_map(_tdir(thread_id), doc_id)}), 200
    except OSError:
        return jsonify({'message': f'{doc_id} is not in this thread.'}), 404


@documents_bp.route('/documents/<thread_id>/<doc_id>/text', methods=['GET'])
@requires_auth
def document_text(thread_id, doc_id):
    """The units (text.json) for the Documents tab; a page or section at a time is the page's business."""
    if not (_THREAD_RE.match(thread_id) and _DOC_RE.match(doc_id)):
        return jsonify({'message': 'Invalid id.'}), 400
    try:
        return jsonify(docs.read_units(_tdir(thread_id), doc_id)), 200
    except OSError:
        return jsonify({'message': f'{doc_id} is not in this thread.'}), 404


@documents_bp.route('/documents/<thread_id>/<doc_id>', methods=['DELETE'])
@requires_auth
def remove_document(thread_id, doc_id):
    if not (_THREAD_RE.match(thread_id) and _DOC_RE.match(doc_id)):
        return jsonify({'message': 'Invalid id.'}), 400
    removed = docs.remove(_tdir(thread_id), doc_id)
    inst = _instance()
    if removed and inst is not None and str(getattr(inst, 'thread_id', '')) == thread_id:
        inst.remove_document_from_kernel(doc_id)                 # the kernel's copy goes too
    out = _listing(thread_id)
    out['removed'] = doc_id if removed else None
    return jsonify(out), 200 if removed else 404
