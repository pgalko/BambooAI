// Dataset Manager Module - the Dataset cache dialog. Since 2026-10-29 (docs/DATASETS_DESIGN.md §8) it draws the executor's
// cache as a tree - source → athlete → dataset (named as the load dialog names them) - and a click on a line opens its
// details on the right, where the actions are: Load and Load to today bring the span held straight from the store onto the
// Data tab, Forget drops a dataset or the athlete; uploads and generated files keep their own groups. A load's window files
// are not listed: they are a run's inputs, shown on the run's Data tab.
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
                    <div><div class="dataset-modal-title title">Dataset cache</div><div class="sub">what your executor holds - by source and athlete, with uploads and generated files</div></div>
                    <span class="sp"></span>
                    <button class="close x" aria-label="Close">×</button>
                </div>
                <div class="dataset-modal-body">
                    <div class="dataset-list-panel">
                        <input type="search" id="datasetFilter" class="ds-filter ui-input" placeholder="Filter by name or feed" autocomplete="off">
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
            if (e.target.classList.contains('dataset-load-btn')) {
                handleLoadDataset(e.target);
            } else if (e.target.classList.contains('dataset-remove-btn')) {
                handleRemoveDataset(e.target);
            } else if (e.target.classList.contains('dataset-download-btn')) {
                handleDownloadDataset(e.target);
            }
        });
        // the tree's lines (2026-10-29, docs/DATASETS_DESIGN.md §8): the caret folds an athlete; a click on an athlete's line or a
        // feed line opens its details on the right, where the actions are (Load, Load to today, Forget) - as the files' Load and Remove
        const tree = document.getElementById('datasetTree');
        if (tree) tree.addEventListener('click', handleTreeClick);
        const filter = document.getElementById('datasetFilter');
        if (filter) filter.addEventListener('input', () => renderTree());
        document.addEventListener('click', function(e) {
            const b = e.target.closest('#datasetDetails [data-act]');
            if (!b) return;
            const d = b.dataset;
            if (d.act === 'load') startLoad(d.folder, d.from, d.to, false);
            else if (d.act === 'today') startLoad(d.folder, d.from, localDay(), true);
            else if (d.act === 'forget') forgetFromCache(d.folder, d.feed, d.name);
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
    function loadKinds(subject) {
        // the datasets a Load asks for: those of the athlete's last load (the record keeps them); for a record from before
        // they were kept, what the store holds, named as the load dialog names them
        if (Array.isArray(subject.kinds) && subject.kinds.length) return subject.kinds.slice();
        const held = new Set((subject.feeds || []).map(f => f.feed));
        const kinds = ['summary'];
        if (held.has('laps')) kinds.push('intervals');
        if (held.has('wellness')) kinds.push('wellness');
        if (held.has('events') || held.has('chats')) kinds.push('context');
        return kinds;
    }

    // Load / Load to today (docs/DATASETS_DESIGN.md §1, as the product owner asked on 2026-10-29): the window is loaded straight
    // from the store - the same job the Intervals.icu dialog starts, with the span held and the datasets held, no dialog; the
    // store serves what it holds and only what the window lacks is downloaded. A window loaded now is let go first, as its
    // pill's × does, after asking. The job's progress shows in the details pane; the pills appear on the Data tab as always.
    async function startLoad(folder, from, to, toToday) {
        const subject = subjectOf(folder);
        if (!subject || !from || !to) return;
        if (window.Intervals && window.Intervals.state.isLoaded && window.Intervals.state.pillId) {
            if (!confirm('The Data tab holds a window from Intervals.icu. Let it go and load ' + from + ' → ' + to + '?')) return;
            const pill = document.getElementById(window.Intervals.state.pillId);
            if (pill && typeof removeDatasetPill === 'function') await removeDatasetPill(pill, null, true);
            else if (window.Intervals.removePill) window.Intervals.removePill();
            // the window's file pills go with it (the files stay on the executor; the new load brings its own pills)
            let gone = 0;
            document.querySelectorAll('#datasetStatusPillsContainer .auxiliary-dataset-pill').forEach(p => { if (p.id !== 'contextPill' && /\/views\//.test(p.dataset.identifier || '')) { p.remove(); gone += 1; } });
            if (typeof contextPillClear === 'function') contextPillClear();
            if (typeof window.auxiliaryDatasetCount !== 'undefined') window.auxiliaryDatasetCount = Math.max(0, (window.auxiliaryDatasetCount || 0) - gone);
        }
        const busy = primaryLoadedMessage();
        if (busy) { if (typeof showUploadLimitMessage === 'function') showUploadLimitMessage(busy); return; }
        const kinds = loadKinds(subject);
        const status = document.getElementById('dsLoadStatus');
        const buttons = document.querySelectorAll('#datasetDetails [data-act]');
        buttons.forEach(b => { b.disabled = true; });
        if (status) { status.style.display = ''; status.className = 'ds-load-status loading'; status.textContent = 'Starting the load of ' + from + ' → ' + to + '…'; }
        try {
            const response = await window.authService.fetch('/intervals/load_data', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ start_date: from, end_date: to, metrics: [], aux_datasets: kinds, refresh: false }) });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            if (typeof pollIntervalsJob !== 'function') throw new Error('the Intervals.icu module is not on the page');
            const msg = document.getElementById('intervals-modal-message');
            if (msg) { msg.textContent = ''; msg.className = msg.className.replace(/\b(success|error|loading)-message\b/g, '').trim(); }      // an earlier load's line must not pass for this one's
            pollIntervalsJob(data.job_id, { start: from, end: to }, kinds);          // the dialog's own poller: the pills and the Data tab on completion
            const mirror = setInterval(() => {
                const text = msg ? msg.textContent : '';
                if (status) status.textContent = text || 'Loading…';
                if (/Data loaded successfully/.test(text)) {
                    clearInterval(mirror);
                    if (status) status.className = 'ds-load-status success';
                    setTimeout(() => { hideModal(); buttons.forEach(b => { b.disabled = false; }); }, 1500);
                } else if (/^✗|Failed|timed out|expired/.test(text)) {
                    clearInterval(mirror);
                    if (status) status.className = 'ds-load-status error';
                    buttons.forEach(b => { b.disabled = false; });
                }
            }, 500);
        } catch (error) {
            console.error('Error starting the load from the cache:', error);
            if (status) { status.className = 'ds-load-status error'; status.textContent = 'Could not start the load: ' + (error.message || error); }
            buttons.forEach(b => { b.disabled = false; });
        }
    }

    async function forgetFromCache(folder, feed, name) {
        const what = feed ? (FEED_NAMES[feed] || feed) + ' of ' + (name || folder) : 'everything held for ' + (name || folder);
        if (!confirm('Forget ' + what + '? What a later load needs is downloaded again.')) return;
        try {
            const response = await window.authService.fetch('/cache/forget', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder: folder, feed: feed || '' }) });
            const out = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(out.error || ('HTTP ' + response.status));
            if (out.primary_dropped) clearPrimaryPills({ source: 'intervals' });     // the Data tab's frame was the athlete's: its pill goes, the tab is free
            const details = document.getElementById('datasetDetails');
            if (details) { details.className = 'dataset-details-empty'; details.innerHTML = 'Select a dataset to see its details'; }
            loadDatasets();
        } catch (error) {
            console.error('Error forgetting from the cache:', error);
            alert('Could not forget: ' + (error.message || error));
        }
    }

    // the feeds, named as the load dialog names its datasets (2026-10-29: the lines must read as what was asked for)
    const FEED_NAMES = { activities: 'Activities', laps: 'Activity intervals', wellness: 'Wellness', events: 'Calendar', chats: 'Context · chats', profile: 'Rider profile' };
    const FEED_HINTS = { activities: 'The second-by-second rows of every activity, every metric the file had. The frame and the activity summary file are made from them.',
                         laps: 'The laps of every activity, as Intervals.icu detected them (the Activity intervals dataset). Settled activities are served from here; recent ones are fetched again.',
                         wellness: 'The daily log, a row per day (the Wellness dataset). The window\'s days come down each load and are merged, so the span held grows.',
                         events: 'The calendar: planned sessions, notes, races and status entries (the planned workouts file and the calendar\'s part of the context).',
                         chats: 'The messages under the activities (the Context dataset\'s chats). Settled activities\' chats are served from here; recent ones are fetched again.',
                         profile: 'The settings the data is read against - thresholds, zones, weight, the custom fields - as fetched; a snapshot is kept when it changes (the Rider profile dataset).' };
    const FEED_FILES = { activities: 'the frame on the Data tab and activity_summary_<window>.csv', laps: 'activity_intervals_<window>.csv', wellness: 'wellness_data_<window>.csv',
                         events: 'planned_workouts_<window>.csv and the calendar\'s passages in context_notes_<window>.csv', chats: 'the messages in context_notes_<window>.csv (and context_codes_<window>.csv, the coding pass\'s reading)',
                         profile: 'rider_profile_<window>.csv and custom_zone_times_<window>.csv' };
    
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
                 uploads: { frames: frames.filter(f => !['intervals', 'endura', 'sweatstack'].includes(String(f.source))), files: files.filter(f => !f.folder && !/^(athlete_profiles|race_turns|race_climbs|race_waymarkers)_race_|^(activity_summary|wellness_data|activity_intervals|context_notes|context_codes|planned_workouts|rider_profile|custom_zone_times)_/.test(f.filename || '')) },
                 legacy: [] };
    }
    
    function displayDatasets() {
        renderTree();

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
    
    // ---- the tree (docs/DATASETS_DESIGN.md §1, §8) -------------------------------------------------------------------
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
    function count(f) {
        const n = Number(f.count || 0);
        if (f.feed === 'activities' || f.feed === 'laps') return n + ' activit' + (n === 1 ? 'y' : 'ies');
        if (f.feed === 'wellness') return n + ' day' + (n === 1 ? '' : 's');
        if (f.feed === 'events') return n + ' entr' + (n === 1 ? 'y' : 'ies');
        if (f.feed === 'chats') return n + ' chat' + (n === 1 ? '' : 's') + (f.rows ? ', ' + f.rows + ' message' + (f.rows === 1 ? '' : 's') : '');
        if (f.feed === 'profile') return n + ' snapshot' + (n === 1 ? '' : 's');
        return String(n);
    }
    function matches(q, ...texts) { return !q || texts.some(t => String(t || '').toLowerCase().includes(q)); }

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
    function feedLine(subject, f) {
        const line = document.createElement('div');
        line.className = 'ds-feed';
        line.dataset.feed = f.feed;
        line.title = 'Click for the details';
        const used = f.last_used ? ' · used ' + ago(f.last_used) : '';
        line.innerHTML = `<span class="ds-feed-name">${esc(FEED_NAMES[f.feed] || f.feed)}</span><span class="ds-feed-span">${span(f)}</span>` +
            `<span class="ds-feed-count">${esc(count(f))}${f.bytes ? ' · ' + mb(f.bytes) : ''}${used}</span>`;
        return line;
    }
    function subjectBlock(subject, q) {
        const open = isOpen(subject.folder);
        const block = document.createElement('div');
        block.className = 'ds-subj' + (open ? ' open' : '');
        block.dataset.folder = subject.folder;
        const head = document.createElement('div');
        head.className = 'ds-subj-head';
        head.title = 'Click for the details: load the span held, or forget it';
        const held = subject.held_since ? 'held since ' + dayOf(subject.held_since) : '';
        const last = subject.last_load ? 'loaded ' + ago(subject.last_load) : '';
        head.innerHTML = `<span class="ds-caret" title="${open ? 'Fold' : 'Unfold'}">${open ? '▾' : '▸'}</span><span class="ds-subj-name" title="${esc(subject.id)}">${esc(subject.name || subject.id)}</span>` +
            `<span class="ds-subj-meta">${[held, last].filter(Boolean).join(' · ')}</span><span class="dataset-size">${mb(null, Number(subject.size_mb || 0))}</span>`;
        block.appendChild(head);
        if (open) {
            const body = document.createElement('div');
            body.className = 'ds-subj-body';
            const feeds = (subject.feeds || []).filter(f => matches(q, FEED_NAMES[f.feed], f.feed, subject.name, subject.id));
            feeds.forEach(f => body.appendChild(feedLine(subject, f)));
            if (!body.children.length) body.innerHTML = '<div class="dataset-empty">nothing held</div>';
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
        const tree = currentDatasets.tree || { sources: [], uploads: { frames: [], files: [] }, legacy: [] };
        const filter = document.getElementById('datasetFilter');
        const q = String((filter || {}).value || '').trim().toLowerCase();
        // the filter box earns its place when there is more than one athlete to tell apart
        const athletes = (tree.sources || []).reduce((n, src) => n + (src.subjects || []).length, 0);
        if (filter) filter.style.display = (athletes > 1 || q) ? '' : 'none';
        (tree.sources || []).forEach(src => {
            const subjects = (src.subjects || []).filter(sb => matches(q, sb.name, sb.id) || (sb.feeds || []).some(f => matches(q, FEED_NAMES[f.feed], f.feed)));
            const frames = (src.frames || []).filter(f => matches(q, f.date_range, f.race_title, f.original_filename, src.title));
            const files = (src.files || []).filter(f => matches(q, f.filename));
            const legacy = src.source === 'intervals' ? (tree.legacy || []).filter(lg => matches(q, 'earlier', lg.folder)) : [];
            if (src.source !== 'intervals' && !frames.length && !files.length) return;
            const g = group(src.title, (src.source === 'intervals' && !subjects.length && !frames.length && !legacy.length) ? (q ? 'nothing matches' : 'nothing held yet — a load fills it') : '');
            subjects.forEach(sb => g.appendChild(subjectBlock(sb, q)));
            frames.forEach(f => g.appendChild(frameLine(f)));
            files.forEach(f => g.appendChild(fileLine(f)));
            legacy.forEach(lg => {
                // a key's folder from before the athlete was known that holds no activity of a known athlete (one of theirs is
                // absorbed on the next load): its frames and files, and Forget in its details
                const key = String(lg.folder || '');
                const block = document.createElement('div');
                block.className = 'ds-subj open';
                block.dataset.folder = key;
                block.innerHTML = `<div class="ds-subj-head" title="Loads from before the athlete was known, under the key …${esc(key.slice(-4))}; click for the details"><span class="ds-caret">·</span><span class="ds-subj-name">earlier loads · key …${esc(key.slice(-4))}</span><span class="ds-subj-meta">${lg.store ? esc(lg.store.activities || 0) + ' activities' : ''}</span><span class="dataset-size">${lg.store ? mb(null, Number(lg.store.size_mb || 0)) : ''}</span></div>`;
                const body = document.createElement('div'); body.className = 'ds-subj-body';
                (lg.frames || []).forEach(f => body.appendChild(frameLine(f)));
                (lg.files || []).filter(f => !f.view).forEach(f => body.appendChild(fileLine(f)));
                if (body.children.length) block.appendChild(body);
                g.appendChild(block);
            });
            root.appendChild(g);
        });
        const up = tree.uploads || { frames: [], files: [] };
        const upFrames = (up.frames || []).filter(f => matches(q, f.original_filename, f.source)), upFiles = (up.files || []).filter(f => matches(q, f.filename));
        const ug = group('Uploads', (!upFrames.length && !upFiles.length) ? (q ? 'nothing matches' : 'no uploaded datasets') : '');
        upFrames.forEach(f => ug.appendChild(frameLine(f)));
        upFiles.forEach(f => ug.appendChild(fileLine(f)));
        root.appendChild(ug);
    }

    // ---- the details of an athlete and of a feed (the right pane; the actions live here, as the files' Load and Remove do) ----
    function showSubjectDetails(folder) {
        const panel = document.getElementById('datasetDetails');
        const tree = currentDatasets.tree || {};
        const subject = subjectOf(folder);
        const legacy = (tree.legacy || []).find(lg => lg.folder === folder);
        if (!panel || (!subject && !legacy)) return;
        panel.classList.remove('dataset-details-empty');
        if (!subject) {
            const key = String(folder);
            panel.innerHTML = `<div class="dataset-details-content"><div class="dataset-info-section"><h3>Earlier loads</h3><div class="dataset-metadata">` +
                `<span class="metadata-label">Key:</span><span class="metadata-value">…${esc(key.slice(-4))} (a key from before the athlete was known)</span>` +
                (legacy.store ? `<span class="metadata-label">Store:</span><span class="metadata-value">${esc(legacy.store.activities || 0)} activities · ${mb(null, Number(legacy.store.size_mb || 0))}</span>` : '') +
                `</div><p class="ds-note">Loads made under this key before the athlete was known. When a load of a known athlete holds one of these activities, the folder is absorbed into theirs; otherwise it stays here until forgotten.</p></div></div>` +
                `<div class="dataset-actions"><button class="dataset-action-btn dataset-remove-btn" data-act="forget" data-folder="${esc(key)}" data-feed="" data-name="key …${esc(key.slice(-4))}">Forget</button></div>`;
            return;
        }
        const acts = (subject.feeds || []).find(f => f.feed === 'activities');
        const kinds = loadKinds(subject);
        const rows = (subject.feeds || []).map(f => `<tr><td>${esc(FEED_NAMES[f.feed] || f.feed)}</td><td>${span(f)}</td><td>${esc(count(Object.assign({}, f, { rows: 0 })))}</td><td class="num">${mb(f.bytes)}</td></tr>`).join('');
        panel.innerHTML = `<div class="dataset-details-content">
            <div class="dataset-info-section"><h3>Athlete</h3><div class="dataset-metadata">
                <span class="metadata-label">Name:</span><span class="metadata-value">${esc(subject.name || subject.id)}</span>
                <span class="metadata-label">Intervals.icu id:</span><span class="metadata-value">${esc(subject.id)}</span>
                <span class="metadata-label">Held since:</span><span class="metadata-value">${esc(dayOf(subject.held_since))}</span>
                <span class="metadata-label">Last load:</span><span class="metadata-value">${esc(ago(subject.last_load))}${subject.last_load ? ' (' + esc(dayOf(subject.last_load)) + ')' : ''}</span>
                <span class="metadata-label">Size:</span><span class="metadata-value">${mb(null, Number(subject.size_mb || 0))}</span>
                <span class="metadata-label">Loaded by:</span><span class="metadata-value">${(subject.marks || []).length === 1 ? '1 API key' : (subject.marks || []).length + ' API keys'}</span>
            </div></div>
            <div class="dataset-info-section dataset-info-columns"><h3>Held</h3><div class="dataset-columns"><table class="dataset-preview-table ds-feeds"><thead><tr><th>Dataset</th><th>Span</th><th>Held</th><th>Size</th></tr></thead><tbody>${rows}</tbody></table>
                <p class="ds-note">${acts ? 'Load brings the span held, ' + esc(acts.from) + ' → ' + esc(acts.to) + ', onto the Data tab with the datasets of the last load (' + esc(kinds.join(', ')) + '): the store serves what it holds and only what the window lacks is downloaded. Load to today extends the span to today. For another window or other datasets, use the Intervals.icu dialog.' : 'No activities held yet.'}</p>
            </div></div>
            <div id="dsLoadStatus" class="ds-load-status" style="display:none"></div>
        </div>
        <div class="dataset-actions">
            ${acts ? `<button class="dataset-action-btn dataset-load-btn" data-act="load" data-folder="${esc(folder)}" data-from="${esc(acts.from)}" data-to="${esc(acts.to)}" title="Load ${esc(acts.from)} → ${esc(acts.to)} from the store">Load</button>
            <button class="dataset-action-btn dataset-load-btn" data-act="today" data-folder="${esc(folder)}" data-from="${esc(acts.from)}" data-to="${esc(acts.to)}" title="Load ${esc(acts.from)} → today: only the missing days are fetched">Load to today</button>` : ''}
            <button class="dataset-action-btn dataset-remove-btn" data-act="forget" data-folder="${esc(folder)}" data-feed="" data-name="${esc(subject.name || subject.id)}" title="Drop everything held for this athlete: the store and the window files">Forget</button>
        </div>`;
    }

    function showFeedDetails(folder, feedName) {
        const panel = document.getElementById('datasetDetails');
        const subject = subjectOf(folder);
        const f = subject && (subject.feeds || []).find(x => x.feed === feedName);
        if (!panel || !f) return;
        panel.classList.remove('dataset-details-empty');
        const cols = (f.columns || []);
        const cats = f.categories ? Object.keys(f.categories).sort((a, b) => f.categories[b] - f.categories[a]).map(k => esc(k || '(none)') + ' ' + f.categories[k]).join(', ') : '';
        panel.innerHTML = `<div class="dataset-details-content">
            <div class="dataset-info-section"><h3>${esc(FEED_NAMES[f.feed] || f.feed)} · ${esc(subject.name || subject.id)}</h3><div class="dataset-metadata">
                <span class="metadata-label">${f.as_of ? 'As of:' : 'Span:'}</span><span class="metadata-value">${span(f)}</span>
                <span class="metadata-label">Held:</span><span class="metadata-value">${esc(count(f))}${f.feed === 'laps' && f.rows ? ' (' + Number(f.rows).toLocaleString() + ' laps)' : ''}</span>
                <span class="metadata-label">Size:</span><span class="metadata-value">${mb(f.bytes) || '0 KB'}</span>
                ${f.last_used ? `<span class="metadata-label">Last used:</span><span class="metadata-value">${esc(ago(f.last_used))}</span>` : ''}
                ${cats ? `<span class="metadata-label">Entries:</span><span class="metadata-value">${cats}</span>` : ''}
                <span class="metadata-label">A load writes:</span><span class="metadata-value">${esc(FEED_FILES[f.feed] || '')}</span>
            </div><p class="ds-note">${esc(FEED_HINTS[f.feed] || '')}</p></div>
            ${cols.length ? `<div class="dataset-info-section dataset-info-columns"><h3>Columns (${cols.length})</h3><div class="dataset-columns"><div class="column-list">${cols.map(c => `<span class="column-chip">${esc(c)}</span>`).join('')}</div></div></div>` : ''}
        </div>
        <div class="dataset-actions">
            <button class="dataset-action-btn dataset-remove-btn" data-act="forget" data-folder="${esc(folder)}" data-feed="${esc(f.feed)}" data-name="${esc(subject.name || subject.id)}" title="Drop this dataset from the store; a later load downloads it again">Forget</button>
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