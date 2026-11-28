//--------------------
//  GLOBAL VARIABLES
//--------------------

let currentData = { 
    chain_id: null,
    thread_id: null 
};
let lastActiveChainId = null;
let tabCounter = 0;
let currentResponseIndex = -1;
let responses = [];
let buffer = '';
let currentDatasetName = null;
let taskContents = {};
let popupTimeout;
let autoScroll = true;
let initialScrollTop = 0;
let previewElement = null;
let answerTabSynthesis = false;
let auxiliaryDatasetCount = 0;
const MAX_AUXILIARY_DATASETS = Number(window.MAX_AUXILIARY_DATASETS) || 10;   // the app's one limit (web_app/app.py, derived from the loaders' kinds plus room for uploads), set on the page by the template (2026-10-16); the fallback is for a page served without it

// The calendar day of a Date as the person sees it (2026-10-15): the loaders' dialogs and the routine run dialog had taken
// "today" from toISOString(), the UTC day - before 11:00 in Melbourne the Data tab and a run made minutes apart asked for
// windows a day apart, and the cache could never serve the one from the other. Every "today" on the page goes through this.
function localIsoDay(d) {
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}
// The store's part in a load from Intervals.icu (docs/INCREMENTAL_LOADS_DESIGN.md, 2026-10-15): the executor keeps every
// activity it has fetched and downloads only what a window asks for that it does not hold. One phrase for the load's
// completion line, from the job result's `store` (window, held, fetched, refresh; since 2026-10-29 `laps` the same
// account for the laps file, when it was asked - the laps of settled activities come from the store too).
function storeLine(st) {
    if (!st || !st.window) return '';
    const n = st.window, held = st.held || 0, word = n === 1 ? 'activity' : 'activities';
    const laps = st.laps && st.laps.window ? (st.laps.held === st.laps.window ? '; every lap from the store' : st.laps.held ? '; laps: ' + st.laps.held + ' of ' + st.laps.window + ' from the store' : '') : '';
    if (st.offline) return (held === n ? 'all ' + n + ' ' + word : held + ' of ' + n + ' ' + word) + ' from the store, nothing fetched';     // the Dataset cache dialog's Load (2026-10-29)
    if (st.refresh) return n + ' ' + word + ' fetched again';
    if (!held) return n + ' ' + word + ' downloaded' + laps;
    if (held === n) return 'all ' + n + ' ' + word + ' from the store, nothing downloaded' + laps;
    return held + ' of ' + n + ' ' + word + ' from the store, ' + (n - held) + ' downloaded' + laps;
}
// The end of a load in the three load dialogs - Intervals.icu, Endura, SweatStack (2026-11-27, the product owner's pick of
// three mockups; docs/DATASETS_DESIGN.md section 19): the Load button takes one look for each moment of a load.
//   busy   the load runs: the button grey, its icon still
//   done   the data is in: "Loaded" with a tick where the button was - no frame, nothing to press - until the dialog closes
//          itself, LOAD_DONE_MS later
//   close  something asked for was not loaded, and the dialog stays to say so: the button closes it
//   idle   as the page drew it (its own markup, kept at the first call)
const LOAD_DONE_MS = 1500;
const LOAD_TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
const loadButtonDrawn = new WeakMap();
function setLoadButton(button, state) {
    if (!button) return;
    if (!loadButtonDrawn.has(button)) loadButtonDrawn.set(button, { html: button.innerHTML, title: button.getAttribute('title'), label: button.getAttribute('aria-label') });
    const drawn = loadButtonDrawn.get(button);
    const word = state === 'done' ? 'Loaded' : state === 'close' ? 'Close' : '';
    button.dataset.state = state;
    button.classList.toggle('loading', state === 'busy');
    button.classList.toggle('done', state === 'done');
    button.disabled = state === 'busy' || state === 'done';
    button.innerHTML = state === 'done' ? LOAD_TICK + word : word || drawn.html;
    for (const [attr, was] of [['title', drawn.title], ['aria-label', drawn.label]]) {
        if (word || was) button.setAttribute(attr, word || was); else button.removeAttribute(attr);
    }
}
// A load dialog's openings are counted, so the close a load schedules shuts only the opening it was meant for - not the
// dialog closed and opened again in those moments (found on the Intervals.icu dialog, 2026-11-06)
function loadDialogOpened(modal) {
    if (modal) modal.dataset.opening = String(Number(modal.dataset.opening || 0) + 1);
}
function closeLoadDialogSoon(modal, hide) {
    const opening = modal ? modal.dataset.opening : undefined;
    setTimeout(() => { if (modal && modal.dataset.opening === opening) hide(); }, LOAD_DONE_MS);
}
// The query box emptied: what was typed has gone - to an analysis, to the Pathfinder, or as a question about the passage
// quoted on the box - and the quote goes with it (selection.js). The one place that empties it (2026-11-27; three
// places each did, in their own lines).
function emptyComposer() {
    const input = document.getElementById('queryInput');
    if (input) { input.value = ''; input.style.height = 'auto'; }
    if (window.SelectionUI) window.SelectionUI.unquote();
}
let limitMessageTimeout = null;

let mermaidReady = false;

let isWaitingForApiKeys = false;

// Query state
let queryRunning = false;

// Auto-explore state
let autoExploreEnabled = false;
let currentMode = 'deep';        // quick | deep | adaptive - the brain's hover menu; sent with every /query
let autoExploreIterations = 3;   // replaced on load by the tier's real budget
// THE SIMPLIFICATION (2026-08-18): the dial opens at the tier's
// adaptive_max_investigations so users adjust from truth. The user's
// choice is always honoured downward (dial 4 on a 9-tier runs exactly
// 4); the tier value is the CEILING, and the UI's plus button stops
// there - so a UI user never hits a server clamp at all. The server's
// own min(dial, tier) exists only as defence in depth for requests
// that bypass this interface: stale tabs, direct API calls, future
// clients. Same boundary, enforced at both layers.
let adaptiveDialDefault = 3;
let autoExploreRunning = false;
let autoExploreStopped = false; // Track if user manually stopped

//--------------------
//  CORE CONFIGURATION
//--------------------

const mermaidTheme = {
    theme: 'dark',
    themeVariables: {
        primaryColor: '#384B5E',
        primaryTextColor: '#C1DAFF',
        primaryBorderColor: '#536B8A',
        lineColor: '#87A2BF',
        secondaryColor: '#2B3847',
        tertiaryColor: '#1E2730',
        fontSize: '14px',
        fontFamily: 'arial',
        background: '#1a1a1a',
        mainBkg: '#2B3847',
        nodeBorder: '#87A2BF',
        clusterBkg: '#1a1a1a',
        clusterBorder: '#536B8A',
        titleColor: '#C1DAFF',
        edgeLabelBackground: '#384B5E',
        textColor: '#C1DAFF'
    },
    flowchart: {
        curve: 'basis',
        padding: 15,
        useMaxWidth: true,
        htmlLabels: false,
        nodeSpacing: 50,
        rankSpacing: 50,
        diagramPadding: 8,
        width: 'auto',
    },
    securityLevel: 'loose'
};

//--------------------
//  CORE INITIALIZATION
//--------------------

function initializeApp() {
    console.log('Initializing BambooAI application...');
    
    // Configure LocalForage for in-browser storage
    localforage.config({
        name: 'bambooAI',
        storeName: 'responses',
        description: 'BambooAI responses and session data'
    });

    // Initialize window.currentData if not exists
    if (!window.currentData) {
        window.currentData = { chain_id: null, thread_id: null };
        console.log('Initialized window.currentData');
    }

    // Configure marked for LaTeX handling
    configureMarkdown();
    
    console.log('Core initialization complete');
}

function configureMarkdown() {
    // Configure marked to handle LaTeX safely
    const renderer = new marked.Renderer();
    const originalCode = renderer.code.bind(renderer);

    renderer.code = function(code, language) {
        if (language === 'math' || language === 'latex') {
            return code;  // Don't wrap in code blocks
        }
        return originalCode(code, language);
    };

    marked.setOptions({
        renderer: renderer,
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false,
        sanitize: false,
        smartLists: true,
        smartypants: false
    });
}

//--------------------
//  THEME MANAGEMENT
//--------------------

function initializeThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    const html = document.documentElement;
    const sunIcon = themeToggle.querySelector('.sun-icon');
    const moonIcon = themeToggle.querySelector('.moon-icon');
    const themeLabel = themeToggle.querySelector('.theme-label');
    const logo = document.querySelector('.menu-logo');
    
    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'dark') {
        html.setAttribute('data-theme', 'dark');
        sunIcon.style.display = 'block';  // Show SUN icon when you can switch to LIGHT
        moonIcon.style.display = 'none';
        themeLabel.textContent = 'Light Theme'; // Show what you can switch TO
        logo.src = '/static/image/logo_dark.svg';
    } else {
        html.setAttribute('data-theme', 'light');
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';  // Show MOON icon when you can switch to DARK
        themeLabel.textContent = 'Dark Theme'; // Show what you can switch TO
        logo.src = '/static/image/logo_light.svg';
    }

    themeToggle.addEventListener('click', () => {
        const currentTheme = html.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        html.setAttribute('data-theme', newTheme);
        
        sunIcon.style.display = newTheme === 'dark' ? 'block' : 'none';  // Show SUN when you can switch to LIGHT
        moonIcon.style.display = newTheme === 'dark' ? 'none' : 'block';  // Show MOON when you can switch to DARK
        themeLabel.textContent = newTheme === 'dark' ? 'Light Theme' : 'Dark Theme'; // Show what you can switch TO next
        
        logo.src = newTheme === 'dark' ? '/static/image/logo_dark.svg' : '/static/image/logo_light.svg';
        
        localStorage.setItem('theme', newTheme);
    });
}

//--------------------
//  UTILITY FUNCTIONS
//--------------------

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function ensureMermaid() {
    if (!mermaidReady) {
        mermaid.initialize({ startOnLoad: false, ...mermaidTheme });
        mermaidReady = true;
    }
}

//--------------------
//  POST-AUTHENTICATION INITIALIZATION
//--------------------

function initializeAppAfterAuth() {
    console.log('Authentication complete, initializing app modules...');
    
    // Initialize theme system and basic UI first
    initializeThemeToggle();
    if (typeof initializeUIControls === 'function') initializeUIControls();
    
    // Initialize subscription management (fully replaces API keys management)
    if (typeof initializeSubscriptionModal === 'function') {
        initializeSubscriptionModal();
        
        // Add subscription settings button handler for optional access later
        const subscriptionOption = document.querySelector('.subscription-option');
        if (subscriptionOption) {
            subscriptionOption.addEventListener('click', () => {
                if (typeof showSubscriptionModal === 'function') {
                    showSubscriptionModal(false); // Show as optional from settings
                }
            });
        }
    }

    // Initialize compression utilities early (before other modules need them)
    if (typeof initializeCompression === 'function') initializeCompression();
    
    // THE WORKSPACE START (v63, 2026-09-10): a fresh load starts its workspace now - the server reset and
    // the executor request - alongside the pause below, and the modules initialise after it on THIS page.
    // (Until v62 the modules initialised first and the page then reloaded itself: two start-ups.)
    const workspaceStarted = (typeof startWorkspaceIfFreshLoad === 'function')
        ? startWorkspaceIfFreshLoad().catch(e => console.error('[workspace] start failed:', e))
        : Promise.resolve();

    // IMPORTANT: Check subscription AFTER authentication is confirmed
    // This delay ensures auth tokens are ready
    setTimeout(async () => {
        await workspaceStarted;
        // Now check subscription (which includes API key validation for "own" tier)
        if (typeof checkSubscriptionOnLoad === 'function') {
            checkSubscriptionOnLoad();
        } else {
            // If no checks needed, continue normally
            continueAppInitialization();
        }
    }, 1000); // Delay to ensure auth is fully ready
}

function continueAppInitialization() {
    console.log('Continuing app initialization after API keys check...');
    isWaitingForApiKeys = false;
    
    // Continue with the rest of the initialization that was blocked
    if (typeof initializeFileManagement === 'function') initializeFileManagement();
    if (typeof initializeQueryProcessing === 'function') initializeQueryProcessing();
    if (typeof initializeContentRendering === 'function') initializeContentRendering();
    if (typeof initializeWorkflowManagement === 'function') initializeWorkflowManagement();
    if (typeof initializePDFExport === 'function') initializePDFExport();
    if (window.UsageUI) window.UsageUI.initialize();                  // the Usage dialog (usage.js, 2026-10-31)

    // Add container status initialization
    if (typeof window.containerStatus !== 'undefined' && typeof window.containerStatus.initialize === 'function') {
        window.containerStatus.initialize();
    }

    // Initialize Dataset Manager
    if (typeof window.DatasetManager !== 'undefined' && typeof window.DatasetManager.initialize === 'function') {
        window.DatasetManager.initialize();
    }
    
    // Initialize Workflow Modal
    if (typeof window.WorkflowModal !== 'undefined' && typeof initializeWorkflowModal === 'function') {
        initializeWorkflowModal();
    }

    // Routines (docs/ROUTINES_DESIGN.md): the Save pill's menu, the rail entry, the favourites' cards' button
    if (typeof window.RoutinesUI !== 'undefined' && typeof window.RoutinesUI.initialize === 'function') {
        window.RoutinesUI.initialize();
    }

    // The context codebook (docs/CONTEXT_DESIGN.md S3): the gear item and its count of proposals, read once auth has settled
    if (typeof window.CodebookUI !== 'undefined' && typeof window.CodebookUI.initialize === 'function') {
        window.CodebookUI.initialize();
    }

    // The code trace (docs/CODEMAP_DESIGN.md): the modal behind the closing card's button and the Workflow map's eye
    if (typeof window.CodeMapUI !== 'undefined' && typeof window.CodeMapUI.initialize === 'function') {
        window.CodeMapUI.initialize();
    }

    // The Pathfinder (docs/ARCHITECT_DESIGN.md §2.8): the switch beside the mode control, the Brief tab's clicks
    if (typeof window.ArchitectUI !== 'undefined' && typeof window.ArchitectUI.initialize === 'function') {
        window.ArchitectUI.initialize();
    }

    // The maps drawer: the left bar's button, the switch between the maps
    if (typeof window.MapsUI !== 'undefined' && typeof window.MapsUI.initialize === 'function') {
        window.MapsUI.initialize();
    }

    // Branches (docs/BRANCH_DESIGN.md §5): the buttons on an analysis's turns, the composer as a hint's
    if (typeof window.BranchUI !== 'undefined' && typeof window.BranchUI.initialize === 'function') {
        window.BranchUI.initialize();
    }

    // Asking about a selection (selection.js): the bar beside selected text, the quote on the query box
    if (typeof window.SelectionUI !== 'undefined' && typeof window.SelectionUI.initialize === 'function') {
        window.SelectionUI.initialize();
    }

    // What was asked about a passage (explain.js): its mark in the tab, the note under it
    if (typeof window.ExplainUI !== 'undefined' && typeof window.ExplainUI.initialize === 'function') {
        window.ExplainUI.initialize();
    }

    // The report in plain language (simplify.js): the Answer tab's button, which asks for it and then shows it
    if (typeof window.SimplifyUI !== 'undefined' && typeof window.SimplifyUI.initialize === 'function') {
        window.SimplifyUI.initialize();
    }

    // Next questions (docs/ARCHITECT_DESIGN.md §2.7): the button on a finished analysis' closing card, the cards under it
    if (typeof window.NextQuestionsUI !== 'undefined' && typeof window.NextQuestionsUI.initialize === 'function') {
        window.NextQuestionsUI.initialize();
    }

    // Initialize Labels Manager
    if (typeof window.LabelsManager !== 'undefined' && typeof window.LabelsManager.initialize === 'function') {
        window.LabelsManager.initialize();
    }

    // Initialize Agent Instructions - ADD THIS
    if (typeof window.AgentInstructions !== 'undefined' && typeof window.AgentInstructions.initialize === 'function') {
        console.log('Initializing Agent Instructions module...');
        window.AgentInstructions.initialize();
    }

    // Initialize Workflow Manager

    if (typeof window.SweatStack !== 'undefined' && typeof window.SweatStack.initialize === 'function') {
        window.SweatStack.initialize();
    }

    if (typeof window.Intervals !== 'undefined' && typeof window.Intervals.initialize === 'function') {
        window.Intervals.initialize();
    }

    if (typeof window.Endura !== 'undefined' && typeof window.Endura.initialize === 'function') {
        window.Endura.initialize();
    }
    
    console.log('App initialization complete');
}

//--------------------
//  APPLICATION STARTUP
//--------------------

// The dataset chips' row in the top bar (2026-10-15): one row that scrolls sideways when the chips outrun it. The wheel
// moves it (a mouse wheel is vertical; the row is not), the edge fades say there is more on either side, and a chip that
// has just been added or is loading is brought into view. The chips themselves are made by file-management.js.
function pillStrip(container) {
    if (!container || container.__strip) return;
    container.__strip = true;
    const update = () => {
        const more = container.scrollWidth - container.clientWidth > 1;
        container.classList.toggle('more-left', more && container.scrollLeft > 1);
        container.classList.toggle('more-right', more && container.scrollLeft + container.clientWidth < container.scrollWidth - 1);
    };
    container.addEventListener('wheel', e => {
        if (container.scrollWidth <= container.clientWidth) return;
        const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
        if (!d) return;
        // at the wheel's own pace (2026-10-29: smooth scrolling animated every tick from the position mid-animation, a crawl);
        // a wheel that reports lines or pages moves by lines or pages
        const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? container.clientWidth : 1;
        container.scrollLeft += d * unit;
        e.preventDefault();
    }, { passive: false });
    container.addEventListener('scroll', update, { passive: true });
    if (typeof ResizeObserver === 'function') new ResizeObserver(update).observe(container);
    if (typeof MutationObserver === 'function') {
        new MutationObserver(records => {
            update();
            const added = records.flatMap(r => [...r.addedNodes]).filter(n => n.nodeType === 1).pop();   // the newest chip, into view
            if (added && typeof added.scrollIntoView === 'function') added.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }).observe(container, { childList: true });
    }
    update();
    return update;
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event triggered');
    
    // Initialize core application (this happens immediately)
    initializeApp();
    pillStrip(document.getElementById('datasetStatusPillsContainer'));
    
    // Initialize authentication after core is ready
    if (window.authService && typeof window.authService.initialize === 'function') {
        console.log('Starting authentication initialization...');
        window.authService.initialize();
    } else {
        console.error('Auth service not found! Make sure auth.js loaded correctly.');
        // Fallback: try again after a short delay in case auth.js is still loading
        setTimeout(() => {
            if (window.authService && typeof window.authService.initialize === 'function') {
                console.log('Starting authentication initialization (delayed)...');
                window.authService.initialize();
            } else {
                console.error('Auth service still not available after delay');
            }
        }, 100);
    }
    
    console.log('Core initialization complete, authentication starting...');
});