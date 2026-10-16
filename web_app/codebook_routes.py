"""The context codebook's screen (docs/CONTEXT_DESIGN.md §7 S3, §4 F4; 2026-10-16): the book as the page shows it,
the coach's decisions on the coder's proposals - confirmed as they are, renamed, merged into a code the book has,
or declined - and the book exported and imported as JSON. The book lives under storage/<user>/context/codebook.json
in both editions; a confirmed change bumps its version and applies from the next load, nothing already coded is
re-coded (a load's codes carry the version they were coded under)."""
import json

from flask import Blueprint, Response, jsonify, request

from auth import requires_auth
from logger_config import get_logger

logger = get_logger(__name__)
codebook_bp = Blueprint('codebook', __name__)


def _app():
    import app as webapp                                     # the main module: the paths
    return webapp


def _storage():
    return _app().user_path('storage')


def _view():
    from analyst import codebook as cb
    return cb.view(cb.load(_storage()))


@codebook_bp.route('/codebook', methods=['GET'])
@requires_auth
def get_codebook():
    try:
        return jsonify(_view()), 200
    except Exception as exc:                                    # noqa: BLE001
        logger.exception("codebook: read failed")
        return jsonify({'error': str(exc)}), 500


@codebook_bp.route('/codebook/confirm', methods=['POST'])
@requires_auth
def confirm_proposal():
    """A proposal confirmed - as it is, renamed (`rename_to`), or merged into an active code (`merge_into`); the
    version bumps. A refusal names its reason."""
    from analyst import codebook as cb
    data = request.get_json(silent=True) or {}
    code = str(data.get('code') or '').strip()
    # a key sent blank is a choice not made, refused with its reason - not read as a plain confirmation
    rename_to = None if data.get('rename_to') is None else str(data.get('rename_to'))
    merge_into = None if data.get('merge_into') is None else str(data.get('merge_into'))
    try:
        storage = _storage()
        book = cb.load(storage)
        reason = cb.why_not(book, code, rename_to or None, merge_into or None)
        if not reason and rename_to is not None and not cb.normalise_code(rename_to):
            reason = 'the new name is empty'
        if not reason and merge_into is not None and not cb.normalise_code(merge_into):
            reason = 'no code chosen to merge into'
        if reason:
            return jsonify({'error': reason}), 400
        book, changed = cb.confirm(book, code, rename_to=rename_to, merge_into=merge_into)
        if not changed:
            return jsonify({'error': 'the proposal could not be confirmed'}), 400
        cb.save(storage, book)
        logger.info("codebook: %s %s -> version %s", code, (f"merged into {merge_into}" if merge_into else (f"confirmed as {rename_to}" if rename_to else "confirmed")), book.get("version"))
        return jsonify(cb.view(book)), 200
    except Exception as exc:                                    # noqa: BLE001
        logger.exception("codebook: confirm failed")
        return jsonify({'error': str(exc)}), 500


@codebook_bp.route('/codebook/decline', methods=['POST'])
@requires_auth
def decline_proposal():
    from analyst import codebook as cb
    data = request.get_json(silent=True) or {}
    code = str(data.get('code') or '').strip()
    try:
        storage = _storage()
        book, changed = cb.decline(cb.load(storage), code)
        if not changed:
            return jsonify({'error': f"there is no proposal named {cb.normalise_code(code) or '?'}"}), 400
        cb.save(storage, book)
        logger.info("codebook: %s declined", code)
        return jsonify(cb.view(book)), 200
    except Exception as exc:                                    # noqa: BLE001
        logger.exception("codebook: decline failed")
        return jsonify({'error': str(exc)}), 500


@codebook_bp.route('/codebook/export', methods=['GET'])
@requires_auth
def export_codebook():
    """The book as it is stored, as a file."""
    from analyst import codebook as cb
    book = cb.load(_storage())
    body = json.dumps(book, indent=1, ensure_ascii=False)
    return Response(body, mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="codebook_v{int(book.get("version", 1))}.json"'})


@codebook_bp.route('/codebook/import', methods=['POST'])
@requires_auth
def import_codebook():
    """A book from a file (the form's `file`, or the request's JSON) in place of the user's, once it checks out; the
    version is one more than the greater of the two."""
    from analyst import codebook as cb
    try:
        if 'file' in request.files:
            raw = request.files['file'].read()
            try:
                obj = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                return jsonify({'error': 'the file is not JSON'}), 400
        else:
            obj = request.get_json(silent=True)
        imported, reason = cb.validate_import(obj)
        if imported is None:
            return jsonify({'error': reason}), 400
        book = cb.replace(_storage(), imported)
        logger.info("codebook: imported %d codes -> version %s", len(book.get("codes") or []), book.get("version"))
        return jsonify(cb.view(book)), 200
    except Exception as exc:                                    # noqa: BLE001
        logger.exception("codebook: import failed")
        return jsonify({'error': str(exc)}), 500
