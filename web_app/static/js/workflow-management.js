//--------------------
//  WORKFLOW MANAGEMENT MODULE
//--------------------

function initializeWorkflowManagement() {
    console.log('Initializing workflow management...');
    
    initializeResponseManagement();
    initializeWorkflowMap();
    initializeThreadsManagement();
    handlePageLoad();
    
    console.log('Workflow management initialized');
}

//--------------------
//  RESPONSE MANAGEMENT
//--------------------

function initializeResponseManagement() {
    // The deprecated unload event is blocked by Chrome's Permissions
    // Policy ("[Violation] unload is not allowed in this document")
    // and breaks bfcache. pagehide is the modern replacement and fires
    // in every case the old one did; the beforeunload duplicate was
    // redundant with it and is folded in.
    window.addEventListener('pagehide', () => {
        localforage.removeItem('responses');
    });
}

// THE WORKSPACE START (v63, 2026-09-10). A load that is not the reload New workflow performs - a
// refresh, a login, a new tab - starts a new workspace HERE, after sign-in and before the modules
// initialise, and this page IS that workspace: no second load. Until v62 the page initialised
// completely, discovered in handlePageLoad that it should start a workspace, called the server and
// reloaded itself into ?new=true - two complete start-ups around one server reset. The rail's New
// workflow button (handleNewConversation) keeps its reload: a deliberate action on a live page.
// Every step logs to the console under [workspace].
let newWorkspaceStarted = false;             // this load started the workspace (handlePageLoad reads it)

function wsLog() { console.log.apply(console, ['[workspace]'].concat(Array.prototype.slice.call(arguments))); }

function isReloadIntoNewWorkspace() {
    return new URLSearchParams(window.location.search).get('new') === 'true';
}

function navigationType() {
    try {
        const e = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
        if (e && e.type) return e.type;                                   // navigate | reload | back_forward | prerender
    } catch (err) { /* fall through */ }
    return (performance.navigation && performance.navigation.type === 1) ? 'reload' : 'navigate';
}

async function clearSavedResponses() {
    // the browser's own snapshots of the previous workspace's chains; verified gone, never assumed
    if (typeof localforage === 'undefined') { wsLog('localforage unavailable: no saved responses to clear'); return; }
    try {
        await localforage.removeItem('responses');
        let left = await localforage.getItem('responses');
        if (left) {
            wsLog('saved responses still present after removeItem - clearing the whole store');
            await localforage.clear();
            left = await localforage.getItem('responses');
        }
        wsLog('saved responses cleared; verified empty:', left === null || left === undefined);
    } catch (e) {
        console.warn('[workspace] could not clear the saved responses:', e);
    }
}

async function startWorkspaceIfFreshLoad() {
    const t0 = performance.now();
    if (isReloadIntoNewWorkspace()) {
        wsLog('reload into a new workspace (?new=true): the server reset ran on the previous page; nothing to start');
        return;
    }
    newWorkspaceStarted = true;
    wsLog('fresh load (' + navigationType() + '): starting a new workspace before the modules initialise');
    await clearSavedResponses();
    if (window.userSessionReady) {
        try { await window.userSessionReady; } catch (e) { /* the initialise call reports its own failure */ }
        wsLog('user session initialised (' + Math.round(performance.now() - t0) + ' ms)');
    }
    if (window.WorkspaceGate) WorkspaceGate.stage('executor');
    try {
        const t1 = performance.now();
        const response = await window.authService.fetch('/new_conversation', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        wsLog('server reset done in ' + Math.round(performance.now() - t1) + ' ms:', data && data.message);
    } catch (e) {
        console.error('[workspace] /new_conversation failed - the page continues without an executor:', e);
        if (window.WorkspaceGate) WorkspaceGate.end();
    }
    wsLog('workspace start finished in ' + Math.round(performance.now() - t0) + ' ms');
}

function handlePageLoad() {
    const urlParams = new URLSearchParams(window.location.search);
    const streamOutputDiv = document.getElementById('streamOutput');

    if (newWorkspaceStarted || urlParams.get('new') === 'true') {
        // this page is the new workspace: the pane stays empty (the workspace gate says what is happening)
        streamOutputDiv.innerHTML = '';
        if (urlParams.get('new') === 'true') {
            // Remove the 'new' parameter from the URL without reloading the page
            window.history.replaceState({}, document.title, window.location.pathname);
        }
        wsLog('this page is the new workspace (' + (newWorkspaceStarted ? 'started on this load' : 'reloaded into it') + ')');
    } else {
        // a page that skipped the boot step (the render tools call the initialisation directly): the old restore
        loadSavedResponses().catch(error => {
            console.error('Error loading saved responses:', error);
        });
    }
}

// ---- the running chain while you browse (2026-09-09) ----
// A chain is a navigable entry from the moment it starts. While it runs and you look at another
// chain, its live DOM (stream, tabs, tab content) is parked in detached holders and the incoming
// events keep rendering into them; coming back moves the nodes into view again. Nothing is
// serialised until the chain ends, so plots and listeners survive the trip.
const liveState = { running: false, away: false, index: null, parent: null, data: null, rank: null, tasks: null, holders: null, forceView: false };

function liveTargets() {
    if (liveState.away && liveState.holders && !liveState.forceView) return liveState.holders;
    return { stream: document.getElementById('streamOutput'), tabs: document.getElementById('tabContainer'), content: document.getElementById('contentOutput') };
}

// A click on a tab comes from the visible strip, so it acts on the view even while a run is parked off-screen
// (2026-09-10: with a chain running in the background, tab clicks on the chain being viewed looked for the tab in
// the parked strip and did nothing - "Tab or content for type ... not found").
function activateTabInView(type) {
    liveState.forceView = true;
    try { if (typeof activateTab === 'function') activateTab(type); } finally { liveState.forceView = false; }
}

function beginLiveChain() {
    liveState.running = true; liveState.away = false; liveState.holders = null;
    liveState.parent = lastActiveChainId;
    responses.push({ status: 'running', chain_id: currentData.chain_id || null, thread_id: currentData.thread_id || null, parentChainId: lastActiveChainId,
                     queryText: currentData.queryText || 'No query', tabContent: '', contentOutput: '', streamOutput: '', taskContents: {}, technicalAnswer: null });
    liveState.index = responses.length - 1;
    currentResponseIndex = liveState.index;
    if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
}

function _moveChildren(from, to) { while (from.firstChild) to.appendChild(from.firstChild); }

function liveGoAway() {
    if (!liveState.running || liveState.away) return;
    const h = { stream: document.createElement('div'), tabs: document.createElement('div'), content: document.createElement('div') };
    _moveChildren(document.getElementById('streamOutput'), h.stream);
    _moveChildren(document.getElementById('tabContainer'), h.tabs);
    _moveChildren(document.getElementById('contentOutput'), h.content);
    liveState.holders = h; liveState.data = currentData; liveState.rank = currentRankData; liveState.tasks = taskContents;
    currentData = {}; currentRankData = null; taskContents = {};
    liveState.away = true;
}

function liveComeBack() {
    if (!liveState.running || !liveState.away) return;
    const so = document.getElementById('streamOutput'), tc = document.getElementById('tabContainer'), co = document.getElementById('contentOutput');
    so.innerHTML = ''; tc.innerHTML = ''; co.innerHTML = '';
    _moveChildren(liveState.holders.stream, so); _moveChildren(liveState.holders.tabs, tc); _moveChildren(liveState.holders.content, co);
    currentData = liveState.data; currentRankData = liveState.rank; taskContents = liveState.tasks || {};
    liveState.away = false; liveState.holders = null;
    currentResponseIndex = liveState.index; lastActiveChainId = currentData.chain_id || liveState.parent;
    if (typeof updateRankButtonVisibility === 'function') updateRankButtonVisibility();
    if (window.Plotly) co.querySelectorAll('.js-plotly-plot').forEach(el => { try { Plotly.Plots.resize(el); } catch (e) {} });
    so.scrollTop = so.scrollHeight;
}

function endLiveChain(saved) {
    // the placeholder becomes the saved entry; the view stays where the person is
    if (liveState.running && liveState.index !== null && responses[liveState.index] && responses[liveState.index].status === 'running') {
        responses[liveState.index] = saved;
        if (!liveState.away) currentResponseIndex = liveState.index;
    } else {
        responses.push(saved);
        if (!liveState.away) currentResponseIndex = responses.length - 1;
    }
    liveState.running = false; liveState.holders = null; liveState.data = null; liveState.rank = null; liveState.tasks = null;
    if (liveState.away) { liveState.away = false; }
}

async function saveCurrentResponse(explicitParentChainId = null) {
    const t = liveTargets();
    const tabContainer = t.tabs, contentOutput = t.content, streamOutput = t.stream;
    // the live chain's own data (the person may be looking at another chain right now)
    const data = (liveState.running && liveState.away) ? liveState.data : currentData;
    const rank = (liveState.running && liveState.away) ? liveState.rank : currentRankData;
    const tasks = (liveState.running && liveState.away) ? liveState.tasks : taskContents;
    
    // Use explicit parent if provided, otherwise the parent captured when the chain started
    const parentToUse = explicitParentChainId !== null ? explicitParentChainId : (liveState.running ? liveState.parent : lastActiveChainId);
    
    const newResponse = {
        tabContent: tabContainer.innerHTML,
        contentOutput: contentOutput.innerHTML,
        streamOutput: streamOutput.innerHTML,
        taskContents: tasks,
        chain_id: data.chain_id || null,
        thread_id: data.thread_id || null,
        parentChainId: parentToUse,
        queryText: data.queryText || 'No query',
        technicalAnswer: data.technicalAnswer || null,
        simplifiedAnswer: data.simplifiedAnswer || null,
        summaryViewMode: data.summaryViewMode || 'technical',
        synthesisImage: data.synthesisImage || null,
        rankData: rank || null
    };
    
    // Update lastActiveChainId for next interaction (only if no explicit parent was given, and only
    // if the person is still looking at this chain - a follow-up branches from the chain on screen)
    if (explicitParentChainId === null && !(liveState.running && liveState.away)) {
        lastActiveChainId = data.chain_id || null;
    }
    
    endLiveChain(newResponse);

    // Enable suggest questions after first response
    const suggestQuestions = document.getElementById('suggestQuestions');
    if (suggestQuestions) {
        suggestQuestions.classList.remove('disabled');
    }
    
    try {
        await localforage.setItem('responses', responses);
        console.log('Responses saved successfully with chain_id:', currentData.chain_id);
    } catch (error) {
        console.error('Error saving responses to localStorage:', error);
    }
    
    if (typeof updateNavigationButtons === 'function') {
        updateNavigationButtons();
    }
}

async function loadSavedResponses() {
    const savedResponses = await localforage.getItem('responses');

    if (savedResponses) {
        try {
            responses = savedResponses;

            if (Array.isArray(responses) && responses.length > 0) {
                currentResponseIndex = responses.length - 1;

                // Load the content
                const response = responses[currentResponseIndex];
                loadResponseContent(response);
            } else {
                console.warn('No valid responses found in localStorage');
            }
        } catch (error) {
            console.error('Error parsing saved responses:', error);
        }
    } else {
        console.warn('No saved responses found in localStorage');
        const streamOutput = document.getElementById('streamOutput');
        if (streamOutput) {
            streamOutput.innerHTML = '<div>Ready for your query.</div>';
        }
    }

    if (typeof updateNavigationButtons === 'function') {
        updateNavigationButtons();
    }
}

function loadResponseContent(response) {
    if (!response) {
        console.log('No response to load');
        return;
    }
    if (liveState.running) {
        const idx = responses.indexOf(response);
        if (idx === liveState.index) {                       // back to the running chain: its live DOM returns
            liveComeBack();
            if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
            return;
        }
        liveGoAway();                                        // leaving it: park the live DOM, keep rendering into it
    }

    console.log('Loading response content:', response);

    // Restore DOM content
    document.getElementById('tabContainer').innerHTML = response.tabContent;
    document.getElementById('contentOutput').innerHTML = response.contentOutput;
    document.getElementById('streamOutput').innerHTML = response.streamOutput;
    taskContents = response.taskContents || {};

    // Restore state
    currentData.chain_id = response.chain_id || null;
    currentData.thread_id = response.thread_id || null;
    lastActiveChainId = currentData.chain_id;
    currentData.technicalAnswer = response.technicalAnswer || null;
    currentData.simplifiedAnswer = response.simplifiedAnswer || null;
    currentData.summaryViewMode = response.summaryViewMode || 'technical';
    currentData.synthesisImage = response.synthesisImage || null;
    currentRankData = response.rankData || null;
    console.log('Loaded chain_id:', currentData.chain_id);

    // Reattach all event listeners lost during innerHTML restore
    reattachRestoredListeners();
}


function reattachRestoredListeners() {
    // this rebuilds the VIEWED chain's DOM; while a run is parked off-screen, the renderer must target the view here
    liveState.forceView = true;
    try { _reattachRestoredListeners(); } finally { liveState.forceView = false; }
}

function _reattachRestoredListeners() {

    // Tab click handlers
    const tabs = document.getElementsByClassName('tab');
    for (let tab of tabs) {
        tab.onclick = () => activateTabInView(tab.id.split('-')[1]);
    }

    // Answer tab — rebuild content and restore simplified button state
    const answerTab = document.getElementById('content-answer');
    if (answerTab) {
        const markdownContent = answerTab.querySelector('.markdown-content');
        if (markdownContent && typeof updateTabContent === 'function') {
            updateTabContent('answer', markdownContent.innerHTML);
        }

        function updateSimplifiedButton() {
            const button = document.querySelector('.simplified-summary-btn');
            if (button) {
                if (currentData.simplifiedAnswer) {
                    button.style.display = '';
                    button.disabled = false;
                    button.classList.remove('loading');
                    if (typeof updateSimplifiedButtonLabel === 'function') {
                        updateSimplifiedButtonLabel();
                    }
                } else {
                    button.style.display = 'none';
                }
                return true;
            }
            return false;
        }

        setTimeout(() => {
            if (!updateSimplifiedButton()) {
                setTimeout(() => {
                    if (!updateSimplifiedButton()) {
                        setTimeout(updateSimplifiedButton, 150);
                    }
                }, 150);
            }
        }, 200);
    }

    // Synthesis infographic — must come after answer tab rebuild
    if (currentData.synthesisImage && typeof appendSynthesisImage === 'function') {
        const existingInfographic = document.querySelector('.synthesis-infographic-container');
        if (existingInfographic) existingInfographic.remove();

        appendSynthesisImage(
            currentData.synthesisImage.data,
            currentData.synthesisImage.mime_type || 'image/png'
        );
    }

    // Code tab
    const codeTab = document.getElementById('content-code');
    if (codeTab && typeof updateTabContent === 'function') {
        updateTabContent('code', codeTab.querySelector('code').textContent);
    }

    // Dataframe tab
    const dataframeTab = document.getElementById('content-dataframe');
    if (dataframeTab) {
        const tableElement = dataframeTab.querySelector('table.dataframe');
        if (tableElement && typeof updateTabContent === 'function') {
            updateTabContent('dataframe', tableElement.outerHTML);
        }
    }

    // Plan & model diagram tabs: strip any stale zoom buttons left from the
    // retired graph viewer (graphControls.js - see memory_pack_design.md).
    ['plan', 'model'].forEach(type => {
        const tab = document.getElementById(`content-${type}`);
        if (!tab) return;

        const container = tab.querySelector('.diagram-container');
        if (container) {
            const staleControls = container.querySelector('.graph-controls');
            if (staleControls) staleControls.remove();
        }

        if (typeof hljs !== 'undefined') {
            tab.querySelectorAll('pre code').forEach(block => {
                if (!block.classList.contains('hljs')) {
                    hljs.highlightElement(block);
                }
            });
        }
    });

    // Plot tab — re-init Plotly instances and reattach query/expand listeners
    const plotTab = document.getElementById('content-plot');
    if (plotTab) {
        if (typeof attachPlotQueryListeners === 'function') {
            attachPlotQueryListeners(plotTab);
        }

        const plotlyDivs = plotTab.querySelectorAll('.plotly-plot div');
        plotlyDivs.forEach(div => {
            const scripts = div.getElementsByTagName('script');
            if (scripts.length > 0) {
                Array.from(scripts).forEach(script => {
                    if (!script.src) eval(script.textContent);
                });
                const plotDiv = div.querySelector('.js-plotly-plot');
                if (plotDiv) {
                    Plotly.relayout(plotDiv, { autosize: true, width: undefined, dragmode: 'pan' });
                }
            }
            else if (div.dataset.plotlyJson) {
                const newDiv = document.createElement('div');
                div.parentNode.replaceChild(newDiv, div);

                setTimeout(() => {
                    try {
                        const plotData = JSON.parse(div.dataset.plotlyJson);
                        newDiv.dataset.plotlyJson = div.dataset.plotlyJson;

                        Plotly.newPlot(newDiv, plotData.data,
                            Object.assign({}, plotData.layout, {
                                autosize: true,
                                width: undefined,
                                dragmode: 'pan'
                            }), {
                            responsive: true,
                            useResizeHandler: true,
                            displayModeBar: true,
                            scrollZoom: true
                        }).catch(error => {
                            console.error('Plot rendering failed:', error);
                            newDiv.innerHTML = `
                                <div class="plot-error">
                                    Failed to render plot. Please try refreshing the page.
                                    <br><small>${error.message}</small>
                                </div>
                            `;
                        });
                    } catch (error) {
                        console.error('Error processing plot data:', error);
                        newDiv.innerHTML = `
                            <div class="plot-error">
                                Failed to process plot data. Please try refreshing the page.
                                <br><small>${error.message}</small>
                            </div>
                        `;
                    }
                }, 100);
            }
        });
    }

    // Stream output — copy buttons, syntax highlighting, agent instructions
    const streamOutput = document.getElementById('streamOutput');
    if (streamOutput) {

        streamOutput.querySelectorAll('.copy-button').forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);

            newButton.addEventListener('click', function() {
                const codeElement = this.closest('.code-header').nextElementSibling.querySelector('code');
                if (codeElement) {
                    navigator.clipboard.writeText(codeElement.textContent)
                        .then(() => {
                            const copyIcon = this.querySelector('.copy-icon');
                            const checkIcon = this.querySelector('.check-icon');
                            copyIcon.style.display = 'none';
                            checkIcon.style.display = 'block';
                            setTimeout(() => {
                                copyIcon.style.display = 'block';
                                checkIcon.style.display = 'none';
                            }, 2000);
                        })
                        .catch(err => console.error('Failed to copy:', err));
                }
            });
        });

        if (typeof hljs !== 'undefined') {
            streamOutput.querySelectorAll('pre code').forEach(block => {
                try {
                    if (!block.classList.contains('hljs')) {
                        const originalContent = block.textContent;
                        if (originalContent) {
                            block.textContent = '';
                            block.textContent = originalContent;
                            hljs.highlightElement(block);
                        }
                    }
                } catch (error) {
                    console.warn('Highlighting failed for block:', error);
                }
            });
        }

        streamOutput.querySelectorAll('.agent-instructions-btn').forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);

            newButton.addEventListener('click', function(e) {
                e.stopPropagation();
                const agent = this.dataset.agent;
                const chain = this.dataset.chain;
                if (typeof showAgentInstructions === 'function') {
                    showAgentInstructions(agent, chain, this.dataset.call);      // this call's prompt, not the seat's first (2026-09-10)
                }
            });
        });

        // Synthesis image click-to-fullscreen (complements expand button from appendSynthesisImage)
        const synthesisImg = document.querySelector('.synthesis-infographic-image');
        if (synthesisImg && currentData.synthesisImage) {
            const newImg = synthesisImg.cloneNode(true);
            synthesisImg.parentNode.replaceChild(newImg, synthesisImg);

            newImg.addEventListener('click', () => {
                if (typeof openSynthesisFullscreen === 'function') {
                    openSynthesisFullscreen(
                        currentData.synthesisImage.data,
                        currentData.synthesisImage.mime_type || 'image/png'
                    );
                }
            });
        }
    }
}

function navigateResponses(direction) {
    const prevIndex = currentResponseIndex;
    currentResponseIndex += direction;
    if (currentResponseIndex < 0) currentResponseIndex = 0;
    if (currentResponseIndex >= responses.length) currentResponseIndex = responses.length - 1;

    // Update lastActiveChainId when navigating
    if (responses[currentResponseIndex]) {
        lastActiveChainId = responses[currentResponseIndex].chain_id || null;
    }

    loadResponseContent(responses[currentResponseIndex]);
    if (typeof updateNavigationButtons === 'function') {
        updateNavigationButtons();
    }
}

//--------------------
//  WORKFLOW MAP
//--------------------

function initializeWorkflowMap() {
    const workflowMapModal = document.getElementById('workflowMapModal');
    const closeBtn = workflowMapModal?.querySelector('.workflow-close');
    const synthesisButton = document.getElementById('synthesisButton');
    const trajectoryButton = document.getElementById('trajectoryButton');
    
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            workflowMapModal.style.display = 'none';
        });
    }
    
    // Synthesis button handler
    if (synthesisButton) {
        synthesisButton.addEventListener('click', requestSynthesis);
    }
    
    // Trajectory button handler
    if (trajectoryButton) {
        trajectoryButton.addEventListener('click', requestTrajectoryRank);
    }
    
    // Close the modal if user clicks outside of it
    if (workflowMapModal) {
        workflowMapModal.addEventListener('click', function(event) {
            if (event.target === workflowMapModal) {
                workflowMapModal.style.display = 'none';
            }
        });
    }
}

function showWorkflowMap() {
    var modal = document.getElementById('workflowMapModal');
    var container = document.getElementById('workflowMapContainer');
    document.getElementById('nodeTaskContent').innerHTML = 'Hover over a chain to see its question and where it sits';
    document.getElementById('nodePlotPreview').innerHTML = '';
    modal.style.display = 'flex';
    updateSynthesisButtonState();
    updateTrajectoryButtonState();
    WorkflowGraph.render(container, responses, currentResponseIndex);
    // the drawer's subtitle (2026-09-08): how many chains, how many branch points
    var sub = document.getElementById('mapDrawerSub');
    if (sub) {
        var children = {};
        (responses || []).forEach(function (r) { if (r.parentChainId) children[r.parentChainId] = (children[r.parentChainId] || 0) + 1; });
        var branches = Object.keys(children).filter(function (k) { return children[k] > 1; }).length;
        var n = (responses || []).length;
        sub.textContent = n ? (n + ' chain' + (n === 1 ? '' : 's') + (branches ? ' · ' + branches + ' branch' + (branches === 1 ? '' : 'es') : '') + ' · click one to open it') : 'no chains yet';
    }
}

function updateSynthesisButtonState() {
    const synthesisButton = document.getElementById('synthesisButton');
    if (!synthesisButton) return;
    
    // Disable if:
    // - Auto-explore is currently running
    // - Less than 2 responses (no exploration to synthesize)
    const shouldDisable = autoExploreRunning || responses.length < 2;
    
    synthesisButton.disabled = shouldDisable;
    
    if (autoExploreRunning) {
        synthesisButton.title = 'Wait for exploration to complete';
    } else if (responses.length < 2) {
        synthesisButton.title = 'Need at least one completed analysis to synthesize';
    } else {
        synthesisButton.title = 'Generate a comprehensive report of all findings';
    }
}

function requestSynthesis() {
    const workflowMapModal = document.getElementById('workflowMapModal');
    
    // Close the modal
    workflowMapModal.style.display = 'none';
    
    // Set synthesis tab mode
    answerTabSynthesis = true;
    
    // Trigger synthesis via handleQuerySubmit
    if (typeof handleQuerySubmit === 'function') {
        handleQuerySubmit({ synthesis: true });
    }
}

function updateTrajectoryButtonState() {
    const trajectoryButton = document.getElementById('trajectoryButton');
    if (!trajectoryButton) return;
    
    const shouldDisable = autoExploreRunning || responses.length < 2;
    
    trajectoryButton.disabled = shouldDisable;
    
    if (autoExploreRunning) {
        trajectoryButton.title = 'Wait for exploration to complete';
    } else if (responses.length < 2) {
        trajectoryButton.title = 'Need at least one completed analysis to save';
    } else {
        trajectoryButton.title = 'Save the entire exploration trajectory to favorites';
    }
}

function requestTrajectoryRank() {
    const workflowMapModal = document.getElementById('workflowMapModal');
    
    // Close the modal
    workflowMapModal.style.display = 'none';
    
    // Set trajectory rank mode
    isTrajectoryRank = true;
    
    // Show the rank modal
    if (typeof showRankModal === 'function') {
        showRankModal();
    }
}

//--------------------
//  CONTENT EXTRACTORS
//--------------------

function extractPlotDataFromResponse(response) {
    try {
        // Create a temporary div to parse HTML content
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = response.contentOutput || '';
        
        // Look for plot content
        const plotTab = tempDiv.querySelector('#content-plot');
        if (!plotTab) return null;
        
        // Try to find Plotly JSON data in the plot tab
        const plotlyDiv = plotTab.querySelector('.plotly-plot div[data-plotly-json]');
        if (plotlyDiv && plotlyDiv.dataset.plotlyJson) {
            return plotlyDiv.dataset.plotlyJson;
        }
        
        // If no JSON data found, check for plot images
        const plotImage = plotTab.querySelector('.plot-image');
        if (plotImage && plotImage.src) {
            // For image-based plots, return the src
            // Note: This would need additional handling in renderPlotlyPreview
            return plotImage.src;
        }
        
        return null;
    } catch (error) {
        console.error('Error extracting plot data:', error);
        return null;
    }
}

function extractTaskFromResponse(response) {
    // The Query tab is retired (2026-09-05): a chain's label is the question as typed.
    const q = (response && response.queryText && response.queryText !== 'No query') ? String(response.queryText).trim() : null;
    return { task: null, originalQuestion: q };
}

function renderPlotlyPreview(plotlyData) {
    // Create container
    const previewContainer = document.createElement('div');
    previewContainer.className = 'plotly-preview-container';
    
    try {
        // Check if Plotly is available
        if (typeof Plotly === 'undefined') {
            previewContainer.innerHTML = '<div class="preview-error">Plotly not available</div>';
            return previewContainer;
        }
        
        // Parse the data
        const plotData = JSON.parse(plotlyData);
        
        // Create a temporary div for generating the image
        const tempPlot = document.createElement('div');
        tempPlot.style.width = '800px';  // Larger size for quality (original size)
        tempPlot.style.height = '500px';
        tempPlot.style.position = 'absolute';
        tempPlot.style.left = '-9999px';  // Off-screen
        tempPlot.style.visibility = 'hidden';
        document.body.appendChild(tempPlot);
        
        // Create the plot at higher resolution (original settings)
        Plotly.newPlot(
            tempPlot, 
            plotData.data || [], 
            Object.assign({}, plotData.layout || {}, {
                width: 800,
                height: 500,
                margin: { t: 30, r: 30, b: 50, l: 60 }
            }),
            { displayModeBar: false }
        ).then(() => {
            // Convert to image
            return Plotly.toImage(tempPlot, {format: 'png', width: 800, height: 500});
        }).then(imgUrl => {
            // Clean up the temporary plot
            try {
                Plotly.purge(tempPlot);
            } catch (e) {
                console.warn('Error purging temp plot:', e);
            }
            if (document.body.contains(tempPlot)) {
                document.body.removeChild(tempPlot);
            }
            
            // Create image element with the URL (original styling)
            const img = document.createElement('img');
            img.src = imgUrl;
            img.style.width = '100%';
            img.style.height = 'auto';
            img.style.maxHeight = '100%';
            img.alt = 'Plot preview';
            
            // Add to container
            previewContainer.appendChild(img);
        }).catch(err => {
            console.error('Error generating plot image:', err);
            previewContainer.innerHTML = '<div class="preview-error">Error creating plot preview</div>';
            
            // Clean up if needed
            try {
                if (document.body.contains(tempPlot)) {
                    Plotly.purge(tempPlot);
                    document.body.removeChild(tempPlot);
                }
            } catch (e) {
                console.warn('Error cleaning up temp plot:', e);
            }
        });
    } catch (e) {
        console.error('Error with plot data:', e);
        previewContainer.innerHTML = '<div class="preview-error">Error parsing plot data</div>';
    }
    
    return previewContainer;
}

//--------------------
//  THREADS MANAGEMENT
//--------------------

function initializeThreadsManagement() {
    // Initialize threads UI when menu is opened - this is handled by ui-controls
    // but we set up the functions here that will be called
    console.log('Threads management functions initialized');
}

function initializeThreadsUI() {
    const menuPopup = document.querySelector('.menu-popup');
    
    if (!menuPopup) {
        console.error('Menu popup element not found');
        return;
    }
    
    if (document.querySelector('.threads-header')) {
        console.log('Threads UI already initialized, loading threads...');
        loadThreadsList();
        return;
    }
    
    const uiHTML = `
        <hr class="menu-divider">
        <h3 class="threads-header">Saved Workflows:</h3>
        <div id="threads-list" class="threads-list">
            <div class="thread-loading">Loading workflows...</div>
        </div>
    `;
    
    menuPopup.insertAdjacentHTML('beforeend', uiHTML);

    const threadsList = document.getElementById('threads-list');

    loadThreadsList();

    if (window.LabelsManager && typeof window.LabelsManager.initializeResizableDivider === 'function') {
        window.LabelsManager.initializeResizableDivider();
    }
    
    console.log('Threads UI initialized');
}

// In workflow-management.js, update loadThreadsList:
function loadThreadsList() {
    const threadsList = document.getElementById('threads-list');
    
    if (!threadsList) {
        console.error('Threads list element not found - UI may not be initialized yet');
        if (typeof initializeThreadsUI === 'function') {
            initializeThreadsUI();
            return Promise.resolve();
        }
        return Promise.resolve();
    }
    
    // Show loading indicator
    threadsList.innerHTML = '<div class="thread-loading">Loading threads...</div>';
    
    // Return the promise so we can await it
    return window.authService.fetch(`/get_threads?t=${Date.now()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (!data.threads || data.threads.length === 0) {
                threadsList.innerHTML = '<div class="no-threads">No saved threads found</div>';
                return;
            }
            
            // Render the threads with fresh label data
            renderThreadsList(data.threads);
        })
        .catch(error => {
            console.error('Error loading threads:', error);
            threadsList.innerHTML = `<div class="no-threads">Error loading threads: ${error.message}</div>`;
        });
}

function renderThreadsList(threads) {
    const threadsList = document.getElementById('threads-list');
    
    if (!threadsList) {
        console.error('Threads list element not found');
        return;
    }
    
    // Clear the threads list
    threadsList.innerHTML = '';
    
    // Add each thread to the list
    threads.forEach(thread => {
        // Skip threads with no chains
        if (!thread.chains || thread.chains.length === 0) {
            return;
        }
        
        // Get the most recent chain
        const recentChain = thread.chains[0];
        
        // Create thread container
        const threadContainer = document.createElement('div');
        threadContainer.className = 'thread-container';
        threadContainer.setAttribute('data-thread-id', thread.thread_id);
        
        // Create thread item for the most recent chain
        const threadItem = createThreadItem(recentChain, true);
        
        // Add collapse/expand button
        if (thread.chains.length > 1) {
            const toggleButton = document.createElement('button');
            toggleButton.className = 'thread-toggle';
            toggleButton.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>';
            toggleButton.title = 'Show more chains';
            
            // Add click handler
            toggleButton.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent thread from loading when clicking button
                toggleChains(threadContainer);
            });
            
            threadItem.appendChild(toggleButton);
            
            // Create hidden container for older chains
            const chainsContainer = document.createElement('div');
            chainsContainer.className = 'chains-container hidden';
            
            // Add each chain (except the first one which is already shown)
            thread.chains.slice(1).forEach(chain => {
                const chainItem = createThreadItem(chain, false);
                chainsContainer.appendChild(chainItem);
            });
            
            threadContainer.appendChild(threadItem);
            threadContainer.appendChild(chainsContainer);
        } else {
            // Just add the single chain
            threadContainer.appendChild(threadItem);
        }
        
        threadsList.appendChild(threadContainer);
    });
    
    // Check for text overflow after adding all threads
    setTimeout(checkTextOverflow, 0);
}

function createThreadItem(chain, isLatest) {
    // Format the timestamp
    let formattedTimestamp = 'No date';
    if (chain.timestamp) {
        try {
            const date = new Date(chain.timestamp);
            formattedTimestamp = date.toLocaleString(undefined, {
                year: 'numeric', 
                month: 'short', 
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            console.error('Error formatting timestamp:', e);
        }
    }

    //////////////////////////////////////
    
    const threadItem = document.createElement('div');
    threadItem.className = isLatest ? 'thread-item' : 'thread-item chain-item';
    threadItem.setAttribute('data-thread-id', chain.thread_id);
    threadItem.setAttribute('data-chain-id', chain.chain_id);
    threadItem.setAttribute('data-dataset-name', chain.dataset_name);
    threadItem.setAttribute('data-label-id', chain.label_id || '');
    threadItem.setAttribute('data-label-name', chain.label_name || '');
    
    // Add label icon (top right)
    const labelIcon = document.createElement('button');
    labelIcon.className = `thread-label-icon ${chain.label_id ? 'labeled' : ''}`;
    labelIcon.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
            <line x1="7" y1="7" x2="7.01" y2="7"/>
        </svg>
    `;
    labelIcon.title = chain.label_name || 'Add label';
    
    // Add click handler for label icon
    labelIcon.addEventListener('click', async function(e) {
        e.stopPropagation();
        await showLabelSelector(chain.chain_id, chain.label_id, labelIcon, threadItem);
    });
    
    threadItem.appendChild(labelIcon);
    
    // Add timestamp
    const timestamp = document.createElement('span');
    timestamp.className = 'thread-timestamp';
    timestamp.textContent = formattedTimestamp;
    threadItem.appendChild(timestamp);
    
    // Add Thread ID only for the latest/main thread item
    if (isLatest) {
        const threadId = document.createElement('span');
        threadId.className = 'thread-id';
        threadId.textContent = `Thread: ${chain.thread_id}`;
        threadItem.appendChild(threadId);
        
        // Add label display if exists
        if (chain.label_name) {
            const labelDisplay = document.createElement('span');
            labelDisplay.className = 'thread-label-display';
            labelDisplay.textContent = `Label: ${chain.label_name}`;
            threadItem.appendChild(labelDisplay);
        }

        const datasetName = document.createElement('span');
        datasetName.className = 'thread-dataset-name';
        datasetName.textContent = `Dataset: ${chain.dataset_name || 'None'}`;
        threadItem.appendChild(datasetName);
    } else {
        // For child chains, also show label if it exists
        if (chain.label_name) {
            const labelDisplay = document.createElement('span');
            labelDisplay.className = 'thread-label-display';
            labelDisplay.textContent = `Label: ${chain.label_name}`;
            threadItem.appendChild(labelDisplay);
        }
    }

    //////////////////////////////////////
    
    // Add task text with limited height
    const taskText = document.createElement('div');
    taskText.className = 'thread-task';
    taskText.textContent = chain.task || chain.queryText || `Chain ${chain.chain_id}`;
    threadItem.appendChild(taskText);
    
    // Add delete button
    const deleteButton = document.createElement('button');
    deleteButton.className = 'thread-delete-btn';
    deleteButton.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path></svg>';
    deleteButton.title = 'Delete from favorites';
    
    // Add click handler for delete button
    deleteButton.addEventListener('click', function(e) {
        e.stopPropagation();
        
        const threadId = chain.thread_id;
        const chainId = chain.chain_id;
        
        if (isLatest) {
            // Parent card — delete entire thread
            if (confirm('Delete this entire workflow and all its chains from favorites?')) {
                deleteThread(threadId, element);
            }
        } else {
            // Child chain — delete just this chain
            if (confirm('Delete this chain from favorites?')) {
                deleteChain(threadId, chainId, threadItem);
            }
        }
    });
    
    threadItem.appendChild(deleteButton);
    
    // Add click event listener for the thread item
    threadItem.addEventListener('click', () => {
        // Load the thread content
        loadThreadContent(chain.thread_id, chain.chain_id);

        // Update lastActiveChainId to current chain_id
        lastActiveChainId = chain.chain_id;
        
        // Close the menu and overlay when chain is clicked
        if (typeof toggleMenu === 'function') {
            toggleMenu(false);
        }
        
        // Make sure menu popup is completely hidden
        const menuPopup = document.querySelector('.menu-popup');
        if (menuPopup) {
            menuPopup.classList.remove('active');
            menuPopup.style.display = 'none';
        }
    });

    threadItem.addEventListener('mouseenter', function(e) {
        const threadId = this.getAttribute('data-thread-id');
        const chainId = this.getAttribute('data-chain-id');
        
        initializePreviewElement();
        
        const rect = this.getBoundingClientRect();
        previewElement.style.top = `${rect.top + window.scrollY}px`;
        previewElement.style.left = `${rect.right + window.scrollX + 10}px`;
        
        previewElement.innerHTML = '<div class="preview-loading">Loading preview...</div>';
        previewElement.style.display = 'block';
        
        getChainPreview(threadId, chainId).then(data => {
            if (previewElement && previewElement.style.display === 'block') {
                if (data && data.hasPlotly && data.plotPreview) {
                    const img = document.createElement('img');
                    img.src = data.plotPreview;
                    img.style.cssText = 'width:100%;height:auto;max-height:100%;';
                    img.alt = 'Plot preview';
                    
                    previewElement.innerHTML = '';
                    previewElement.appendChild(img);
                } else {
                    previewElement.innerHTML = '<div class="preview-error">No preview available</div>';
                }
            }
        }).catch((err) => {
            console.error('Error loading preview:', err);
            if (previewElement && previewElement.style.display === 'block') {
                previewElement.innerHTML = '<div class="preview-error">Error loading preview</div>';
            }
        });
    });

    threadItem.addEventListener('mouseleave', function() {
        if (previewElement) {
            previewElement.style.display = 'none';
            // Clear any plotly plots to free memory
            previewElement.innerHTML = '';
        }
    });

    return threadItem;
}

function toggleChains(threadContainer) {
    const chainsContainer = threadContainer.querySelector('.chains-container');
    const toggleButton = threadContainer.querySelector('.thread-toggle');
    
    if (chainsContainer.classList.contains('hidden')) {
        // Show chains
        chainsContainer.classList.remove('hidden');
        toggleButton.classList.add('expanded');
        toggleButton.title = 'Hide older chains';
    } else {
        // Hide chains
        chainsContainer.classList.add('hidden');
        toggleButton.classList.remove('expanded');
        toggleButton.title = 'Show more chains';
    }
}

function checkTextOverflow() {
    document.querySelectorAll('.thread-task').forEach(element => {
        // If the scroll height is greater than the client height, it's overflowing
        if (element.scrollHeight > element.clientHeight) {
            element.classList.add('overflow');
        } else {
            element.classList.remove('overflow');
        }
    });
}

function deleteThread(threadId, element) {
    window.authService.fetch(`/delete_thread/${threadId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.error || `Server responded with status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Thread deleted:', data);
        
        // Remove the entire thread container from DOM
        const threadContainer = element.closest('.thread-container');
        if (threadContainer) {
            threadContainer.remove();
        } else {
            loadThreadsList();
        }
    })
    .catch(error => {
        console.error('Error deleting thread:', error);
        alert(`Error deleting thread: ${error.message}`);
    });
}

function deleteChain(threadId, chainId, element) {
    window.authService.fetch(`/delete_chain/${threadId}/${chainId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.error || `Server responded with status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Chain deleted:', data);
        
        // Remove the element from DOM
        if (element) {
            // If it's a chain-item (not the main thread)
            if (element.classList.contains('chain-item')) {
                element.remove();
            } else {
                // If it's the main thread item
                const threadContainer = element.closest('.thread-container');
                
                if (data.thread_empty) {
                    // If thread is now empty, remove the entire thread container
                    threadContainer.remove();
                } else {
                    // If other chains remain, just remove this item and refresh
                    element.remove();
                    // Refresh the threads list to update the view
                    loadThreadsList();
                }
            }
        } else {
            // If element not provided, refresh the entire list
            loadThreadsList();
        }
    })
    .catch(error => {
        console.error('Error deleting chain:', error);
        alert(`Error deleting chain: ${error.message}`);
    });
}

async function loadThreadContent(threadId, chainId) {
    console.log(`Loading thread ${threadId} with chain ${chainId}`);
    
    const streamOutput = document.getElementById('streamOutput');
    if (streamOutput) {
        streamOutput.innerHTML = '<div>Loading thread content...</div>';
    }
    
    try {
        const response = await window.authService.fetch(`/load_thread/${threadId}/${chainId}`);
        
        if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
        }
        
        const data = await response.json();
        
        currentData.thread_id = threadId;
        currentData.chain_id = chainId;
        
        // Decompress content if needed — NOTE: 'resp' not 'response'
        const processedResponses = await Promise.all(data.responses.map(async (resp) => {
            if (resp.compressed) {
                console.log('Decompressing response...');
                const decompressedContentOutput = await decompressContent(resp.contentOutput);
                const decompressedStreamOutput = await decompressContent(resp.streamOutput);
                
                return {
                    ...resp,
                    contentOutput: decompressedContentOutput,
                    streamOutput: decompressedStreamOutput,
                    compressed: false
                };
            }
            return resp;
        }));
        
        await localforage.setItem('responses', processedResponses);
        
        responses = processedResponses;
        
        // Anything loaded from favorites is at minimum trajectory-saved
        responses.forEach(resp => {
            if (resp && !resp.bookmark_type) {
                resp.bookmark_type = 'trajectory';
            }
        });
        
        // Find the clicked chain
        const targetChainId = data.target_chain_id || chainId;
        const targetIndex = responses.findIndex(r => String(r.chain_id) === String(targetChainId));
        
        // Debug logging
        console.log('Target chain_id:', targetChainId);
        console.log('Available chain_ids:', responses.map(r => r.chain_id));
        console.log('Found at index:', targetIndex);
        
        currentResponseIndex = targetIndex >= 0 ? targetIndex : responses.length - 1;
        
        loadResponseContent(responses[currentResponseIndex]);
        
        if (typeof updateNavigationButtons === 'function') {
            updateNavigationButtons();
        }
        
        console.log(`Thread ${threadId} loaded: ${responses.length} chains, viewing index ${currentResponseIndex}`);
    } catch (error) {
        console.error('Error loading thread content:', error);
        if (streamOutput) {
            streamOutput.innerHTML = `<div class="error">Error loading thread content: ${error.message}</div>`;
        }
    }
}

function initializePreviewElement() {
    // Create the preview element if it doesn't exist
    if (!previewElement) {
        previewElement = document.createElement('div');
        previewElement.className = 'chain-preview';
        document.body.appendChild(previewElement);
    }
}

function getChainPreview(threadId, chainId) {
    return window.authService.fetch(`/get_chain_preview/${threadId}/${chainId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            return response.json();
        })
        .catch(error => {
            console.error('Error loading preview:', error);
            return null;
        });
}

async function assignLabelToChain(chainId, labelId, labelName) {
    try {
        const response = await window.authService.fetch(`/api/chains/${chainId}/label`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label_id: labelId })
        });
        
        if (!response.ok) throw new Error('Failed to assign label');
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error assigning label:', error);
        throw error;
    }
}

// Add label selector function
async function showLabelSelector(chainId, currentLabelId, iconElement, threadItem) {
    // Remove any existing selector
    const existingSelector = document.querySelector('.label-selector-dropdown');
    if (existingSelector) existingSelector.remove();
    
    // Get labels from LabelsManager
    const labels = window.LabelsManager ? await getAvailableLabels() : [];
    
    // Create dropdown
    const dropdown = document.createElement('div');
    dropdown.className = 'label-selector-dropdown';
    
    // Add "No label" option
    const noLabelOption = document.createElement('div');
    noLabelOption.className = `label-option ${!currentLabelId ? 'selected' : ''}`;
    noLabelOption.textContent = '× Remove label';
    noLabelOption.addEventListener('click', () => updateChainLabel(chainId, null, null, iconElement, threadItem));
    dropdown.appendChild(noLabelOption);
    
    // Add separator
    if (labels.length > 0) {
        const separator = document.createElement('div');
        separator.className = 'label-separator';
        dropdown.appendChild(separator);
    }
    
    // Add label options
    labels.forEach(label => {
        const option = document.createElement('div');
        option.className = `label-option ${label.id == currentLabelId ? 'selected' : ''}`;
        option.textContent = label.label;
        option.addEventListener('click', () => updateChainLabel(chainId, label.id, label.label, iconElement, threadItem));
        dropdown.appendChild(option);
    });
    
    // Position dropdown
    const rect = iconElement.getBoundingClientRect();
    dropdown.style.position = 'absolute';
    dropdown.style.top = `${rect.bottom + 5}px`;
    dropdown.style.right = `${window.innerWidth - rect.right}px`;
    dropdown.style.zIndex = '1100';
    
    document.body.appendChild(dropdown);
    
    // Close dropdown when clicking outside
    setTimeout(() => {
        document.addEventListener('click', function closeDropdown(e) {
            if (!dropdown.contains(e.target)) {
                dropdown.remove();
                document.removeEventListener('click', closeDropdown);
            }
        });
    }, 0);
}

// Helper function to get labels
async function getAvailableLabels() {
    try {
        const response = await window.authService.fetch('/api/labels');
        const data = await response.json();
        return data.labels || [];
    } catch (error) {
        console.error('Error fetching labels:', error);
        return [];
    }
}

// Update chain label
async function updateChainLabel(chainId, labelId, labelName, iconElement, threadItem) {
    try {
        await assignLabelToChain(chainId, labelId, labelName);
        
        // Update UI
        iconElement.classList.toggle('labeled', !!labelId);
        iconElement.title = labelName || 'Add label';
        
        // Update data attributes
        threadItem.setAttribute('data-label-id', labelId || '');
        threadItem.setAttribute('data-label-name', labelName || '');
        
        // Update label display if it's a main thread item
        if (threadItem.classList.contains('thread-item') && !threadItem.classList.contains('chain-item')) {
            let labelDisplay = threadItem.querySelector('.thread-label-display');
            
            if (labelName) {
                if (!labelDisplay) {
                    labelDisplay = document.createElement('span');
                    labelDisplay.className = 'thread-label-display';
                    
                    // Insert after thread ID, before dataset
                    const datasetElement = threadItem.querySelector('.thread-dataset-name');
                    threadItem.insertBefore(labelDisplay, datasetElement);
                }
                labelDisplay.textContent = `Label: ${labelName}`;
            } else if (labelDisplay) {
                labelDisplay.remove();
            }
        }
        
        // Remove dropdown
        document.querySelector('.label-selector-dropdown')?.remove();
        
        // Show success message
        if (window.showSystemMessage) {
            window.showSystemMessage(labelName ? `Label "${labelName}" assigned` : 'Label removed', 'success');
        }
    } catch (error) {
        if (window.showSystemMessage) {
            window.showSystemMessage('Failed to update label', 'error');
        }
    }
}

//--------------------
//  VARIATION EXTRACTION & MATCHING
//--------------------

function extractVariationsFromStreamOutput(streamOutput) {
    // Parse the 5 numbered questions from streamOutput HTML
    // Format: 1. **Title**\n   Question text\n   Code execution needed: Yes/No
    
    const variations = [];
    
    // Create temp element to get text content from HTML
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = streamOutput || '';
    const textContent = tempDiv.textContent || tempDiv.innerText || '';
    
    // Regex to match numbered questions with bold titles
    // Matches: 1. **Title**\n or 1. **Title:**\n
    const pattern = /(?:^|\n)(\d+)\.\s+\*\*(.+?)\*\*:?\s*([\s\S]*?)(?=(?:^|\n)\d+\.\s+\*\*|Code execution needed:\s*(?:Yes|No)\s*$|$)/gm;
    
    let match;
    while ((match = pattern.exec(textContent)) !== null) {
        const number = parseInt(match[1]);
        const title = match[2].trim();
        let questionText = match[3].trim();
        
        // Clean up the question text - remove "Code execution needed" suffix
        questionText = questionText.replace(/Code execution needed:\s*(Yes|No)\s*/gi, '').trim();
        
        if (title && number >= 1 && number <= 5) {
            variations.push({
                number: number,
                title: title,
                question: questionText,
                explored: false,
                exploredChainId: null
            });
        }
    }
    
    // Alternative simpler pattern if the above doesn't match well
    if (variations.length === 0) {
        const simplePattern = /(?:^|\n)\d+\.\s+\*\*(.+?)\*\*/gm;
        let simpleMatch;
        let num = 1;
        while ((simpleMatch = simplePattern.exec(textContent)) !== null && num <= 5) {
            variations.push({
                number: num,
                title: simpleMatch[1].trim(),
                question: '',
                explored: false,
                exploredChainId: null
            });
            num++;
        }
    }
    
    return variations;
}

function getExploredVariations(forkChainId, variations) {
    // Find all responses that are children of this fork node
    const children = responses.filter(r => r.parentChainId === forkChainId);
    
    // Helper to normalize text for comparison
    const normalize = (text) => {
        return (text || '')
            .toLowerCase()
            .replace(/["'"'`]/g, '')  // Remove all quote variants
            .replace(/\s+/g, ' ')      // Normalize whitespace
            .trim();
    };
    
    // For each variation, check if any child's queryText contains the title
    variations.forEach(variation => {
        const normalizedTitle = normalize(variation.title);
        
        const matchingChild = children.find(child => {
            const normalizedQuery = normalize(child.queryText);
            return normalizedQuery.includes(normalizedTitle);
        });
        
        if (matchingChild) {
            variation.explored = true;
            variation.exploredChainId = matchingChild.chain_id;
        }
    });
    
    return variations;
}

function renderVariationPills(variations, container) {
    // Clear container
    container.innerHTML = '';
    
    // Add header
    const header = document.createElement('div');
    header.className = 'variations-header';
    header.textContent = 'Generated Variations:';
    container.appendChild(header);
    
    // Create pills container
    const pillsContainer = document.createElement('div');
    pillsContainer.className = 'variations-pills-container';
    
    variations.forEach(variation => {
        const pill = document.createElement('div');
        pill.className = `variation-pill ${variation.explored ? 'explored' : 'dormant'}`;
        pill.setAttribute('data-chain-id', variation.exploredChainId || '');
        pill.setAttribute('title', variation.explored 
            ? `Click to navigate to "${variation.title}"` 
            : 'Not explored');
        
        // Pill content
        const titleSpan = document.createElement('span');
        titleSpan.className = 'pill-title';
        titleSpan.textContent = variation.title;
        pill.appendChild(titleSpan);
        
        // Add checkmark for explored
        if (variation.explored) {
            const checkmark = document.createElement('span');
            checkmark.className = 'pill-checkmark';
            checkmark.innerHTML = '✓';
            pill.appendChild(checkmark);
            
            // Add click handler to navigate
            pill.addEventListener('click', () => {
                const targetIndex = responses.findIndex(r => r.chain_id === variation.exploredChainId);
                if (targetIndex >= 0) {
                    currentResponseIndex = targetIndex;
                    lastActiveChainId = responses[targetIndex].chain_id || null;
                    loadResponseContent(responses[currentResponseIndex]);
                    if (typeof updateNavigationButtons === 'function') {
                        updateNavigationButtons();
                    }
                    // Close the modal
                    document.getElementById('workflowMapModal').style.display = 'none';
                }
            });
        }
        
        pillsContainer.appendChild(pill);
    });
    
    container.appendChild(pillsContainer);
}