// Dataset Manager Module - the Dataset cache dialog. Since 2026-10-29 (docs/DATASETS_DESIGN.md §8) it draws the executor's
// cache as a tree - source → athlete → feed, with the frames in memory under the athlete - with Use, Extend to today and
// Forget on each line; uploads and generated files keep their own groups. A load's window files are not listed: they are a
// run's inputs, shown on the run's Data tab.
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
        // the tree's own lines and actions (2026-10-29): fold an athlete, Use / Extend to today / Forget a feed, Forget an athlete
        const tree = document.getElementById('datasetTree');
        if (tree) tree.addEventListener('click', handleTreeClick);
        const filter = document.getElementById('datasetFilter');
        if (filter) filter.addEventListener('input', () => renderTree());
    }

    function handleTreeClick(e) {
        const act = e.target.closest('[data-act]');
        if (act) {
            e.stopPropagation();
            const d = act.dataset;
            if (d.act === 'use' || d.act === 'extend') openIntervalsLoad(d.feed, d.from, d.act === 'extend' ? localDay() : d.to);
            else if (d.act === 'forget') forgetFromCache(d.folder, d.feed, d.name);
            return;
        }
        const subj = e.target.closest('.ds-subj');
        if (subj && !e.target.closest('.dataset-item')) {
            openSubjects[subj.dataset.folder] = !openSubjects[subj.dataset.folder];
            renderTree();
        }
    }

    function localDay() {
        return typeof localIsoDay === 'function' ? localIsoDay(new Date()) : new Date().toISOString().slice(0, 10);
    }

    // Use / Extend to today (docs/DATASETS_DESIGN.md §1): the Intervals.icu load dialog with the span and the feed filled in -
    // the person sees what will be fetched and presses Load; the store serves what it holds, only the missing days come down
    async function openIntervalsLoad(feed, from, to) {
        if (window.Intervals && window.Intervals.state.isLoaded && window.Intervals.state.pillId) {
            // the Data tab holds an Intervals.icu window: replacing it is what its pill's × does, then the dialog
            if (!confirm('The Data tab holds a window from Intervals.icu. Let it go and load this one?')) return;
            const pill = document.getElementById(window.Intervals.state.pillId);
            if (pill && typeof removeDatasetPill === 'function') await removeDatasetPill(pill, null, true);
            else if (window.Intervals.removePill) window.Intervals.removePill();
        }
        const busy = primaryLoadedMessage();
        if (busy) { if (typeof showUploadLimitMessage === 'function') showUploadLimitMessage(busy); return; }
        if (typeof showIntervalsModal !== 'function') return;
        hideModal();
        showIntervalsModal();
        const s = document.getElementById('intervalsStartDate'), e = document.getElementById('intervalsEndDate');
        const put = (input, v) => { if (!input || !v) return; input.min = ''; input.value = input.max && v > input.max ? input.max : v; };
        put(s, from); put(e, to);
        const box = { laps: 'intervals-checkbox', wellness: 'wellness-checkbox', events: 'context-checkbox', profile: 'rider-checkbox' }[feed];
        if (box) { const c = document.getElementById(box); if (c && !c.checked) { c.checked = true; c.dispatchEvent(new Event('change', { bubbles: true })); } }
    }

    async function forgetFromCache(folder, feed, name) {
        const what = feed ? (FEED_NAMES[feed] || feed) + ' of ' + (name || folder) : 'everything held for ' + (name || folder);
        if (!confirm('Forget ' + what + '? What a later load needs is downloaded again.')) return;
        try {
            const response = await window.authService.fetch('/cache/forget', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder: folder, feed: feed || '' }) });
            const out = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(out.error || ('HTTP ' + response.status));
            if (out.primary_dropped) clearPrimaryPills({ source: 'intervals' });     // the Data tab's frame was the athlete's: its pill goes, the tab is free
            loadDatasets();
        } catch (error) {
            console.error('Error forgetting from the cache:', error);
            alert('Could not forget: ' + (error.message || error));
        }
    }

    const FEED_NAMES = { activities: 'Activities', laps: 'Laps', wellness: 'Wellness', events: 'Calendar', profile: 'Profile · zones' };
    const FEED_HINTS = { activities: 'the second-by-second rows of every activity, with its chat', laps: 'the laps of every activity, as Intervals.icu detected them',
                         wellness: 'the daily log, a row per day', events: 'the calendar: planned sessions, notes, races, status entries', profile: 'the settings the data is read against, as fetched each load' };
    
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
    function span(f) { return f.from ? esc(f.from) + ' → ' + esc(f.to) : (f.as_of ? 'as of ' + esc(f.as_of) : ''); }
    function count(f) {
        const n = Number(f.count || 0);
        if (f.feed === 'activities') return n + ' activit' + (n === 1 ? 'y' : 'ies') + (f.chats ? ', ' + f.chats + ' chat' + (f.chats === 1 ? '' : 's') : '');
        if (f.feed === 'laps') return n + ' activit' + (n === 1 ? 'y' : 'ies');
        if (f.feed === 'wellness') return n + ' day' + (n === 1 ? '' : 's');
        if (f.feed === 'events') return n + ' entr' + (n === 1 ? 'y' : 'ies');
        if (f.feed === 'profile') return n + ' snapshot' + (n === 1 ? '' : 's');
        return String(n);
    }
    function matches(q, ...texts) { return !q || texts.some(t => String(t || '').toLowerCase().includes(q)); }

    function frameLine(f) {
        const item = document.createElement('div');
        item.className = 'dataset-item ds-frame';
        const where = f.date_range ? esc(f.date_range) : f.race_title ? esc(f.race_title) : f.original_filename ? esc(f.original_filename) : esc(f.source || 'frame');
        const rows = f.shape ? Number(f.shape[0]).toLocaleString() + ' rows' : '';
        item.innerHTML = `<span class="ds-mem" title="in memory: loads without a download">in memory</span><span class="dataset-item-name">${where}${rows ? ' · ' + rows : ''}${f.metrics && f.metrics.length ? ' · ' + esc(f.metrics.join(', ')) : ''}</span><span class="dataset-size">${mb(null, Number(f.memory_mb || 0))}</span>`;
        item.dataset.id = f.df_id; item.dataset.type = 'primary';
        const full = (currentDatasets.cached || []).find(c => c.df_id === f.df_id) || f;
        item.addEventListener('click', ev => selectDataset.call(item, full, 'primary', ev));
        return item;
    }
    function fileLine(f) {
        const item = createDatasetItem(f, 'auxiliary');
        return item;
    }
    function feedLine(subject, f) {
        const line = document.createElement('div');
        line.className = 'ds-feed';
        line.title = FEED_HINTS[f.feed] || '';
        const usable = f.feed !== 'profile';
        const used = f.last_used ? ' · used ' + ago(f.last_used) : '';
        line.innerHTML = `<span class="ds-feed-name">${esc(FEED_NAMES[f.feed] || f.feed)}</span><span class="ds-feed-span">${span(f)}</span>` +
            `<span class="ds-acts">${usable ? `<button type="button" class="ds-act" data-act="use" data-feed="${esc(f.feed)}" data-from="${esc(f.from)}" data-to="${esc(f.to)}" title="Open the load dialog with this span and feed filled in; the store serves what it holds">Use</button>` +
            `<button type="button" class="ds-act" data-act="extend" data-feed="${esc(f.feed)}" data-from="${esc(f.from)}" data-to="${esc(f.to)}" title="Load from the first day held to today: only the missing days are fetched">To today</button>` : ''}` +
            `<button type="button" class="ds-act danger" data-act="forget" data-folder="${esc(subject.folder)}" data-feed="${esc(f.feed)}" data-name="${esc(subject.name || subject.id)}" title="Drop this feed from the store; a later load downloads it again">Forget</button></span>` +
            `<span class="ds-feed-count">${esc(count(f))}${f.bytes ? ' · ' + mb(f.bytes) : ''}${used}</span>`;
        return line;
    }
    function subjectBlock(subject, q, forceOpen) {
        const block = document.createElement('div');
        block.className = 'ds-subj' + (openSubjects[subject.folder] || forceOpen ? ' open' : '');
        block.dataset.folder = subject.folder;
        const head = document.createElement('div');
        head.className = 'ds-subj-head';
        const held = subject.held_since ? 'held since ' + new Date(Number(subject.held_since) * 1000).toISOString().slice(0, 10) : '';
        const last = subject.last_load ? 'loaded ' + ago(subject.last_load) : '';
        head.innerHTML = `<span class="ds-caret">${openSubjects[subject.folder] || forceOpen ? '▾' : '▸'}</span><span class="ds-subj-name" title="${esc(subject.id)}">${esc(subject.name || subject.id)}</span>` +
            `<span class="ds-subj-meta">${[held, last].filter(Boolean).join(' · ')}</span><span class="dataset-size">${mb(null, Number(subject.size_mb || 0))}</span>` +
            `<span class="ds-acts"><button type="button" class="ds-act danger" data-act="forget" data-folder="${esc(subject.folder)}" data-feed="" data-name="${esc(subject.name || subject.id)}" title="Drop everything held for this athlete: the store, the frames in memory, the window files">Forget</button></span>`;
        block.appendChild(head);
        if (openSubjects[subject.folder] || forceOpen) {
            const body = document.createElement('div');
            body.className = 'ds-subj-body';
            const feeds = (subject.feeds || []).filter(f => matches(q, FEED_NAMES[f.feed], f.feed, subject.name, subject.id));
            feeds.forEach(f => body.appendChild(feedLine(subject, f)));
            (subject.frames || []).filter(f => matches(q, 'in memory', f.date_range, subject.name, subject.id)).forEach(f => body.appendChild(frameLine(f)));
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
        const q = String((document.getElementById('datasetFilter') || {}).value || '').trim().toLowerCase();
        (tree.sources || []).forEach(src => {
            const subjects = (src.subjects || []).filter(sb => matches(q, sb.name, sb.id) || (sb.feeds || []).some(f => matches(q, FEED_NAMES[f.feed], f.feed)));
            const frames = (src.frames || []).filter(f => matches(q, f.date_range, f.race_title, src.title));
            const files = (src.files || []).filter(f => matches(q, f.filename));
            const legacy = src.source === 'intervals' ? (tree.legacy || []) : [];
            if (src.source !== 'intervals' && !frames.length && !files.length) return;
            const g = group(src.title, (src.source === 'intervals' && !subjects.length && !frames.length && !legacy.length) ? (q ? 'nothing matches' : 'nothing held yet — a load fills it') : '');
            const few = subjects.length <= 2 || !!q;              // unfold when there are few athletes or a filter is on
            subjects.forEach(sb => g.appendChild(subjectBlock(sb, q, few)));
            frames.forEach(f => g.appendChild(frameLine(f)));
            files.forEach(f => g.appendChild(fileLine(f)));
            legacy.forEach(lg => {
                const key = String(lg.folder || '');
                const block = document.createElement('div');
                block.className = 'ds-subj open';
                block.innerHTML = `<div class="ds-subj-head"><span class="ds-caret">·</span><span class="ds-subj-name">earlier loads · key …${esc(key.slice(-4))}</span><span class="ds-subj-meta">${lg.store ? esc(lg.store.activities || 0) + ' activities' : ''}</span><span class="dataset-size">${lg.store ? mb(null, Number(lg.store.size_mb || 0)) : ''}</span>` +
                    `<span class="ds-acts"><button type="button" class="ds-act danger" data-act="forget" data-folder="${esc(key)}" data-feed="" data-name="key …${esc(key.slice(-4))}" title="Drop this key's folder from before the athlete was known">Forget</button></span></div>`;
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