//--------------------
//  QUERY PROCESSING MODULE
//--------------------

function initializeQueryProcessing() {
    console.log('Initializing query processing...');

    // Configure Highlight.js to disable security warnings
    if (typeof hljs !== 'undefined') {
        hljs.configure({
            ignoreUnescapedHTML: true,
            throwUnescapedHTML: false
        });
    }
    
    initializeMainQuerySubmission();
    initializeSaveButton();
    initializePopupSystem();
    
    console.log('Query processing initialized');
}

//--------------------
//  MAIN QUERY SUBMISSION
//--------------------

function initializeMainQuerySubmission() {
    const submitQueryButton = document.getElementById('submitQuery');
    
    if (submitQueryButton) {
        submitQueryButton.addEventListener('click', () => handleQuerySubmit({ typed: true }));
    } else {
        console.warn('Submit query button not found');
    }
}

// options.typed: the composer's own send; options.framed: the chain whose brief is being started (architect.js), with
// options.step, the step of its conversation on screen, from which the analysis starts - under the brief that stands there;
// options.next: the next question the analysis is started from (next-questions.js) - run as it stands, with no brief.
// With a turn gone back to (branch.js) what is typed is a hint: the analysis on screen goes on from that turn, another way
function handleQuerySubmit(options = {}) {
    const { synthesis, image, typed, framed, next, step } = options;
    const queryInput = document.getElementById('queryInput');
    const submitButton = document.getElementById('submitQuery');
    const query = framed ? String(framed.queryText || '').trim() : (next ? String(next.text || '').trim() : queryInput.value.trim());
    
    // If normal query is running, clicking submit = stop
    if (queryRunning && !autoExploreRunning) {
        stopQuery();
        return;
    }
    
    // If auto-explore is running, clicking submit = stop
    if (autoExploreRunning) {
        stopAutoExplore();
        return;
    }
    
    if (!query && !synthesis) {
        return;
    }
    if (window.NextQuestionsUI && window.NextQuestionsUI.holds()) return;      // a set of next questions is being written: nothing starts beside it

    // a turn gone back to: the branch the hint starts - in the mode, under the limits and the brief of the analysis it
    // goes on from, so the Pathfinder is not asked
    const branch = typed && window.BranchUI ? window.BranchUI.hint(query) : null;

    if (window.ArchitectUI && !framed && !branch) {
        // a brief not yet run is on screen: what is typed is said to the Pathfinder, and nothing else starts from it
        if (window.ArchitectUI.framingInView()) {
            answerTabSynthesis = false;
            if (typed) window.ArchitectUI.tell(query);
            else showSystemMessage('This brief has not been run: start its analysis, or open another chain');
            return;
        }
        // a typed question with the Pathfinder on is framed first: its brief opens, and nothing runs until Start analysis
        if (typed && window.ArchitectUI.isOn()) {
            window.ArchitectUI.open(query);
            return;
        }
    }

    // Set running state
    queryRunning = true;

    // If auto-explore enabled, switch to running state (don't disable button)
    if (autoExploreEnabled) {
        setAutoExploreRunning(true);
    } else {
        // Normal mode - show stop button (don't disable)
        setQueryRunning(true);
    }

    // Hide the Save pill while the new chain runs
    const saveButton = document.getElementById('saveButton');
    if (saveButton) {
        saveButton.style.display = 'none';
    }
    // the maps drawer lies over the pane the run is shown in: it shuts (maps.js)
    if (window.MapsUI) window.MapsUI.shut();

    // Store the query text
    if (synthesis) {
        currentData.queryText = 'Synthesis of exploration results';
    } else {
        currentData.queryText = branch ? branch.question : query;      // a branch is its analysis's question, asked another way
    }
    currentData.branch = branch ? { of: branch.of, turn: branch.turn, hint: query } : null;      // kept with the chain (saveCurrentResponse)

    if (typeof liveState !== 'undefined' && liveState.running && liveState.away) liveComeBack();   // a new run takes the view
    const streamOutputDiv = document.getElementById('streamOutput');
    streamOutputDiv.innerHTML = '';
    if (typeof clearAllTabs === 'function') {
        clearAllTabs();
    }
    if (typeof beginLiveChain === 'function') beginLiveChain(framed);   // the running chain is navigable from now on (2026-09-09)
    if (branch) window.BranchUI.started(branch);
    if (framed) window.ArchitectUI.started(framed);
    if (next) window.NextQuestionsUI.started(next);

    // Clear and reset input (not for a synthesis, nor for a next question: neither was typed there)
    if (!synthesis && !next) {
        queryInput.value = '';
        queryInput.style.height = 'auto';
    }

    // Prepare request
    const requestBody = {
        query: query || null,
        chain_id: framed ? framed.parentChainId : currentData.chain_id,
        thread_id: currentData.thread_id,
        mode: (typeof currentMode !== 'undefined' ? currentMode : 'deep'),
        auto_explore: autoExploreEnabled,
        // THE SIMPLIFICATION (2026-08-18): the dial means INVESTIGATIONS -
        // "up to N investigations, each up to M steps". The legacy key is
        // still sent so an older server keeps working.
        max_investigations: autoExploreIterations,
        max_iterations: autoExploreIterations
    };

    if (next) requestBody.next = { set: next.set, k: next.k };      // the server marks it as run on the analysis it follows
    if (synthesis) requestBody.synthesis = true;
    if (image) requestBody.image = image;
    if (framed) requestBody.run_id = framed.chain_id;   // the analysis continues the run its brief was written in
    if (framed && step) requestBody.step = step;               // ... from the step of its conversation on screen
    if (branch) requestBody.branch = { turn: branch.turn };    // the chain on screen goes on from that turn; the query is the hint

    let streaming = false;      // the server has started the run

    window.authService.fetch('/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
    })
    .then(async response => {
        if (response.status === 403) {
            const errorData = await response.json();
            const details = {
                balance: errorData.balance,
                query_cost: errorData.query_cost,
                tier: errorData.tier,
                reason: errorData.reason
            };
            showQueryLimitModal(errorData.message, details);
            if (!framed && !next) queryInput.value = query;

            // Reset state
            queryRunning = false;
            if (autoExploreEnabled) {
                resetAutoExplore();
            } else {
                setQueryRunning(false);
            }
            if (framed) window.ArchitectUI.notStarted(framed);      // the chain is a brief again
            if (branch) window.BranchUI.notStarted();               // the chain is at its turn again, the hint in the composer
            return;
        }
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        streaming = true;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        function readStream() {
            return reader.read().then(({done, value}) => {
                if (done) {
                    console.log('Stream complete');
        
                    // Reset state
                    queryRunning = false;
                    if (autoExploreEnabled || autoExploreRunning) {
                        resetAutoExplore();
                    } else {
                        setQueryRunning(false);
                    }
        
                    if (branch && window.BranchUI.unstarted()) window.BranchUI.notStarted();      // the server started no branch, and said why: nothing of the request is kept
                    else if (typeof saveCurrentResponse === 'function') saveCurrentResponse();
                    return;
                }
                const chunk = decoder.decode(value);
                processChunk(chunk);
                return readStream();
            });
        }

        if (typeof updateQueryCounter === 'function') {
            updateQueryCounter();
        }

        return readStream();
    })
    .catch(error => {
        console.error('Error:', error);
        if (!framed || streaming) streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;

        // Reset state
        queryRunning = false;
        if (autoExploreEnabled || autoExploreRunning) {
            resetAutoExplore();
        } else {
            setQueryRunning(false);
        }
        if (framed && !streaming) window.ArchitectUI.notStarted(framed, error.message);      // the server did not start it: a brief again
        if (branch && !streaming) window.BranchUI.notStarted(error.message);
    });
}

//--------------------
//  STREAMING RESPONSE PROCESSING
//--------------------

function processChunk(chunk) {
    const streamOutputDiv = document.getElementById('streamOutput');

    buffer += chunk;
    let startIndex = 0;

    while (true) {
        let endIndex = buffer.indexOf('\n', startIndex);
        if (endIndex === -1) break;

        let line = buffer.substring(startIndex, endIndex).trim();
        if (line) {
            const away = (typeof liveState !== 'undefined' && liveState.running && liveState.away);
            let viewData = null, viewTasks = null;
            if (away) { viewData = currentData; viewTasks = taskContents; currentData = liveState.data; taskContents = liveState.tasks; }
            try {
                const data = JSON.parse(line);
                if (data.type === "id") {
                    if (data.chain_id) currentData.chain_id = data.chain_id;
                    if (data.thread_id) currentData.thread_id = data.thread_id;
                    if (typeof liveState !== 'undefined' && liveState.running && responses[liveState.index] && responses[liveState.index].status === 'running') { responses[liveState.index].chain_id = data.chain_id || null; responses[liveState.index].thread_id = data.thread_id || null; }
                    // The server says where this chain attached: adopt it, so the
                    // map is drawn from the record instead of a parent computed here.
                    if ('parent_chain_id' in data) lastActiveChainId = data.parent_chain_id;
                    if (typeof paneIds === 'function') paneIds(data);
                    if (window.BranchUI) window.BranchUI.announced(data);      // a branch asked for: the server has started it
                    if (window.NextQuestionsUI) window.NextQuestionsUI.ran(data.chain_id);      // the run is on: the question that started it is marked on its card
                }
                else if (data.type === "html") { /* the search seam's SERP preview: retired, nothing renders it (2026-09-06) */ }
                else if (data.type === "pane_run_start")  { if (typeof paneRunStart === 'function') paneRunStart(data); }
                else if (data.type === "pane_turn_start") { if (typeof paneTurnStart === 'function') paneTurnStart(data); }
                else if (data.type === "pane_turn_end")   { if (typeof paneTurnEnd === 'function') paneTurnEnd(data); }
                else if (data.type === "pane_cell")       { if (typeof paneCell === 'function') paneCell(data); if (window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(false); }
                else if (data.type === "pane_cell_start") { if (window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(true); handled = true; }   // the executor chip: Executing (2026-09-08)
                else if (data.type === "pane_lookup_start") { if (typeof paneLookupStart === 'function') paneLookupStart(data); }   // a READ or SEARCH under way (2026-10-03)
                else if (data.type === "pane_lookup")     { if (typeof paneLookup === 'function') paneLookup(data); if ((data.kind === 'replay' || data.kind === 'routine' || data.kind === 'run') && window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(false); }   // the replay, run zero or a routine's run done: the chip back to Ready (2026-10-04; 2026-10-10 the routine's rows, which set it as a cell does)
                else if (data.type === "pane_passages")   { if (typeof panePassages === 'function') panePassages(data); }   // the report's cited passages, before the answer renders (2026-10-14)
                else if (data.type === "pane_heartbeat")  { if (typeof paneHeartbeat === 'function') paneHeartbeat(data); }
                else if (data.type === "pane_datasets")   { if (typeof paneDatasets === 'function') paneDatasets(data); }
                else if (data.type === "pane_run_end")    { if (typeof paneRunEnd === 'function') paneRunEnd(data); if (window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(false); }
                else if (data.thought) {
                    // reasoning-channel tokens of the live turn (kept, collapsed)
                    if (!(typeof paneThought === 'function' && paneThought(data.thought))) { /* no live turn: dropped */ }
                }
                else if (data.type === "synthesis_image") {
                    currentData.synthesisImage = { data: data.data, mime_type: data.mime_type || 'image/png' };
                    if (typeof appendSynthesisImage === 'function') appendSynthesisImage(data.data, data.mime_type || 'image/png');
                }
                else if (data.type === "simplified_answer") {
                    currentData.simplifiedAnswer = data.data;
                    
                    function enableAndShowButton() {
                        const button = document.querySelector('.simplified-summary-btn');
                        if (button) {
                            button.style.display = '';  // Show it
                            button.disabled = false;
                            button.classList.remove('loading');
                            if (typeof updateSimplifiedButtonLabel === 'function') {
                                updateSimplifiedButtonLabel();
                            }
                            console.log("Simplified summary button enabled");
                            return true;
                        }
                        return false;
                    }
                    
                    if (!enableAndShowButton()) {
                        setTimeout(() => {
                            if (!enableAndShowButton()) {
                                setTimeout(enableAndShowButton, 200);
                            }
                        }, 150);
                    }
                    
                    console.log("Simplified summary received");
                } else if (data.report_head) {
                    // the report's head (2026-10-17): the title and lead the analyst wrote for the finished report, the question,
                    // what data it stands on, the mode, the replay's verdict - kept with the chain for the PDF export's top section
                    currentData.reportHead = Object.assign({}, data.report_head, { chain_id: data.chain_id || null });
                } else if (data.call_summary) {
                    if (typeof paneSummary === 'function') paneSummary(data.call_summary);
                } else if (data.system_message) {
                    showSystemMessage(data.system_message);
                    if (typeof paneSystem === 'function') paneSystem(data.system_message);
                } else if (data.error) {
                    if (window.BranchUI) window.BranchUI.heard(data.error);      // why a branch was not started, where one was asked for
                    if (typeof paneSystem === 'function') paneSystem(data.error, 'error');
                    else streamOutputDiv.innerHTML += '<div class="sp-sys error">' + escapeHtml(String(data.error)) + '</div>';
                } else if (data.type && data.type !== 'end' && data.type !== 'id') {
                    // Reset simplified summary data when new answer arrives
                    if (data.type === 'answer') {
                        currentData.simplifiedAnswer = null;
                        currentData.summaryViewMode = 'technical';
                        // the head arrives just before the answer (2026-10-17); one from an earlier chain never outlives its answer
                        if (currentData.reportHead && String(currentData.reportHead.chain_id) !== String(data.chain_id)) currentData.reportHead = null;
                    }
                    
                    console.log(`Right panel data detected: ${data.type}`, data);
                    if (typeof createOrUpdateTab === 'function') {
                        createOrUpdateTab(data.type, data.data, data.id, data.format);
                    }
                } else if (data.text) {
                    // content tokens: into the live turn card; outside a turn, plain text in the pane
                    if (!(typeof paneToken === 'function' && paneToken(data.text))) {
                        const escapedText = data.text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        streamOutputDiv.innerHTML += escapedText;
                    }
                } else if (data.type === 'end') {
                    console.log("End of results detected");
                } else {
                    console.log("Unhandled data detected:", data);
                }
            } catch (e) {
                console.error("Error processing line:", e);
                console.log("Problematic line:", line);
                // Don't add the line to the output, keep it in the buffer
                break;
            }
            if (away) { liveState.data = currentData; liveState.tasks = taskContents; currentData = viewData; taskContents = viewTasks; }
        }
        startIndex = endIndex + 1;
    }

    // Remove processed data from the buffer
    buffer = buffer.substring(startIndex);
    
    // Scroll to the bottom of the output unless user interrupts
    if (streamOutputDiv) {
        if (autoScroll) {
            streamOutputDiv.scrollTop = streamOutputDiv.scrollHeight;
        }
    }
}

//--------------------
//  CONTENT PROCESSORS
//--------------------

//--------------------
//  SAVING
//--------------------

function initializeSaveButton() {
    const saveButton = document.getElementById('saveButton');
    if (!saveButton) return;
    // the pill opens its menu (routines.js): Save as favourite, Save as routine
    saveButton.addEventListener('click', () => {
        if (window.RoutinesUI && typeof window.RoutinesUI.toggleSaveMenu === 'function') window.RoutinesUI.toggleSaveMenu();
    });
    saveButton.style.display = 'none';
}

let savesInOrder = Promise.resolve();   // one save at a time, in the order asked

// Save to Saved workflows, in one click. `target` is the chain the coach picked, or 'all' for the whole thread.
// Every chain of the thread is stored: the picked one marked 'individual', the others 'trajectory'. `quiet` leaves
// out the closing message (Save as routine saves the favourite on its way). Resolves true once stored.
function saveToFavourites(target, quiet = false) {
    savesInOrder = savesInOrder.then(() => storeFavourites(target, quiet));
    return savesInOrder;
}

async function storeFavourites(target, quiet) {
    const label = document.querySelector('#saveButton .save-label');
    if (label) label.textContent = 'Saving…';
    try {
        const allResponses = await localforage.getItem('responses');
        const threadId = currentData.thread_id;

        // every chain of this thread, in the order they were made
        const threadResponses = [];
        (Array.isArray(allResponses) ? allResponses : []).forEach((resp, idx) => {
            if (resp && threadId && resp.thread_id === threadId && resp.status !== 'framing') {      // a brief not yet run is not an analysis
                threadResponses.push({ resp, idx });
            }
        });
        if (threadResponses.length === 0) throw new Error('nothing to save yet');

        // the chains the server holds already are not sent again (String(): its ids are strings)
        const existingResponse = await window.authService.fetch(
            `/storage/get_existing_chains/${threadId}`
        );
        const existingData = await existingResponse.json();
        const existingChainIds = new Set(existingData.chain_ids || []);
        const newChains = threadResponses.filter(
            ({ resp }) => !existingChainIds.has(String(resp.chain_id))
        );
        const existingChains = threadResponses.filter(
            ({ resp }) => existingChainIds.has(String(resp.chain_id))
        );

        // except the picked chain: sent every time, so its mark and its pane are the current ones
        const pickedIdx = existingChains.findIndex(({ resp }) => String(resp.chain_id) === String(target));
        if (pickedIdx > -1) newChains.push(existingChains.splice(pickedIdx, 1)[0]);

        const trajectoryData = [];
        for (const { resp: chainData, idx } of newChains) {
            const plotPreview = await generatePlotPreview(chainData.contentOutput || '');
            const compressedContentOutput = await compressContent(chainData.contentOutput || '');
            const compressedStreamOutput = await compressContent(chainData.streamOutput || '');

            const contentCompressed = compressedContentOutput !== (chainData.contentOutput || '');
            const streamCompressed = compressedStreamOutput !== (chainData.streamOutput || '');

            let task = '';
            if (typeof extractTaskFromResponse === 'function') {
                const extracted = extractTaskFromResponse(chainData);
                task = extracted.task || extracted.originalQuestion || '';
            }
            if (!task) {
                task = chainData.queryText || '';
            }

            trajectoryData.push({
                chain_id: chainData.chain_id,
                parentChainId: chainData.parentChainId || null,
                index: idx,
                task: task,
                bookmark_type: String(chainData.chain_id) === String(target) ? 'individual' : 'trajectory',
                content: {
                    tabContent: chainData.tabContent || '',
                    contentOutput: compressedContentOutput,
                    streamOutput: compressedStreamOutput,
                    taskContents: chainData.taskContents || {},
                    queryText: chainData.queryText || '',
                    plotPreview: plotPreview,
                    compressed: contentCompressed || streamCompressed,
                    technicalAnswer: chainData.technicalAnswer || null,
                    simplifiedAnswer: chainData.simplifiedAnswer || null,
                    summaryViewMode: chainData.summaryViewMode || 'technical',
                    synthesisImage: chainData.synthesisImage || null,
                    reportHead: chainData.reportHead || null
                }
            });
        }

        if (trajectoryData.length > 0) {
            const response = await window.authService.fetch('/storage/trajectory_favourites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    thread_id: threadId,
                    dataset_name: currentDatasetName,
                    trajectory: trajectoryData
                }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || result.error) {
                throw new Error(result.error || `the server answered ${response.status}`);
            }
            if (result.errors) throw new Error(result.errors[0]);
        }

        // the marks on the page's own copies; a picked chain is never downgraded to 'trajectory'
        trajectoryData.forEach(item => {
            const lfMatch = allResponses.find(r => r && String(r.chain_id) === String(item.chain_id));
            if (lfMatch && lfMatch.bookmark_type !== 'individual') {
                lfMatch.bookmark_type = item.bookmark_type;
            }
            const globalMatch = responses.find(r => r && String(r.chain_id) === String(item.chain_id));
            if (globalMatch && globalMatch.bookmark_type !== 'individual') {
                globalMatch.bookmark_type = item.bookmark_type;
            }
        });
        existingChains.forEach(({ resp }) => {
            const globalMatch = responses.find(r => r && String(r.chain_id) === String(resp.chain_id));
            if (globalMatch && !globalMatch.bookmark_type) {
                globalMatch.bookmark_type = 'trajectory';
            }
        });
        await localforage.setItem('responses', allResponses);

        if (!quiet) showSystemMessage(target === 'all' ? 'Saved the whole thread' : 'Saved as favourite');
        return true;
    } catch (error) {
        console.error('Error saving:', error);
        if (!quiet) showSystemMessage(`Could not save: ${error.message}`);
        return false;
    } finally {
        if (label) label.textContent = 'Save';
        updateSaveButton();
    }
}

function updateSaveButton() {
    const saveButton = document.getElementById('saveButton');
    if (!saveButton) return;

    if (window.RoutinesUI && typeof window.RoutinesUI.inRunView === 'function' && window.RoutinesUI.inRunView()) { saveButton.style.display = 'none'; return; }   // a run is recorded as it completes: nothing to save
    const currentResponse = responses[currentResponseIndex];

    // the pill shows on any finished chain in view (2026-10-10, routines): saved or not, since its menu offers Save as
    // routine beside Save as favourite; a running chain, a brief not yet run, or none, hides it. A saved chain marks the pill .saved.
    const finished = currentResponse && currentResponse.status !== 'running' && currentResponse.status !== 'framing' && (currentResponse.bookmark_type || currentResponse.chain_id);
    if (!finished) {
        saveButton.style.display = 'none';
        saveButton.classList.remove('saved');
        if (window.RoutinesUI && typeof window.RoutinesUI.hideSaveMenu === 'function') window.RoutinesUI.hideSaveMenu();
        return;
    }
    saveButton.style.display = 'block';
    const saved = currentResponse.bookmark_type === 'individual';
    saveButton.classList.toggle('saved', saved);
    saveButton.setAttribute('data-tip', saved ? 'Saved · Save as routine' : 'Save this chain');
}

//--------------------
//  POPUP SYSTEM
//--------------------

function startPopupTimer() {
    // the toast (#summaryPopup) hides itself after a few seconds
    popupTimeout = setTimeout(() => {
        const popup = document.getElementById('summaryPopup');
        if (popup) {
            popup.style.display = 'none';
        }
    }, 5000);
}

function initializePopupSystem() {
    const popup = document.getElementById('summaryPopup');
    const closeButton = popup?.querySelector('.close-button');

    if (closeButton) {
        closeButton.addEventListener('click', closePopup);
    }

    if (popup) {
        popup.addEventListener('mouseenter', () => {
            clearTimeout(popupTimeout);
        });

        popup.addEventListener('mouseleave', startPopupTimer);
    }
}

function showSystemMessage(message) {
    const popup = document.getElementById('summaryPopup');
    const content = document.getElementById('summaryContent');
    
    if (!popup || !content) return;
    
    // Check if popup is already showing system messages - stack them
    if (popup.style.display === 'block' && popup.classList.contains('system-message')) {
        // Add separator and new message
        const separator = document.createElement('hr');
        separator.className = 'message-separator';
        content.appendChild(separator);
        
        const messagePre = document.createElement('pre');
        messagePre.textContent = message;
        content.appendChild(messagePre);
    } else {
        // First message - clear and setup
        content.innerHTML = '';
        
        const header = document.createElement('h4');
        header.textContent = 'System Message';
        content.appendChild(header);
        
        const messagePre = document.createElement('pre');
        messagePre.textContent = message;
        content.appendChild(messagePre);
        
        popup.classList.add('system-message');
        popup.style.display = 'block';
    }
    
    clearTimeout(popupTimeout);
    startPopupTimer();
}

function closePopup() {
    const popup = document.getElementById('summaryPopup');
    if (popup) {
        popup.style.display = 'none';
    }
    clearTimeout(popupTimeout);
}

//--------------------
//  FORMATTERS
//--------------------

async function downloadFile(datasetPath) {
    // Ensure the path is properly formatted for URL encoding
    datasetPath = datasetPath.replace(/\\/g, '/');

    try {
        const response = await window.authService.fetch(`/download_generated_dataset?path=${encodeURIComponent(datasetPath)}`);
        
        if (!response.ok) {
            throw new Error('Download failed');
        }
        
        const blob = await response.blob();
        const filename = datasetPath.split('/').pop() || 'dataset_file.csv';
        
        // Create download link and trigger download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        console.error('Download failed:', error);
    }
}

