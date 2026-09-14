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
let currentRankData = null;
let currentDatasetName = null;
let taskContents = {};
let popupTimeout;
let currentSelection = null;
let currentRange = null;
let highlightElements = [];
let selectedText = '';
let autoScroll = true;
let initialScrollTop = 0;
let previewElement = null;
let answerTabInteractive = false;
let answerTabExplore = false;      // the seedling's page: no PDF, no Simplified (2026-09-08)
let answerTabSynthesis = false;
let auxiliaryDatasetCount = 0;
let limitMessageTimeout = null;

let mermaidReady = false;

let isWaitingForApiKeys = false;

let isTrajectoryRank = false;

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
    // Memory Review (step 27): initialized here, after auth settles,
    // so its first /memory/review check carries a valid token instead
    // of racing authentication behind a timer.
    if (typeof window.initializeMemoryReview === 'function') window.initializeMemoryReview();
    if (typeof initializePDFExport === 'function') initializePDFExport();
    if (typeof initializeUsageTracking === 'function') initializeUsageTracking();

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

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event triggered');
    
    // Initialize core application (this happens immediately)
    initializeApp();
    
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