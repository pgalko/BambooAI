//--------------------
//  UI CONTROLS MODULE
//--------------------

function initializeUIControls() {
    console.log('Initializing UI controls...');
    
    initializeScrollBehavior();
    initializeRail();
    initializeMenuOverlay();                 // a no-op now that the history drawer is gone (2026-09-08)
    initializeSettingsMenu();
    initializePanelCollapse();
    initializeNavigationButtons();
    initializeModeSwitch();
    initializeSuggestQuestions();
    initializeTextareaResize();
    initializeKeyboardShortcuts();
    initializeGenericToast();
    initializeURLDetection();
    initializeAutoExplore();
    
    console.log('UI controls initialized');
}

//--------------------
//  URL DETECTION
//--------------------

function initializeURLDetection() {
    const queryInput = document.getElementById('queryInput');
    
    if (queryInput) {
        // Create the external context indicator
        const indicator = document.createElement('div');
        indicator.className = 'external-context-indicator';
        indicator.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
        </svg>
        <span>External Context</span>
    `;
        indicator.style.display = 'none';
        indicator.style.cursor = 'pointer';
        
        // Create URL list popup
        const urlPopup = document.createElement('div');
        urlPopup.className = 'url-list-popup';
        urlPopup.style.display = 'none';
        
        // Insert both into the textarea container
        const container = queryInput.closest('.textarea-container');
        if (container) {
            container.style.position = 'relative';
            container.appendChild(indicator);
            container.appendChild(urlPopup);
        }
        
        // Track URLs
        let currentURLs = [];
        
        queryInput.addEventListener('input', function() {
            const urlRegex = /https?:\/\/[^\s]+/gi;
            currentURLs = this.value.match(urlRegex) || [];
            
            if (currentURLs.length > 0) {
                indicator.style.display = 'block';
            } else {
                indicator.style.display = 'none';
                urlPopup.style.display = 'none';
            }
            
            // Update auto-explore indicator position
            if (typeof updateIndicatorPositions === 'function') {
                updateIndicatorPositions();
            }
        });
        
        // Toggle popup on click
        indicator.addEventListener('click', function(e) {
            e.stopPropagation();
            
            if (urlPopup.style.display === 'none') {
                // Build URL list
                urlPopup.innerHTML = currentURLs.map(url => 
                    `<a href="${url}" target="_blank" rel="noopener">${url}</a>`
                ).join('');
                urlPopup.style.display = 'block';
            } else {
                urlPopup.style.display = 'none';
            }
        });
        
        // Close popup when clicking elsewhere
        document.addEventListener('click', function() {
            urlPopup.style.display = 'none';
        });
    }
}

//--------------------
//  SCROLL BEHAVIOR
//--------------------

function initializeScrollBehavior() {
    const streamOutput = document.getElementById('streamOutput');
    const indicator = document.querySelector('.scroll-indicator');
    
    if (streamOutput) {                                       // the indicator is gone (2026-09-08); auto-scroll still follows the reader
        streamOutput.addEventListener('scroll', () => {
            const distanceFromBottom = streamOutput.scrollHeight - streamOutput.scrollTop - streamOutput.clientHeight;
            autoScroll = distanceFromBottom < 50;
            if (indicator) indicator.classList.toggle('visible', !autoScroll);
        });
    }
}

//--------------------
//  MENU SYSTEM
//--------------------

function initializeRail() {
    // the rail's own buttons (2026-09-08): New workflow and the thread map; the other pills bind themselves
    const railNewButton = document.getElementById('railNewButton');
    if (railNewButton) {
        railNewButton.addEventListener('click', function (event) {
            event.stopPropagation();
            if (typeof handleNewConversation === 'function') handleNewConversation();
        });
    }
    const railMapButton = document.getElementById('railMapButton');
    if (railMapButton) {
        railMapButton.addEventListener('click', function (event) {
            event.stopPropagation();
            const map = document.getElementById('workflowMapModal');
            if (map && map.style.display === 'flex') { map.style.display = 'none'; return; }
            if (typeof showWorkflowMap === 'function') showWorkflowMap();
        });
    }
}

function initializeMenuOverlay() {
    if (!document.querySelector('.menu-popup')) return;   // the history drawer is gone (2026-09-08): no overlay, no bindings
    // Create the overlay element
    const overlay = document.createElement('div');
    overlay.className = 'menu-overlay';
    document.body.appendChild(overlay);
    
    // Get menu elements
    const menuButton = document.querySelector('.menu-button');
    const menuPopup = document.querySelector('.menu-popup');
    
    if (!menuButton || !menuPopup) {
        console.error('Menu elements not found');
        return;
    }
    
    // Add click event to the menu button
    menuButton.addEventListener('click', function(event) {
        event.stopPropagation();
        toggleMenu(!menuPopup.classList.contains('active'));   // the rail button opens and closes the drawer (2026-09-08)
    });
    
    // Close menu when clicking the overlay
    overlay.addEventListener('click', function() {
        toggleMenu(false);
    });
    
    // Close menu when pressing Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            toggleMenu(false);
        }
    });
    
    // Handle menu options
    const newConversationOption = document.querySelector('.new-conversation-option');
    const loginOption = document.querySelector('.login-option');
    const workflowMapOption = document.querySelector('.workflow-map-option');
    
    if (newConversationOption) {
        newConversationOption.addEventListener('click', function() {
            menuPopup.style.display = 'none';
            handleNewConversation();
        });
    }
    
    if (loginOption) {
        loginOption.addEventListener('click', function() {
            menuPopup.style.display = 'none';
            // Add login functionality here
        });
    }
    
    if (workflowMapOption) {
        workflowMapOption.addEventListener('click', function() {
            document.querySelector('.menu-popup').style.display = 'none';
            document.querySelector('.menu-overlay').classList.remove('active');
            if (typeof showWorkflowMap === 'function') {
                showWorkflowMap();
            }
        });
    }
    
    console.log('Menu overlay initialized');
}

function toggleMenu(show) {
    if (!document.querySelector('.menu-popup')) return;   // the drawer is gone (2026-09-08); callers may still ask
    const menuPopup = document.querySelector('.menu-popup');
    const overlay = document.querySelector('.menu-overlay');
    const menuButton = document.querySelector('.menu-button');
    const scrollIndicator = document.querySelector('.scroll-indicator');
    const collapseButton = document.getElementById('collapseButton');
    
    if (!menuPopup || !overlay) {
        console.error('Menu elements not found');
        return;
    }
    
    if (show) {
        const buttonRect = menuButton.getBoundingClientRect();
        menuPopup.style.left = `${buttonRect.left}px`;
        menuPopup.style.top = `${buttonRect.bottom + 5}px`;
        
        // Set CSS variable for dynamic height calculation
        document.documentElement.style.setProperty('--menu-top-offset', `${buttonRect.bottom + 5}px`);
        
        menuPopup.classList.add('active');
        menuPopup.style.display = 'flex';
        overlay.classList.add('active');
        
        // Hide scroll indicator when menu is open
        if (scrollIndicator) {
            scrollIndicator.style.display = 'none';
        }
        // Hide collapse button when menu is open
        if (collapseButton) {
            collapseButton.style.display = 'none';
        }
        
        // Initialize threads UI
        if (typeof initializeThreadsUI === 'function') {
            initializeThreadsUI();
        }
    } else {
        menuPopup.classList.remove('active');
        overlay.classList.remove('active');
        
        // Show scroll indicator when menu is closed
        if (scrollIndicator) {
            scrollIndicator.style.display = 'flex';
        }

        // Show collapse button when menu is closed
        if (collapseButton) {
            collapseButton.style.display = '';
        }
        
        setTimeout(() => {
            if (!menuPopup.classList.contains('active')) {
                menuPopup.style.display = 'none';
            }
        }, 200);
    }
}

function initializeSettingsMenu() {
    const sweatstackOption = document.querySelector('.sweatstack-option');
    const intervalsOption = document.querySelector('.intervals-option');
    const enduraOption = document.querySelector('.endura-option');
    
    if (sweatstackOption) {
        sweatstackOption.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleMenu(false);
            // Use SweatStack module function
            if (window.SweatStack && typeof window.SweatStack.handleSweatStack === 'function') {
                window.SweatStack.handleSweatStack();
            } else {
                console.warn('SweatStack module not loaded');
            }
        });
    }
    
    if (intervalsOption) {
        intervalsOption.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleMenu(false);
            // Use Intervals module function
            if (window.Intervals && typeof window.Intervals.handleIntervals === 'function') {
                window.Intervals.handleIntervals();
            } else {
                console.warn('Intervals module not loaded');
            }
        });
    }

    if (enduraOption) {
        enduraOption.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleMenu(false);
            if (window.Endura && typeof window.Endura.handleEndura === 'function') {
                window.Endura.handleEndura();
            } else {
                console.warn('Endura module not loaded');
            }
        });
    }
}

//--------------------
//  PANEL COLLAPSE
//--------------------

function initializePanelCollapse() {
    const collapseButton = document.getElementById('collapseButton');
    const leftPanel = document.getElementById('leftPanel');
    const rightPanel = document.getElementById('rightPanel');
    
    if (!collapseButton || !leftPanel || !rightPanel) {
        console.warn('Panel collapse elements not found');
        return;
    }
    
    function updateButtonPosition(immediate = false) {
        const update = () => {
            if (leftPanel.classList.contains('collapsed')) {
                collapseButton.style.left = '0px';
                collapseButton.style.transform = 'translateY(-50%) rotate(180deg)';
            } else {
                collapseButton.style.left = (leftPanel.offsetWidth - 12) + 'px';
                collapseButton.style.transform = 'translateY(-50%)';
            }
        };

        if (immediate) {
            update();
        } else {
            setTimeout(update, 200); // Delay to match transition duration
        }
    }

    // Set initial button position
    updateButtonPosition(true);

    collapseButton.addEventListener('click', function() {
        leftPanel.classList.toggle('collapsed');
        rightPanel.classList.toggle('expanded');
        updateButtonPosition();
    });

    // Update button position on window resize
    window.addEventListener('resize', () => updateButtonPosition(true));
}

//--------------------
//  NAVIGATION BUTTONS
//--------------------

function initializeNavigationButtons() {
    const prevButton = document.getElementById('prevResponse');
    const nextButton = document.getElementById('nextResponse');
    
    if (!prevButton || !nextButton) {
        console.error('Navigation buttons not found');
        return;
    }
    
    prevButton.addEventListener('click', () => {
        if (typeof navigateResponses === 'function') {
            navigateResponses(-1);
        }
    });
    
    nextButton.addEventListener('click', () => {
        if (typeof navigateResponses === 'function') {
            navigateResponses(1);
        }
    });
}

function updateNavigationButtons() {
    const prevButton = document.getElementById('prevResponse');
    const nextButton = document.getElementById('nextResponse');
    const navContainer = document.querySelector('.tab-navigation');

    if (!prevButton || !nextButton || !navContainer) return;

    if (responses.length <= 1) {
        navContainer.style.display = 'none';
    } else {
        navContainer.style.display = 'flex';
        prevButton.disabled = currentResponseIndex <= 0;
        nextButton.disabled = currentResponseIndex >= responses.length - 1;
        const pos = document.getElementById('chainPosition');
        if (pos) pos.textContent = 'chain ' + (currentResponseIndex + 1) + ' of ' + responses.length;
    }

    console.log('Navigation buttons updated:', {
        prevDisabled: prevButton.disabled,
        nextDisabled: nextButton.disabled
    });

    if (typeof updateRankButtonVisibility === 'function') {
        updateRankButtonVisibility();
    }
}

//--------------------
//  MODE SWITCH (2026-09-05): hover the brain for Quick | Deep | Adaptive.
//  The mode is a per-request field of /query - no server state, no
//  re-instantiation. Deep is the default; the choice persists in the session.
//--------------------

function setMode(mode) {
    if (['quick', 'deep', 'adaptive'].indexOf(mode) === -1) mode = 'deep';
    currentMode = mode;
    autoExploreEnabled = (mode === 'adaptive');
    const brain = document.getElementById('modeSwitch');
    const popup = document.getElementById('modeSliderPopup');
    if (brain) {
        brain.setAttribute('data-mode', mode);
        brain.title = 'Mode: ' + mode.charAt(0).toUpperCase() + mode.slice(1);
        brain.classList.toggle('active', mode !== 'quick');
        brain.classList.toggle('adaptive', mode === 'adaptive');
    }
    if (popup) {
        popup.classList.toggle('adaptive', mode === 'adaptive');
        popup.querySelectorAll('.mode-option').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-mode') === mode);
        });
    }
    const submitButton = document.getElementById('submitQuery');
    if (submitButton) submitButton.classList.toggle('auto-explore-active', mode === 'adaptive');
    try { sessionStorage.setItem('analystMode', mode); } catch (e) { /* ignore */ }
}

function initializeModeSwitch() {
    const brain = document.getElementById('modeSwitch');
    const popup = document.getElementById('modeSliderPopup');
    if (!brain || !popup) {
        console.warn('Mode switch elements not found');
        return;
    }
    let hideTimer = null;
    const show = function () { clearTimeout(hideTimer); popup.style.display = 'flex'; };
    const hideSoon = function () {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            if (!popup.matches(':hover') && !brain.matches(':hover')) popup.style.display = 'none';
        }, 250);
    };
    brain.addEventListener('mouseenter', show);
    brain.addEventListener('mouseleave', hideSoon);
    popup.addEventListener('mouseleave', hideSoon);
    brain.addEventListener('click', function (e) {          // a click cycles the modes for keyboard/touch users
        e.preventDefault();
        const order = ['quick', 'deep', 'adaptive'];
        setMode(order[(order.indexOf(currentMode) + 1) % order.length]);
    });
    popup.querySelectorAll('.mode-option').forEach(function (b) {
        b.addEventListener('click', function (e) {
            e.stopPropagation();
            setMode(b.getAttribute('data-mode'));
            if (b.getAttribute('data-mode') !== 'adaptive') popup.style.display = 'none';
        });
    });
    // the Adaptive stepper (the dial): investigations x 4 turns on the server, within the tier's ceiling
    const iterationsValue = document.getElementById('iterationsValue');
    const minusBtn = popup.querySelector('.iter-minus');
    const plusBtn = popup.querySelector('.iter-plus');
    if (minusBtn) minusBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (autoExploreIterations > 1) { autoExploreIterations--; if (iterationsValue) iterationsValue.textContent = autoExploreIterations; }
    });
    if (plusBtn) plusBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (autoExploreIterations < Math.max(adaptiveDialDefault, 12)) { autoExploreIterations++; if (iterationsValue) iterationsValue.textContent = autoExploreIterations; }
    });
    let stored = null;
    try { stored = sessionStorage.getItem('analystMode'); } catch (e) { /* ignore */ }
    setMode(stored || 'deep');
}

//--------------------
//  SUGGEST QUESTIONS
//--------------------

function initializeSuggestQuestions() {
    const suggestQuestions = document.getElementById('suggestQuestions');
    const branchingSliderPopup = document.getElementById('branchingSliderPopup');
    const branchingIcons = document.querySelectorAll('.branching-icon');
    
    if (!suggestQuestions) {
        console.warn('Suggest questions element not found');
        return;
    }
    
    // Show popup on hover
    suggestQuestions.addEventListener('mouseenter', function() {
        branchingSliderPopup.style.display = 'flex';
        // anchored to the button (2026-09-08): just above it, left-aligned, no gap to lose the hover across
        branchingSliderPopup.style.left = suggestQuestions.offsetLeft + 'px';
        branchingSliderPopup.style.top = (suggestQuestions.offsetTop - branchingSliderPopup.offsetHeight - 2) + 'px';
        branchingSliderPopup.style.bottom = 'auto';
    });
    
    // Hide popup when leaving both button and popup
    suggestQuestions.addEventListener('mouseleave', function() {
        setTimeout(() => {
            if (!branchingSliderPopup.matches(':hover') && !suggestQuestions.matches(':hover')) {
                branchingSliderPopup.style.display = 'none';
            }
        }, 100);
    });
    
    branchingSliderPopup.addEventListener('mouseleave', function() {
        setTimeout(() => {
            if (!branchingSliderPopup.matches(':hover') && !suggestQuestions.matches(':hover')) {
                branchingSliderPopup.style.display = 'none';
            }
        }, 100);
    });
    
    // Handle icon clicks
    branchingIcons.forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.stopPropagation();
            const branchingCvValue = parseInt(this.getAttribute('data-value'));
            const queryInput = document.getElementById('queryInput');
            
            if (!queryInput) return;
            
            // Clear the input and submit with selected branching_cv
            queryInput.value = 'User requested variations of the enquiry';
            
            if (typeof handleQuerySubmit === 'function') {
                handleQuerySubmit({branching_cv: branchingCvValue});
            }
            answerTabInteractive = true;
            
            // Hide the popup after submission
            branchingSliderPopup.style.display = 'none';
        });
    });
}

//--------------------
//  TEXTAREA RESIZE
//--------------------

function initializeTextareaResize() {
    const queryInput = document.getElementById('queryInput');
    
    if (!queryInput) {
        console.warn('Query input element not found');
        return;
    }
    
    queryInput.addEventListener('input', function() {
        this.style.height = '60px';  // Reset to minimum height
        // Clamp to the same 40vh ceiling the CSS enforces, so the inline
        // height stays honest and the scrollbar takes over beyond it.
        const newHeight = Math.min(Math.floor(window.innerHeight * 0.4),
                                   Math.max(60, this.scrollHeight));
        this.style.height = newHeight + 'px';
    });
}

//--------------------
//  KEYBOARD SHORTCUTS
//--------------------

function initializeKeyboardShortcuts() {
    const queryInput = document.getElementById('queryInput');
    
    // Handle query submission with Ctrl+Enter or Cmd+Enter
    if (queryInput) {
        queryInput.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                if (typeof handleQuerySubmit === 'function') {
                    handleQuerySubmit();
                }
            }
        });
    }
    
    // Handle show workflow map with Ctrl+M or Cmd+M
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
            e.preventDefault();
            if (typeof showWorkflowMap === 'function') {
                showWorkflowMap();
            }
        }
    });

    // Handle new conversation with Ctrl+N or Cmd+N
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (typeof handleNewConversation === 'function') {
                handleNewConversation();
            }
        }
    });
}

//--------------------
//  LOADING OVERLAY FUNCTIONS
//--------------------

function showLoadingOverlay(message = "Loading...") {
    // the workspace gate is the overlay (2026-09-09): the pill, the page inert, the clock carried across the reload
    if (window.WorkspaceGate) { WorkspaceGate.begin('executor'); return; }
    // Remove any existing overlay
    hideLoadingOverlay();
    
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.innerHTML = `
        <div class="spinner"></div>
        <span>${message}</span>
    `;
    
    document.body.appendChild(overlay);
}

function hideLoadingOverlay() {
    if (window.WorkspaceGate) WorkspaceGate.end();
    const overlay = document.querySelector('.loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

//--------------------
//  NEW CONVERSATION
//--------------------

async function handleNewConversation() {
    try {
        // Show loading overlay immediately
        showLoadingOverlay("Starting new workflow...");
        
        // Call backend
        const response = await window.authService.fetch('/new_conversation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        
        if (!response.ok) {
            throw new Error('Network response was not ok when starting new conversation');
        }
        
        const data = await response.json();
        console.log('New conversation started:', data);
        
        // Reload with replace (no history entry)
        window.location.replace(window.location.pathname + '?new=true');
        
    } catch (error) {
        console.error('Error starting new workflow:', error);
        hideLoadingOverlay();
        alert('Error starting new workflow: ' + error.message);
    }
}

function setQueryRunning(running) {
    const submitButton = document.getElementById('submitQuery');
    if (!submitButton) return;
    
    if (running) {
        submitButton.classList.add('query-running');
    } else {
        submitButton.classList.remove('query-running');
        submitButton.disabled = false;
    }
}

async function stopQuery() {
    const submitButton = document.getElementById('submitQuery');
    if (submitButton) {
        submitButton.disabled = true;
    }
    
    try {
        const response = await window.authService.fetch('/stop_exploration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            console.log('Stop signal sent');
        } else {
            console.error('Failed to stop query');
        }
    } catch (error) {
        console.error('Error stopping query:', error);
    }
}

//--------------------
//  AUTO EXPLORE
//--------------------

function initializeAutoExplore() {
    // (2026-09-05) Adaptive is chosen from the brain's mode menu; this keeps the
    // running indicator and reads the tier's dial default.
    const queryInput = document.getElementById('queryInput');
    if (queryInput) {
        const container = queryInput.closest('.textarea-container');
        if (container && !document.getElementById('autoExploreIndicator')) {
            const indicator = document.createElement('div');
            indicator.className = 'auto-explore-indicator';
            indicator.id = 'autoExploreIndicator';
            indicator.innerHTML = `
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21.5 2v6h-6"></path>
                    <path d="M21.34 15.57a10 10 0 1 1-.57-8.38"></path>
                    <path d="M2.5 22v-6h6"></path>
                    <path d="M2.66 8.43a10 10 0 1 1 .57 8.38"></path>
                </svg>
                <span id="autoExploreIterationText">Adaptive Workflow</span>
            `;
            indicator.style.display = 'none';
            container.appendChild(indicator);
        }
    }
    const _cfgFetch = window.authService ? window.authService.fetch('/api/llm-config') : fetch('/api/llm-config');
    _cfgFetch.then(r => r.json()).then(j => {
        const cfg = (j && j.config) || {};
        const n = parseInt(cfg.adaptive_max_investigations || (cfg.analyst_turns_adaptive ? cfg.analyst_turns_adaptive / 4 : 0), 10);
        if (n && n > 0) {
            adaptiveDialDefault = n;
            autoExploreIterations = Math.min(autoExploreIterations, n) || n;
            const iterationsValue = document.getElementById('iterationsValue');
            if (iterationsValue) iterationsValue.textContent = autoExploreIterations;
        }
    }).catch(() => {});
}

function showAutoExploreIndicator(show) {
    const indicator = document.getElementById('autoExploreIndicator');
    if (indicator) {
        indicator.style.display = show ? 'flex' : 'none';
        if (show) {
            updateIndicatorPositions();
        }
    }
}

function updateIndicatorPositions() {
    const autoExploreIndicator = document.getElementById('autoExploreIndicator');
    const externalContextIndicator = document.querySelector('.external-context-indicator');
    
    if (!autoExploreIndicator) return;
    
    // Check if external context indicator is visible
    const externalVisible = externalContextIndicator && 
        externalContextIndicator.style.display !== 'none' &&
        externalContextIndicator.style.display !== '';
    
    // Position auto-explore indicator based on external context visibility
    if (externalVisible) {
        autoExploreIndicator.style.right = '120px';
    } else {
        autoExploreIndicator.style.right = '10px';
    }
}

function setAutoExploreRunning(running) {
    autoExploreRunning = running;
    autoExploreStopped = false;
    const submitButton = document.getElementById('submitQuery');
    const indicator = document.getElementById('autoExploreIndicator');
    
    if (!submitButton) return;
    
    if (running) {
        submitButton.classList.remove('auto-explore-active');
        submitButton.classList.add('auto-explore-running');
        if (indicator) indicator.classList.add('running');
    } else {
        submitButton.classList.remove('auto-explore-running');
        if (indicator) indicator.classList.remove('running');
    }
}

function resetAutoExplore() {
    const wasStoppedByUser = autoExploreStopped;

    autoExploreEnabled = (currentMode === 'adaptive');   // the mode is the user's choice; a run ending does not change it
    autoExploreRunning = false;
    autoExploreStopped = false;
    
    const submitButton = document.getElementById('submitQuery');
    if (submitButton) {
        submitButton.classList.remove('auto-explore-active');
        submitButton.classList.remove('auto-explore-running');
        submitButton.disabled = false; // Always enable - user can continue in normal mode
    }
    
    
    // Reset indicator text
    const iterationText = document.getElementById('autoExploreIterationText');
    if (iterationText) {
        iterationText.textContent = 'Auto-Explore (3 loops)';
    }

    showAutoExploreIndicator(false);
    // the map stays closed when an Adaptive run ends (2026-09-10): the same as a Deep run - it opens
    // from the rail, the menu or Ctrl/Cmd+M when the person asks for it
    
    console.log('Auto-explore reset' + (wasStoppedByUser ? ' - interrupted by user' : ' - completed normally'));
}

async function stopAutoExplore() {
    autoExploreStopped = true;
    
    // Disable button immediately but keep stop icon visible
    const submitButton = document.getElementById('submitQuery');
    if (submitButton) {
        submitButton.disabled = true;
        // Don't remove auto-explore-running class yet - keep stop icon showing
    }
    
    // Update indicator to show stopping state
    const indicator = document.getElementById('autoExploreIndicator');
    if (indicator) {
        indicator.classList.remove('running');
        const textSpan = indicator.querySelector('span');
        if (textSpan) {
            textSpan.textContent = 'Stopping...';
        }
    }
    
    try {
        const response = await window.authService.fetch('/stop_exploration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            console.log('Stop signal sent');
        } else {
            console.error('Failed to stop exploration');
        }
    } catch (error) {
        console.error('Error stopping exploration:', error);
    }
}

//--------------------
//  GENERIC TOAST SYSTEM
//--------------------

function initializeGenericToast() {
    const toast = document.getElementById('summaryPopup');
    const closeButton = toast.querySelector('.close-button');

    if (!toast || !closeButton) {
        console.warn('Generic toast elements not found');
        return;
    }

    closeButton.addEventListener('click', closeGenericToast);

    // Prevent auto-hide when hovering over the toast
    toast.addEventListener('mouseenter', function() {
        if (popupTimeout) {
            clearTimeout(popupTimeout);
            popupTimeout = null;
        }
    });

    // Restart auto-hide timer when leaving the toast
    toast.addEventListener('mouseleave', function() {
        startToastTimer();
    });
}

function showGenericToast(message, duration = 5000) {
    const toast = document.getElementById('summaryPopup');
    const toastContent = document.getElementById('summaryContent');

    if (!toast || !toastContent) {
        console.error('Generic toast elements not found');
        return;
    }

    if (popupTimeout) {
        clearTimeout(popupTimeout);
        popupTimeout = null;
    }

    toastContent.innerHTML = message;

    toast.className = 'summary-popup';
    toast.classList.add('system-message');

    toast.style.display = 'block';

    if (duration > 0) {
        popupTimeout = setTimeout(() => {
            closeGenericToast();
        }, duration);
    }
}

function startToastTimer(duration = 5000) {
    if (popupTimeout) {
        clearTimeout(popupTimeout);
    }

    popupTimeout = setTimeout(() => {
        closeGenericToast();
    }, duration);
}

function closeGenericToast() {
    const toast = document.getElementById('summaryPopup');

    if (toast) {
        toast.style.display = 'none';
    }

    if (popupTimeout) {
        clearTimeout(popupTimeout);
        popupTimeout = null;
    }
}