# integrations/intervals.py - Updated with database storage

import os
import requests
import threading
import time
import uuid
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from auth import requires_auth, get_current_user_id

# Import Intervals functions from supabase_client
from auth.supabase_client import (
    store_intervals_api_key,
    get_intervals_api_key,
    remove_intervals_api_key,
    get_intervals_integration_status,
    list_intervals_athletes,
    name_pending_intervals_key,
    get_user_subscription,
    can_execute_chain,
    increment_queries_counter,
)

# Whose key (2026-10-30, docs/DATASETS_DESIGN.md §17): a key is an athlete. Intervals.icu is asked who owns a key when it is
# saved - `whose_key` - so the list in Settings names the athlete and every load can pick the athlete's own key. The base URL
# is the service's; INTERVALS_API_BASE_URL points it elsewhere (the stack's fake, a proxy).
INTERVALS_API_BASE_URL = os.getenv('INTERVALS_API_BASE_URL', 'https://intervals.icu/api/v1').rstrip('/')


def whose_key(api_key, timeout=12):
    """{'id', 'name'} of the athlete whose key this is, from Intervals.icu's own record; {'refused': True} when the service
    does not accept the key; {'unreachable': '<why>'} when it could not be asked."""
    try:
        r = requests.get(f"{INTERVALS_API_BASE_URL}/athlete/0", auth=('API_KEY', str(api_key or '')), timeout=timeout)
    except Exception as exc:                                   # noqa: BLE001
        return {'unreachable': str(exc)[:200]}
    if r.status_code in (401, 403):
        return {'refused': True}
    if not r.ok:
        return {'unreachable': f'HTTP {r.status_code}'}
    try:
        a = r.json() if isinstance(r.json(), dict) else {}
    except ValueError:
        return {'unreachable': 'no record in the answer'}
    athlete_id = str(a.get('id') or '').strip()
    name = str(a.get('name') or ' '.join(str(a.get(k) or '') for k in ('firstname', 'lastname')).strip() or '').strip()
    if not athlete_id:
        return {'unreachable': 'the record names no athlete'}
    return {'id': athlete_id, 'name': name}


def _name_pending(user_id, auth0_id):
    """A key stored without its athlete (the one from before the keys were kept per athlete, or saved while Intervals.icu was
    unreachable): asked for now, named when the service answers. The list and the load call this."""
    pending = get_intervals_api_key(user_id, auth0_id, '')
    if not pending:
        return
    who = whose_key(pending)
    if who.get('id'):
        name_pending_intervals_key(user_id, auth0_id, who['id'], who.get('name') or '')
    elif who.get('refused'):
        intervals_bp.logger.warning(f'Intervals.icu refused the pending key of user {user_id}; it stays listed unnamed until removed')


def _job_keys():
    """job id -> the athlete id whose key the load ran on ('' for the pending key), for naming it when the job completes."""
    if getattr(intervals_bp, 'job_keys', None) is None:
        intervals_bp.job_keys = {}
    return intervals_bp.job_keys


def athlete_rows(user_id, auth0_id):
    """The athletes with a key, for the page: id, name, added, last used; a pending key as an entry without an id."""
    return [{'id': a['athlete_id'], 'name': a['athlete_name'], 'added': a.get('created_at'), 'last_used': a.get('last_used_at')}
            for a in list_intervals_athletes(user_id, auth0_id)]

# Create the blueprint
intervals_bp = Blueprint('intervals', __name__, url_prefix='/intervals')

def get_intervals_context():
    """Get Intervals context - check if user has API key stored"""
    has_api_key = False
    
    try:
        auth0_id = get_current_user_id()
        
        if auth0_id:
            # Extract bamboo_user_id from auth0_id
            bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
            
            # Check if user has API key in database
            status = get_intervals_integration_status(bamboo_user_id, auth0_id)
            has_api_key = status.get('has_api_key', False)
    except Exception as e:
        print(f"Error checking Intervals context: {str(e)}")
        has_api_key = False
    
    return {
        'intervals_enabled': has_api_key,  # Only enabled if user has API key
        'intervals_authenticated': has_api_key
    }

def init_intervals_integration(app, **dependencies):
    """Initialize Intervals integration with the main app and dependencies"""
    # Store dependencies for use in routes
    intervals_bp.user_preferences = dependencies['user_preferences']
    intervals_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    intervals_bp.get_user_id = dependencies['get_user_id']
    intervals_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    intervals_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    intervals_bp.global_execution_mode = dependencies['global_execution_mode']
    intervals_bp.logger = dependencies['logger']
    
    # Additional constants from main app
    intervals_bp.EXPLORATORY = dependencies['EXPLORATORY']
    intervals_bp.SEARCH_TOOL = dependencies['SEARCH_TOOL']
    intervals_bp.WEBUI = dependencies['WEBUI']
    intervals_bp.utils = dependencies['utils']
    intervals_bp.executor_client = dependencies['executor_client']
    
    # Register the blueprint
    app.register_blueprint(intervals_bp)

    # Make context function available to main app
    app.get_intervals_context = get_intervals_context

@intervals_bp.route('/store_api_key', methods=['POST'])
@requires_auth
def store_api_key():
    """Store an Intervals API key: Intervals.icu is asked whose it is, and the key is kept as that athlete's - their earlier
    key replaced when they had one. A key the service refuses is not kept; one it could not be asked about is kept pending
    and named at the first chance. The answer carries the athlete and the list."""
    data = request.json or {}
    api_key = str(data.get('api_key') or '').strip()
    
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400
    
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        who = whose_key(api_key)
        if who.get('refused'):
            return jsonify({'error': 'Intervals.icu did not accept this key'}), 400
        athlete_id, name = who.get('id') or '', who.get('name') or ''
        before = {a['id'] for a in athlete_rows(user_id, auth0_id)}
        success = store_intervals_api_key(user_id, auth0_id, api_key, athlete_id, name)
        if not success:
            return jsonify({'error': 'Failed to store API key'}), 500
        if athlete_id:
            message = f"{name or athlete_id}'s key " + ('replaced' if athlete_id in before else 'added')
        else:
            message = 'Key kept; Intervals.icu could not be reached to name its athlete (' + str(who.get('unreachable') or '') + ') - it is named at the next load'
        intervals_bp.logger.info(f'Intervals API key stored for user {user_id}: {message}')
        return jsonify({'message': message, 'athlete': {'id': athlete_id, 'name': name}, 'replaced': bool(athlete_id and athlete_id in before),
                        'athletes': athlete_rows(user_id, auth0_id)}), 200
            
    except Exception as e:
        intervals_bp.logger.error(f'Error storing Intervals API key: {str(e)}')
        return jsonify({'error': f'Failed to store API key: {str(e)}'}), 500

@intervals_bp.route('/athletes', methods=['GET'])
@requires_auth
def athletes():
    """The athletes with a key, last used first (a pending key named now if Intervals.icu answers)."""
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        _name_pending(user_id, auth0_id)
        return jsonify({'athletes': athlete_rows(user_id, auth0_id)}), 200
    except Exception as e:
        intervals_bp.logger.error(f'Error listing Intervals athletes: {str(e)}')
        return jsonify({'error': f'Failed to list the athletes: {str(e)}'}), 500

@intervals_bp.route('/remove_api_key', methods=['POST'])
@requires_auth
def remove_api_key():
    """Remove an athlete's Intervals API key (`athlete_id`; '' the pending key); without one, every key."""
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        data = request.json or {}
        athlete_id = data.get('athlete_id')
        success = remove_intervals_api_key(user_id, auth0_id, None if athlete_id is None else str(athlete_id))
        
        if success:
            intervals_bp.logger.info(f'Intervals API key removed for user: {user_id}')
            return jsonify({'message': 'API key removed successfully', 'athletes': athlete_rows(user_id, auth0_id)}), 200
        else:
            return jsonify({'error': 'Failed to remove API key'}), 500
            
    except Exception as e:
        intervals_bp.logger.error(f'Error removing Intervals API key: {str(e)}')
        return jsonify({'error': f'Failed to remove API key: {str(e)}'}), 500
    
@intervals_bp.route('/get_data_limits', methods=['GET'])
@requires_auth
def get_data_limits():
    """Get data limits based purely on compute tier for Intervals"""
    try:
        auth0_id = get_current_user_id()
        if not auth0_id:
            return jsonify({'max_days': 14}), 200

        result = get_user_subscription(auth0_id)
        
        compute_tier = 'free'
        if result.get('ok') and result.get('data'):
            compute_tier = result['data'].get('compute_tier', 'free')
        
        # Intervals: Always based on compute tier (no payment required)
        max_days_map = {
            'free': 14,
            'plus': 182,  # 6 months
            'pro': 365,    # 1 year
            'local': 3650  # your own machine: no limit that matters
        }
        max_days = max_days_map.get(compute_tier, 14)
        
        return jsonify({
            'max_days': max_days,
            'compute_tier': compute_tier
        }), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting data limits: {str(e)}')
        return jsonify({'max_days': 14}), 200

@intervals_bp.route('/load_data', methods=['POST'])
@requires_auth
def load_data():
    """Start Intervals.icu data load job with tier-based date restrictions"""
    data = request.json or {}
    
    # Get user's API key from database - the athlete's own (2026-10-30): the dialog's pick (`athlete`), or the athlete whose
    # folder the Dataset cache dialog names; neither given, the key last used
    user_id = intervals_bp.get_user_id()
    auth0_id = get_current_user_id()
    folder = str(data.get('folder') or '').replace('\\', '/')
    athlete_id = str(data.get('athlete') or (folder.split('/', 1)[1] if folder.startswith('intervals/') else '') or '')
    if athlete_id:
        api_key = get_intervals_api_key(user_id, auth0_id, athlete_id)
        used = athlete_id
        if not api_key and not data.get('from_store'):
            name = str(data.get('athlete_name') or '').strip() or athlete_id      # the page's head names the athlete; the key list no longer can
            return jsonify({'error': f"No Intervals.icu key stored for {name}: add it under Settings \u2192 Intervals ICU"}), 401
    else:
        api_key = get_intervals_api_key(user_id, auth0_id)
        named = [a for a in athlete_rows(user_id, auth0_id) if a['id']]
        used = named[0]['id'] if named else ''                 # whose key was taken: the last used named athlete's, else the pending one
    
    if not api_key and not data.get('from_store'):
        return jsonify({'error': 'No API key configured. Please add your Intervals.icu API key.'}), 401
    api_key = api_key or ''                                    # a load from the store alone needs none
    
    # Validate and auto-adjust date range based on compute tier
    retention_days = 400                        # how long the executor's store keeps a key's activities (docs/INCREMENTAL_LOADS_DESIGN.md)
    if data.get('start_date') and data.get('end_date'):
        from datetime import datetime, timedelta
        
        sub_result = get_user_subscription(auth0_id)
        compute_tier = 'free'
        
        if sub_result.get('ok') and sub_result.get('data'):
            compute_tier = sub_result['data'].get('compute_tier', 'free')
        
        # Max days based on compute tier
        max_days_map = {'free': 14, 'plus': 182, 'pro': 365, 'local': 3650}
        max_days = max_days_map.get(compute_tier, 14)
        retention_days = {'free': 120}.get(compute_tier, 400)
        
        # Parse and adjust dates
        requested_start = datetime.strptime(data['start_date'], '%Y-%m-%d')
        requested_end = datetime.strptime(data['end_date'], '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate the allowed date range
        earliest_allowed = today - timedelta(days=max_days)
        
        # Auto-adjust if needed
        if requested_end > today:
            requested_end = today
        
        if requested_start < earliest_allowed:
            requested_start = earliest_allowed
        
        if requested_start >= requested_end:
            requested_start = requested_end - timedelta(days=1)
        
        # Update with adjusted dates
        data['start_date'] = requested_start.strftime('%Y-%m-%d')
        data['end_date'] = requested_end.strftime('%Y-%m-%d')
        
        intervals_bp.logger.info(f'Date range adjusted to {max_days} days limit ({compute_tier} tier)')
    
    try:
        session_id = session['session_id']
        with_frame = data.get('with_frame') is not False   # the Dataset cache dialog's Load <dataset> (2026-10-29): the files asked for, the frame untouched

        # Generate new df_id
        new_df_id = str(uuid.uuid4())

        # Start job on executor
        executor_urls = intervals_bp.get_dynamic_executor_urls(user_id)
        if not executor_urls:                      # the self-hosted edition on the local kernel (docs/OSS_DESIGN.md D5)
            return jsonify({'error': 'Loading from Intervals needs an executor in this edition for now: run the executor image in Docker and set EXECUTION_MODE=api and EXECUTOR_API_BASE_URL in .env'}), 409
        
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/fetch_intervals_data",
            json={
                'api_key': api_key,
                'df_id': new_df_id,
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'metrics': data.get('metrics', []),
                'aux_datasets': data.get('aux_datasets', []),
                'user_id': user_id,
                'refresh': bool(data.get('refresh')),          # Refresh everything: every file and chat of the window again (2026-10-15)
                'retention_days': retention_days,
                'from_store': bool(data.get('from_store')),    # the Dataset cache dialog's Load (2026-10-29): from the store alone, nothing fetched
                'folder': str(data.get('folder') or ''),       # ...the athlete's folder it names
                'with_frame': with_frame                       # off: one dataset alone (2026-10-29) - the frame on the Data tab stays as it is
            },
            timeout=10
        )
        response.raise_for_status()

        job_data = response.json()
        if api_key:
            _job_keys()[job_data['job_id']] = used             # whose key the job ran on ('' = the pending one, named when the job completes)

        if not with_frame:                                     # the load record is the frame's: a dataset alone joins it when it completes
            return jsonify({'job_id': job_data['job_id']}), 202
        # Store df_id in session for later
        session['intervals_df_id'] = new_df_id
        session['intervals_job_id'] = job_data['job_id']
        # how the data was asked for (2026-10-10, routines): kept with the job, put on the instance when it completes
        prefs = intervals_bp.user_preferences.setdefault(session_id, {'planning': False, 'auxiliary_datasets': []})
        from analyst.routines import key_fingerprint
        prefs['load'] = {'source': 'intervals', 'start_date': data['start_date'], 'end_date': data['end_date'],
                         'metrics': list(data.get('metrics', []) or []), 'aux_kinds': list(data.get('aux_datasets', []) or []), 'df_id': new_df_id,
                         'key': key_fingerprint(api_key)}             # whose data this is - a one-way mark of the key, never the key (2026-10-11, routines)
        if data.get('from_store'):
            prefs['load']['from_store'] = True                 # loaded from the store alone (2026-10-29)

        return jsonify({'job_id': job_data['job_id']}), 202
        
    except Exception as e:
        intervals_bp.logger.error(f'Error starting Intervals load: {str(e)}')
        return jsonify({'error': f'Failed to start data load: {str(e)}'}), 500

@intervals_bp.route('/job/<job_id>', methods=['GET'])
@requires_auth
def get_job_status(job_id):
    """Get status of Intervals data loading job"""
    try:
        user_id = intervals_bp.get_user_id()
        executor_urls = intervals_bp.get_dynamic_executor_urls(user_id)
        if not executor_urls:                      # the self-hosted edition on the local kernel (docs/OSS_DESIGN.md D5)
            return jsonify({'error': 'Loading from Intervals needs an executor in this edition for now: run the executor image in Docker and set EXECUTION_MODE=api and EXECUTOR_API_BASE_URL in .env'}), 409
        
        # Forward request to executor
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/intervals_job/{job_id}",
            timeout=5
        )
        
        if response.status_code == 404:
            return jsonify({'status': 'not_found'}), 404
        
        response.raise_for_status()
        job_data = response.json()
        
        # If completed successfully, set up the BambooAI instance
        if job_data['status'] == 'completed' and 'result' in job_data:
            session_id = session['session_id']
            result = job_data['result']
            # the load ran on the pending key (its athlete not named yet): the loader's record of whom it fetched names it (2026-10-30)
            if _job_keys().pop(job_id, None) == '' and (result.get('subject') or {}).get('id'):
                try:
                    name_pending_intervals_key(user_id, get_current_user_id(), str(result['subject']['id']), str(result['subject'].get('name') or ''))
                except Exception as exc:                       # noqa: BLE001
                    intervals_bp.logger.warning(f'the pending Intervals key could not be named after the load: {exc}')

            # Update user preferences
            prefs = intervals_bp.user_preferences.get(session_id, {
                'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
            })
            # the session's files: those of the kinds this load asked for are replaced by what it wrote, the rest stay
            # (2026-10-29: a load of one dataset alone replaces that dataset's files; an upload, another kind's file, keep)
            from analyst.routines import aux_kind, brings
            kinds = [str(k) for k in (result.get('kinds') if result.get('kinds') is not None else (prefs.get('load') or {}).get('aux_kinds') or [])]
            owned = set(kinds) | set(brings('intervals', kinds))
            new_files = list(result.get('aux_datasets') or [])
            if kinds or new_files:
                prefs['auxiliary_datasets'] = [p for p in (prefs.get('auxiliary_datasets') or []) if aux_kind(p) not in owned and p not in new_files] + new_files
            mine = str((result.get('subject') or {}).get('folder') or '')
            if mine:                                             # one athlete at a time on the Data tab (2026-10-29): the others' files go
                prefs['auxiliary_datasets'] = [p for p in (prefs.get('auxiliary_datasets') or []) if not _other_athletes_file(p, mine)]
            if result.get('frame') is False:
                # one dataset alone (the dialog's Load <dataset>): the frame and its load record stay; the kinds loaded join the record
                intervals_bp.user_preferences[session_id] = prefs
                inst = intervals_bp.bamboo_ai_instances[session_id] = intervals_bp.get_bamboo_ai(session_id)
                inst.auxiliary_datasets = list(prefs['auxiliary_datasets'])
                if prefs.get('load'):
                    prefs['load']['aux_kinds'] = list(dict.fromkeys(list(prefs['load'].get('aux_kinds') or []) + kinds))
                    inst.load_params = dict(prefs['load'])
                _coding_start(job_id, session_id, result, prefs)       # a context file came: the pass behind it, as after a whole load
                return jsonify(job_data), 200
            prefs['df_id'] = result['df_id']

            # Clean up and create new instance
            #intervals_bp.cleanup_and_remove_bamboo_instance(session_id)

            # 1. Update user preferences FIRST
            intervals_bp.user_preferences[session_id] = prefs

            # 2. Get the BambooAI instance (creates new or returns existing)
            intervals_bp.bamboo_ai_instances[session_id] = intervals_bp.get_bamboo_ai(session_id)

            # 3. Always update the properties (in case it was an existing instance)
            intervals_bp.bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
            intervals_bp.bamboo_ai_instances[session_id].auxiliary_datasets = prefs.get('auxiliary_datasets', [])
            if (prefs.get('load') or {}).get('df_id') == result['df_id']:
                st = result.get('store') or {}                # what the store held of the window (docs/INCREMENTAL_LOADS_DESIGN.md), on the load record
                if st.get('window'):
                    prefs['load']['store'] = {'window': st.get('window'), 'held': st.get('held', 0), 'fetched': st.get('fetched', 0), 'refresh': bool(st.get('refresh')), 'offline': bool(st.get('offline'))}
                    if isinstance(st.get('laps'), dict) and st['laps'].get('window'):     # the laps' account (2026-10-29)
                        prefs['load']['store']['laps'] = {k: int(st['laps'].get(k) or 0) for k in ('window', 'held', 'fetched')}
                if isinstance(result.get('subject'), dict) and result['subject'].get('id'):
                    # whose data (2026-10-29, docs/DATASETS_DESIGN.md): the source's own id of the person and the name the
                    # profile gave, from the executor - on the load record, so a run and a routine know whose
                    prefs['load']['subject'] = {k: result['subject'].get(k, '') for k in ('source', 'id', 'name')}
                intervals_bp.bamboo_ai_instances[session_id].load_params = dict(prefs['load'])
            
            # Generate DataFrame sample
            executor_client = intervals_bp.executor_client.ExecutorAPIClient(
                base_url=executor_urls['EXECUTOR_API_BASE_URL']
            )
            
            # the Data tab's grid (2026-09-08): the first page from the executor; the 100-row preview only if it has no page
            df_html = None
            try:
                _page = executor_client.dataframe_page(result['df_id'], 0, 50)
                if _page:
                    _page['df_id'] = result['df_id']
                    df_html = _page
            except Exception:                                # noqa: BLE001
                df_html = None
            if df_html is None:
                df_sample_for_preview = intervals_bp.utils.computeDataframeSample(
                    df=None,
                    execution_mode='api',
                    df_id=result['df_id'],
                    executor_client=executor_client
                )

                df_html = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
            job_data['dataframe'] = json.dumps({'type': 'dataframe', 'data': df_html})
            # the coding pass (docs/CONTEXT_DESIGN.md §4 F1): a load that wrote a context file completes now, and the
            # app codes the passages in a thread behind it - the page polls /intervals/context_coding/<job_id> for the
            # codes file and the pass's line (2026-10-14: holding the load for the pass was minutes nobody would sit through)
            _coding_start(job_id, session_id, result, prefs)
        
        return jsonify(job_data), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting job status: {str(e)}')
        return jsonify({'status': 'error', 'error': str(e)}), 500

def _other_athletes_file(path, folder):
    """Whether a session file is another athlete's than `folder` (intervals/<id>): a file the loader writes, by its name,
    that is not under that athlete's views/ (2026-10-29: one athlete at a time on the Data tab; a file an earlier load
    left under another path is another athlete's too)."""
    from analyst.routines import other_subjects_file
    return other_subjects_file(path, folder)


def _coding_states():
    jobs = getattr(intervals_bp, 'context_coding', None)
    if jobs is None:
        jobs = intervals_bp.context_coding = {}
    now = time.time()
    for k in [k for k, v in jobs.items() if v.get('done_at') and now - v['done_at'] > 3600]:
        jobs.pop(k, None)                                   # a finished pass is remembered for an hour: a poll in flight when the
    return jobs                                             # load completed must not start it again


def _coding_view(state):
    """What the page and the run dialog see of a pass: its status, progress, the line, the codes file."""
    report = state.get('report') or {}
    return {'status': state['status'], 'message': state.get('message', ''), 'percent': state.get('percent'),
            'line': state.get('line', ''), 'codes_path': report.get('codes_path', ''), 'report': report}


def _coding_start(job_id, session_id, result, prefs):
    """Start the coding pass for a completed load with a context file, once per job, in a thread of the app; the
    load completes meanwhile. The result carries result['context']['coding'] = the pass's view (running, or the
    finished pass when the load's completion is read again). When the pass ends, the codes file joins the session's
    auxiliary files - the instance's list is assigned, which drops its frames - and the state says so."""
    from analyst.routines import aux_kind
    from analyst.coder import report_line
    from bambooai import utils
    files = list(result.get('aux_datasets') or [])
    notes_path = next((p for p in files if aux_kind(p) == 'context'), None)
    if not notes_path:
        return
    ctx = result.get('context') if isinstance(result.get('context'), dict) else {}
    result['context'] = ctx
    jobs = _coding_states()
    state = jobs.get(job_id)
    if state is not None:
        # the load's completion read again (a poll in flight): the codes file a finished pass wrote stays among the
        # session's files, which the completion block above has just reset to the executor's list
        codes_path = (state.get('report') or {}).get('codes_path')
        if codes_path and codes_path not in (prefs.get('auxiliary_datasets') or []):
            prefs['auxiliary_datasets'] = list(prefs.get('auxiliary_datasets') or []) + [codes_path]
            inst = intervals_bp.bamboo_ai_instances.get(session_id)
            if inst is not None:
                inst.auxiliary_datasets = list(prefs['auxiliary_datasets'])
        ctx['coding'] = _coding_view(state)
        return
    state = jobs[job_id] = {'status': 'running', 'message': 'Coding the context\u2026', 'percent': None, 'report': None, 'line': ''}
    instance = intervals_bp.bamboo_ai_instances.get(session_id) or intervals_bp.get_bamboo_ai(session_id)
    intervals_bp.bamboo_ai_instances[session_id] = instance
    instance._context_coding = state
    # a query for the account's purposes - the same authorisation as Save as routine, charged as one when it ends
    auth0_user_id = get_current_user_id()
    allowed, reason = True, ''
    if auth0_user_id:
        auth_result = can_execute_chain(auth0_user_id)
        if auth_result.get('ok') and not (auth_result.get('data') or {}).get('allowed'):
            allowed, reason = False, (auth_result.get('data') or {}).get('reason', 'not authorised')
        else:
            try:
                increment_queries_counter(auth0_user_id)
            except Exception as exc:                        # noqa: BLE001
                intervals_bp.logger.error(f"Failed to increment counter: {exc}")
    if not allowed:
        state.update(status='skipped', done_at=time.time(), line=f'the context was not coded: {reason}', report={'passages': None, 'skipped': reason})
        ctx['coding'] = _coding_view(state)
        return
    billing_chain = utils.next_chain_id()
    # the store of coded passages is the subject's (docs/CONTEXT_DESIGN.md D1): keyed by the athlete's own id as
    # Intervals.icu reports it (the job's context report), so a regenerated key keeps the store and two athletes never
    # share one; the key's mark only when the report carries no id (2026-10-14, Palo: a coach switches athletes)
    key_mark = str(ctx.get('subject_id') or '').strip() or (prefs.get('load') or {}).get('key') or ''

    def progress(k, n):
        state['message'] = f'Coding the context: batch {k} of {n}\u2026'
        state['percent'] = int(100 * k / max(1, n))

    def work():
        try:
            report = instance.code_context(notes_path, progress=progress, billing_chain_id=billing_chain, key_mark=key_mark or None)
        except Exception as exc:                            # noqa: BLE001
            intervals_bp.logger.error(f"the coding pass failed: {exc}")
            report = {'passages': None, 'error': f'the coding pass failed ({type(exc).__name__})'}
        finally:
            try:
                instance.log_and_call_manager.charge_for_completed_query(billing_chain)
            except Exception:                               # noqa: BLE001
                pass
        codes_path = report.get('codes_path')
        if codes_path:
            aux = list(prefs.get('auxiliary_datasets') or [])
            if codes_path not in aux:
                aux.append(codes_path)
            prefs['auxiliary_datasets'] = aux
            instance.auxiliary_datasets = list(aux)         # assigned: the frames read before the pass are dropped
        else:
            instance.auxiliary_datasets = list(instance.auxiliary_datasets or [])
        state['report'] = report
        state['line'] = report.get('skipped') or report.get('error') or report_line(report)
        state['status'] = 'done' if not report.get('error') else 'failed'
        state['done_at'] = time.time()
    threading.Thread(target=work, daemon=True, name=f'context-coding-{job_id}').start()
    ctx['coding'] = _coding_view(state)


@intervals_bp.route('/context_coding/<job_id>', methods=['GET'])
@requires_auth
def context_coding_status(job_id):
    """The coding pass behind a load: running (with its progress), done (with the codes file and the line), skipped
    or failed (with the reason); 404 for a job the app does not hold a pass for."""
    state = _coding_states().get(job_id)
    if state is None:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(_coding_view(state)), 200


@intervals_bp.route('/remove_data', methods=['POST'])
@requires_auth
def remove_data():
    """Remove PRIMARY Intervals.icu data only (not auxiliary datasets)"""
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    try:
        bamboo_ai_instance = intervals_bp.bamboo_ai_instances.get(session_id)
        prefs = intervals_bp.user_preferences.get(session_id)

        if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
            return jsonify({'message': 'No Intervals.icu data is currently loaded.'}), 400

        # Clear main DataFrame
        bamboo_ai_instance.df = None
        bamboo_ai_instance.df_id = None

        # Clear df_id from preferences
        if prefs and 'df_id' in prefs:
            del prefs['df_id']
        
        # NOTE: Do NOT remove auxiliary datasets here - they have their own pills
        # Users can remove them individually if needed
        
        intervals_bp.user_preferences[session_id] = prefs

        intervals_bp.logger.info(f"Intervals.icu primary data removed for session {session_id}")
        return jsonify({'message': 'Intervals.icu data removed successfully.'}), 200

    except Exception as e:
        intervals_bp.logger.error(f"Error removing Intervals.icu data for session {session_id}: {str(e)}")
        return jsonify({'error': f'Error removing Intervals.icu data: {str(e)}'}), 500

@intervals_bp.route('/status', methods=['GET'])
@requires_auth
def status():
    """Get Intervals.icu integration status"""
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        status = get_intervals_integration_status(user_id, auth0_id)
        
        return jsonify({
            'enabled': True,
            'authenticated': status.get('has_api_key', False),
            'has_api_key': status.get('has_api_key', False),
            'athletes': [{'id': a['athlete_id'], 'name': a['athlete_name']} for a in status.get('athletes') or []]      # with a key (2026-10-30)
        }), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting Intervals status: {str(e)}')
        return jsonify({
            'enabled': True,
            'authenticated': False,
            'has_api_key': False
        }), 200