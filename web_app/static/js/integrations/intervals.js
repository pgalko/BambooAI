//--------------------
//  INTERVALS ICU INTEGRATION MODULE
//--------------------

// Intervals-specific state
let currentIntervalsState = {
    isLoaded: false,
    pillId: null,
    dataInfo: null
};

function initializeIntervalsIntegration() {
    console.log('Initializing Intervals ICU integration...');
    
    initializeIntervalsDataOption();
    initializeIntervalsModals();
    
    console.log('Intervals ICU integration initialized');
}

//--------------------
//  INTERVALS DATA LOADING
//--------------------

function initializeIntervalsDataOption() {
    const intervalsDataButton = document.querySelector('.intervals-data-option');

    if (!intervalsDataButton) {
        console.log('Intervals ICU data option not found (not configured)');
        return;
    }

    intervalsDataButton.addEventListener('click', function() {
        console.log('Intervals ICU data option clicked');
        
        // Check if primary dataset already exists
        if (currentDatasetName) {
            showUploadLimitMessage('Primary dataset already loaded. Remove current to upload new.');
            return; 
        }
        
        // Check if SweatStack data is loaded
        if (window.SweatStack && window.SweatStack.state.isLoaded) {
            showUploadLimitMessage('SweatStack data already loaded. Remove current to upload primary dataset.');
            return;
        }

        // Check if Intervals data is loaded
        if (window.Intervals && window.Intervals.state.isLoaded) {
            showUploadLimitMessage('Intervals ICU data already loaded. Remove current to upload primary dataset.');
            return;
        }

        // Check if Endura data is loaded
        if (window.Endura && window.Endura.state.isLoaded) {
            showUploadLimitMessage('Endura data already loaded. Remove current to upload primary dataset.');
            return;
        }
    
        showIntervalsModal();
    });
}

// The plan's limit, asked once per page (2026-10-15). The dialog's dates are the person's once set: every opening puts
// the bounds on the inputs, but the values are written only while the inputs are empty - the first opening - so a
// window typed in stays for the next opening, and an answer landing after the dialog opened does not wipe a choice
// made meanwhile (it did: the limits were fetched and both values rewritten on every opening).
let intervalsLimitsPromise = null;

async function applyIntervalsDateLimits() {
    const startDateInput = document.getElementById('intervalsStartDate');
    const endDateInput = document.getElementById('intervalsEndDate');
    if (!startDateInput || !endDateInput) return;
    if (!intervalsLimitsPromise) {
        intervalsLimitsPromise = window.authService.fetch('/intervals/get_data_limits').then(r => r.json())
            .catch(error => { console.error('Error fetching data limits:', error); return {}; });   // 14 days when the answer fails
    }
    const limits = await intervalsLimitsPromise;
    const today = new Date();
    const maxDays = limits.max_days || 14;
    const earliestDate = new Date(today);
    earliestDate.setDate(today.getDate() - maxDays);
    const lo = localIsoDay(earliestDate), hi = localIsoDay(today);
    startDateInput.min = lo; startDateInput.max = hi;
    endDateInput.min = lo; endDateInput.max = hi;
    if (!startDateInput.value) startDateInput.value = lo;       // each input on its own: one typed before the answer landed stays
    if (!endDateInput.value) endDateInput.value = hi;
}

// The context's report as one line (docs/CONTEXT_DESIGN.md §4 F1): "Context: 212 passages — activity_message 198,
// day_note 13 …; 1 call failed: …". '' when the load carried no context.
function contextReportLine(report) {
    if (!report || typeof report !== 'object') return '';
    const n = Number(report.passages || 0);
    const kinds = report.kinds || {};
    const parts = Object.keys(kinds).sort((a, b) => kinds[b] - kinds[a]).map(k => k + ' ' + kinds[k]);
    const failed = Array.isArray(report.failed) ? report.failed : [];
    let line = n ? ('Context: ' + n + ' passage' + (n === 1 ? '' : 's') + (parts.length ? ' — ' + parts.join(', ') : '')) : 'Context: no passages in this window';
    if (failed.length) line += '; ' + failed.length + ' call' + (failed.length === 1 ? '' : 's') + ' failed: ' + failed.join('; ');
    // the coding pass (step 3): running behind the load, or what it did, or why it did not run
    const coding = report.coding;
    if (n && coding && coding.status === 'running') line += '; coding in the background';
    else if (n && coding && coding.line) line += '; ' + coding.line;
    else if (n && report.coding_line) line += '; ' + report.coding_line;
    return line + '.';
}
if (typeof module !== 'undefined' && module.exports) module.exports.contextReportLine = contextReportLine;

function createIntervalsPill(dataInfo) {
    const pillId = 'intervals-pill-' + Date.now();
    const dayCount = Math.ceil((new Date(dataInfo.end_date) - new Date(dataInfo.start_date)) / (1000 * 60 * 60 * 24));
    const auxDatasets = dataInfo.aux_datasets || [];
    let auxText = '';
    if (auxDatasets.includes('wellness')) auxText += 'W';
    if (auxDatasets.includes('summary')) auxText += auxText ? '+S' : 'S';
    if (auxDatasets.includes('intervals')) auxText += auxText ? '+I' : 'I';
    if (auxDatasets.includes('context')) auxText += auxText ? '+C' : 'C';
    if (auxDatasets.includes('rider')) auxText += auxText ? '+R' : 'R';
    if (auxText) auxText = ` [${auxText}]`;
    
    const displayText = `Intervals ICU (${dayCount} days${auxText}) loaded`;

    if (typeof createOrUpdateDatasetPill === 'function') {
        createOrUpdateDatasetPill(pillId, displayText, 'intervals', 'success', false, 'intervals_data');
    }

    // Update global state
    currentIntervalsState.isLoaded = true;
    currentIntervalsState.pillId = pillId;
    currentIntervalsState.dataInfo = dataInfo;

    console.log('Intervals ICU data pill created successfully');
}

function intervalsAuxDisplayName(filepath, dayCount) {
    const filename = filepath.split('/').pop();
    if (filename.includes('wellness_data')) return `Wellness Summary (${dayCount} days)`;
    if (filename.includes('activity_summary')) return `Activity Summary (${dayCount} days)`;
    if (filename.includes('activity_intervals')) return `Activity Intervals (${dayCount} days)`;
    if (filename.includes('context_notes')) return `Context (${dayCount} days)`;
    if (filename.includes('context_codes')) return `Context codes (${dayCount} days)`;
    if (filename.includes('planned_workouts')) return `Planned workouts (${dayCount} days)`;
    if (filename.includes('rider_profile')) return 'Rider profile';                       // the settings as they stand: no window on the pill (2026-10-16)
    if (filename.includes('custom_zone_times')) return `Custom zones (${dayCount} days)`;
    return filename.replace('.csv', '');
}

function intervalsDayCount(dataInfo) {
    const n = Math.ceil((new Date(dataInfo.end_date) - new Date(dataInfo.start_date)) / (1000 * 60 * 60 * 24));
    return Number.isFinite(n) ? n : 0;
}

function createIntervalsAuxiliaryPills(auxDatasets, dataInfo, options) {
    if (!auxDatasets || auxDatasets.length === 0) return {};
    const dayCount = intervalsDayCount(dataInfo);
    const ids = {};
    let shown = 0;
    auxDatasets.forEach((filepath, index) => {
        // the context files stack under the one Context pill (2026-10-14); every other file keeps a pill of its own
        if (contextPillAdd([filepath], dataInfo, options)) { shown += 1; return; }
        const displayName = intervalsAuxDisplayName(filepath, dayCount);
        const pillId = `intervals-aux-pill-${Date.now()}-${index}`;
        ids[filepath] = pillId;
        if (typeof createOrUpdateDatasetPill === 'function') {
            createOrUpdateDatasetPill(pillId, `Auxiliary (${displayName})`, 'auxiliary', 'success', false, filepath);
        }
        shown += 1;
    });
    
    if (typeof window.auxiliaryDatasetCount !== 'undefined') {
        window.auxiliaryDatasetCount = (window.auxiliaryDatasetCount || 0) + shown;
    }
    return ids;
}

// ---- the one Context pill (2026-10-14, Palo: two pills for one thing was wasteful) ----
// The passages and the codes of a load stack under a single pill, as the documents do: the label carries the days and a
// spinner with "coding…" while the pass runs behind the load; the hover list names the two files with their row counts
// (a click previews either in the Data tab) and the pass's line once it has ended; the pill's x removes both files.
// When the pass proposed codes, the list gains a row to the codebook screen (step 6, 2026-10-16): it stays while the book
// has proposals waiting (the count follows the book's) and goes when the coach has decided on them all.
const contextPillState = { notes: null, codes: null, dataInfo: null, coding: false, line: '', proposed: 0 };
const CONTEXT_PILL_REMOVE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line></svg>';
function contextPillEsc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function contextPillRender() {
    const host = document.getElementById('datasetStatusPillsContainer');
    if (!host) return;
    let pill = document.getElementById('contextPill');
    const st = contextPillState;
    if (!st.notes && !st.codes) { if (pill) pill.remove(); return; }
    if (!pill) { pill = document.createElement('div'); pill.setAttribute('id', 'contextPill'); host.appendChild(pill); }
    const days = st.dataInfo ? intervalsDayCount(st.dataInfo) : 0;
    const first = st.notes || st.codes;
    pill.className = 'dataset-status-pill auxiliary-dataset-pill context-pill success';
    pill.setAttribute('data-dataset-type', 'auxiliary');
    pill.setAttribute('data-identifier', first);
    pill.setAttribute('onmouseenter', 'contextMenuPlace(this)');
    const label = 'Context (' + days + ' days)' + (st.coding ? ' · coding…' : '');
    const title = st.coding ? 'The coding pass is running behind the load; the passages can be viewed meanwhile' : (st.line ? 'Context: ' + st.line : 'Click to view the passages');
    const rows = [];
    if (st.notes) rows.push('<div class="row" onclick="contextPreview(\'' + contextPillEsc(st.notes) + '\')"><span class="id">Passages</span><span class="file">' + contextPillEsc(st.notes.split('/').pop()) + '</span></div>');
    if (st.codes) rows.push('<div class="row" onclick="contextPreview(\'' + contextPillEsc(st.codes) + '\')"><span class="id">Codes</span><span class="file">' + contextPillEsc(st.codes.split('/').pop()) + '</span></div>');
    else if (st.coding) rows.push('<div class="row muted"><span class="id">Codes</span><span class="file">coding…</span></div>');
    if (st.line && !st.coding) rows.push('<div class="row muted line"><span class="file">' + contextPillEsc(st.line) + '</span></div>');
    if (st.proposed > 0 && !st.coding) rows.push('<div class="row codebook" onclick="event.stopPropagation(); contextCodebookOpen()"><span class="id">Codebook</span><span class="file">' + contextPillEsc(contextPillProposalsText(st.proposed)) + '</span></div>');
    const badge = (st.proposed > 0 && !st.coding) ? '<span class="pill-badge" title="' + contextPillEsc(contextPillProposalsText(st.proposed).replace('Codebook · ', '')) + ' in the codebook">' + st.proposed + '</span>' : '';
    pill.innerHTML = '<span class="dataset-pill-content clickable-pill-content" title="' + contextPillEsc(title) + '" onclick="contextPreview(\'' + contextPillEsc(first) + '\')"><span>' + contextPillEsc(label) + '</span>' + badge +
        (st.coding ? '<div class="file-upload-spinner"></div>' : '') + '</span>' +
        '<span class="dataset-pill-remove-icon" title="Remove the context" onclick="event.stopPropagation(); contextRemove()">' + CONTEXT_PILL_REMOVE + '</span>' +
        '<div class="context-pill-menu">' + rows.join('') + '</div>';
}
// a context file for the pill: true when the path is one (context_notes_… or context_codes_…), false for any other file
function contextPillAdd(files, dataInfo, options) {
    let took = false;
    (files || []).forEach(f => {
        const name = String(f || '').split('/').pop();
        if (name.includes('context_notes')) { contextPillState.notes = f; took = true; }
        else if (name.includes('context_codes')) { contextPillState.codes = f; took = true; }
    });
    if (!took) return false;
    if (dataInfo) contextPillState.dataInfo = dataInfo;
    if (options && 'coding' in options) contextPillState.coding = !!options.coding;
    if (options && options.line) contextPillState.line = options.line;
    contextPillRender();
    return true;
}
function contextPillSettle(view) {
    contextPillState.coding = false;
    contextPillState.line = view ? (view.line || view.status || '') : 'the coding pass could not be followed';
    if (view && view.codes_path) contextPillState.codes = view.codes_path;
    contextPillState.proposed = Number(view && view.report && view.report.proposed) || 0;
    contextPillRender();
    // the gear item's count follows the book when a pass ends (the codebook screen reads it; it corrects the row's count too)
    if (window.CodebookUI && typeof window.CodebookUI.badge === 'function') window.CodebookUI.badge();
}
function contextPillClear() {
    contextPillState.notes = null; contextPillState.codes = null; contextPillState.coding = false; contextPillState.line = ''; contextPillState.proposed = 0;
    contextPillRender();
}
function contextPillProposalsText(n) { return 'Codebook · ' + (n === 1 ? '1 proposal awaits you' : n + ' proposals await you'); }
// the book's count of proposals waiting, read by the codebook screen: the row shown when the last pass proposed codes follows it
function contextPillProposals(n) {
    if (!(contextPillState.proposed > 0)) return;
    contextPillState.proposed = Number(n) || 0;
    contextPillRender();
}
function contextCodebookOpen() {
    if (window.CodebookUI && typeof window.CodebookUI.open === 'function') window.CodebookUI.open();
}
function contextMenuPlace(pill) {
    const menu = pill && pill.querySelector ? pill.querySelector('.context-pill-menu') : null;
    if (!menu || typeof pill.getBoundingClientRect !== 'function') return;
    const r = pill.getBoundingClientRect();
    menu.style.left = Math.max(8, r.left) + 'px';
    menu.style.top = (r.bottom + 4) + 'px';
}
function contextPreview(path) {
    if (!path) return;
    if (typeof showDatasetPreview === 'function') showDatasetPreview('/get_dataset_preview', { file_path: path }, 'auxiliary');
}
async function contextRemove() {
    const files = [contextPillState.notes, contextPillState.codes].filter(Boolean);
    for (const f of files) {
        try {
            await window.authService.fetch('/remove_auxiliary_dataset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_path: f }) });
        } catch (e) { console.error('Context: the file could not be removed', f, e); }
    }
    if (typeof window.auxiliaryDatasetCount !== 'undefined') window.auxiliaryDatasetCount = Math.max(0, (window.auxiliaryDatasetCount || 0) - files.length);
    contextPillClear();
}

// The coding pass behind a load (docs/CONTEXT_DESIGN.md §4 F1): the load has completed; the app codes the passages in
// the background. Every two seconds: the Context pill keeps its spinner while it runs; when it ends the pill settles -
// the pass's line as its tooltip and in its list, the codes file in its list. Nobody waits for it.
function pollContextCoding(jobId, dataInfo, onDone) {
    const t0 = Date.now();
    const tick = async () => {
        let view = null;
        try {
            const r = await window.authService.fetch(`/intervals/context_coding/${jobId}`);
            view = r.ok ? await r.json() : null;
        } catch (e) { view = null; }
        const running = view && view.status === 'running';
        if (running && Date.now() - t0 < 1800000) { setTimeout(tick, 2000); return; }
        contextPillSettle(view);
        const line = view ? (view.line || view.status) : 'the coding pass could not be followed';
        const msg = document.getElementById('intervals-modal-message');
        const modal = document.getElementById('intervalsModal');
        if (msg && modal && modal.style.display !== 'none' && /Data loaded successfully/.test(msg.textContent || '')) showIntervalsMessage(msg.textContent.replace(/\.$/, '') + '; ' + line + '.', 'success');
        console.log('Context coding: ' + line);
        if (typeof onDone === 'function') onDone(view);
    };
    setTimeout(tick, 2000);
}
if (typeof module !== 'undefined' && module.exports) { Object.assign(module.exports, { intervalsAuxDisplayName, pollContextCoding, contextPillAdd, contextPillSettle, contextPillClear, contextPillState, contextPillProposals, contextPillProposalsText, contextCodebookOpen, createIntervalsAuxiliaryPills, contextPreview, contextRemove, contextMenuPlace, setIntervalsRefresh, initializeDownloadChoice, showIntervalsStoreLine }); }

function removeIntervalsPill() {
    if (currentIntervalsState.pillId) {
        const pill = document.getElementById(currentIntervalsState.pillId);
        if (pill) {
            pill.remove();
        }

        // Reset global state
        currentIntervalsState.isLoaded = false;
        currentIntervalsState.pillId = null;
        currentIntervalsState.dataInfo = null;

        console.log('Intervals ICU data pill removed');
    }
}



//--------------------
//  API KEY MANAGEMENT
//--------------------

async function checkIntervalsApiKey() {
    try {
        const response = await window.authService.fetch('/intervals/status');
        const data = await response.json();
        return data.has_api_key || false;
    } catch (error) {
        console.error('Error checking Intervals API key:', error);
        return false;
    }
}

async function saveIntervalsApiKey(apiKey) {
    try {
        const response = await window.authService.fetch('/intervals/store_api_key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save API key');
        }
        
        return true;
    } catch (error) {
        console.error('Error saving Intervals API key:', error);
        throw error;
    }
}

async function removeIntervalsApiKey() {
    try {
        const response = await window.authService.fetch('/intervals/remove_api_key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to remove API key');
        }
        
        return true;
    } catch (error) {
        console.error('Error removing Intervals API key:', error);
        throw error;
    }
}

//--------------------
//  INTERVALS MODAL SYSTEM
//--------------------

function initializeIntervalsModals() {
    initializeIntervalsMainModal();
    initializeIntervalsConfigModal();
}

function initializeIntervalsMainModal() {
    const modal = document.getElementById('intervalsModal');
    const closeButton = modal?.querySelector('.close');
    const connectButton = document.getElementById('connectIntervals');

    if (!modal || !closeButton || !connectButton) {
        console.warn('Intervals modal elements not found');
        return;
    }

    closeButton.addEventListener('click', hideIntervalsModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) hideIntervalsModal();
    });

    connectButton.addEventListener('click', function() {
        // the dates as typed: both needed, the start before the end (checked here, not while typing - 2026-10-15)
        if (!document.getElementById('intervalsStartDate')?.value || !document.getElementById('intervalsEndDate')?.value) {
            showIntervalsMessage('Please pick both dates.', 'error');
            return;
        }
        const dateRange = getIntervalsDateRange();
        const auxDatasets = getSelectedAuxDatasets();
        const refresh = !!document.getElementById('intervals-refresh')?.checked;    // Refresh everything (2026-10-15): the whole window fetched again
        
        // Validation
        const daysDiff = Math.ceil((new Date(dateRange.end) - new Date(dateRange.start)) / (1000 * 60 * 60 * 24));
        if (daysDiff > 365) {
            showIntervalsMessage('Date range cannot exceed 1 year.', 'error');
            return;
        }
        
        if (daysDiff <= 0) {
            showIntervalsMessage('Please select a valid date range: the start before the end.', 'error');
            return;
        }
    
        setIntervalsButtonLoading(true);
        
        // The ontology download option retired with the ontology; memory
        // packs attach from the Cache manager modal (see MEMORY_LEDGER.md).
        Promise.resolve().then(() => {
            showIntervalsMessage('Starting data load...', 'loading');
            
            // Start the job
            return window.authService.fetch('/intervals/load_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_date: dateRange.start,
                    end_date: dateRange.end,
                    metrics: [],
                    aux_datasets: auxDatasets,
                    refresh: refresh
                })
            });
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || `Server error: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            // Start polling for job status
            pollIntervalsJob(data.job_id, dateRange, auxDatasets);
        })
        .catch(error => {
            console.error('Error starting Intervals load:', error);
            setIntervalsButtonLoading(false);
            showIntervalsMessage(`Failed to start: ${error.message}`, 'error');
        });
    });
}

function pollIntervalsJob(jobId, dateRange, auxDatasets) {
    let jobCompleted = false;  // Add flag to prevent multiple completions
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await window.authService.fetch(`/intervals/job/${jobId}`);
            const job = await response.json();
            
            if (job.status === 'processing' || job.status === 'starting') {
                // Update progress message
                let message = job.message || 'Processing...';
                if (job.percent !== undefined) {
                    message += ` (${job.percent}%)`;
                }
                showIntervalsMessage(message, 'loading');
                
            } else if (job.status === 'completed' && !jobCompleted) {  // Check flag
                jobCompleted = true;  // Set flag immediately
                clearInterval(pollInterval);  // Clear interval first
                
                console.log('Intervals ICU data loaded successfully');
                setIntervalsButtonLoading(false);
                // the store's line (docs/INCREMENTAL_LOADS_DESIGN.md): what was already held and what was downloaded; the box cleared for the next load
                const stLine = storeLine(job.result && job.result.store);
                setIntervalsRefresh(false);
                // the context's line (docs/CONTEXT_DESIGN.md §4 F1): what was written beside the data, and any call that failed
                const ctxLine = contextReportLine(job.result && job.result.context);
                showIntervalsMessage('Data loaded successfully!' + (stLine ? ' ' + stLine + '.' : '') + (ctxLine ? ' ' + ctxLine : ''), 'success');

                setTimeout(() => {
                    hideIntervalsModal();
                }, ctxLine ? 6000 : 2000);

                // Create pill ONLY ONCE
                const dataInfo = {
                    start_date: dateRange.start,
                    end_date: dateRange.end,
                    aux_datasets: auxDatasets,
                    shape: job.result.shape,
                    columns: job.result.columns,
                    files: (job.result && job.result.aux_datasets) || []
                };
                createIntervalsPill(dataInfo);

                const coding = job.result && job.result.context && job.result.context.coding;
                if (job.result && job.result.aux_datasets && job.result.aux_datasets.length > 0) {
                    createIntervalsAuxiliaryPills(job.result.aux_datasets, dataInfo, { coding: !!(coding && coding.status === 'running'), line: (coding && coding.line) || '' });
                    if (coding && coding.status === 'running') pollContextCoding(jobId, dataInfo);
                    else if (coding && coding.codes_path) contextPillAdd([coding.codes_path], dataInfo, { coding: false, line: coding.line || '' });
                }

                // Update dataframe tab if available
                if (job.dataframe) {
                    try {
                        const dfData = JSON.parse(job.dataframe);
                        if (typeof createOrUpdateTab === 'function') {
                            createOrUpdateTab('dataframe', dfData.data);
                            if (typeof activateTab === 'function') {
                                activateTab('dataframe');
                            }
                        }

                        if (typeof window !== 'undefined' && typeof currentDatasetName !== 'undefined') {
                            //Total number of days
                            currentDatasetName = `Intervals ICU Data`;
                        }
                    } catch (error) {
                        console.error('Error parsing Intervals dataframe:', error);
                    }
                }
                
            } else if (job.status === 'error' && !jobCompleted) {  // Also check flag for errors
                jobCompleted = true;  // Set flag
                clearInterval(pollInterval);
                
                console.error('Intervals job failed:', job.error);
                setIntervalsButtonLoading(false);
                showIntervalsMessage(`Failed: ${job.error}`, 'error');
                
            } else if (job.status === 'not_found') {
                clearInterval(pollInterval);
                
                console.error('Job not found');
                setIntervalsButtonLoading(false);
                showIntervalsMessage('Job expired or not found', 'error');
            }
            
        } catch (error) {
            // Keep polling even if one request fails
            console.error('Error polling job status:', error);
        }
    }, 1000); // Poll every 1 seconds
    
    // Safety timeout after 5 minutes
    setTimeout(() => {
        if (!jobCompleted) {  // Only timeout if not completed
            clearInterval(pollInterval);
            setIntervalsButtonLoading(false);
            showIntervalsMessage('Operation timed out', 'error');
        }
    }, 300000);
}

function initializeIntervalsConfigModal() {
    const modal = document.getElementById('intervalsConfigModal');
    const closeButton = modal?.querySelector('.close');
    const apiKeyInput = document.getElementById('intervalsApiKeyInput');
    const saveButton = document.getElementById('saveIntervalsApiKey');
    const removeButton = document.getElementById('removeIntervalsApiKey');
    const statusIndicator = document.getElementById('intervalsApiKeyStatus');

    if (!modal || !closeButton) {
        console.warn('Intervals config modal elements not found');
        return;
    }

    closeButton.addEventListener('click', () => modal.style.display = 'none');
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.style.display = 'none';
    });
    
    // Initialize API key status when modal opens
    modal.addEventListener('show', updateApiKeyStatus);
    
    // Save API key
    if (saveButton) {
        saveButton.addEventListener('click', async function() {
            const apiKey = apiKeyInput?.value?.trim();
            
            if (!apiKey) {
                showIntervalsConfigMessage('Please enter your API key', 'error');
                return;
            }
            
            // Show loading state
            saveButton.disabled = true;
            saveButton.textContent = 'Saving...';
            
            try {
                await saveIntervalsApiKey(apiKey);
                showIntervalsConfigMessage('API key saved successfully!', 'success');
                
                // Update status indicator
                await updateApiKeyStatus();
                
                // Clear input for security
                apiKeyInput.value = '';
                
                // Close modal after success
                setTimeout(() => {
                    modal.style.display = 'none';
                    // Reload to update button visibility
                    window.location.reload();
                }, 1500);
                
            } catch (error) {
                showIntervalsConfigMessage(`Failed to save API key: ${error.message}`, 'error');
            } finally {
                saveButton.disabled = false;
                saveButton.textContent = 'Save';
            }
        });
    }
    
    // Remove API key
    if (removeButton) {
        removeButton.addEventListener('click', async function() {
            if (!confirm('Are you sure you want to remove your Intervals.icu API key?')) {
                return;
            }
            
            // Show loading state
            removeButton.disabled = true;
            removeButton.textContent = 'Removing...';
            
            try {
                await removeIntervalsApiKey();
                showIntervalsConfigMessage('API key removed successfully', 'success');
                
                // Update status indicator
                await updateApiKeyStatus();
                
                // Close modal after success
                setTimeout(() => {
                    modal.style.display = 'none';
                    // Reload to update button visibility
                    window.location.reload();
                }, 1500);
                
            } catch (error) {
                showIntervalsConfigMessage(`Failed to remove API key: ${error.message}`, 'error');
            } finally {
                removeButton.disabled = false;
                removeButton.textContent = 'Remove';
            }
        });
    }
}

async function updateApiKeyStatus() {
    const statusIndicator = document.getElementById('intervalsApiKeyStatus');
    const apiKeyInput = document.getElementById('intervalsApiKeyInput');
    const removeButton = document.getElementById('removeIntervalsApiKey');
    
    if (!statusIndicator) return;
    
    try {
        const hasKey = await checkIntervalsApiKey();
        
        if (hasKey) {
            statusIndicator.innerHTML = `
                <svg class="status-icon success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span>API key is configured</span>
            `;
            statusIndicator.className = 'api-key-status has-key';
            
            // Show masked placeholder
            if (apiKeyInput) {
                apiKeyInput.placeholder = '••••••••••••••••••••••••••••••••';
            }
            
            // Show remove button
            if (removeButton) {
                removeButton.style.display = 'inline-block';
            }
        } else {
            statusIndicator.innerHTML = `
                <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                <span>No API key configured</span>
            `;
            statusIndicator.className = 'api-key-status no-key';
            
            // Show regular placeholder
            if (apiKeyInput) {
                apiKeyInput.placeholder = 'Enter your Intervals.icu API key';
            }
            
            // Hide remove button
            if (removeButton) {
                removeButton.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error updating API key status:', error);
        statusIndicator.innerHTML = '<span>Unable to check API key status</span>';
        statusIndicator.className = 'api-key-status error';
    }
}

function showIntervalsConfigMessage(message, type = 'default') {
    const messageElement = document.getElementById('intervals-config-message');
    if (!messageElement) return;
    
    messageElement.classList.remove('success-message', 'error-message', 'loading-message');
    
    switch(type) {
        case 'loading':
            messageElement.classList.add('loading-message');
            messageElement.textContent = message;
            break;
        case 'success':
            messageElement.classList.add('success-message');
            messageElement.textContent = '✓ ' + message;
            break;
        case 'error':
            messageElement.classList.add('error-message');
            messageElement.textContent = '✗ ' + message;
            break;
        default:
            messageElement.textContent = message;
    }
    
    messageElement.style.display = 'block';
    
    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            messageElement.style.display = 'none';
        }, 3000);
    }
}

//--------------------
//  MODAL DISPLAY FUNCTIONS
//--------------------

function showIntervalsModal() {
    const modal = document.getElementById('intervalsModal');
    if (modal) {
        modal.style.display = 'flex';
        showIntervalsMessage('', 'default');
        initializeIntervalsDatePickers();
        initializeAuxDatasetOptions();
        initializeDownloadChoice();
        showIntervalsStoreLine();
        if (window.CodebookUI && typeof window.CodebookUI.badge === 'function') window.CodebookUI.badge();   // the Context card's codebook line, current
    }
}

// Download (2026-10-16): a two-sided choice, Only what's new / Everything again; the hidden box #intervals-refresh keeps the
// state the load reads (docs/INCREMENTAL_LOADS_DESIGN.md: the request's `refresh`)
function setIntervalsRefresh(on) {
    const box = document.getElementById('intervals-refresh');
    if (box) box.checked = !!on;
    document.querySelectorAll('#intervalsDownload [data-refresh]').forEach(b => b.classList.toggle('on', (b.getAttribute('data-refresh') === '1') === !!on));
}
function initializeDownloadChoice() {
    const seg = document.getElementById('intervalsDownload');
    if (!seg || seg._bound) return;
    seg._bound = true;
    seg.addEventListener('click', e => {
        const b = e.target.closest('[data-refresh]');
        if (b) setIntervalsRefresh(b.getAttribute('data-refresh') === '1');
    });
}
// the foot's line while nothing is happening: what the store holds for this account (the Dataset cache panel's figures), so a
// person sees before loading that the window will come mostly from the store; a message of the load replaces it
function showIntervalsStoreLine() {
    const el = document.getElementById('intervals-modal-message');
    if (!el || !window.authService || typeof window.authService.fetch !== 'function') return;
    window.authService.fetch('/cache/inspect').then(r => r.ok ? r.json() : null).then(d => {
        if (!el || el.textContent.trim() !== '' || !d) return;
        const stores = d.stores || [];
        if (!stores.length) { el.innerHTML = 'Nothing in the store yet \u00b7 the first load fills it; later loads fetch only what they lack'; return; }
        const n = stores.reduce((a, st) => a + (Number(st.activities) || 0), 0);
        const froms = stores.map(st => st.from).filter(Boolean).sort(), tos = stores.map(st => st.to).filter(Boolean).sort();
        const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
        const names = stores.map(st => st.subject && (st.subject.name || st.subject.id)).filter(Boolean);     // whose (2026-10-29)
        el.innerHTML = 'Store' + (names.length === 1 ? ' \u00b7 ' + esc(names[0]) : names.length > 1 ? ' \u00b7 ' + names.length + ' athletes' : '') + ' \u00b7 <b>' + n + ' activit' + (n === 1 ? 'y' : 'ies') + '</b>' + (froms.length ? ' \u00b7 ' + esc(froms[0]) + ' \u2192 ' + esc(tos[tos.length - 1]) : '') + ' \u00b7 only what the window lacks is fetched';
    }).catch(() => {});
}

async function showIntervalsConfigModal() {
    const modal = document.getElementById('intervalsConfigModal');
    if (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        // Update API key status before showing
        await updateApiKeyStatus();
        
        modal.style.display = 'flex';
        
        // Trigger custom event for modal show
        const event = new Event('show');
        modal.dispatchEvent(event);
    }
}

function hideIntervalsModal() {
    const modal = document.getElementById('intervalsModal');
    if (modal) modal.style.display = 'none';
}

//--------------------
//  FORM HANDLING
//--------------------

function initializeIntervalsDatePickers() {
    // The bounds and, the first time, the default window. Nothing rewrites a date while it is being typed: the
    // change handlers that clamped start and end to each other are gone (2026-10-15) - a date being typed passes
    // through '' and through partial values, each of which the clamp read as out of order and overwrote, until both
    // inputs held the same day and neither could be changed. The order is checked when Load is pressed.
    applyIntervalsDateLimits();
}

function initializeAuxDatasetOptions() {
    // Handle auxiliary dataset options
    const auxOptions = document.querySelectorAll('.intervals-aux-option');
    
    auxOptions.forEach((option) => {
        // Remove any existing listeners
        const existingListener = option._clickListener;
        if (existingListener) {
            option.removeEventListener('click', existingListener);
        }

        const clickListener = function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const checkbox = option.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            
            checkbox.checked = !checkbox.checked;
            option.classList.toggle('selected', checkbox.checked);
        };

        option._clickListener = clickListener;
        option.addEventListener('click', clickListener);
    });

    // Initialize selected state for aux datasets
    document.querySelectorAll('.intervals-aux-option input[type="checkbox"]:checked').forEach(checkbox => {
        const label = checkbox.closest('.intervals-aux-option');
        if (label) label.classList.add('selected');
    });
}

//--------------------
//  SELECTION FUNCTIONS
//--------------------

function getIntervalsDateRange() {
    const startDate = document.getElementById('intervalsStartDate')?.value;
    const endDate = document.getElementById('intervalsEndDate')?.value;
    
    if (!startDate || !endDate) {
        const end = new Date();
        const start = new Date();
        start.setMonth(start.getMonth() - 3);
        
        return {
            start: localIsoDay(start),
            end: localIsoDay(end)
        };
    }
    
    return { start: startDate, end: endDate };
}

function getSelectedAuxDatasets() {
    const auxDatasets = [];
    const wellnessCheckbox = document.getElementById('wellness-checkbox');
    const summaryCheckbox = document.getElementById('summary-checkbox');
    const intervalsCheckbox = document.getElementById('intervals-checkbox');
    
    if (wellnessCheckbox?.checked) auxDatasets.push('wellness');
    if (summaryCheckbox?.checked) auxDatasets.push('summary');
    if (intervalsCheckbox?.checked) auxDatasets.push('intervals');
    const riderCheckbox = document.getElementById('rider-checkbox');
    if (riderCheckbox?.checked) auxDatasets.push('rider');                // the settings the data is read against (2026-10-16); the custom zone times ride with it when the account defines any
    const contextCheckbox = document.getElementById('context-checkbox');
    if (contextCheckbox?.checked) auxDatasets.push('context', 'plan');   // the planned workouts ride with the context (2026-10-15): the calendar's numbers beside its words
    
    return auxDatasets;
}

//--------------------
//  UI HELPER FUNCTIONS
//--------------------

function showIntervalsMessage(message, type = 'default') {
    const messageElement = document.getElementById('intervals-modal-message');
    if (!messageElement) return;
    
    messageElement.classList.remove('success-message', 'error-message', 'loading-message');
    
    switch(type) {
        case 'loading':
            messageElement.classList.add('loading-message');
            messageElement.textContent = message;
            break;
        case 'success':
            messageElement.classList.add('success-message');
            messageElement.textContent = '✓ ' + message;
            break;
        case 'error':
            messageElement.classList.add('error-message');
            messageElement.textContent = '✗ ' + message;
            break;
        default:
            messageElement.innerHTML = message;
    }
}

function setIntervalsButtonLoading(isLoading) {
    const connectButton = document.getElementById('connectIntervals');
    const buttonLabel = connectButton?.parentElement?.querySelector('.button-label');
    
    if (!connectButton) return;
    
    if (isLoading) {
        connectButton.classList.add('loading');
        connectButton.disabled = true;
        if (buttonLabel) buttonLabel.textContent = 'Loading Data...';
    } else {
        connectButton.classList.remove('loading');
        connectButton.disabled = false;
        if (buttonLabel) buttonLabel.textContent = 'Load Data';
    }
}

//--------------------
//  INTEGRATION WITH MAIN APP
//--------------------

function handleIntervals() {
    const intervalsOption = document.querySelector('.intervals-option');
    const isEnabled = intervalsOption?.getAttribute('data-enabled') === 'true';

    if (!isEnabled) {
        showIntervalsConfigModal();
    } else {
        // For now, just show the config modal since we don't have OAuth
        // In the future, this could handle OAuth flow
        showIntervalsConfigModal();
    }
}

// Export functions for use by other modules
if (typeof window !== 'undefined') {
    window.Intervals = {
        initialize: initializeIntervalsIntegration,
        handleIntervals: handleIntervals,
        createPill: createIntervalsPill,
        removePill: removeIntervalsPill,
        showModal: showIntervalsModal,
        hideModal: hideIntervalsModal,
        state: currentIntervalsState,
        pollJob: pollIntervalsJob
    };
}