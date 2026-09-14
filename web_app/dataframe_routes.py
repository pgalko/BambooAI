"""The Data tab's pages (2026-09-07): one page of the primary dataframe at a
time - offset, limit, order_by, ascending - fetched from the executor in api
mode or taken from the instance's own frame locally. The browser never holds
more than one page."""
from flask import Blueprint, request, jsonify, session
from auth import requires_auth
from logger_config import get_logger

logger = get_logger(__name__)
dataframe_bp = Blueprint('dataframe', __name__)


@dataframe_bp.route('/api/dataframe/page', methods=['GET'])
@requires_auth
def dataframe_page():
    from app import bamboo_ai_instances
    session_id = session.get('session_id')
    inst = bamboo_ai_instances.get(session_id) if session_id else None
    if inst is None:
        return jsonify({'error': 'No active session'}), 400
    try:
        offset = int(request.args.get('offset', 0)); limit = int(request.args.get('limit', 50))
    except ValueError:
        return jsonify({'error': 'offset and limit must be integers'}), 400
    order_by = request.args.get('order_by') or None
    ascending = request.args.get('ascending', 'true').lower() != 'false'
    df_id = request.args.get('df_id') or inst.df_id
    try:
        if df_id and df_id.startswith('aux:'):                 # an auxiliary file (2026-09-08)
            path = df_id[4:]
            if inst.execution_mode == 'api' and inst.api_client is not None:
                page = inst.api_client.aux_page(path, offset, limit, order_by, ascending)
                if page is None:
                    return jsonify({'error': 'The executor returned no page for the auxiliary file'}), 502
            else:
                from bambooai.utils import aux_page
                page = aux_page(path, offset, limit, order_by, ascending)
            return jsonify(page)
        if inst.execution_mode == 'api' and inst.api_client is not None and df_id:
            page = inst.api_client.dataframe_page(df_id, offset, limit, order_by, ascending)
            if page is None:
                return jsonify({'error': 'The executor returned no page'}), 502
        elif inst.df is not None:
            from bambooai.utils import page_frame
            page = page_frame(inst.df, offset, limit, order_by, ascending)
        else:
            return jsonify({'error': 'No dataset attached'}), 404
        page['df_id'] = df_id
        return jsonify(page)
    except Exception as exc:                                # noqa: BLE001
        logger.warning("dataframe page failed: %s", exc)
        return jsonify({'error': str(exc)}), 500
