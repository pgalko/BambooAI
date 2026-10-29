// Dataset Manager Module - the Dataset cache dialog. Since 2026-10-29 (docs/DATASETS_DESIGN.md §8, §16) it draws the executor's
// store as a tree - source → athlete → dataset, exactly the datasets the Intervals.icu dialog offers plus the frame - with a
// dot and the words on each line saying whether it is on the Data tab now or in the store only (an indicator, not a control:
// the product owner clicked it, 2026-10-29). A click on a line opens its details on the right, where the actions are: Load
// <dataset> (the span held, from the store alone) and Load <dataset> to today (through Intervals.icu for the missing days)
// for one dataset, Load everything / Load everything to today for the athlete; Forget takes the pill(s) off the Data tab and
// the data out of the cache (his word); the pill's × takes a dataset off the tab alone. Uploads and generated files keep their
// own groups. A load's window files are not listed: they are a run's inputs, shown on the Data tab.
window.DatasetManager = (function() {
    'use strict';
    
    let currentDatasets = {
        cached: [],
        auxiliary: [],
        generated: [],
        tree: null
    };
    let selectedDataset = null;
    let openSubjects = {};                                   // which athletes are unfolded (their folder → true), kept across refreshes
    let shown = null;                                        // what the details pane shows now: { folder, feed } (feed '' for the athlete), redrawn after a change
    
    function initialize() {
        console.log('Initializing Dataset Manager...');
        
        // Create modal
        createModal();
        
        // Set up event handlers
        setupEventHandlers();
        
        // Set up button handlers
        setupButtonHandlers();
    }
    
    function createModal() {
        const modal = document.createElement('div');
        modal.id = 'datasetManagerModal';
        modal.className = 'modal ui-modal';
        modal.innerHTML = `
            <div class="modal-content ui-dlg lg">
                <div class="dataset-modal-header ui-dlg-h">
                    <div><div class="dataset-modal-title title">Dataset cache</div><div class="sub">what your executor holds, by athlete - and what is on the Data tab now</div></div>
                    <span class="sp"></span>
                    <button class="close x" aria-label="Close">×</button>
                </div>
                <div class="dataset-modal-body">
                    <div class="dataset-list-panel">
                        <input type="search" id="datasetFilter" class="ds-filter ui-input" placeholder="Filter by name or dataset" autocomplete="off">
                        <div id="datasetTree"></div>
                        <div class="dataset-category">
                            <h4>Generated</h4>
                            <div id="generatedDatasetList"></div>
                        </div>
                    </div>
                    <div class="dataset-details-panel">
                        <div id="datasetDetails" class="dataset-details-empty">Select a dataset to see its details</div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    function setupEventHandlers() {
        // Pill click handler
        const pill = document.getElementById('datasetManagerPill');
        if (pill) {
            pill.addEventListener('click', showModal);
        }
        
        // Modal close handlers
        const modal = document.getElementById('datasetManagerModal');
        const closeButton = modal?.querySelector('.close');
        
        if (closeButton) {
            closeButton.addEventListener('click', hideModal);
        }
        
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) hideModal();
            });
        }
    }
    
    function setupButtonHandlers() {
        // Use event delegation for dynamically created buttons
        document.addEventListener('click', function(e) {
            if (e.target.closest('#datasetDetails [data-act]')) return;           // the athlete's and the datasets' actions, below
            if (e.target.classList.contains('dataset-load-btn')) {
                handleLoadDataset(e.target);
            } else if (e.target.classList.contains('dataset-remove-btn')) {
                handleRemoveDataset(e.target);
            } else if (e.target.classList.contains('dataset-download-btn')) {
                handleDownloadDataset(e.target);
            }
        });
        // the tree's lines (docs/DATASETS_DESIGN.md §8): the caret folds an athlete; a click on an athlete's line or a dataset's
        // line opens its details on the right, where the actions are - as the files' Load and Remove always were
        const tree = document.getElementById('datasetTree');
        if (tree) tree.addEventListener('click', handleTreeClick);
        const filter = document.getElementById('datasetFilter');
        if (filter) filter.addEventListener('input', () => renderTree());
        document.addEventListener('click', function(e) {
            const b = e.target.closest('#datasetDetails [data-act]');
            if (!b || b.disabled) return;
            const d = b.dataset;
            if (d.act === 'load') startLoad(d.folder, d.feed, false);             // the span held, from the store alone
            else if (d.act === 'today') startLoad(d.folder, d.feed, true);       // through Intervals.icu: the missing days come down
            else if (d.act === 'forget') forgetDataset(d.folder, d.feed, d.name);   // off the Data tab and out of the cache, after asking
        });
    }

    function handleTreeClick(e) {
        const caret = e.target.closest('.ds-caret');
        const subj = e.target.closest('.ds-subj');
        if (caret && subj) {
            openSubjects[subj.dataset.folder] = !isOpen(subj.dataset.folder);
            renderTree();
            return;
        }
        const head = e.target.closest('.ds-subj-head');
        if (head && subj) { selectLine(head); showSubjectDetails(subj.dataset.folder); return; }
        const feed = e.target.closest('.ds-feed');
        if (feed && subj) { selectLine(feed); showFeedDetails(subj.dataset.folder, feed.dataset.feed); return; }
    }

    function isOpen(folder) {
        if (openSubjects[folder] === undefined) openSubjects[folder] = true;     // unfolded until the person folds it
        return !!openSubjects[folder];
    }
    function selectLine(el) {
        document.querySelectorAll('#datasetManagerModal .dataset-item, #datasetManagerModal .ds-subj-head, #datasetManagerModal .ds-feed').forEach(x => x.classList.remove('active'));
        if (el) el.classList.add('active');
        selectedDataset = null;
    }

    function localDay() {
        return typeof localIsoDay === 'function' ? localIsoDay(new Date()) : new Date().toISOString().slice(0, 10);
    }

    function subjectOf(folder) {
        const tree = currentDatasets.tree || {};
        for (const src of tree.sources || []) for (const sb of src.subjects || []) if (sb.folder === folder) return sb;
        return null;
    }
    function lineOf(subject, feed) { return (subject.feeds || []).find(f => f.feed === feed) || null; }

    // the datasets, named as the Intervals.icu dialog names them (2026-10-29: the lines must read as what was asked for), the
    // kinds a load of each asks for (the planned workouts ride with the context, as in the dialog), and the window file prefixes
    // that belong to each line (what a pill on the Data tab stands for)
    const FEED_NAMES = { activities: 'Activities', summary: 'Activity summary', laps: 'Activity intervals', wellness: 'Wellness', context: 'Context', profile: 'Rider profile' };
    const FEED_KINDS = { activities: [], summary: ['summary'], laps: ['intervals'], wellness: ['wellness'], context: ['context', 'plan'], profile: ['rider'] };
    const PREFIX_FEED = { activity_summary: 'summary', activity_intervals: 'laps', wellness_data: 'wellness', context_notes: 'context', context_codes: 'context', planned_workouts: 'context', rider_profile: 'profile', custom_zone_times: 'profile' };
    const FEED_HINTS = { activities: 'The second-by-second rows of every activity, every metric the file had: the frame on the Data tab.',
                         summary: 'One row per activity - the activity list as Intervals.icu keeps it: times, distance, load, the settings in force that day, the account\'s activity fields.',
                         laps: 'The laps of every activity, as Intervals.icu detected them, with the labels, RPE and lactate typed in.',
                         wellness: 'The daily log, a row per day: sleep, resting HR, HRV, weight, how the day felt.',
                         context: 'The words beside the data: the chats under the activities, the notes, the calendar\'s entries - with the planned workouts as numbers.',
                         profile: 'The settings the data is read against - thresholds, zones, weight, the custom fields - as last fetched, and the time in the account\'s custom zones per activity.' };
    const notHidden = f => !/^\./.test(String((f && f.filename) || ''));      // a dotfile (.DS_Store) is the system's, not an upload

    // ---- what is on the Data tab now (the dots): from the pills, by the athlete's folder --------------------------------------
    function windowOf(name) {
        const m = String(name || '').match(/(\d{4})(\d{2})(\d{2})_to_(\d{4})(\d{2})(\d{2})/);
        return m ? `${m[1]}-${m[2]}-${m[3]} → ${m[4]}-${m[5]}-${m[6]}` : '';
    }
    function onTab(folder) {
        // { feed: { span, files } } for the athlete's datasets on the Data tab now
        const out = {};
        const st = window.Intervals && window.Intervals.state;
        if (st && st.isLoaded && st.dataInfo && st.dataInfo.folder === folder) out.activities = { span: `${st.dataInfo.start_date} → ${st.dataInfo.end_date}`, files: [] };
        document.querySelectorAll('#datasetStatusPillsContainer .auxiliary-dataset-pill').forEach(p => {
            const id = String(p.dataset.identifier || '').replace(/\\/g, '/');
            if (!id.includes('/' + folder + '/views/')) return;
            const name = id.split('/').pop();
            const feed = PREFIX_FEED[(name.match(/^([a-z_]+?)_\d{8}_to_/) || [])[1]];
            if (!feed) return;
            if (!out[feed]) out[feed] = { span: windowOf(name), files: [] };
            if (!out[feed].files.includes(name)) out[feed].files.push(name);
            if (p.id === 'contextPill' && typeof contextPillState !== 'undefined' && contextPillState.codes) {
                const codes = String(contextPillState.codes).split('/').pop();
                if (!out[feed].files.includes(codes)) out[feed].files.push(codes);
            }
        });
        return out;
    }
    function pillsOf(folder, feed) {
        // the Data tab's pills that stand for the athlete's dataset (every dataset when feed is '')
        const out = [];
        document.querySelectorAll('#datasetStatusPillsContainer .auxiliary-dataset-pill').forEach(p => {
            const id = String(p.dataset.identifier || '').replace(/\\/g, '/');
            if (!id.includes('/' + folder + '/views/')) return;
            const f = PREFIX_FEED[(id.split('/').pop().match(/^([a-z_]+?)_\d{8}_to_/) || [])[1]];
            if (f && (!feed || f === feed)) out.push(p);
        });
        return out;
    }

    // ---- the actions (docs/DATASETS_DESIGN.md §16, as the product owner asked on 2026-10-29) ---------------------------------------
    // Load <dataset> brings the span held onto the Data tab from the store alone - nothing is fetched; Load <dataset> to today goes
    // through Intervals.icu for the same span extended to today, only the missing days come down. Loading Activities loads the
    // frame (the frame on the Data tab is let go first, after asking); any other dataset alone leaves the frame as it is and
    // replaces its own pill(s). Load everything is every dataset held at once. The job is the one the Intervals.icu dialog
    // starts; the progress shows in the details pane and the dialog closes by itself.
    function spanOf(subject, feed) {
        const lines = feed ? [lineOf(subject, feed)].filter(Boolean) : (subject.feeds || []);
        const acts = lineOf(subject, 'activities');
        const froms = lines.map(l => l.from).filter(Boolean), tos = lines.map(l => l.to).filter(Boolean);
        if (feed === 'profile' || !froms.length) return acts && acts.from ? { from: acts.from, to: acts.to } : (froms.length ? { from: froms.sort()[0], to: tos.sort().slice(-1)[0] } : null);
        return { from: froms.sort()[0], to: tos.sort().slice(-1)[0] };
    }
    function kindsOf(subject, feed) {
        // the datasets a load asks for beside the frame: everything held for the athlete's Load everything; for Activities the
        // datasets on the Data tab now, so the tab stays one window (2026-10-29: a frame loaded to today beside files from May
        // read as broken); one dataset alone asks for its own kinds
        if (feed === 'activities') return Object.keys(onTab(subject.folder)).filter(f => f !== 'activities').reduce((a, f) => a.concat(FEED_KINDS[f] || []), []);
        if (feed) return FEED_KINDS[feed] || [];
        const held = new Set((subject.feeds || []).map(f => f.feed));
        return ['summary', 'laps', 'wellness', 'context', 'profile'].filter(f => held.has(f)).reduce((a, f) => a.concat(FEED_KINDS[f]), []);
    }
    function withFrameOf(subject, feed) { return feed ? feed === 'activities' : !!lineOf(subject, 'activities'); }

    async function startLoad(folder, feed, online) {
        const subject = subjectOf(folder);
        const span = subject && spanOf(subject, feed);
        if (!subject || !span) return;
        const from = span.from, to = online ? localDay() : span.to;
        const kinds = kindsOf(subject, feed), withFrame = withFrameOf(subject, feed);
        const what = feed ? FEED_NAMES[feed] : 'everything';
        // one athlete at a time on the Data tab (2026-10-29): another athlete's pills - the frame's and the files' - go first, after asking
        const others = typeof intervalsOtherAthletePills === 'function' ? intervalsOtherAthletePills(folder) : [];
        if (others.length) {
            if (!confirm("The Data tab holds another athlete's data. Let it go and load " + (subject.name || subject.id) + "'s " + what + '?')) return;
            for (const p of others) {
                if (p.dataset.datasetType === 'intervals' && p.id !== (window.Intervals && window.Intervals.state.pillId)) { p.remove(); continue; }    // a frame pill an earlier load left behind: the page's alone
                if (typeof removeDatasetPill === 'function') await removeDatasetPill(p, null, true); else p.remove();
            }
        }
        if (withFrame && window.Intervals && window.Intervals.state.isLoaded && window.Intervals.state.pillId) {
            if (!confirm('The Data tab holds a window from Intervals.icu. Let it go and load ' + from + ' → ' + to + '?')) return;
            const pill = document.getElementById(window.Intervals.state.pillId);
            if (pill && typeof removeDatasetPill === 'function') await removeDatasetPill(pill, null, true);
            else if (window.Intervals.removePill) window.Intervals.removePill();
        }
        if (withFrame) {
            const busy = primaryLoadedMessage();
            if (busy) { if (typeof showUploadLimitMessage === 'function') showUploadLimitMessage(busy); return; }
        }
        const status = document.getElementById('dsLoadStatus');
        const buttons = document.querySelectorAll('#datasetDetails [data-act]');
        buttons.forEach(b => { b.disabled = true; });
        if (status) { status.style.display = ''; status.className = 'ds-load-status loading'; status.textContent = 'Loading ' + what + ' ' + from + ' → ' + to + (online ? ' - the store serves what it holds, the rest comes from Intervals.icu…' : ' from the store…'); }
        const done = (ok, text) => {
            if (status) { status.className = 'ds-load-status ' + (ok ? 'success' : 'error'); status.textContent = text; }
            buttons.forEach(b => { b.disabled = false; });
            if (ok && !/Not written/.test(text)) setTimeout(hideModal, 1500);     // a line naming what was not written stays
            else if (ok) loadDatasets();
        };
        try {
            const response = await window.authService.fetch('/intervals/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ start_date: from, end_date: to, metrics: [], aux_datasets: kinds, refresh: false, from_store: !online, folder: folder, with_frame: withFrame }) });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            if (withFrame) {
                dropPills(folder, kinds);                     // the pills of the kinds this load replaces go with the frame; the rest stay
                if (typeof pollIntervalsJob !== 'function') throw new Error('the Intervals.icu module is not on the page');
                const msg = document.getElementById('intervals-modal-message');
                if (msg) { msg.textContent = ''; msg.className = msg.className.replace(/\b(success|error|loading)-message\b/g, '').trim(); }      // an earlier load's line must not pass for this one's
                pollIntervalsJob(data.job_id, { start: from, end: to }, kinds);          // the dialog's own poller: the frame and the pills on completion
                const mirror = setInterval(() => {
                    const text = msg ? msg.textContent : '';
                    if (status) status.textContent = text || 'Loading…';
                    if (/Data loaded successfully/.test(text)) { clearInterval(mirror); done(true, text); }
                    else if (/^✗|Failed|timed out|expired/.test(text)) { clearInterval(mirror); done(false, text); }
                }, 500);
            } else {
                pollDatasetJob(data.job_id, { start_date: from, end_date: to, aux_datasets: kinds, folder: folder }, what, online, status, done);
            }
        } catch (error) {
            console.error('Error starting the load from the cache:', error);
            done(false, 'Could not start the load: ' + (error.message || error));
        }
    }

    // the pills of the kinds a load replaces: the Data tab's, for this athlete; the count follows (no call - the app replaces the files)
    function dropPills(folder, kinds) {
        const feeds = new Set(Object.keys(FEED_KINDS).filter(f => f !== 'activities' && FEED_KINDS[f].some(k => kinds.includes(k))));
        let gone = 0;
        pillsOf(folder, '').forEach(p => {
            const f = PREFIX_FEED[(String(p.dataset.identifier || '').split('/').pop().match(/^([a-z_]+?)_\d{8}_to_/) || [])[1]];
            if (!feeds.has(f)) return;
            if (p.id === 'contextPill') { if (typeof contextPillClear === 'function') contextPillClear(); gone += 1; return; }
            p.remove(); gone += 1;
        });
        if (typeof window.auxiliaryDatasetCount !== 'undefined') window.auxiliaryDatasetCount = Math.max(0, (window.auxiliaryDatasetCount || 0) - gone);
    }

    // a load of one dataset alone: polled here (the Intervals.icu dialog's poller makes the frame's pill); on completion the
    // dataset's pill(s) appear, the context's coding pass is followed as after a whole load, the pane says what came
    function pollDatasetJob(jobId, dataInfo, what, online, status, done) {
        let ended = false;
        const t0 = Date.now();
        const tick = async () => {
            if (ended) return;
            let job = null;
            try { const r = await window.authService.fetch('/intervals/job/' + jobId); job = await r.json(); } catch (e) { job = null; }
            if (job && (job.status === 'processing' || job.status === 'starting')) {
                if (status) status.textContent = job.message || 'Loading…';
            } else if (job && job.status === 'completed') {
                ended = true;
                const files = (job.result && job.result.aux_datasets) || [];
                const coding = job.result && job.result.context && job.result.context.coding;
                dropPills(dataInfo.folder, dataInfo.aux_datasets);       // the dataset's old pill(s) go as the new come (the app replaced the files on completion)
                if (typeof createIntervalsAuxiliaryPills === 'function') createIntervalsAuxiliaryPills(files, dataInfo, { coding: !!(coding && coding.status === 'running'), line: (coding && coding.line) || '' });
                if (coding && coding.status === 'running' && typeof pollContextCoding === 'function') pollContextCoding(jobId, dataInfo);
                else if (coding && coding.codes_path && typeof contextPillAdd === 'function') contextPillAdd([coding.codes_path], dataInfo, { coding: false, line: coding.line || '' });
                const warn = (job.result && Array.isArray(job.result.warnings) && job.result.warnings.length) ? ' Not written: ' + job.result.warnings.join('; ') + '.' : '';
                done(true, 'Loaded ' + what + ' ' + dataInfo.start_date + ' → ' + dataInfo.end_date + (online ? ' through Intervals.icu' : ' from the store, nothing fetched') + (files.length ? ': ' + files.map(f => String(f).split('/').pop()).join(', ') : ': no file written') + '.' + warn);
            } else if (job && job.status === 'error') { ended = true; done(false, 'Failed: ' + (job.error || 'the load failed')); }
            else if (job && job.status === 'not_found') { ended = true; done(false, 'The load is gone from the executor (restarted?)'); }
            else if (Date.now() - t0 > 300000) { ended = true; done(false, 'The load timed out'); }
            if (!ended) setTimeout(tick, 1000);
        };
        setTimeout(tick, 800);
    }

    // off the Data tab: the dataset's pill(s) - or every pill of the athlete - through the pills' own removers; the cache keeps the data
    async function unloadFromTab(folder, feed) {
        const pills = pillsOf(folder, feed);
        if ((!feed || feed === 'activities') && window.Intervals && window.Intervals.state.isLoaded && window.Intervals.state.dataInfo && window.Intervals.state.dataInfo.folder === folder && window.Intervals.state.pillId) {
            const pill = document.getElementById(window.Intervals.state.pillId);
            if (pill && typeof removeDatasetPill === 'function') await removeDatasetPill(pill, null, true);
            else if (window.Intervals.removePill) window.Intervals.removePill();
        }
        for (const p of pills) {
            if (typeof removeDatasetPill === 'function') await removeDatasetPill(p, null, true);     // the pill's own × (the context pill drops both its files)
            else p.remove();
        }
        if (shown && shown.folder === folder) (shown.feed ? showFeedDetails(folder, shown.feed) : showSubjectDetails(folder));
        renderTree();
    }

    // Forget (the product owner's word, 2026-10-29): the dataset off the Data tab and out of the cache - or the athlete whole -
    // after asking; a later load downloads it again. The activity summary is the activity list, which every load from the
    // store starts from: its Forget is off the Data tab alone.
    async function forgetDataset(folder, feed, name) {
        const what = feed ? (FEED_NAMES[feed] || feed) + ' of ' + (name || folder) : 'everything held for ' + (name || folder);
        if (feed === 'summary') { await unloadFromTab(folder, feed); return; }
        if (!confirm('Forget ' + what + '? It comes off the Data tab and out of the cache; a later load downloads it again.')) return;
        await unloadFromTab(folder, feed);
        try {
            const response = await window.authService.fetch('/cache/forget', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder: folder, feed: feed || '' }) });
            const out = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(out.error || ('HTTP ' + response.status));
            if (out.primary_dropped) clearPrimaryPills({ source: 'intervals' });     // the Data tab's frame was the athlete's: its pill goes, the tab is free
            const details = document.getElementById('datasetDetails');
            if (details) { details.className = 'dataset-details-empty'; details.innerHTML = 'Select a dataset to see its details'; }
            shown = null;
            loadDatasets();
        } catch (error) {
            console.error('Error forgetting from the cache:', error);
            alert('Could not forget: ' + (error.message || error));
        }
    }
    
    async function handleLoadDataset(button) {
        const dfId = button.dataset.dfId;
        const filePath = button.dataset.path;
        
        if (dfId) {
            await loadPrimaryDataset(dfId);
        } else if (filePath) {
            // Load both auxiliary and generated datasets as auxiliary
            await loadAuxiliaryDataset(filePath);
        }
    }

    async function handleRemoveDataset(button) {
        const dfId = button.dataset.dfId;
        const filePath = button.dataset.path;
        
        if (dfId) {
            await removePrimaryDataset(dfId);
        } else if (filePath) {
            await removeAuxiliaryDataset(filePath);
        }
    }
    
    async function handleDownloadDataset(button) {
        const filePath = button.dataset.path;
        
        if (filePath) {
            // Use the existing main app download endpoint
            window.authService.fetch(`/download_generated_dataset?path=${encodeURIComponent(filePath)}`)
                .then(response => {
                    if (!response.ok) throw new Error('Download failed');
                    return response.blob();
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filePath.split('/').pop();
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                })
                .catch(error => {
                    console.error('Error downloading dataset:', error);
                    alert('Failed to download dataset');
                });
        }
    }

    function showModal() {
        const modal = document.getElementById('datasetManagerModal');
        if (modal) {
            modal.style.display = 'flex';
            loadDatasets();
        }
    }
    
    function hideModal() {
        const modal = document.getElementById('datasetManagerModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    function loadDatasets() {
        // Show loading state
        showLoadingState();
        
        // Fetch cache data from backend
        window.authService.fetch('/cache/inspect', { method: 'GET' })
        .then(cacheResponse => {
            if (!cacheResponse.ok) {
                throw new Error(`Failed to fetch datasets: ${cacheResponse.status}`);
            }
            return cacheResponse.json();
        })
        .then(cacheData => {
            currentDatasets.cached = cacheData.cached_dataframes || [];
            currentDatasets.auxiliary = cacheData.auxiliary_datasets || [];
            currentDatasets.generated = cacheData.generated_datasets || [];
            currentDatasets.stores = cacheData.stores || [];
            currentDatasets.tree = cacheData.tree || treeFromLists(cacheData);
            displayDatasets();
        })
        .catch(error => {
            console.error('Error loading datasets:', error);
            showErrorState('Failed to load datasets');
        });
    }

    // an executor from before the tree (v68 and earlier) lists frames and files only: the same groups, without athletes
    function treeFromLists(d) {
        const frames = d.cached_dataframes || [], files = (d.auxiliary_datasets || []).filter(f => !f.view);
        const by = src => frames.filter(f => String(f.source) === src);
        return { sources: [{ source: 'intervals', title: 'Intervals.icu', subjects: [], frames: by('intervals') },
                           { source: 'endura', title: 'Endura', frames: by('endura'), files: files.filter(f => /^(athlete_profiles|race_turns|race_climbs|race_waymarkers)_race_/.test(f.filename || '')) },
                           { source: 'sweatstack', title: 'SweatStack', frames: by('sweatstack') }],
                 uploads: { frames: frames.filter(f => !['intervals', 'endura', 'sweatstack'].includes(String(f.source))), files: files.filter(f => !f.folder && !/^(athlete_profiles|race_turns|race_climbs|race_waymarkers)_race_|^(activity_summary|wellness_data|activity_intervals|context_notes|context_codes|planned_workouts|rider_profile|custom_zone_times)_/.test(f.filename || '')) } };
    }
    
    function displayDatasets() {
        renderTree();
        if (shown && subjectOf(shown.folder)) (shown.feed ? showFeedDetails(shown.folder, shown.feed) : showSubjectDetails(shown.folder));     // redrawn over the fresh tree

        // Display generated datasets
        const genList = document.getElementById('generatedDatasetList');
        if (genList) {
            genList.innerHTML = '';
            
            if (currentDatasets.generated.length === 0) {
                genList.innerHTML = '<div class="dataset-empty">No generated datasets</div>';
            } else {
                currentDatasets.generated.forEach(dataset => {
                    const item = createDatasetItem(dataset, 'generated');
                    genList.appendChild(item);
                });
            }
        }
    }
    
    // ---- the tree (docs/DATASETS_DESIGN.md §1, §8, §16) --------------------------------------------------------------
    const esc = t => escapeHtml(String(t == null ? '' : t));
    function mb(bytes, mbValue) {
        const v = typeof mbValue === 'number' ? mbValue : Number(bytes || 0) / (1024 * 1024);
        return v >= 100 ? Math.round(v) + ' MB' : v >= 1 ? v.toFixed(1) + ' MB' : v > 0 ? (v * 1024).toFixed(0) + ' KB' : '';
    }
    function ago(epoch) {
        if (!epoch) return '';
        const days = Math.floor((Date.now() / 1000 - Number(epoch)) / 86400);
        return days <= 0 ? 'today' : days === 1 ? 'yesterday' : days < 30 ? days + ' days ago' : days < 365 ? Math.round(days / 30) + ' months ago' : new Date(Number(epoch) * 1000).toISOString().slice(0, 10);
    }
    function dayOf(epoch) { return epoch ? new Date(Number(epoch) * 1000).toISOString().slice(0, 10) : ''; }
    function span(f) { return f.from ? esc(f.from) + ' → ' + esc(f.to) : (f.as_of ? 'as of ' + esc(f.as_of) : ''); }
    const n_ = v => Number(v || 0).toLocaleString();
    function count(f) {
        const n = Number(f.count || 0);
        if (f.feed === 'activities') return n_(n) + ' activit' + (n === 1 ? 'y' : 'ies');
        if (f.feed === 'summary') return n_(n) + ' row' + (n === 1 ? '' : 's') + ', one per activity';
        if (f.feed === 'laps') return n_(n) + ' activit' + (n === 1 ? 'y' : 'ies') + (f.rows ? ' · ' + n_(f.rows) + ' lap' + (f.rows === 1 ? '' : 's') : '');
        if (f.feed === 'wellness') return n_(n) + ' day' + (n === 1 ? '' : 's');
        if (f.feed === 'context') return n_(n) + ' chat' + (n === 1 ? '' : 's') + ' · ' + n_(f.entries) + ' calendar entr' + (Number(f.entries || 0) === 1 ? 'y' : 'ies');
        if (f.feed === 'profile') return 'the settings and the zones';
        return String(n);
    }
    function matches(q, ...texts) { return !q || texts.some(t => String(t || '').toLowerCase().includes(q)); }
    const dot = on => `<span class="ds-dot${on ? ' on' : ''}" title="${on ? 'on the Data tab now' : 'in the store only'}"></span>`;

    function frameLine(f) {
        // a frame the executor holds as a frame alone: an upload, an Endura race, a SweatStack load (an Intervals.icu window is a view of the store, not listed)
        const item = document.createElement('div');
        item.className = 'dataset-item';
        const where = f.original_filename ? esc(f.original_filename) : f.race_title ? esc(f.race_title) : f.date_range ? esc(f.date_range) : esc(f.source || 'frame');
        const rows = f.shape ? Number(f.shape[0]).toLocaleString() + ' rows' : '';
        item.innerHTML = `<span class="dataset-item-name">${where}${rows ? ' · ' + rows : ''}</span><span class="dataset-size">${mb(null, Number(f.memory_mb || 0))}</span>`;
        item.dataset.id = f.df_id; item.dataset.type = 'primary';
        const full = (currentDatasets.cached || []).find(c => c.df_id === f.df_id) || f;
        item.addEventListener('click', ev => selectDataset.call(item, full, 'primary', ev));
        return item;
    }
    function fileLine(f) { return createDatasetItem(f, 'auxiliary'); }
    function feedLine(subject, f, tab) {
        const line = document.createElement('div');
        line.className = 'ds-feed' + (shown && shown.folder === subject.folder && shown.feed === f.feed ? ' active' : '');
        line.dataset.feed = f.feed;
        line.title = 'Click for the details';
        const on = !!tab[f.feed];
        line.innerHTML = dot(on) + `<span class="ds-feed-name">${esc(FEED_NAMES[f.feed] || f.feed)}</span><span class="ds-feed-span">${span(f)}</span>` +
            `<span class="ds-feed-count">${esc(count(f))}${f.bytes ? ' · ' + mb(f.bytes) : ''}</span><span class="ds-feed-state${on ? ' on' : ''}">${on ? 'on the Data tab' : 'in the store only'}</span>`;
        return line;
    }
    function subjectBlock(subject, q) {
        const open = isOpen(subject.folder);
        const tab = onTab(subject.folder);
        const block = document.createElement('div');
        block.className = 'ds-subj' + (open ? ' open' : '');
        block.dataset.folder = subject.folder;
        const head = document.createElement('div');
        head.className = 'ds-subj-head' + (shown && shown.folder === subject.folder && !shown.feed ? ' active' : '');
        head.title = 'Click for the details: load everything held, or take it off the Data tab';
        const held = subject.held_since ? 'held since ' + dayOf(subject.held_since) : '';
        const last = subject.last_load ? 'loaded ' + ago(subject.last_load) : '';
        head.innerHTML = `<span class="ds-caret" title="${open ? 'Fold' : 'Unfold'}">${open ? '▾' : '▸'}</span><span class="ds-subj-name" title="${esc(subject.id)}">${esc(subject.name || subject.id)}</span>` +
            `<span class="ds-subj-meta">${[held, last].filter(Boolean).join(' · ')}</span><span class="dataset-size">${mb(null, Number(subject.size_mb || 0))}</span>`;
        block.appendChild(head);
        if (open) {
            const body = document.createElement('div');
            body.className = 'ds-subj-body';
            const feeds = (subject.feeds || []).filter(f => matches(q, FEED_NAMES[f.feed], f.feed, subject.name, subject.id));
            feeds.forEach(f => body.appendChild(feedLine(subject, f, tab)));
            if (!feeds.length) body.innerHTML = '<div class="dataset-empty">nothing held</div>';
            block.appendChild(body);
        }
        return block;
    }
    function group(title, hint) {
        const g = document.createElement('div');
        g.className = 'dataset-category ds-group';
        g.innerHTML = `<h4>${esc(title)}</h4>`;
        if (hint) { const e = document.createElement('div'); e.className = 'dataset-empty'; e.textContent = hint; g.appendChild(e); }
        return g;
    }

    function renderTree() {
        const root = document.getElementById('datasetTree');
        if (!root) return;
        root.innerHTML = '';
        const tree = currentDatasets.tree || { sources: [], uploads: { frames: [], files: [] } };
        const filter = document.getElementById('datasetFilter');
        const q = String((filter || {}).value || '').trim().toLowerCase();
        // the filter box earns its place when there is more than one athlete to tell apart
        const athletes = (tree.sources || []).reduce((n, src) => n + (src.subjects || []).length, 0);
        if (filter) filter.style.display = (athletes > 1 || q) ? '' : 'none';
        (tree.sources || []).forEach(src => {
            const subjects = (src.subjects || []).filter(sb => matches(q, sb.name, sb.id) || (sb.feeds || []).some(f => matches(q, FEED_NAMES[f.feed], f.feed)));
            const frames = (src.frames || []).filter(f => matches(q, f.date_range, f.race_title, f.original_filename, src.title));
            const files = (src.files || []).filter(f => matches(q, f.filename));
            if (src.source !== 'intervals' && !frames.length && !files.length) return;
            const g = group(src.title, (src.source === 'intervals' && !subjects.length && !frames.length) ? (q ? 'nothing matches' : 'nothing held yet — a load fills it') : '');
            subjects.forEach(sb => g.appendChild(subjectBlock(sb, q)));
            frames.forEach(f => g.appendChild(frameLine(f)));
            files.forEach(f => g.appendChild(fileLine(f)));
            root.appendChild(g);
        });
        const up = tree.uploads || { frames: [], files: [] };
        const upFrames = (up.frames || []).filter(f => matches(q, f.original_filename, f.source)), upFiles = (up.files || []).filter(f => notHidden(f) && matches(q, f.filename));
        const ug = group('Uploads', (!upFrames.length && !upFiles.length) ? (q ? 'nothing matches' : 'no uploaded datasets') : '');
        upFrames.forEach(f => ug.appendChild(frameLine(f)));
        upFiles.forEach(f => ug.appendChild(fileLine(f)));
        root.appendChild(ug);
    }

    // ---- the details of an athlete and of a dataset (the right pane; the actions live here, as the files' Load and Remove do) ----
    function onTabCell(entry, files) {
        return entry ? `<span class="ds-on" title="on the Data tab now">● ${esc(entry.span)}</span>${files ? ' &nbsp;' + esc(entry.files.join(', ')) : ''}` : '<span class="ds-off">○ not loaded</span>';
    }
    function actionRows(folder, feed, name, loaded, held) {
        const what = feed ? FEED_NAMES[feed] : 'everything';
        const from = feed ? 'the span held, from the store alone' : 'every dataset held, from the store alone - nothing fetched';
        const replaces = feed === 'activities' ? 'replaces the frame, and the datasets on the Data tab come with it to the same window' : feed ? 'replaces the ' + what + ' pill' : 'replaces what is on the Data tab';
        const forgetOn = feed === 'summary' ? loaded : held;
        const forgetHint = feed === 'summary' ? (loaded ? 'takes the pill off the Data tab; the activity list stays in the cache (every load from the store starts from it)' : 'not on the Data tab')
                         : feed ? 'off the Data tab and out of the cache; a later load downloads it again' : 'every pill off the Data tab and the athlete out of the cache; a later load downloads it all again';
        return `<div class="ds-actions">
            <div class="ds-row"><button class="dataset-action-btn dataset-load-btn wide" data-act="load" data-folder="${esc(folder)}" data-feed="${esc(feed)}" ${held ? '' : 'disabled'}>Load ${esc(what)}</button><span class="hint">${held ? from + '; ' + replaces : 'nothing held yet: load from the Intervals.icu dialog first'}</span></div>
            <div class="ds-row"><button class="dataset-action-btn dataset-load-btn wide" data-act="today" data-folder="${esc(folder)}" data-feed="${esc(feed)}" ${held ? '' : 'disabled'}>Load ${esc(what)} to today</button><span class="hint">through Intervals.icu: only the missing days come down${feed === 'activities' ? '; the datasets on the Data tab come with it' : ''}</span></div>
            <div class="ds-row"><button class="dataset-action-btn dataset-remove-btn wide" data-act="forget" data-folder="${esc(folder)}" data-feed="${esc(feed)}" data-name="${esc(name)}" ${forgetOn ? '' : 'disabled'}>Forget ${esc(what)}</button><span class="hint">${forgetHint}</span></div>
        </div>`;
    }

    function showSubjectDetails(folder) {
        const panel = document.getElementById('datasetDetails');
        const subject = subjectOf(folder);
        if (!panel || !subject) return;
        shown = { folder: folder, feed: '' };
        panel.classList.remove('dataset-details-empty');
        const tab = onTab(folder);
        const feeds = subject.feeds || [];
        const onNames = feeds.filter(f => tab[f.feed]).map(f => FEED_NAMES[f.feed]), offNames = feeds.filter(f => !tab[f.feed]).map(f => FEED_NAMES[f.feed]);
        const spans = Object.values(tab).map(e => e.span);
        const whole = spanOf(subject, '');
        const rows = feeds.map(f => `<tr><td>${dot(!!tab[f.feed])}</td><td>${esc(FEED_NAMES[f.feed] || f.feed)}</td><td>${span(f)}</td><td>${esc(count(f))}</td></tr>`).join('');
        panel.innerHTML = `<div class="dataset-details-content">
            <div class="dataset-info-section"><h3>${esc(subject.name || subject.id)}</h3><div class="ds-kv">
                <span class="k">Intervals.icu id</span><span>${esc(subject.id)}</span>
                <span class="k">Held since</span><span>${esc(dayOf(subject.held_since))}${subject.last_load ? ' · last load ' + esc(ago(subject.last_load)) : ''} · ${mb(null, Number(subject.size_mb || 0)) || '0 KB'}</span>
                <span class="k">Span held</span><span>${whole ? esc(whole.from) + ' → ' + esc(whole.to) : 'nothing yet'}</span>
                <span class="k">On the Data tab</span><span>${onNames.length ? `<span class="ds-on">● ${esc(spans[0])}</span> &nbsp;${esc(onNames.join(', '))}` : '<span class="ds-off">○ nothing of this athlete</span>'}</span>
                ${offNames.length && onNames.length ? `<span class="k">Not loaded</span><span>${esc(offNames.join(', '))}</span>` : ''}
            </div></div>
            <div class="dataset-info-section dataset-info-columns"><h3>Held</h3><div class="dataset-columns"><table class="dataset-preview-table ds-feeds"><thead><tr><th></th><th>Dataset</th><th>Span</th><th>Held</th></tr></thead><tbody>${rows || '<tr><td colspan="4">nothing held yet</td></tr>'}</tbody></table></div></div>
            <div id="dsLoadStatus" class="ds-load-status" style="display:none"></div>
            ${actionRows(folder, '', subject.name || subject.id, onNames.length > 0, feeds.length > 0)}
        </div>`;
    }

    function showFeedDetails(folder, feedName) {
        const panel = document.getElementById('datasetDetails');
        const subject = subjectOf(folder);
        const f = subject && lineOf(subject, feedName);
        if (!panel || !f) return;
        shown = { folder: folder, feed: feedName };
        panel.classList.remove('dataset-details-empty');
        const tab = onTab(folder)[f.feed];
        const files = f.feed === 'activities' ? [{ file: 'the frame on the Data tab', columns: f.columns || [] }] : (f.files || []);
        const cats = f.categories ? Object.keys(f.categories).sort((a, b) => f.categories[b] - f.categories[a]).map(k => esc(k || '(none)') + ' ' + f.categories[k]).join(', ') : '';
        // the span is the window the loads covered; the data's own first and last day beside the count when they differ (2026-10-29)
        const days = f.first && (f.first !== f.from || f.last !== f.to) ? ' (' + esc(f.first) + ' → ' + esc(f.last) + ')' : '';
        const held = [span(f), count(f) + days, mb(f.bytes), f.last_used ? 'last used ' + esc(ago(f.last_used)) : ''].filter(Boolean).join(' · ');
        const cols = files.map(x => {
            const note = x.file.startsWith('context_codes') ? ', written by the coding pass behind the load' : x.file.startsWith('custom_zone_times') && !x.columns.length ? ': only when the account defines a custom zone set' : '';
            const label = files.length > 1 ? `<div class="ds-file"><span class="mono">${esc(x.file)}</span> · ${x.columns.length} column${x.columns.length === 1 ? '' : 's'}${note}</div>` : '';
            return label + `<div class="column-list">${x.columns.map(c => `<span class="column-chip">${esc(c)}</span>`).join('') || '<span class="dataset-empty">no columns known yet</span>'}</div>`;
        }).join('');
        panel.innerHTML = `<div class="dataset-details-content">
            <div class="dataset-info-section"><h3>${esc(FEED_NAMES[f.feed] || f.feed)} · ${esc(subject.name || subject.id)}</h3><div class="ds-kv">
                <span class="k">What it is</span><span>${esc(FEED_HINTS[f.feed] || '')}</span>
                <span class="k">Held</span><span>${held}${cats ? ' · ' + cats : ''}</span>
                <span class="k">On the Data tab</span><span>${onTabCell(tab, true)}</span>
                <span class="k">A load writes</span><span>${f.feed === 'activities' ? 'the frame on the Data tab' : esc(files.map(x => x.file).join(', '))}</span>
            </div></div>
            <div class="dataset-info-section dataset-info-columns"><h3>Columns${files.length === 1 ? ' (' + files[0].columns.length + ')' : ''}</h3><div class="dataset-columns">${cols}</div></div>
            <div id="dsLoadStatus" class="ds-load-status" style="display:none"></div>
            ${actionRows(folder, f.feed, subject.name || subject.id, !!tab, true)}
        </div>`;
    }

    function createDatasetItem(dataset, type) {
        const item = document.createElement('div');
        item.className = 'dataset-item';
        
        // Add type-specific class for styling
        if (type === 'generated') {
            item.classList.add('generated-type');
        }
        
        if (type === 'primary') {
            const name = dataset.source === 'csv' ? 
                (dataset.original_filename || 'Dataset') : 
                `${dataset.source || 'Dataset'} (${dataset.shape[0]} rows)`;
            
            item.innerHTML = `
                <span class="dataset-item-name">${name}</span>
                <span class="dataset-size">${dataset.memory_mb.toFixed(3)} MB</span>
            `;
            item.dataset.id = dataset.df_id;
            item.dataset.type = 'primary';
        } else if (type === 'generated') {
            // Generated datasets with download icon
            item.innerHTML = `
                <svg class="dataset-icon-download" viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
                    <path d="M8 2a.5.5 0 0 1 .5.5v8.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 1 1 .708-.708L7.5 11.293V2.5A.5.5 0 0 1 8 2z"/>
                    <path d="M2.5 14a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11z"/>
                </svg>
                <span class="dataset-item-name">${dataset.filename}</span>
                <span class="dataset-size">${dataset.size_mb.toFixed(3)} MB</span>
            `;
            item.dataset.path = dataset.path;
            item.dataset.type = 'generated';
        } else {
            item.innerHTML = `
                <span class="dataset-item-name">${dataset.filename}</span>
                <span class="dataset-size">${dataset.size_mb.toFixed(3)} MB</span>
            `;
            item.dataset.path = dataset.path;
            item.dataset.type = 'auxiliary';
        }
        
        item.addEventListener('click', ev => selectDataset.call(item, dataset, type, ev));
        
        return item;
    }

    function selectDataset(dataset, type, ev) {
        // Update active state
        document.querySelectorAll('.dataset-item').forEach(item => {
            item.classList.remove('active');
        });
        const el = (ev && ev.currentTarget) || this;
        if (el && el.classList) el.classList.add('active');
        
        // Store selected dataset
        selectedDataset = { dataset, type };
        
        // Load and display details
        if (type === 'primary') {
            loadPrimaryDatasetDetails(dataset);
        } else if (type === 'generated') {
            loadGeneratedDatasetDetails(dataset);
        } else {
            loadAuxiliaryDatasetDetails(dataset);
        }
    }
    
    function loadPrimaryDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Fetch detailed preview
        window.authService.fetch(`/cache/preview/${dataset.df_id}`, {
            method: 'GET'
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayPrimaryDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }
    
    function loadAuxiliaryDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Fetch auxiliary dataset preview
        window.authService.fetch('/cache/preview_aux', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: dataset.path })
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayAuxiliaryDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }

    function loadGeneratedDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Use same preview endpoint as auxiliary (they're both files)
        window.authService.fetch('/cache/preview_aux', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: dataset.path })
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayGeneratedDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }
    
    function displayPrimaryDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>Dataset Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">ID:</span>
                        <span class="metadata-value">${details.df_id}</span>
                        
                        <span class="metadata-label">Shape:</span>
                        <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
        `;
        
        if (details.metadata) {
            if (details.metadata.source) {
                html += `
                    <span class="metadata-label">Source:</span>
                    <span class="metadata-value">${details.metadata.source}</span>
                `;
            }
            
            // Add Endura-specific metadata
            if (details.metadata.source === 'endura') {
                if (details.metadata.race_title) {
                    html += `
                        <span class="metadata-label">Race:</span>
                        <span class="metadata-value">${details.metadata.race_title}</span>
                    `;
                }
                if (details.metadata.race_date) {
                    html += `
                        <span class="metadata-label">Race Date:</span>
                        <span class="metadata-value">${details.metadata.race_date}</span>
                    `;
                }
                if (details.metadata.athletes_count) {
                    html += `
                        <span class="metadata-label">Athletes:</span>
                        <span class="metadata-value">${details.metadata.athletes_count}</span>
                    `;
                }
            }
            
            // Existing date_range and cached_at handling
            if (details.metadata.date_range) {
                html += `
                    <span class="metadata-label">Date Range:</span>
                    <span class="metadata-value">${details.metadata.date_range}</span>
                `;
            }
            if (details.metadata.cached_at) {
                html += `
                    <span class="metadata-label">Cached:</span>
                    <span class="metadata-value">${new Date(details.metadata.cached_at).toLocaleString()}</span>
                `;
            }
        }
        
        html += `
                    </div>
                </div>
                
                <div class="dataset-info-section dataset-info-columns">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
        `;
        
        details.columns.forEach(col => {
            html += `<span class="column-chip">${col}</span>`;
        });
        
        html += `
                        </div>
                    </div>
                </div>
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-df-id="${details.df_id}">Load</button>
                <button class="dataset-action-btn dataset-remove-btn" data-df-id="${details.df_id}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }
    
    function displayAuxiliaryDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>File Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">Filename:</span>
                        <span class="metadata-value">${details.filename}</span>
                        
                        <span class="metadata-label">Path:</span>
                        <span class="metadata-value">${details.path}</span>
                        
                        <span class="metadata-label">Size:</span>
                        <span class="metadata-value">${details.size_mb.toFixed(3)} MB</span>
        `;
        
        if (details.shape) {
            html += `
                <span class="metadata-label">Shape:</span>
                <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
            `;
        }
        
        html += `
                        <span class="metadata-label">Created:</span>
                        <span class="metadata-value">${new Date(details.created_at).toLocaleString()}</span>
                        
                        <span class="metadata-label">Modified:</span>
                        <span class="metadata-value">${new Date(details.modified_at).toLocaleString()}</span>
                    </div>
                </div>
        `;
        
        if (details.columns && details.columns.length > 0) {
            html += `
                <div class="dataset-info-section dataset-info-columns">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
            `;
            
            details.columns.forEach(col => {
                html += `<span class="column-chip">${col}</span>`;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += `
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-path="${details.path}">Load</button>
                <button class="dataset-action-btn dataset-remove-btn" data-path="${details.path}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }
    
    function displayGeneratedDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>Generated File Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">Filename:</span>
                        <span class="metadata-value">${details.filename}</span>
                        
                        <span class="metadata-label">Path:</span>
                        <span class="metadata-value">${details.path}</span>
                        
                        <span class="metadata-label">Size:</span>
                        <span class="metadata-value">${details.size_mb.toFixed(3)} MB</span>
        `;
        
        if (details.shape) {
            html += `
                <span class="metadata-label">Shape:</span>
                <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
            `;
        }
        
        html += `
                        <span class="metadata-label">Generated:</span>
                        <span class="metadata-value">${new Date(details.created_at).toLocaleString()}</span>
                    </div>
                </div>
        `;
        
        if (details.columns && details.columns.length > 0) {
            html += `
                <div class="dataset-info-section dataset-info-columns">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
            `;
            
            details.columns.forEach(col => {
                html += `<span class="column-chip">${col}</span>`;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += `
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-path="${details.path}">Load</button>
                <button class="dataset-action-btn dataset-download-btn" data-path="${details.path}">Download</button>
                <button class="dataset-action-btn dataset-remove-btn" data-path="${details.path}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }

    async function removePrimaryDataset(dfId) {
        // Update button state
        const removeButton = document.querySelector(`.dataset-remove-btn[data-df-id="${dfId}"]`);
        const originalText = removeButton ? removeButton.textContent : 'Remove';
        
        if (removeButton) {
            removeButton.textContent = 'Removing...';
            removeButton.classList.add('loading');
            removeButton.disabled = true;
        }
        
        try {
            const response = await window.authService.fetch('/cache/remove_primary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ df_id: dfId })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to remove dataset');
            }
            
            // Get dataset info to determine source
            const dataset = currentDatasets.cached.find(d => d.df_id === dfId);
            clearPrimaryPills(dataset);
            
            // Clear the details pane if this was the selected dataset
            if (selectedDataset && selectedDataset.dataset.df_id === dfId) {
                const detailsPanel = document.getElementById('datasetDetails');
                if (detailsPanel) {
                    detailsPanel.className = 'dataset-details-empty';
                    detailsPanel.innerHTML = 'Select a dataset to view details';
                }
                selectedDataset = null;
            }
            
            // Refresh cache display
            loadDatasets();
            
            console.log('Primary dataset removed from cache');
            
        } catch (error) {
            console.error('Error removing primary dataset:', error);
            alert('Failed to remove dataset: ' + error.message);
        } finally {
            if (removeButton) {
                removeButton.textContent = originalText;
                removeButton.classList.remove('loading');
                removeButton.disabled = false;
            }
        }
    }

    // the Data tab's pills and the loaders' state after the primary frame went (removed, or forgotten with its athlete)
    function clearPrimaryPills(dataset) {
        {                                                      // (the block as it stood in removePrimaryDataset)
            if (dataset) {
                if (dataset.source === 'sweatstack') {
                    // Remove SweatStack pill
                    if (window.SweatStack && window.SweatStack.state.pillId) {
                        const pill = document.getElementById(window.SweatStack.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear SweatStack state
                    if (window.SweatStack) {
                        window.SweatStack.state.isLoaded = false;
                        window.SweatStack.state.pillId = null;
                    }
                } else if (dataset.source === 'intervals') {
                    // Remove Intervals pill
                    if (window.Intervals && window.Intervals.state.pillId) {
                        const pill = document.getElementById(window.Intervals.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear Intervals state
                    if (window.Intervals) {
                        window.Intervals.state.isLoaded = false;
                        window.Intervals.state.pillId = null;
                    }
                } else if (dataset.source === 'endura') {
                    // Remove Endura pill
                    if (window.Endura && window.Endura.state.pillId) {
                        const pill = document.getElementById(window.Endura.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear Endura state
                    if (window.Endura) {
                        window.Endura.state.isLoaded = false;
                        window.Endura.state.pillId = null;
                        window.Endura.state.raceInfo = null;
                    }
                } else {
                    // Remove regular primary dataset pills
                    const pills = document.querySelectorAll('.primary-dataset-pill');
                    pills.forEach(pill => {
                        // Check if it's a cache-loaded pill
                        if (pill.id && (pill.id.startsWith('cache-primary-pill-') || pill.id.startsWith('gen-primary-pill-'))) {
                            pill.remove();
                        }
                    });
                }
            } else {
                // Fallback: remove any primary pills if dataset info not found
                const pills = document.querySelectorAll('.primary-dataset-pill');
                pills.forEach(pill => {
                    if (pill.id && (pill.id.startsWith('cache-primary-pill-') || pill.id.startsWith('gen-primary-pill-'))) {
                        pill.remove();
                    }
                });
            }
            
            // Clear global state
            currentDatasetName = null;
        }
    }

    async function removeAuxiliaryDataset(filePath) {
        // Update button state
        const removeButton = document.querySelector(`.dataset-remove-btn[data-path="${filePath}"]`);
        const originalText = removeButton ? removeButton.textContent : 'Remove';
        
        if (removeButton) {
            removeButton.textContent = 'Removing...';
            removeButton.classList.add('loading');
            removeButton.disabled = true;
        }
        
        try {
            const response = await window.authService.fetch('/cache/remove_auxiliary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to remove dataset');
            }
            
            const data = await response.json();
            
            // Find and remove the pill if it exists
            const pills = document.querySelectorAll('.auxiliary-dataset-pill');
            pills.forEach(pill => {
                if (pill.dataset.identifier === filePath) {
                    pill.remove();
                }
            });
            
            // Update auxiliary count
            auxiliaryDatasetCount = data.aux_count || Math.max(0, auxiliaryDatasetCount - 1);
            
            // Clear the details pane if this was the selected dataset
            if (selectedDataset && selectedDataset.dataset.path === filePath) {
                const detailsPanel = document.getElementById('datasetDetails');
                if (detailsPanel) {
                    detailsPanel.className = 'dataset-details-empty';
                    detailsPanel.innerHTML = 'Select a dataset to view details';
                }
                selectedDataset = null;
            }
            
            // Refresh cache display
            loadDatasets();
            
            console.log('Auxiliary dataset removed from cache');
            
        } catch (error) {
            console.error('Error removing auxiliary dataset:', error);
            alert(`Failed to remove dataset: ${error.message}`);
        } finally {
            if (removeButton) {
                removeButton.textContent = originalText;
                removeButton.classList.remove('loading');
                removeButton.disabled = false;
            }
        }
    }
    
    // why a primary frame cannot be loaded now, or '' (the Data tab holds one dataset at a time)
    function primaryLoadedMessage() {
        if (typeof currentDatasetName !== 'undefined' && currentDatasetName) return 'Primary dataset already loaded. Remove current to load new.';
        if (window.SweatStack && window.SweatStack.state.isLoaded) return 'SweatStack data already loaded. Remove current to load primary dataset.';
        if (window.Intervals && window.Intervals.state.isLoaded) return 'Intervals ICU data already loaded. Remove current to load primary dataset.';
        if (window.Endura && window.Endura.state.isLoaded) return 'Endura data already loaded. Remove current to load primary dataset.';
        return '';
    }

    async function loadPrimaryDataset(dfId) {
        const busy = primaryLoadedMessage();
        if (busy) {
            if (typeof showUploadLimitMessage === 'function') showUploadLimitMessage(busy);
            return;
        }
        
        // Find and update the load button
        const loadButton = document.querySelector(`.dataset-load-btn[data-df-id="${dfId}"]`);
        const originalText = loadButton ? loadButton.textContent : 'Load';
        
        if (loadButton) {
            loadButton.textContent = 'Loading...';
            loadButton.classList.add('loading');
            loadButton.disabled = true;
        }
        
        try {
            // Call backend to load the dataset
            const response = await window.authService.fetch('/cache/load_primary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ df_id: dfId })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load dataset');
            }
            
            const data = await response.json();

            // Handle dataframe preview - render tab
            if (data.dataframe && typeof createOrUpdateTab === 'function') {
                const dfData = JSON.parse(data.dataframe);
                createOrUpdateTab('dataframe', dfData.data);
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            
            // Get dataset info from cache for pill creation
            const dataset = currentDatasets.cached.find(d => d.df_id === dfId);
            if (dataset) {
                const pillId = 'cache-primary-pill-' + Date.now();
                let displayText = '';
                let pillType = 'primary';
                
                // Determine display text based on source
                if (dataset.source === 'csv') {
                    displayText = `Primary (${dataset.original_filename || 'Dataset'}) loaded`;
                    currentDatasetName = dataset.original_filename || 'Dataset';
                    pillType = 'primary'
                } else if (dataset.source === 'intervals') {
                    displayText = `Intervals ICU (${dataset.activities_count} activities) loaded`;
                    currentDatasetName = `Intervals ICU Data`;
                    pillType = 'intervals';
                    
                    // Update Intervals state if module exists
                    if (window.Intervals) {
                        window.Intervals.state.isLoaded = true;
                        window.Intervals.state.pillId = pillId;
                    }
                } else if (dataset.source === 'sweatstack') {
                    // List sports
                    displayText = `SweatStack (${dataset.sports.join(', ')}) loaded`;
                    currentDatasetName = `SweatStack Data`;
                    pillType = 'sweatstack';

                    // Update SweatStack state if module exists
                    if (window.SweatStack) {
                        window.SweatStack.state.isLoaded = true;
                        window.SweatStack.state.pillId = pillId;
                    }
                } else if (dataset.source === 'endura') {
                    // Handle Endura dataset
                    displayText = `Endura (${dataset.race_title || 'Race'}) loaded`;
                    currentDatasetName = `Endura Race Data`;
                    pillType = 'endura';
                    
                    // Update Endura state if module exists
                    if (window.Endura) {
                        window.Endura.state.isLoaded = true;
                        window.Endura.state.pillId = pillId;
                        window.Endura.state.raceInfo = {
                            race_id: dataset.race_id,
                            race_title: dataset.race_title,
                            race_date: dataset.race_date
                        };
                    }
                } else {
                    displayText = `Primary (${dataset.source || 'Dataset'}) loaded`;
                    currentDatasetName = dataset.source || 'Dataset';
                    pillType = 'primary';
                }
                
                // Create pill using file-management function
                if (typeof createOrUpdateDatasetPill === 'function') {
                    createOrUpdateDatasetPill(pillId, displayText, pillType, 'success', false, null);
                }
            }
            
            // Close modal
            hideModal();
            
            // Show success message
            console.log('Primary dataset loaded successfully from cache');
            
        } catch (error) {
            console.error('Error loading primary dataset:', error);
            alert(`Failed to load dataset: ${error.message}`);
        } finally {
            // Restore button state
            if (loadButton) {
                loadButton.textContent = originalText;
                loadButton.classList.remove('loading');
                loadButton.disabled = false;
            }
        }
    }
    
    async function loadAuxiliaryDataset(filePath) {
        // Check auxiliary limit
        if (auxiliaryDatasetCount >= MAX_AUXILIARY_DATASETS) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('Maximum ' + MAX_AUXILIARY_DATASETS + ' auxiliary datasets allowed.');
            }
            return;
        }
        
        // Find and update the load button
        const loadButton = document.querySelector(`.dataset-load-btn[data-path="${filePath}"]`);
        const originalText = loadButton ? loadButton.textContent : 'Load';
        
        if (loadButton) {
            loadButton.textContent = 'Loading...';
            loadButton.classList.add('loading');
            loadButton.disabled = true;
        }
        
        try {
            // Call backend to load the dataset
            const response = await window.authService.fetch('/cache/load_auxiliary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load dataset');
            }
            
            const data = await response.json();
            
            // Handle dataframe preview - same as primary
            if (data.dataframe && typeof createOrUpdateTab === 'function') {
                const dfData = JSON.parse(data.dataframe);
                createOrUpdateTab('dataframe', dfData.data);
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            
            // Determine dataset source for proper naming
            const isGenerated = filePath.includes('/generated/');
            const datasetList = isGenerated ? currentDatasets.generated : currentDatasets.auxiliary;
            const dataset = datasetList.find(d => d.path === filePath);
            
            if (dataset) {
                const filename = dataset.filename;
                const pillId = isGenerated ? 'gen-aux-pill-' + Date.now() : 'cache-aux-pill-' + Date.now();
                let displayName = filename;
                
                // Special handling for Intervals auxiliary datasets
                if (filename.includes('wellness_data')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Wellness Summary (${days} days)`;
                    }
                } else if (filename.includes('activity_summary')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Activity Summary (${days} days)`;
                    }
                } else if (filename.includes('activity_intervals')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Activity Intervals (${days} days)`;
                    }
                } else if ((filename.includes('context_notes') || filename.includes('context_codes')) && typeof contextPillAdd === 'function') {
                    // the context and codes files of a load stack under the one Context pill (docs/CONTEXT_DESIGN.md, 2026-10-14)
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    const iso = s => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
                    contextPillAdd([filePath], dateMatch ? { start_date: iso(dateMatch[1]), end_date: iso(dateMatch[2]) } : null, { coding: false });
                    auxiliaryDatasetCount = data.aux_count || (auxiliaryDatasetCount + 1);
                    hideModal();
                    return;
                }
                
                const pillLabel = isGenerated ? `Generated (${displayName})` : `Auxiliary (${displayName})`;
                
                // Create pill using file-management function
                if (typeof createOrUpdateDatasetPill === 'function') {
                    createOrUpdateDatasetPill(
                        pillId,
                        pillLabel,
                        'auxiliary',
                        'success',
                        false,
                        filePath
                    );
                }
                
                // Update auxiliary count
                auxiliaryDatasetCount = data.aux_count || (auxiliaryDatasetCount + 1);
            }
            
            // Close modal
            hideModal();
            
            // Show success message
            console.log(isGenerated ? 'Generated dataset loaded as auxiliary' : 'Auxiliary dataset loaded successfully from cache');
            
        } catch (error) {
            console.error('Error loading dataset:', error);
            alert(`Failed to load dataset: ${error.message}`);
        } finally {
            // Restore button state
            if (loadButton) {
                loadButton.textContent = originalText;
                loadButton.classList.remove('loading');
                loadButton.disabled = false;
            }
        }
    }
    
    function showLoadingState() {
        const tree = document.getElementById('datasetTree');
        const genList = document.getElementById('generatedDatasetList');
        
        const loadingHtml = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading...</div>';
        
        if (tree) tree.innerHTML = loadingHtml;
        if (genList) genList.innerHTML = loadingHtml;
    }
    
    function showErrorState(message) {
        const tree = document.getElementById('datasetTree');
        const genList = document.getElementById('generatedDatasetList');
        
        const errorHtml = `<div style="color: var(--error-color); font-size: 13px;">${message}</div>`;
        
        if (tree) tree.innerHTML = errorHtml;
        if (genList) genList.innerHTML = '';
    }
    
    // Public API
    return {
        initialize: initialize,
        refresh: loadDatasets,
        loadPrimary: loadPrimaryDataset,
        loadAuxiliary: loadAuxiliaryDataset
    };
})();