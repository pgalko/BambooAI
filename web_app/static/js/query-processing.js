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
    initializeRankingSystem();
    initializePopupSystem();
    
    console.log('Query processing initialized');
}

//--------------------
//  MAIN QUERY SUBMISSION
//--------------------

function initializeMainQuerySubmission() {
    const submitQueryButton = document.getElementById('submitQuery');
    
    if (submitQueryButton) {
        submitQueryButton.addEventListener('click', handleQuerySubmit);
    } else {
        console.warn('Submit query button not found');
    }
}

function handleQuerySubmit(options = {}) {
    const { branching_cv, synthesis, image, user_code } = options;
    const queryInput = document.getElementById('queryInput');
    const submitButton = document.getElementById('submitQuery');
    const query = queryInput.value.trim();
    
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
    
    if (!query && !branching_cv && !synthesis && !user_code) {
        return;
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

    // Hide rank button and reset its state
    const rankButton = document.getElementById('rankButton');
    if (rankButton) {
        rankButton.style.display = 'none';
        rankButton.classList.remove('replay', 'replay-success');
    }
    currentRankData = null;

    // Store the query text
    if (synthesis) {
        currentData.queryText = 'Synthesis of exploration results';
    } else if (user_code) {
        currentData.queryText = 'Manually executed code';
    } else {
        currentData.queryText = query;
    }

    if (typeof liveState !== 'undefined' && liveState.running && liveState.away) liveComeBack();   // a new run takes the view
    const streamOutputDiv = document.getElementById('streamOutput');
    streamOutputDiv.innerHTML = '';
    if (typeof clearAllTabs === 'function') {
        clearAllTabs();
    }
    if (typeof beginLiveChain === 'function') beginLiveChain();   // the running chain is navigable from now on (2026-09-09)

    // Clear and reset input (only if not synthesis)
    if (!synthesis) {
        queryInput.value = '';
        queryInput.style.height = 'auto';
    }

    // Prepare request
    const requestBody = {
        query: query || null,
        chain_id: currentData.chain_id,
        thread_id: currentData.thread_id,
        mode: (typeof currentMode !== 'undefined' ? currentMode : 'deep'),
        auto_explore: autoExploreEnabled,
        // THE SIMPLIFICATION (2026-08-18): the dial means INVESTIGATIONS -
        // "up to N investigations, each up to M steps". The legacy key is
        // still sent so an older server keeps working.
        max_investigations: autoExploreIterations,
        max_iterations: autoExploreIterations
    };

    if (branching_cv) requestBody.branching_cv = branching_cv;
    if (synthesis) requestBody.synthesis = true;
    if (image) requestBody.image = image;
    if (user_code) requestBody.user_code = user_code;

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
            queryInput.value = query;

            // Reset state
            queryRunning = false;
            if (autoExploreEnabled) {
                resetAutoExplore();
            } else {
                setQueryRunning(false);
            }
            return;
        }
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
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
        
                    // Create theoretical stub BEFORE saving
                    if (!currentRankData) {
                        currentRankData = {
                            chain_id: currentData.chain_id,
                            theoretical: true
                        };
                        updateRankButtonVisibility();
                    }
        
                    if (typeof saveCurrentResponse === 'function') {
                        saveCurrentResponse();
                    }
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
        streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;

        // Reset state
        queryRunning = false;
        if (autoExploreEnabled || autoExploreRunning) {
            resetAutoExplore();
        } else {
            setQueryRunning(false);
        }
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
            let viewData = null, viewRank = null, viewTasks = null;
            if (away) { viewData = currentData; viewRank = currentRankData; viewTasks = taskContents; currentData = liveState.data; currentRankData = liveState.rank; taskContents = liveState.tasks; }
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
                }
                else if (data.type === "html") { /* the search seam's SERP preview: retired, nothing renders it (2026-09-06) */ }
                else if (data.type === "pane_run_start")  { if (typeof paneRunStart === 'function') paneRunStart(data); }
                else if (data.type === "pane_turn_start") { if (typeof paneTurnStart === 'function') paneTurnStart(data); }
                else if (data.type === "pane_turn_end")   { if (typeof paneTurnEnd === 'function') paneTurnEnd(data); }
                else if (data.type === "pane_cell")       { if (typeof paneCell === 'function') paneCell(data); if (window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(false); }
                else if (data.type === "pane_cell_start") { if (window.containerStatus && window.containerStatus.setExecuting) window.containerStatus.setExecuting(true); handled = true; }   // the executor chip: Executing (2026-09-08)
                else if (data.type === "pane_lookup")     { if (typeof paneLookup === 'function') paneLookup(data); }
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
                } else if (data.call_summary) {
                    if (typeof paneSummary === 'function') paneSummary(data.call_summary);
                } else if (data.system_message) {
                    showSystemMessage(data.system_message);
                    if (typeof paneSystem === 'function') paneSystem(data.system_message);
                } else if (data.error) {
                    if (typeof paneSystem === 'function') paneSystem(data.error, 'error');
                    else streamOutputDiv.innerHTML += '<div class="sp-sys error">' + escapeHtml(String(data.error)) + '</div>';
                } else if (data.type && data.type !== 'end' && data.type !== 'id') {
                    // Reset simplified summary data when new answer arrives
                    if (data.type === 'answer') {
                        currentData.simplifiedAnswer = null;
                        currentData.summaryViewMode = 'technical';
                    }
                    
                    console.log(`Right panel data detected: ${data.type}`, data);
                    if (typeof createOrUpdateTab === 'function') {
                        if (data.type === 'answer' && data.explore) { answerTabInteractive = true; answerTabExplore = true; }   // the seedling's five questions (2026-09-08)
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
                } else if (data.rank_data) {
                    currentRankData = data.rank_data;
                    updateRankButtonVisibility();
                    console.log("Rank data detected:", data.rank_data);
                } else {
                    console.log("Unhandled data detected:", data);
                }
            } catch (e) {
                console.error("Error processing line:", e);
                console.log("Problematic line:", line);
                // Don't add the line to the output, keep it in the buffer
                break;
            }
            if (away) { liveState.data = currentData; liveState.rank = currentRankData; liveState.tasks = taskContents; currentData = viewData; currentRankData = viewRank; taskContents = viewTasks; if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility(); }
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
//  FEEDBACK SYSTEM
//--------------------

//--------------------
//  RANKING SYSTEM
//--------------------

function initializeRankingSystem() {
    const rankButton = document.getElementById('rankButton');
    const modal = document.getElementById('rankModal');
    const modalContent = modal?.querySelector('.modal-content');
    const submitRankButton = document.getElementById('submit-rank');
    const closeModalButton = modal?.querySelector('.close');

    if (rankButton) {
        // Modified click handler to check for replay
        rankButton.addEventListener('click', () => {
            if (currentRankData && currentRankData.replay) {
                handleReplayStorage();
            } else {
                showRankModal();
            }
        });
        rankButton.style.display = 'none';
    }

    if (submitRankButton) {
        submitRankButton.addEventListener('click', submitRank);
    }

    if (closeModalButton) {
        closeModalButton.addEventListener('click', closeRankModal);
    }

    if (modal && modalContent) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                closeRankModal();
            }
        });

        modalContent.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }

    initializeProgressRating();
}

function initializeProgressRating() {
    const segments = document.querySelectorAll('.rating-segment');
    const ratingFill = document.getElementById('ratingFill');
    const ratingValue = document.getElementById('ratingValue');
    const thresholdHint = document.getElementById('thresholdHint');
    const submitButton = document.getElementById('submit-rank');
    const valueDisplay = document.querySelector('.rating-value-display');
    
    // Store rating in a more reliable way
    let selectedRating = null;
    
    segments.forEach(segment => {
        segment.addEventListener('click', function() {
            const value = parseInt(this.dataset.value);
            selectedRating = value;
            
            // Store in window object for access from submitRank
            window.currentSelectedRating = value;
            
            // Update visual state
            segments.forEach(s => s.classList.remove('active'));
            for (let i = 0; i < value; i++) {
                segments[i].classList.add('active');
            }
            
            // Update fill width
            ratingFill.style.width = `${value * 10}%`;
            
            // Update value display
            const labels = ['Poor', 'Below Average', 'Fair', 'Good', 'Good', 
                          'Very Good', 'Very Good', 'Excellent', 'Excellent', 'Perfect'];
            ratingValue.textContent = `${value}/10 - ${labels[value - 1]}`;
            
            // Update threshold hint with clearer messaging
            if (value >= 5) {
                thresholdHint.textContent = 'Saves to favorites + your private memory for future similar tasks';
                thresholdHint.style.color = 'var(--text-secondary)';
            } else {
                thresholdHint.textContent = 'Saves to favorites only';
                thresholdHint.style.color = 'var(--text-secondary)';
            }
            
            // Color coding
            valueDisplay.classList.remove('low', 'medium', 'high');
            if (value <= 3) valueDisplay.classList.add('low');
            else if (value <= 6) valueDisplay.classList.add('medium');
            else valueDisplay.classList.add('high');
            
            // Enable submit button
            submitButton.disabled = false;
        });
        
        // Hover preview
        segment.addEventListener('mouseenter', function() {
            const value = parseInt(this.dataset.value);
            if (!selectedRating) {
                ratingFill.style.width = `${value * 10}%`;
            }
        });
        
        segment.addEventListener('mouseleave', function() {
            if (!selectedRating) {
                ratingFill.style.width = '0%';
            } else {
                ratingFill.style.width = `${selectedRating * 10}%`;
            }
        });
    });
}

function showRankModal() {
    if (currentRankData) {
        const modal = document.getElementById('rankModal');
        const submitButton = document.getElementById('submit-rank');
        const statusMessage = document.getElementById('rankStatusMessage');
        
        // Reset modal state
        submitButton.disabled = true;
        statusMessage.textContent = '';
        statusMessage.style.display = 'none';
        statusMessage.style.color = '#35c477';
        
        // Reset progress bar
        resetProgressBar();
        
        modal.style.display = 'flex';
    }
}

function closeRankModal() {
    const modal = document.getElementById('rankModal');
    modal.style.display = 'none';
}

// ── Rank-dialog distillation expander (memory.css styles) ──
function ensureDistillExpander() {
    let box = document.getElementById('distillExpander');
    if (box) return box;
    const anchor = document.getElementById('rankStatusMessage');
    if (!anchor) return null;
    box = document.createElement('div');
    box.id = 'distillExpander';
    box.className = 'memory-distill';
    box.style.display = 'none';
    box.innerHTML =
        '<div class="memory-distill-header" id="distillToggle">' +
        '<span class="memory-distill-chevron">\u25b8</span>' +
        '<span>Memory distillation</span></div>' +
        '<pre class="memory-distill-stream" id="distillStream" ' +
        'style="display:none;"></pre>';
    anchor.insertAdjacentElement('afterend', box);
    box.querySelector('#distillToggle').addEventListener('click', () => {
        const pre = document.getElementById('distillStream');
        const chev = box.querySelector('.memory-distill-chevron');
        const open = pre.style.display !== 'none';
        pre.style.display = open ? 'none' : 'block';
        chev.textContent = open ? '\u25b8' : '\u25be';
    });
    return box;
}

function appendDistillStream(text) {
    const box = ensureDistillExpander();
    if (!box) return;
    box.style.display = 'block';
    const pre = document.getElementById('distillStream');
    pre.textContent += (pre.textContent ? '\n' : '') + text;
}

function resetDistillExpander() {
    const box = document.getElementById('distillExpander');
    if (box) {
        box.style.display = 'none';
        const pre = document.getElementById('distillStream');
        if (pre) { pre.textContent = ''; pre.style.display = 'none'; }
        const chev = box.querySelector('.memory-distill-chevron');
        if (chev) chev.textContent = '\u25b8';
    }
}

function submitRank() {
    // Use the new rating system
    const userRank = window.currentSelectedRating || null;
    const submitButton = document.getElementById('submit-rank');
    const statusMessage = document.getElementById('rankStatusMessage');

    console.log('Selected rating:', userRank, typeof userRank);

    // Validate inputs before proceeding
    if (!currentRankData) {
        statusMessage.textContent = "Error: Missing rank data.";
        statusMessage.style.display = 'block';
        statusMessage.style.color = '#ff0000';
        return;
    }

    if (!userRank) {
        statusMessage.textContent = "Please select a rating.";
        statusMessage.style.display = 'block';
        statusMessage.style.color = '#ff0000';
        return;
    }

    submitButton.disabled = true;

    // NEW: Theoretical chains — skip vector DB, save to favorites only
    if (currentRankData.theoretical) {
        statusMessage.textContent = "Saving to favorites...";
        statusMessage.style.display = 'block';
        statusMessage.style.color = '#35c477';
        saveAllResponsesToFavorites(
            userRank, statusMessage, submitButton,
            isTrajectoryRank ? 'all' : currentData.chain_id
        );
        return;
    }

    // Start the submission process (analytical chains)
    statusMessage.textContent = "Saving to favorites...";
    resetDistillExpander();
    statusMessage.style.display = 'block';
    statusMessage.style.color = '#35c477';

    console.log('Current rank data:', currentRankData);

    // Step 1: Submit to vector DB
    window.authService.fetch('/submit_rank', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            rank: userRank,
            ...currentRankData
        }),
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                console.error('Server error details:', errData);
                throw new Error(errData.error || `Server responded with status: ${response.status}`);
            });
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        return new ReadableStream({
            start(controller) {
                function push() {
                    reader.read().then(({ done, value }) => {
                        if (done) {
                            controller.close();
                            
                            // After vector DB response, check for favorites storage
                            if (userRank) {
                                saveAllResponsesToFavorites(
                                    userRank, statusMessage, submitButton,
                                    isTrajectoryRank ? 'all' : currentData.chain_id
                                );
                            } else {
                                setTimeout(() => {
                                    closeRankModal();
                                    document.getElementById('rankButton').style.display = 'none';
                                    statusMessage.textContent = '';
                                    statusMessage.style.display = 'none';
                                    submitButton.disabled = false;
                                    // Reset the progress bar
                                    resetProgressBar();
                                }, 2000);
                            }
                            return;
                        }

                        const chunk = decoder.decode(value, { stream: true });
                        const messages = chunk.split('\n');

                        messages.forEach(message => {
                            if (message.trim()) {
                                try {
                                    const data = JSON.parse(message);
                                    if (data.system_message) {
                                        console.log('System message:', data.system_message);
                                        statusMessage.textContent = data.system_message;
                                    }
                                    if (data.distill_stream) {
                                        // The distiller's draft, live -
                                        // into the dialog's expandable.
                                        appendDistillStream(data.distill_stream);
                                    }
                                    if (data.memory_review &&
                                        typeof window.memoryReviewReady === 'function') {
                                        // A rank just pushed card(s) past the
                                        // promotion threshold - light the
                                        // Memory Review button.
                                        window.memoryReviewReady(data.memory_review);
                                    }
                                } catch (error) {
                                    console.error('Error parsing message:', message, error);
                                }
                            }
                        });

                        push();
                    }).catch(error => {
                        console.error('Error reading from stream:', error);
                        controller.error(error);
                    });
                }

                push();
            }
        });
    })
    .catch(error => {
        console.error('Error submitting to vector DB:', error);
        statusMessage.textContent = "Error submitting rank. Please try again.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
    });
}

async function saveAllResponsesToFavorites(userRank, statusMessage, submitButton, bookmarkTarget = null) {
    let allResponses;
    try {
        allResponses = await localforage.getItem('responses');
        if (!allResponses || !Array.isArray(allResponses)) {
            throw new Error('No valid responses found in storage');
        }
    } catch (error) {
        console.error('Error loading responses:', error);
        statusMessage.textContent = `Error: ${error.message}`;
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        isTrajectoryRank = false;
        return;
    }

    const threadId = currentData.thread_id;

    if (!threadId) {
        statusMessage.textContent = "Error: Missing thread ID.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        isTrajectoryRank = false;
        return;
    }

    // Collect ALL responses for this thread
    const threadResponses = [];
    allResponses.forEach((resp, idx) => {
        if (resp && resp.thread_id === threadId) {
            threadResponses.push({ resp, idx });
        }
    });

    if (threadResponses.length === 0) {
        statusMessage.textContent = "No analytical chains found.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        isTrajectoryRank = false;
        return;
    }

    // Sort by index for chronological order
    threadResponses.sort((a, b) => a.idx - b.idx);

    statusMessage.textContent = "Checking existing saves...";

    try {
        // Ask backend which chains are already saved
        const existingResponse = await window.authService.fetch(
            `/storage/get_existing_chains/${threadId}`
        );
        const existingData = await existingResponse.json();
        const existingChainIds = new Set(existingData.chain_ids || []);

        // Split into new chains (need compression) and existing (skip)
        // FIX 1: String() wrap to match backend's string IDs
        const newChains = threadResponses.filter(
            ({ resp }) => !existingChainIds.has(String(resp.chain_id))
        );
        const existingChains = threadResponses.filter(
            ({ resp }) => existingChainIds.has(String(resp.chain_id))
        );

        // FIX 2: Always re-send the bookmark target even if already on disk
        if (bookmarkTarget && bookmarkTarget !== 'all') {
            const alreadyIncluded = newChains.some(({ resp }) => String(resp.chain_id) === String(bookmarkTarget));
            if (!alreadyIncluded) {
                const targetIdx = existingChains.findIndex(({ resp }) => String(resp.chain_id) === String(bookmarkTarget));
                if (targetIdx > -1) {
                    newChains.push(existingChains[targetIdx]);
                    existingChains.splice(targetIdx, 1);
                }
            }
        }

        console.log(`Thread has ${threadResponses.length} chains: ${newChains.length} new, ${existingChains.length} already saved`);

        const trajectoryData = [];

        // Process NEW chains — full compression
        for (let i = 0; i < newChains.length; i++) {
            const { resp: chainData, idx } = newChains[i];

            statusMessage.textContent = `Compressing ${i + 1}/${newChains.length} new chains...`;

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
                bookmark_type: bookmarkTarget === 'all'
                    ? 'trajectory'
                    : (String(chainData.chain_id) === String(bookmarkTarget) ? 'individual' : 'trajectory'),
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
                    synthesisImage: chainData.synthesisImage || null
                }
            });
        }

        if (trajectoryData.length === 0) {
            statusMessage.textContent = "All chains already saved!";
            statusMessage.style.color = '#35c477';
        } else {
            statusMessage.textContent = `Saving ${trajectoryData.length} new chains...`;

            const response = await window.authService.fetch('/storage/trajectory_favourites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    thread_id: threadId,
                    dataset_name: currentDatasetName,
                    rank: userRank,
                    trajectory: trajectoryData
                }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `Server error: ${response.status}`);
            }

            const result = await response.json();

            if (result.error) {
                throw new Error(result.error);
            }

            statusMessage.textContent = `Saved ${result.saved_count} chains (${existingChains.length} already existed)`;
        }

        // FIX 3: Stamp bookmark_type but never downgrade 'individual' to 'trajectory'
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
        // Existing chains — mark as trajectory at minimum
        existingChains.forEach(({ resp }) => {
            const globalMatch = responses.find(r => r && String(r.chain_id) === String(resp.chain_id));
            if (globalMatch && !globalMatch.bookmark_type) {
                globalMatch.bookmark_type = 'trajectory';
            }
        });
        await localforage.setItem('responses', allResponses);
        updateRankButtonVisibility();

        statusMessage.style.color = '#35c477';

    } catch (error) {
        console.error('Error saving:', error);
        statusMessage.textContent = `Error: ${error.message}`;
        statusMessage.style.color = '#ff0000';
    } finally {
        setTimeout(() => {
            closeRankModal();
            statusMessage.textContent = '';
            statusMessage.style.display = 'none';
            submitButton.disabled = false;
            resetProgressBar();
            isTrajectoryRank = false;
            updateRankButtonVisibility();
        }, 2000);
    }
}

function updateRankButtonVisibility() {
    const rankButton = document.getElementById('rankButton');
    if (!rankButton) return;

    const currentResponse = responses[currentResponseIndex];

    // Already individually saved to vector DB
    if (!currentResponse || currentResponse.bookmark_type === 'individual') {
        rankButton.style.display = 'none';
        return;
    }

    if (currentRankData) {
        rankButton.style.display = 'block';
        if (currentRankData.replay) {
            rankButton.classList.add('replay');
        } else {
            rankButton.classList.remove('replay');
        }
    } else {
        rankButton.style.display = 'none';
    }
}

//--------------------
//  REPLAY STORAGE HANDLER
//--------------------

async function handleReplayStorage() {
    const rankButton = document.getElementById('rankButton');
    
    // Disable button to prevent double-clicks
    rankButton.style.pointerEvents = 'none';
    
    try {
        // Load responses from storage
        let responses;
        try {
            responses = await localforage.getItem('responses');
            if (!responses || !Array.isArray(responses)) {
                throw new Error('No valid responses found in storage');
            }
        } catch (error) {
            console.error('Error loading responses:', error);
            rankButton.style.pointerEvents = 'auto';
            return;
        }

        const threadId = currentData.thread_id;
        const chainId = currentData.chain_id;
        const parentChainId = currentRankData.replay; // This is the original chain being replayed

        if (!threadId || !chainId || !parentChainId) {
            console.error('Missing required IDs:', { threadId, chainId, parentChainId });
            rankButton.style.pointerEvents = 'auto';
            return;
        }
        
        // Find the matching response
        const index = responses.findIndex(response => 
            response && response.thread_id === threadId && response.chain_id === chainId
        );

        if (index === -1) {
            console.error('No matching response found. Available responses:', 
                responses.map(r => ({ thread: r.thread_id, chain: r.chain_id })));
            rankButton.style.pointerEvents = 'auto';
            return;
        }

        const chainData = responses[index];
        
        if (!chainData) {
            console.error('Chain data is null or undefined');
            rankButton.style.pointerEvents = 'auto';
            return;
        }

        // Generate plot preview
        const plotPreview = await generatePlotPreview(chainData.contentOutput || '');
        
        // Compress content
        const compressedContentOutput = await compressContent(chainData.contentOutput || '');
        const compressedStreamOutput = await compressContent(chainData.streamOutput || '');
        
        const contentCompressed = compressedContentOutput !== (chainData.contentOutput || '');
        const streamCompressed = compressedStreamOutput !== (chainData.streamOutput || '');
        
        const content = {
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
            synthesisImage: chainData.synthesisImage || null
            };

        // Prepare the payload for backend
        const replayPayload = {
            thread_id: threadId,
            chain_id: chainId,
            parent_chain_id: parentChainId,
            dataset_name: currentDatasetName,
            index: index,
            content: content
        };
        
        // Send to backend
        const response = await window.authService.fetch('/storage/replay_favourites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(replayPayload)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Server responded with status: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('Replay saved successfully:', result);

        // Provide visual feedback
        showReplaySuccess(rankButton);

    } catch (error) {
        console.error('Error during replay storage:', error);
        rankButton.style.pointerEvents = 'auto';
    }
}

//--------------------
//  REPLAY SUCCESS INDICATOR
//--------------------

function showReplaySuccess(rankButton) {
    // Store original content
    const originalHTML = rankButton.innerHTML;
    
    // Replace with checkmark SVG
    rankButton.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
    `;
    
    // Remove replay class and add success class
    rankButton.classList.remove('replay');
    rankButton.classList.add('replay-success');
    
    // After 3 seconds, hide the button and reset
    setTimeout(() => {
        rankButton.style.display = 'none';
        rankButton.classList.remove('replay-success');
        rankButton.innerHTML = originalHTML;
        rankButton.style.pointerEvents = 'auto';
        
        // Re-add replay class if needed for next time
        if (currentRankData && currentRankData.replay) {
            rankButton.classList.add('replay');
        }
    }, 3000);
}

function resetProgressBar() {
    const segments = document.querySelectorAll('.rating-segment');
    const ratingFill = document.getElementById('ratingFill');
    const ratingValue = document.getElementById('ratingValue');
    const thresholdHint = document.getElementById('thresholdHint');
    
    segments.forEach(s => s.classList.remove('active'));
    if (ratingFill) ratingFill.style.width = '0%';
    if (ratingValue) ratingValue.textContent = 'Click to rate';
    if (thresholdHint) thresholdHint.textContent = 'All solutions are saved • 5+ adds to AI memory';
    
    window.currentSelectedRating = null;
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

