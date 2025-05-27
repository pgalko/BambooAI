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
let currentToolCallId = null;
let toolCallStartTime = null;
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
let auxiliaryDatasetCount = 0;
let currentOntologyState = {
    isActive: false,
    fileName: null, // Name of the uploaded ontology file
    pillId: null    // ID of the ontology pill in the DOM
};
let limitMessageTimeout = null;

let mermaidReady = false;

//--------------------
//  CORE CONFIGURATION
//--------------------

const mermaidTheme = {
    heme: 'dark',
    themeVariables: {
        primaryColor: '#384B5E',
        primaryTextColor: '#C1DAFF',
        primaryBorderColor: '#536B8A',
        lineColor: '#87A2BF',
        secondaryColor: '#2B3847',
        tertiaryColor: '#1E2730',
        fontSize: '14px',
        fontFamily: 'arial',
        background: '#1E2730',
        mainBkg: '#2B3847',
        nodeBorder: '#87A2BF',
        clusterBkg: '#1E2730',
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
    const html = document.documentElement; // Use <html> for data-theme
    const sunIcon = themeToggle.querySelector('.sun-icon');
    const moonIcon = themeToggle.querySelector('.moon-icon');
    const logo = document.querySelector('.menu-logo'); // Reference to the logo
    
    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        html.setAttribute('data-theme', 'dark');
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
        logo.src = '/static/image/logo_dark.svg'; // Set dark logo
    } else {
        html.setAttribute('data-theme', 'light');
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
        logo.src = '/static/image/logo_light.svg'; // Set light logo
    }

    themeToggle.addEventListener('click', () => {
        const currentTheme = html.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        html.setAttribute('data-theme', newTheme);
        
        // Toggle icons
        sunIcon.style.display = newTheme === 'dark' ? 'none' : 'block';
        moonIcon.style.display = newTheme === 'dark' ? 'block' : 'none';

        // Switch logo
        logo.src = newTheme === 'dark' ? '/static/image/logo_dark.svg' : '/static/image/logo_light.svg';
        
        // Save preference
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
//  APPLICATION STARTUP
//--------------------

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event triggered');
    
    // Initialize core application
    initializeApp();
    
    // Initialize theme system
    initializeThemeToggle();
    
    // Initialize all other modules (these functions will be defined in other modules)
    if (typeof initializeUIControls === 'function') initializeUIControls();
    if (typeof initializeFileManagement === 'function') initializeFileManagement();
    if (typeof initializeQueryProcessing === 'function') initializeQueryProcessing();
    if (typeof initializeContentRendering === 'function') initializeContentRendering();
    if (typeof initializeWorkflowManagement === 'function') initializeWorkflowManagement();
    
    console.log('All modules initialized');
});