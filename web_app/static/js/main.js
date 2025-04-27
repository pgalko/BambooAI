//--------------------
//  GLOBAL VARIABLES
//--------------------

let currentData = { 
    chain_id: null,
    thread_id: null 
};
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

// Create and inject the popup HTML
const popupHtml = `
<div id="selectionPopup" class="selection-popup" style="display: none;">
    <form id="selectionForm">
    <input type="text" id="selectionQuery" placeholder="Enter your query">
    <button type="submit" id="selectionRunButton" aria-label="Run query">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
    </button>
    </form>
</div>
`;

document.body.insertAdjacentHTML('beforeend', popupHtml);

// Get references to popup elements
const selectionPopup = document.getElementById('selectionPopup');
const selectionQuery = document.getElementById('selectionQuery');
const selectionForm = document.getElementById('selectionForm');
const selectionRunButton = document.getElementById('selectionRunButton');

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
  
let mermaidReady = false;

//--------------------
//  EVENT LISTENERS
//--------------------

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event triggered');

    // Configure LocalForage for in-browser storage
    localforage.config({
        name: 'bambooAI',
        storeName: 'responses',
        description: 'BambooAI responses and session data'
    });

    // URL and Navigation State
    const urlParams = new URLSearchParams(window.location.search);

    // Query and Output Elements
    const queryInput = document.getElementById('queryInput');
    const streamOutputDiv = document.getElementById('streamOutput');
    const contentOutput = document.getElementById('contentOutput');

    // Navigation Elements
    const prevButton = document.getElementById('prevResponse');
    const nextButton = document.getElementById('nextResponse');
    const suggestQuestions = document.getElementById('suggestQuestions');

    // File Upload Elements
    const uploadComputerButton = document.querySelector('.computer-option');
    const csvFileInput = document.getElementById('csvFile');
    const cloudButton = document.querySelector('.cloud-option');
    const submitQueryButton = document.getElementById('submitQuery');

    // Panel Layout Elements
    const collapseButton = document.getElementById('collapseButton');
    const leftPanel = document.getElementById('leftPanel');
    const rightPanel = document.getElementById('rightPanel');

    // Rank Modal Elements
    const rankButton = document.getElementById('rankButton');
    const modal = document.getElementById('rankModal');
    const modalContent = modal?.querySelector('.modal-content');
    const submitRankButton = document.getElementById('submit-rank');
    const closeModalButton = modal?.querySelector('.close');

    // Menu Navigation Elements
    const newConversationOption = document.querySelector('.new-conversation-option');
    const loginOption = document.querySelector('.login-option');
    const menuPopup = document.querySelector('.menu-popup');
    const menuButton = document.querySelector('.menu-button');

    // Planning Switch Elements
    const planningSwitch = document.getElementById('planningSwitch');

    // Ontology Switch Elements
    const ontologySwitch = document.getElementById('ontologySwitch');

    // Selection and Popup Elements
    const selectionQuery = document.getElementById('selectionQuery');
    const selectionForm = document.getElementById('selectionForm');

    // Initialize window.currentData if not exists
    if (!window.currentData) {
        window.currentData = { chain_id: null, thread_id: null };
        console.log('Initialized window.currentData');
    }

    // Initialize scroll behavior
    initializeScrollBehavior();

    // Initialize menu overlay
    initializeMenuOverlay();
    
    // Initialize theme toggle
    initializeThemeToggle();
    
    // Set up popup listeners
    setupPopupListeners();

    // Set up follow up functionality
    if (suggestQuestions) {
        suggestQuestions.addEventListener('click', function() {
            queryInput.value = `
                What should I ask next? Give 5 possible lines of inquiry to delve deeper into the topic, and analyse the given data further. Ground it in the context of the conversation so far, and the given dataset. Format the response as a numbered markdown list.
                The Task is routed to the Research Specialist, and the response will be formatted as follows:

                1. **question_title:**
                question
                2. **question_title:**
                question
                3. **question_title:**
                question
                4. **question_title:**
                question
                5. **question_title:**
                question
            `;
            handleQuerySubmit();
            answerTabInteractive = true;
        });
    } else {
        console.warn('Suggest questions element not found');
    }

    // Check if this is a page refresh
    if (performance.navigation.type === 1) {
        console.log('This is a page refresh');
        // Actually clear the storage first before handling a new conversation
        localforage.removeItem('responses')
            .then(() => {
                console.log('Storage cleared on refresh');
                handleNewConversation();
            })
            .catch(err => {
                console.error('Error clearing storage on refresh:', err);
                handleNewConversation();
            });
    } else {
        // Check if we are comming from a new converasation
        if (urlParams.get('new') === 'true') {
            streamOutputDiv.innerHTML = '<div>New workflow started. Ready for your query.</div>';
            // Remove the 'new' parameter from the URL without reloading the page
            window.history.replaceState({}, document.title, window.location.pathname);
        } else {
            // Load saved responses if it's not a new conversation
            loadSavedResponses().catch(error => {
                console.error('Error loading saved responses:', error);
            });
        }
    }

    // New upload functionality
    if (uploadComputerButton && csvFileInput) {
        uploadComputerButton.addEventListener('click', function() {
            csvFileInput.click();
        });
    } else {
        console.warn('Computer upload button or file input not found');
    }

    // Keep this part for handling the file upload
    if (csvFileInput) {
        csvFileInput.addEventListener('change', handleFileUpload);
    } else {
        console.warn('CSV file input not found');
    }

    if (cloudButton) {
        cloudButton.addEventListener('click', handleCloudUpload);
    } else {
        console.warn('Cloud upload button not found');
    }

    if (submitQueryButton) {
        submitQueryButton.addEventListener('click', handleQuerySubmit);
    } else {
        console.warn('Submit query button not found');
    }

    if (prevButton && nextButton) {
        prevButton.addEventListener('click', () => {
            navigateResponses(-1);
        });
        nextButton.addEventListener('click', () => {
            navigateResponses(1);
        });
    } else {
        console.error('Navigation buttons not found');
    }

    if (newConversationOption) {
        newConversationOption.addEventListener('click', function() {
            menuPopup.style.display = 'none';  // Hide menu
            handleNewConversation();
        });
    } else {
        console.warn('New conversation option not found');
    }
    
    if (loginOption) {
        loginOption.addEventListener('click', function() {
            menuPopup.style.display = 'none';  // Hide menu
            // Add login functionality here
        });
    } else {
        console.warn('Login option not found');
    }

    // Add menu button click handler to initialize threads UI
    if (menuButton && menuPopup) {
        menuButton.addEventListener('click', function() {
            const isVisible = menuPopup.style.display === 'block';
            menuPopup.style.display = isVisible ? 'none' : 'block';
            
            // Initialize threads UI when menu is opened
            if (!isVisible) {
                initializeThreadsUI();
            }
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(event) {
            if (!menuButton.contains(event.target) && !menuPopup.contains(event.target)) {
                menuPopup.style.display = 'none';
            }
        });
    } else {
        console.warn('Menu button or popup not found');
    }

    // Auto-resize input box
    if (queryInput) {
        queryInput.addEventListener('input', function() {
            this.style.height = '60px';  // Reset to minimum height
            const newHeight = Math.max(60, this.scrollHeight); // Don't go below 60px
            this.style.height = newHeight + 'px';
        });
    } else {
        console.warn('Query input element not found');
    }

    // Code for collapsible panel
    if (collapseButton && leftPanel && rightPanel) {
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
    } else {
        console.warn('Collapsible panel elements not found');
    }

    if (rankButton) {
        rankButton.addEventListener('click', showRankModal);
        rankButton.style.display = 'none'; // Hide the button initially
    } else {
        console.warn('Rank button not found');
    }

    if (submitRankButton) {
        submitRankButton.addEventListener('click', submitRank);
    } else {
        console.warn('Submit rank button not found');
    }

    if (closeModalButton) {
        closeModalButton.addEventListener('click', closeRankModal);
    } else {
        console.warn('Close modal button not found');
    }

    // Close the modal if user clicks outside of it
    modal.addEventListener('click', function(event) {
        if (event.target === modal) {
            closeRankModal();
        }
    });

    // Prevent clicks inside the modal from closing it
    modalContent.addEventListener('click', function(event) {
        event.stopPropagation();
    });

    if (planningSwitch) {
        
        // Initialize state
        planningSwitch.classList.remove('active');
        
        // Attach click event listener
        planningSwitch.addEventListener('click', function(e) {
            const newState = !this.classList.contains('active');
            
            fetch('/update_planning', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ planning: newState })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Planning state updated:', data);
                if (data.current_state) {
                    this.classList.add('active');
                } else {
                    this.classList.remove('active');
                }
            })
            .catch(error => {
                console.error('Error updating planning state:', error);
                // Revert visual state on error
                if (newState) {
                    this.classList.remove('active');
                } else {
                    this.classList.add('active');
                }
            });
        });
        
        // Get initial state
        fetch('/get_planning_state')
            .then(response => response.json())
            .then(data => {
                console.log('Initial planning state:', data);
                if (data.planning_enabled) {
                    planningSwitch.classList.add('active');
                } else {
                    planningSwitch.classList.remove('active');
                }
            })
            .catch(error => {
                console.error('Error getting planning state:', error);
            });
    } else {
        console.warn('Planning switch element not found');
    }

    if (ontologySwitch) {
        // Initialize state
        ontologySwitch.classList.remove('active');
    
        // Attach click event listener
        ontologySwitch.addEventListener('click', function(e) {
            const ontologyFileInput = document.getElementById('ontologyFile');
            const isActive = this.classList.contains('active');
    
            if (isActive) {
                // Clear ontology
                updateOntologyState(null);
                this.classList.remove('active');
            } else {
                // Trigger file selection
                ontologyFileInput.click();
            }
        });
    
        // Handle file selection
        const ontologyFileInput = document.getElementById('ontologyFile');
        if (ontologyFileInput) {
            ontologyFileInput.addEventListener('change', function() {
                const file = this.files[0];
                if (file) {
                    // Send file to backend
                    updateOntologyState(file);
                    ontologySwitch.classList.add('active');
                    // Clear the input to allow re-selection of the same file
                    this.value = '';
                }
            });
        }
    
        // Get initial state
        fetch('/get_ontology_state')
            .then(response => response.json())
            .then(data => {
                console.log('Initial ontology state:', data);
                if (data.ontology_enabled && data.ontology_path) {
                    ontologySwitch.classList.add('active');
                } else {
                    ontologySwitch.classList.remove('active');
                }
            })
            .catch(error => {
                console.error('Error getting ontology state:', error);
            });
    } else {
        console.warn('Ontology switch element not found');
    }

    // Handle text selection
    if (contentOutput) {
        contentOutput.addEventListener('mouseup', (e) => {
            // Check if the click is within a plot tab
            const plotTab = e.target.closest('#content-plot');
            if (!plotTab) {
                handleTextSelection(e);
            }
        });
    } else {
        console.warn('contentOutput element not found');
    }

    // Handle click outside popup
    document.addEventListener('mousedown', handleClickOutside);

    // Handle form submission
    if (selectionForm) {
        selectionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleQuerySubmission(e);
        });
    }
    
    // Handle Enter key
    if (selectionQuery) {
        selectionQuery.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleQuerySubmission(e);
            }
        });
    }

    updateNavigationButtons();

    // Clear localStorage on tab close
    window.addEventListener('beforeunload', function() {
        localforage.removeItem('responses');
    });

    // Clean up event listeners when the page is unloaded
    window.addEventListener('unload', () => {
        console.log('Cleaning up event listeners...');
        
        if (contentOutput) {
            contentOutput.removeEventListener('mouseup', (e) => {
                const plotTab = e.target.closest('#content-plot');
                if (!plotTab) {
                    handleTextSelection(e);
                }
            });
        }
        document.removeEventListener('mousedown', handleClickOutside);
        window.removeEventListener('scroll', handleScroll);
        if (selectionForm) {
            selectionForm.removeEventListener('submit', handleQuerySubmission);
        }
        removeHighlights();
    });
});

//--------------------
//  HELPER FUNCTIONS
//--------------------

// Theme toggle functionality
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

function initializeScrollBehavior() {
    const streamOutput = document.getElementById('streamOutput');
    const indicator = document.querySelector('.scroll-indicator');
    
    if (streamOutput && indicator) {
        streamOutput.addEventListener('scroll', () => {
            const distanceFromBottom = streamOutput.scrollHeight - streamOutput.scrollTop - streamOutput.clientHeight;
            autoScroll = distanceFromBottom < 50;
            indicator.classList.toggle('visible', !autoScroll);
        });
    }
}

// Create highlight overlay
function createHighlightOverlay(range) {
    removeHighlights();

    const rects = range.getClientRects();
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;

    for (const rect of rects) {
        const highlight = document.createElement('div');
        highlight.className = 'highlight-overlay';
        highlight.style.left = (rect.left + scrollX) + 'px';
        highlight.style.top = (rect.top + scrollY) + 'px';
        highlight.style.width = rect.width + 'px';
        highlight.style.height = rect.height + 'px';
        document.body.appendChild(highlight);
        highlightElements.push(highlight);
    }
}

function removeHighlights() {
    highlightElements.forEach(element => {
        if (element.parentNode) {
            element.parentNode.removeChild(element);
        }
    });
    highlightElements = [];
}

function showPopupAtPosition(x, y) {
    
    selectionPopup.style.display = 'block';
    
    // Position popup near but not directly under the mouse
    const popupX = x + 10;
    const popupY = y + 10;
    
    // Keep popup within viewport bounds
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const popupWidth = selectionPopup.offsetWidth;
    const popupHeight = selectionPopup.offsetHeight;
    
    const finalX = Math.min(popupX, viewportWidth - popupWidth - 10);
    const finalY = Math.min(popupY, viewportHeight - popupHeight - 10);
    
    selectionPopup.style.left = finalX + 'px';
    selectionPopup.style.top = finalY + 'px';
}

// Handle text selection in tab content
function handleTextSelection(e) {
    const selection = window.getSelection();
    selectedText = selection.toString().trim();
    
    if (selectedText) {
        currentRange = selection.getRangeAt(0).cloneRange();
        console.log('New selection made:', selectedText);
        
        createHighlightOverlay(currentRange);
        showPopupAtPosition(e.clientX, e.clientY);
        selectionQuery.value = '';
        selectionQuery.focus();
    }
}

// Handle click outside popup
function handleClickOutside(e) {
    if (e.target.closest('#content-plot')) return;
    if (e.target.closest('#selectionForm') || e.target.closest('#selectionRunButton')) return;
    
    if (!selectionPopup.contains(e.target) && e.target !== selectionPopup) {
        selectionPopup.style.display = 'none';
        removeHighlights();
        currentRange = null;
        selectedText = '';
    }
}

// Query submission functions

// This is called when the user submits a query from the input box
function handleQuerySubmit() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();
    if (!query) {
        return;
    }

    const streamOutputDiv = document.getElementById('streamOutput');
    streamOutputDiv.innerHTML = '';
    clearAllTabs();

    // Clear the input textarea
    queryInput.value = '';

    // Reset the height of the textarea
    queryInput.style.height = 'auto';

    fetch('/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: query,
            chain_id: currentData.chain_id,
            thread_id: currentData.thread_id
        }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        function readStream() {
            return reader.read().then(({done, value}) => {
                if (done) {
                    console.log('Stream complete');
                    saveCurrentResponse();
                    return;
                }
                const chunk = decoder.decode(value);
                processChunk(chunk);
                return readStream();
            });
        }

        return readStream();
    })
    .catch(error => {
        console.error('Error:', error);
        streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
    });
}

// This is called when the user submits a query from the popup
async function handleQuerySubmission(e) {
    if (e) {
        e.preventDefault();
    }
    
    const query = selectionQuery.value.trim();
    console.log('Query value:', query);
    console.log('Selected text at submission:', selectedText);
    
    if (!query || !selectedText) {
        console.log('Missing query or selection:', { query, selectedText });
        return;
    }
    
    const queryWithContext = `${query}\n**Task Context:**\n${selectedText}`;
    
    try {
        console.log('Sending fetch request...');
        const response = await fetch('/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: queryWithContext,
                chain_id: currentData.chain_id,
                thread_id: currentData.thread_id
            }),
        });
        
        if (!response.ok) {
            throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
        }
        
        // Only clear UI elements after successful submission start
        selectionPopup.style.display = 'none';
        removeHighlights();
        
        // Handle streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        // Clear previous output
        const streamOutputDiv = document.getElementById('streamOutput');
        if (streamOutputDiv) {
            streamOutputDiv.innerHTML = '';
            window.clearAllTabs();
        } else {
            console.error('streamOutput div not found');
            return;
        }
        
        // Read and process the stream
        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                console.log('Stream complete');
                window.saveCurrentResponse();
                break;
            }
            const chunk = decoder.decode(value);
            window.processChunk(chunk);
        }
        
        // Clear selection only after successful completion
        currentSelection = null;
        selectedText = '';
        
    } catch (error) {
        console.error('Error in query submission:', error);
        const streamOutputDiv = document.getElementById('streamOutput');
        if (streamOutputDiv) {
            streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
        }
    }
}

// This is called when the user wants to submit a query about plot
function attachPlotQueryListeners(element) {
    // Handle query button clicks
    element.querySelectorAll('.plot-query-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const plotContainer = e.target.closest('.plot-container');
            if (!plotContainer) return;
            
            const queryForm = plotContainer.querySelector('.plot-query-form');
            if (!queryForm) return;

            queryForm.style.display = queryForm.style.display === 'none' ? 'flex' : 'none';
            
            if (queryForm.style.display === 'flex') {
                const queryInput = queryForm.querySelector('.plot-query-input');
                if (queryInput) queryInput.focus();
            }
        });
    });

    // Handle form submissions
    element.querySelectorAll('.plot-query-form').forEach(form => {
        const submitQuery = async (e) => {
            e.preventDefault();
            
            const plotContainer = e.target.closest('.plot-container');
            if (!plotContainer) return;
 
            const queryInput = e.target.closest('.plot-query-form').querySelector('.plot-query-input');
            
            if (!queryInput || !queryInput.value.trim()) return;
 
            let imageData;
            const plotImage = plotContainer.querySelector('.plot-image');
            if (plotImage) {
                // Regular PNG plot
                imageData = plotImage.src.split(',')[1];
            } else {
                // Check for Plotly plot
                const plotlyDiv = plotContainer.querySelector('.plotly-plot div');
                if (plotlyDiv) {
                    try {
                        const imgSrc = await Plotly.toImage(plotlyDiv, {format: 'png'});
                        imageData = imgSrc.split(',')[1];
                    } catch (err) {
                        console.error('Error converting Plotly plot to image:', err);
                        return;
                    }
                }
            }
 
            if (!imageData) return;
            
            const streamOutputDiv = document.getElementById('streamOutput');
            if (!streamOutputDiv) return;
            
            try {
                // Clear previous output
                streamOutputDiv.innerHTML = '';
                window.clearAllTabs();

                const response = await fetch('/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: queryInput.value,
                        image: imageData,
                        chain_id: currentData.chain_id,
                        thread_id: currentData.thread_id
                    }),
                });

                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                }

                // Handle streaming response
                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                // Process the stream
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) {
                        console.log('Stream complete');
                        window.saveCurrentResponse();
                        break;
                    }
                    const chunk = decoder.decode(value);
                    window.processChunk(chunk);
                }

                // Hide the query form and reset input after successful submission
                form.style.display = 'none';
                queryInput.value = '';

            } catch (error) {
                console.error('Error in plot query submission:', error);
                streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
            }
        };

        // Add click handler to submit button
        const submitButton = form.querySelector('.plot-query-submit');
        if (submitButton) {
            submitButton.addEventListener('click', submitQuery);
        }

        // Handle form submit event
        form.addEventListener('submit', submitQuery);

        // Handle enter key in input
        const queryInput = form.querySelector('.plot-query-input');
        if (queryInput) {
            queryInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    submitQuery(e);
                }
            });
        }
    });
}

// Update highlights on scroll
function handleScroll() {
    if (selectedText && currentRange) {
        createHighlightOverlay(currentRange);
    } else {
        removeHighlights();
    }
}

function handleFileUpload() {
    const file = this.files[0];
    if (!file) return;

    const statusDiv = document.getElementById('fileStatus');
    
    function updateStatus(message, isError = false) {
        const color = isError ? '#721c24' : '#35c477';
        statusDiv.innerHTML = `
            <div class="file-status-message">
                <span>${message}</span>
                ${!isError ? '<div class="file-upload-spinner"></div>' : ''}
            </div>
        `;
        statusDiv.style.display = 'block';
        statusDiv.style.color = color;
    }

    updateStatus(`Uploading and processing file "${file.name}"...`);

    const formData = new FormData();
    formData.append('file', file);

    currentDatasetName = file.name;

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.dataframe) {
            const dfData = JSON.parse(data.dataframe);
            createOrUpdateTab('dataframe', dfData.data);
        }
        updateStatus(`Dataset "${file.name}" is loaded and ready for analysis`);
        const spinner = statusDiv.querySelector('.file-upload-spinner');
        if (spinner) spinner.remove();
    })
    .catch(error => {
        console.error('Error:', error);
        updateStatus(`Error uploading file "${file.name}": ${error.message}`, true);
    });
}

// Cloud upload handler with matching style
function handleCloudUpload(e) {
    e.preventDefault();
    
    const statusDiv = document.getElementById('fileStatus');
    
    function updateStatus(message, isError = false) {
        const color = isError ? '#721c24' : '#35c477';
        statusDiv.innerHTML = `
            <div class="file-status-message">
                <span>${message}</span>
                ${!isError ? '<div class="file-upload-spinner"></div>' : ''}
            </div>
        `;
        statusDiv.style.display = 'block';
        statusDiv.style.color = color;
    }

    updateStatus('Loading cloud dataset...');

    fetch('/load_cloud_data', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({})
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(() => {
        updateStatus('Cloud dataset loaded and ready for analysis');
        const spinner = statusDiv.querySelector('.file-upload-spinner');
        if (spinner) spinner.remove();
    })
    .catch(error => {
        console.error('Error:', error);
        updateStatus(`Error loading cloud dataset: ${error.message}`, true);
    });
}

async function handleNewConversation() {
    try {
        const response = await fetch('/new_conversation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        const data = await response.json();
        console.log('New conversation started:', data);
        responses = [];
        await localforage.removeItem('responses');

        currentResponseIndex = -1;
        currentDatasetName = null;

        updateNavigationButtons();
        // Reload the page with a flag indicating new conversation
        window.location.href = window.location.pathname + '?new=true';
    } catch (error) {
        console.error('Error starting new conversation:', error);
        alert('Error starting new conversation: ' + error.message);
    }
}

async function saveCurrentResponse() {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    const streamOutput = document.getElementById('streamOutput');
    
    const newResponse = {
        tabContent: tabContainer.innerHTML,
        contentOutput: contentOutput.innerHTML,
        streamOutput: streamOutput.innerHTML,
        taskContents: taskContents,
        chain_id: currentData.chain_id || null,  // Include chain_id in saved response
        thread_id: currentData.thread_id || null  // Include thread_id in saved response
    };
    
    responses.push(newResponse);
    currentResponseIndex = responses.length - 1;

    // Enable suggest questions after first response
    document.getElementById('suggestQuestions')?.classList.remove('disabled');
    
    try {
        await localforage.setItem('responses', responses);
        console.log('Responses saved successfully with chain_id:', currentData.chain_id);
    } catch (error) {
        console.error('Error saving responses to localStorage:', error);
    }
    updateNavigationButtons();
}

// Load saved responses when the page loads
async function loadSavedResponses() {
    const savedResponses = await localforage.getItem('responses');

    if (savedResponses) {
        try {
            responses = savedResponses;

            if (Array.isArray(responses) && responses.length > 0) {
                currentResponseIndex = responses.length - 1;

                // Load the content
                const response = responses[currentResponseIndex];
                document.getElementById('tabContainer').innerHTML = response.tabContent;
                document.getElementById('contentOutput').innerHTML = response.contentOutput;
                document.getElementById('streamOutput').innerHTML = response.streamOutput;

                // Reactivate tabs
                const tabs = document.getElementsByClassName('tab');
                for (let tab of tabs) {
                    tab.onclick = () => {
                        activateTab(tab.id.split('-')[1]);
                    };
                }

                // Activate the first tab (usually 'answer')
                const firstTab = document.querySelector('.tab');
                if (firstTab) {
                    activateTab(firstTab.id.split('-')[1]);
                }

            } else {
                console.warn('No valid responses found in localStorage');
            }
        } catch (error) {
            console.error('Error parsing saved responses:', error);
        }
    } else {
        console.warn('No saved responses found in localStorage');
    }

    updateNavigationButtons();
}

function loadResponseContent(response) {
    if (!response) {
        console.log('No response to load');
        return;
    }

    console.log('Loading response content:', response);

    document.getElementById('tabContainer').innerHTML = response.tabContent;
    document.getElementById('contentOutput').innerHTML = response.contentOutput;
    document.getElementById('streamOutput').innerHTML = response.streamOutput;
    taskContents = response.taskContents || {};
    
    // Store the chain_id in currentData when loading a response
    currentData.chain_id = response.chain_id || null;
    currentData.thread_id = response.thread_id || null;
    console.log('Loaded chain_id:', currentData.chain_id);

    // Reactivate tabs
    const tabs = document.getElementsByClassName('tab');
    for (let tab of tabs) {
        tab.onclick = () => {
            activateTab(tab.id.split('-')[1]);
        };
    }

    // Re-render answer content if there's an answer tab
    const answerTab = document.getElementById('content-answer');
    if (answerTab) {
        const markdownContent = answerTab.querySelector('.markdown-content');
        if (markdownContent) {
            updateTabContent('answer', markdownContent.innerHTML);
        }
    }

    // Trigger the code case initialization if there's a code tab. This is needed for code editing
    const codeTab = document.getElementById('content-code');
    if (codeTab) {
        // This will reuse the existing initialization code from the 'code' case
        updateTabContent('code', codeTab.querySelector('code').textContent);
    }

    // Trigger the dataframe case initialization if there's a dataframe tab
    const dataframeTab = document.getElementById('content-dataframe');
    if (dataframeTab) {
        // Get the HTML content of the table
        const tableElement = dataframeTab.querySelector('table.dataframe');
        if (tableElement) {
            // This will reuse the existing initialization code from the 'dataframe' case
            updateTabContent('dataframe', tableElement.outerHTML);
        }
    }

    // Reattach plot query listeners and plotly scripts if there's a plot tab
    const plotTab = document.getElementById('content-plot');
    if (plotTab) {
        attachPlotQueryListeners(plotTab);

        const plotlyDivs = plotTab.querySelectorAll('.plotly-plot div');
        plotlyDivs.forEach(div => {
            // For HTML format plots (with script tags)
            const scripts = div.getElementsByTagName('script');
            if (scripts.length > 0) {
                Array.from(scripts).forEach(script => {
                    if (!script.src) eval(script.textContent);
                });
            }
            // For JSON format plots
            else if (div.dataset.plotlyJson) {
                const newDiv = document.createElement('div');
                div.parentNode.replaceChild(newDiv, div);
                
                setTimeout(() => {
                    try {
                        const plotData = JSON.parse(div.dataset.plotlyJson);
                        newDiv.dataset.plotlyJson = div.dataset.plotlyJson;
                        
                        Plotly.newPlot(newDiv, plotData.data, plotData.layout, {
                            responsive: true,
                            useResizeHandler: true,
                            displayModeBar: true
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
}

function navigateResponses(direction) {
    const prevIndex = currentResponseIndex;
    currentResponseIndex += direction;
    if (currentResponseIndex < 0) currentResponseIndex = 0;
    if (currentResponseIndex >= responses.length) currentResponseIndex = responses.length - 1;

    loadResponseContent(responses[currentResponseIndex]);
    updateNavigationButtons();
}

function updateNavigationButtons() {
    const prevButton = document.getElementById('prevResponse');
    const nextButton = document.getElementById('nextResponse');
    const navContainer = document.querySelector('.tab-navigation');

    if (responses.length <= 1) {
        navContainer.style.display = 'none';
    } else {
        navContainer.style.display = 'block';
        prevButton.disabled = currentResponseIndex <= 0;
        nextButton.disabled = currentResponseIndex >= responses.length - 1;
    }

    console.log('Navigation buttons updated:', {
        prevDisabled: prevButton.disabled,
        nextDisabled: nextButton.disabled
    });
}

function finishToolCall() {
    if (currentToolCallId) {
        completeToolCall(currentToolCallId, toolCallStartTime);
        currentToolCallId = null;
        toolCallStartTime = null;
    }
}

function processChunk(chunk) {
    const streamOutputDiv = document.getElementById('streamOutput');

    buffer += chunk;
    let startIndex = 0;

    while (true) {
        let endIndex = buffer.indexOf('\n', startIndex);
        if (endIndex === -1) break;

        let line = buffer.substring(startIndex, endIndex).trim();
        if (line) {
            try {
                const data = JSON.parse(line);
                if (data.type === "html") {
                    const uniqueId = `related-searches-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
                    
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(data.content, 'text/html');
                    
                    const chips = doc.querySelectorAll('.carousel .chip');
                    
                    const container = document.createElement('div');
                    container.className = 'related-searches-container';
                    container.id = uniqueId;
                    
                    const header = document.createElement('h3');
                    header.className = 'related-searches-header';
                    header.innerHTML = `
                        <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path>
                            <path d="M2 12h20"></path>
                        </svg>
                        <span class="header-text"> Related Searches</span>
                    `;
                    container.appendChild(header);
                    
                    const chipList = document.createElement('div');
                    chipList.className = 'related-searches-list';
                    
                    chips.forEach(chip => {
                        const href = chip.getAttribute('href') || '#';
                        const text = chip.textContent.trim() || 'Untitled';
                        
                        const chipItem = document.createElement('a');
                        chipItem.className = 'related-search-chip';
                        chipItem.href = href;
                        chipItem.target = '_blank';
                        chipItem.rel = 'noopener noreferrer';
                        chipItem.textContent = text;
                        
                        chipList.appendChild(chipItem);
                    });
                    
                    container.appendChild(chipList);
                    
                    if (container.children.length > 0) {
                        streamOutputDiv.appendChild(container);
                    } else {
                        console.warn('No recognizable content found in HTML:', data.content);
                    }
                }
                else if (data.type === "request_user_context") {
                    // Generate a unique ID for this specific form instance
                    const formId = `feedback-form-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
                    
                    console.log('Received feedback request:', {
                        query_clarification: data.query_clarification,
                        context_needed: data.context_needed,
                        chain_id: currentData.chain_id,
                        formId: formId
                    });
                    
                    // Format the query text for better readability
                    // 1. Convert numbered lists (e.g., "1. Item") to proper HTML list items
                    // 2. Add line breaks for better readability
                    let formattedQuery = data.query_clarification;
                    
                    // Check if the text contains numbered items or bullet points
                    const hasNumberedItems = /\d+\.\s/.test(formattedQuery);
                    const hasBulletPoints = /-\s/.test(formattedQuery);
                    
                    if (hasNumberedItems || hasBulletPoints) {
                        // Split by newlines first
                        const lines = formattedQuery.split('\n');
                        
                        // Format each line
                        const formattedLines = lines.map(line => {
                            // Check for numbered items (e.g., "1. Item")
                            if (/^\s*\d+\.\s/.test(line)) {
                                return `<div class="list-item">${line}</div>`;
                            }
                            // Check for bullet points (e.g., "- Item")
                            else if (/^\s*-\s/.test(line)) {
                                return `<div class="list-item">${line}</div>`;
                            }
                            // Regular lines
                            else if (line.trim()) {
                                return `<div>${line}</div>`;
                            }
                            // Empty lines
                            return '';
                        });
                        
                        formattedQuery = formattedLines.join('');
                    } else {
                        // If no list items, just add paragraph breaks
                        formattedQuery = formattedQuery.replace(/\n\n/g, '</div><div>');
                        formattedQuery = `<div>${formattedQuery}</div>`;
                    }
                    
                    // Create the feedback container with the unique ID and formatted query
                    streamOutputDiv.innerHTML += `
                        <div class="user-context-request">
                            <div class="feedback-container">
                                <div class="feedback-header">
                                    <svg class="question-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        <path d="M9 9C9 8.40666 9.17595 7.82664 9.50559 7.33329C9.83524 6.83994 10.3038 6.45543 10.852 6.22836C11.4002 6.0013 12.0033 5.94189 12.5853 6.05765C13.1672 6.1734 13.7018 6.45912 14.1213 6.87868C14.5409 7.29824 14.8266 7.83279 14.9424 8.41473C15.0581 8.99667 14.9987 9.59981 14.7716 10.148C14.5446 10.6962 14.1601 11.1648 13.6667 11.4944C13.1734 11.8241 12.5933 12 12 12V14" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        <path d="M12 17H12.01" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                    </svg>
                                    <span class="context-text">${formattedQuery} (Context: ${data.context_needed})</span>
                                </div>
                                <form class="feedback-form" id="${formId}">
                                    <input type="text" class="feedback-input" placeholder="Enter your feedback here">
                                    <button type="submit" class="feedback-submit" aria-label="Submit feedback">
                                        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                                        </svg>
                                    </button>
                                </form>
                                <div class="feedback-message"></div>
                            </div>
                        </div>
                    `;
                    
                    // Add some additional CSS styles for the formatted text
                    const styleId = 'feedback-formatting-styles';
                    if (!document.getElementById(styleId)) {
                        const style = document.createElement('style');
                        style.id = styleId;
                        style.textContent = `
                            #streamOutput .user-context-request .list-item {
                                margin-left: 1.5em;
                                position: relative;
                                padding-left: 0.5em;
                            }
                            
                            #streamOutput .user-context-request .context-text > div {
                                margin-bottom: 0.5em;
                            }
                            
                            #streamOutput .user-context-request .context-text > div:last-child {
                                margin-bottom: 0;
                            }
                        `;
                        document.head.appendChild(style);
                    }
                    
                    // Same event listener logic as before
                    setTimeout(() => {
                        const form = document.getElementById(formId);
                        if (form) {
                            // Use a closure to capture the original data and prevent scope issues
                            const queryData = {
                                queryClarification: data.query_clarification,
                                contextNeeded: data.context_needed
                            };
                            
                            form.addEventListener('submit', function(event) {
                                event.preventDefault();
                                
                                // Get fresh input value from the form element
                                const input = this.querySelector('.feedback-input');
                                const feedback = input.value.trim();
                                
                                if (!feedback) {
                                    console.warn('Feedback submission attempted with empty input');
                                    alert('Please provide feedback before submitting.');
                                    return;
                                }
                                
                                // Use the data captured in the closure
                                submitFeedback(feedback, queryData.queryClarification, queryData.contextNeeded, this);
                            });
                            
                            // Focus the input field
                            form.querySelector('.feedback-input').focus();
                        } else {
                            console.error('Could not find form with ID:', formId);
                        }
                    }, 0);
                }                
                else if (data.type === "id") {
                    if (data.chain_id) {
                        currentData.chain_id = data.chain_id;
                    }
                    if (data.thread_id) {
                        currentData.thread_id = data.thread_id;
                    }
                    console.log("Session IDs updated:", currentData);
                    streamOutputDiv.innerHTML += formatSessionIds(data);
                } 
                else if (data.tool_start) {
                    streamOutputDiv.innerHTML += formatToolStart(data.tool_start);
                } else if (data.call_summary) {
                    processSummary(data);
                } else if (data.system_message) {
                    showSystemMessage(data.system_message); 
                } else if (data.tool_call) {
                    currentToolCallId = 'tool-call-' + Date.now();
                    toolCallStartTime = Date.now();
                    streamOutputDiv.innerHTML += formatToolCall(data.tool_call);
                } else if (data.error) {
                    finishToolCall();
                    streamOutputDiv.innerHTML += formatError(data.error);
                } else if (data.type && data.type !== 'end' && data.type !== 'id') {
                    finishToolCall();
                    console.log(`Right panel data detected: ${data.type}`, data);
                    createOrUpdateTab(data.type, data.data, data.id, data.format);
                } else if (data.text) {
                    finishToolCall();
                    // Ensure any XML tags that come in chunks are escaped
                    const escapedText = data.text
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    streamOutputDiv.innerHTML += escapedText;
                } else if (data.type === 'end') {
                    finishToolCall();
                    console.log("End of results detected");
                
                    // 1) Replace any leftover code fences in the final output
                    streamOutputDiv.innerHTML = streamOutputDiv.innerHTML
                        .replaceAll('```python', createCodeHeader('python'))
                        .replaceAll('```yaml', createCodeHeader('yaml'))
                        .replaceAll('```json', createCodeHeader('json'))
                        .replaceAll('```javascript', createCodeHeader('javascript'))
                        .replaceAll('```html', createCodeHeader('html'))
                        .replaceAll('```css', createCodeHeader('css'))
                        // End fence
                        .replaceAll('```', '</code></pre>');
                
                    // 2) Tell Highlight.js to highlight all <code> blocks
                    streamOutputDiv.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                
                    // 3) Add click handlers for copy buttons
                    streamOutputDiv.querySelectorAll('.copy-button').forEach(button => {
                        button.addEventListener('click', function() {
                            const codeElement = this.closest('.code-header').nextElementSibling.querySelector('code');
                            if (codeElement) {
                                navigator.clipboard.writeText(codeElement.textContent)
                                    .then(() => {
                                        // Toggle icons
                                        const copyIcon = this.querySelector('.copy-icon');
                                        const checkIcon = this.querySelector('.check-icon');
                                        
                                        copyIcon.style.display = 'none';
                                        checkIcon.style.display = 'block';
                                        
                                        // Revert back after 2 seconds
                                        setTimeout(() => {
                                            copyIcon.style.display = 'block';
                                            checkIcon.style.display = 'none';
                                        }, 2000);
                                    })
                                    .catch(err => console.error('Failed to copy:', err));
                            }
                        });
                    });
                } else if (data.rank_data) {
                    currentRankData = data.rank_data;
                    document.getElementById('rankButton').style.display = 'block';
                    console.log("Rank data detected:", data.rank_data);
                } else {
                    finishToolCall();
                    console.log("Unhandled data detected:", data);
                }
            } catch (e) {
                console.error("Error processing line:", e);
                console.log("Problematic line:", line);
                // Don't add the line to the output, keep it in the buffer
                break;
            }
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

// Function to submit feedback
function submitFeedback(feedback, queryClarification, contextNeeded, form) {
    if (!currentData.chain_id) {
        console.error('Chain ID is missing:', currentData);
        alert('Error: Chain ID not set. Please try again.');
        return;
    }

    const payload = {
        feedback: feedback,
        chain_id: currentData.chain_id,
        query_clarification: queryClarification,
        context_needed: contextNeeded
    };
    
    console.log('Submitting feedback payload:', payload);

    fetch('/submit_feedback', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    })
    .then(response => {
        console.log('Feedback submission response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Feedback submission successful:', data);
        const container = form.closest('.feedback-container');
        const messageDiv = container.querySelector('.feedback-message');
        const safeHtml = document.createElement('div');
        safeHtml.textContent = feedback;
        messageDiv.innerHTML = `Feedback submitted!<br><span class="submitted-feedback">${safeHtml.innerHTML}</span>`;
        form.querySelector('.feedback-input').disabled = true;
        form.querySelector('.feedback-submit').disabled = true;
    })
    .catch(error => {
        console.error('Feedback submission failed:', error);
        const container = form.closest('.feedback-container');
        const messageDiv = container.querySelector('.feedback-message');
        messageDiv.textContent = 'Error submitting feedback: ' + error.message;
        messageDiv.style.color = '#ff0000';
    });
}

// Helper function to create code header
function createCodeHeader(language) {
    return `<div class="code-header">
        <span class="language-label">${language.toUpperCase()}</span>
        <button class="copy-button" title="Copy code">
            <svg class="copy-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <svg class="check-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none;">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
        </button>
    </div><pre><code class="language-${language.toLowerCase()}">`;
}

function showSystemMessage(message) {
    const popup = document.getElementById('summaryPopup');
    const content = document.getElementById('summaryContent');
    
    content.innerHTML = ''; // Clear existing content
    
    const header = document.createElement('h4');
    header.textContent = 'System Message';
    content.appendChild(header);
    
    const messagePre = document.createElement('pre');
    messagePre.textContent = message;
    content.appendChild(messagePre);
    
    popup.classList.add('system-message');
    popup.style.display = 'block';
    
    // Adjust width to fit content
    popup.style.width = 'auto';
    const maxWidth = Math.min(messagePre.scrollWidth + 30, window.innerWidth * 0.8);
    popup.style.width = maxWidth + 'px';
    
    clearTimeout(popupTimeout);
    startPopupTimer();
}

function showSummaryPopup(summary) {
    const popup = document.getElementById('summaryPopup');
    const content = document.getElementById('summaryContent');
    
    content.innerHTML = ''; // Clear existing content
    
    const header = document.createElement('h4');
    header.textContent = 'Call Summary';
    content.appendChild(header);
    
    const summaryPre = document.createElement('pre');
    summaryPre.textContent = summary;
    content.appendChild(summaryPre);
    
    popup.classList.remove('system-message');
    popup.style.width = ''; // Reset to default width
    popup.style.display = 'block';
    
    clearTimeout(popupTimeout);
    startPopupTimer();
}

function startPopupTimer() {
    popupTimeout = setTimeout(() => {
        document.getElementById('summaryPopup').style.display = 'none';
    }, 5000);  // Hide after 5 seconds
}

function processSummary(data) {
    if (data && data.call_summary) {
        showSummaryPopup(data.call_summary);
    }
}

function closePopup() {
    document.getElementById('summaryPopup').style.display = 'none';
    clearTimeout(popupTimeout);
}

function setupPopupListeners() {
    const popup = document.getElementById('summaryPopup');
    const closeButton = popup.querySelector('.close-button');

    closeButton.addEventListener('click', closePopup);

    popup.addEventListener('mouseenter', () => {
        clearTimeout(popupTimeout);
    });

    popup.addEventListener('mouseleave', startPopupTimer);
}

function completeToolCall(id, startTime) {
    const toolCallElement = document.getElementById(id);
    if (toolCallElement) {
        const spinner = toolCallElement.querySelector('.spinner');
        const statusElement = toolCallElement.querySelector('.tool-call-status');
        const completionMessage = toolCallElement.querySelector('.completion-message');
        
        spinner.style.display = 'none';
        statusElement.style.display = 'none';
        
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);
        completionMessage.textContent = `Completed in ${duration}s`;
        completionMessage.style.display = 'block';
    }
}

function formatToolCall(toolCall) {
    const id = 'tool-call-' + Date.now(); // Generate a unique ID
    const isThinking = toolCall.action === "Thinking";
    
    // Define icons
    const wrenchIcon = `
        <svg class="tool-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
    `;

    const brainIcon = `
        <svg class="tool-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 8.5C12 6 10.5 4.5 8.5 4.5S5 6 5 8.5V9c0 1.7-1.3 3-3 3v1c1.7 0 3 1.3 3 3v.5c0 2.5 1.5 4 3.5 4s3.5-1.5 3.5-4V16c0-1.7 1.3-3 3-3v-1c-1.7 0-3-1.3-3-3V8.5z"/>
            <path d="M12 8.5C12 6 13.5 4.5 15.5 4.5S19 6 19 8.5V9c0 1.7 1.3 3 3 3v1c-1.7 0-3 1.3-3 3v.5c0 2.5-1.5 4-3.5 4s-3.5-1.5-3.5-4V16c0-1.7-1.3-3-3-3v-1c1.7 0 3-1.3 3-3V8.5z"/>
            <path d="M12 8c1.5 0 2-1 2-2"/>
            <path d="M12 16c1.5 0 2 1 2 2"/>
        </svg>
    `;

    return `
        <div class="tool-call ${isThinking ? 'thinking' : ''}" id="${id}">
            <div class="tool-call-header">
                <span class="tool-call-action" title="${toolCall.action}">
                    ${isThinking ? brainIcon : wrenchIcon}
                    Action: "${toolCall.action}"
                </span>
                <span class="tool-call-status">
                    <div class="spinner"></div>
                    <span>In progress...</span>
                </span>
            </div>
            <div class="tool-call-input" title="${toolCall.input}">${toolCall.input}</div>
            <div class="completion-message" style="display: none;"></div>
        </div>
    `;
}

function formatToolStart(toolStart) {
    return `
        <div class="tool-start">
            <div class="agent">
                <svg class="tool-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
                </svg>
                <span>Agent: ${toolStart.agent}</span>
            </div>
            <div class="model">Model: ${toolStart.model}</div>
        </div>
    `;
}

function formatError(error) {
    // Escape HTML special characters to prevent XSS
    const escapeHtml = (unsafe) => {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    return `
        <div class="error-message">
            <div class="error-title">Error during code execution:</div>
            <div class="error-content">${escapeHtml(error)}</div>
            <div class="error-footer">Attempting a correction...</div>
        </div>
    `;
}

function formatSessionIds(data) {
    return `<div class="session-ids"><div class="id-row"><span class="id-label">Workflow ID:</span> <span class="id-value">${data.thread_id}</span></div><div class="id-row"><span class="id-label">Chain ID:</span> <span class="id-value">${data.chain_id}</span></div><div class="id-row"><span class="id-label">Dataframe ID:</span> <span class="id-value">${data.df_id || 'N/A'}</span></div></div>`;
}

function createOrUpdateTab(type, data, id = null, format = null) {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    let tab = document.getElementById(`tab-${type}`);
    let tabContent = document.getElementById(`content-${type}`);

    if (!tab) {
        // Create new tab
        tab = document.createElement('div');
        tab.id = `tab-${type}`;
        tab.className = 'tab';
        tab.textContent = type.charAt(0).toUpperCase() + type.slice(1);
        tab.onclick = () => activateTab(type);
        tabContainer.appendChild(tab);

        // Create new tab content
        tabContent = document.createElement('div');
        tabContent.id = `content-${type}`;
        tabContent.className = 'tab-content';
        contentOutput.appendChild(tabContent);
    }

    updateTabContent(type, data, id, format);
    activateTab(type);
}

function submitTask(taskContent) {
    const queryInput = document.getElementById('queryInput');
    queryInput.value = taskContent;
    console.log("Query input value set to:", queryInput.value);
    handleQuerySubmit();
}

// Function to format query data as YAML with section breaks
function formatQueryDataAsYAML(data) {
    const yaml = `
original_question: 
"${data.original_question}"

rephrased_question:
  unknown: "${data.unknown}"
  condition: "${data.condition}"

intent_breakdown: "${data.intent_breakdown}"

confidence: ${data.confidence}
requires_dataset: ${data.requires_dataset}
expert: "${data.expert || 'undefined'}"
`;
    return yaml.trim();
}

function formatResearchData(researchData) {
    if (!Array.isArray(researchData)) {
        console.error('Research data is not an array:', researchData);
        return 'Error: Invalid research data format';
    }

    let formattedContent = '<div class="research-container">';
    researchData.forEach(item => {
        formattedContent += `
            <div class="research-item">
                <h2 class="research-query">${escapeHtml(item.query)}</h2>
                <div class="research-result markdown-content">${marked.parse(escapeHtml(item.result))}</div>
                <h3 class="links-header">Sources</h3>
                <ul class="links-list">
                    ${item.links.map(link => `
                        <li class="link-item">
                            <a href="${escapeHtml(link.link)}" target="_blank" rel="noopener noreferrer" class="link-title">
                                ${escapeHtml(link.title)}
                            </a>
                            <span class="link-url">${escapeHtml(link.link)}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    });
    formattedContent += '</div>';
    return formattedContent;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function updateTabContent(type, data, id = null, format = null) {
    const tabContent = document.getElementById(`content-${type}`);
    let content = '';

    switch(type) {
        case 'dataframe':
            content = data;
            break;
        case 'query':
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            const yamlData = formatQueryDataAsYAML(data);
            content += '<div class="markdown-content yaml-wrapper">' + marked.parse('```yaml\n' + yamlData + '\n```') + '</div>';
            break;
        case 'plan':
        case 'model': {
            const { html, hasDiagram, mermaidSrc } = buildDiagramTab(type, data);
            tabContent.innerHTML = html;
        
            if (hasDiagram) {
                ensureMermaid();
                const host = tabContent.querySelector('.mermaid');
                mermaid.render(`m-${Date.now()}`, mermaidSrc)
                        .then(({ svg }) => host && (host.innerHTML = svg))
                        .catch(err => console.warn('Mermaid render failed:', err));
            }
        
            // highlight YAML, attach scroll handler, etc.
            tabContent.querySelectorAll('pre code').forEach(hljs.highlightElement);
            tabContent.removeEventListener('scroll', handleScroll);
            tabContent.addEventListener('scroll', handleScroll);
        
            return;
        }
        case 'research':
            // Parse JSON for research data
            let parsedResearchData;
            try {
                parsedResearchData = typeof data === 'string' ? JSON.parse(data) : data;
                if (Array.isArray(parsedResearchData)) {
                    content = formatResearchData(parsedResearchData);
                } else {
                    console.error('Research data is not an array:', parsedResearchData);
                    content = 'Error: Invalid research data format';
                }
            } catch (error) {
                console.error('Error parsing research data:', error);
                content = 'Error: Invalid research data format';
            }
            break;
        case 'review':
        case 'vector_db':
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            content += '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            break;
        case 'code':
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            content += `<div class="markdown-content">
                <div class="code-header">
                    <span class="language-label">PYTHON</span>
                    <div class="header-actions">
                        <button class="code-action-button edit-button" title="Edit">
                            <svg class="edit-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                            </svg>
                            <svg class="save-icon" style="display: none" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                                <polyline points="17 21 17 13 7 13 7 21" />
                            </svg>
                        </button>
                        <button class="code-action-button discard-button" style="display: none" title="Discard changes">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                        <button class="code-action-button execute-button" title="Execute">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="5 3 19 12 5 21 5 3" />
                            </svg>
                        </button>
                    </div>
                </div>
                <pre><code class="language-python">${data}</code></pre>
            </div>`;
        
            // Add event listeners after content is added to DOM
            setTimeout(() => {
                const tabContent = document.getElementById(`content-${type}`);
                if (!tabContent) return;
        
                const header = tabContent.querySelector('.code-header');
                const editButton = header.querySelector('.edit-button');
                const discardButton = header.querySelector('.discard-button');
                const executeButton = header.querySelector('.execute-button');
                const editIcon = editButton.querySelector('.edit-icon');
                const saveIcon = editButton.querySelector('.save-icon');
                const preElement = header.nextElementSibling;
                const codeElement = preElement.querySelector('code');
                let originalCode = codeElement.textContent;
        
                // Apply initial syntax highlighting
                hljs.highlightElement(codeElement);
        
                // Function to restore code view with highlighting
                function restoreCodeView(code) {
                    const newPre = document.createElement('pre');
                    const newCode = document.createElement('code');
                    newCode.className = 'language-python';
                    newCode.textContent = code;
                    newPre.appendChild(newCode);
                    
                    const editorWrapper = header.nextElementSibling;
                    editorWrapper.replaceWith(newPre);
                    
                    // Apply syntax highlighting
                    hljs.highlightElement(newCode);
                    
                    // Reset button states
                    editButton.removeAttribute('data-editing');
                    editIcon.style.display = 'block';
                    saveIcon.style.display = 'none';
                    discardButton.style.display = 'none';
                }
        
                editButton.addEventListener('click', () => {
                    const isEditing = editButton.hasAttribute('data-editing');
                    if (!isEditing) {
                        // Enter edit mode
                        const codeBlock = header.nextElementSibling;
                        const currentCode = codeBlock.querySelector('code').textContent;
                        
                        // Create wrapper for CodeMirror
                        const editorWrapper = document.createElement('div');
                        editorWrapper.className = 'code-editor-wrapper';
                        
                        // Get the height of the original code block
                        const codeHeight = codeBlock.offsetHeight;
                        
                        // Replace code block with wrapper
                        codeBlock.replaceWith(editorWrapper);
                        
                        // Initialize CodeMirror
                        const editor = CodeMirror(editorWrapper, {
                            value: currentCode,
                            mode: 'python',
                            theme: 'default',
                            lineNumbers: true,
                            lineWrapping: true,
                            viewportMargin: Infinity,
                            indentUnit: 4,
                            styleActiveLine: true,
                            matchBrackets: true,
                            extraKeys: {
                                Tab: (cm) => cm.replaceSelection('    ', 'end')
                            }
                        });
                        
                        // Set editor height to match original code block
                        editor.setSize(null, codeHeight);
                        
                        // Store editor instance for later access
                        editorWrapper.editor = editor;
                        
                        // Update button states
                        editButton.setAttribute('data-editing', 'true');
                        editIcon.style.display = 'none';
                        saveIcon.style.display = 'block';
                        discardButton.style.display = 'block';
                        
                        // Focus editor
                        editor.focus();
                    } else {
                        // Save changes
                        const editorWrapper = header.nextElementSibling;
                        originalCode = editorWrapper.editor.getValue();
                        restoreCodeView(originalCode);
                    }
                });
        
                discardButton.addEventListener('click', () => {
                    restoreCodeView(originalCode);
                });
        
                executeButton.addEventListener('click', async () => {
                    const editorWrapper = header.nextElementSibling;
                    const currentCode = editorWrapper.editor ? 
                        editorWrapper.editor.getValue() : 
                        editorWrapper.querySelector('code').textContent;
        
                    try {
                        // Clear existing plots before execution
                        const plotTab = document.getElementById('content-plot');
                        if (plotTab) {
                            plotTab.innerHTML = '';
                        }

                        const response = await fetch('/query', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: null,
                                chain_id: currentData.chain_id,
                                thread_id: currentData.thread_id,
                                user_code: currentCode
                            }),
                        });
                        
                        if (!response.ok) throw new Error('Failed to execute code');
                        
                        const reader = response.body.getReader();
                        const decoder = new TextDecoder();
        
                        while (true) {
                            const {done, value} = await reader.read();
                            if (done) break;
                            processChunk(decoder.decode(value));
                        }

                        // Replace the current local storage response at its current index
                        responses[currentResponseIndex] = {
                            tabContent: document.getElementById('tabContainer').innerHTML,
                            contentOutput: document.getElementById('contentOutput').innerHTML,
                            streamOutput: document.getElementById('streamOutput').innerHTML,
                            chain_id: currentData.chain_id,
                            thread_id: currentData.thread_id
                        };

                        // Update localStorage
                        await localforage.setItem('responses', responses);
                    } catch (error) {
                        console.error('Error executing code:', error);
                    }
                });
            }, 0);
            break;
        case 'plot':
            const baseContainer = `
                <div class="plot-container" data-plot-id="${id}">
                    <div class="plot-header">
                        <h3>Plot ${id ? id.split('_')[1] : ''}:</h3>
                        <button class="plot-query-btn" aria-label="Query plot">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="plot-query-form" style="display: none;">
                        <input type="text" class="plot-query-input" placeholder="Enter your query about plot ${id ? id.split('_')[1] : ''}">
                        <button type="submit" class="plot-query-submit">
                            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                            </svg>
                        </button>
                    </div>`;
            
            if (format === 'html') {
                content = `${baseContainer}
                    <div class="plot-content plotly-plot">
                        <div id="plotly-container-${id}"></div>
                    </div>
                </div>`;
                
                setTimeout(() => {
                    const container = document.getElementById(`plotly-container-${id}`);
                    if (container) {
                        container.innerHTML = data;
                        const scripts = container.getElementsByTagName('script');
                        Array.from(scripts).forEach(script => {
                            if (!script.src) {
                                eval(script.textContent);
                            }
                        });
                    }
                }, 100);
            } 
            else if (format === 'json') {
                content = `${baseContainer}
                    <div class="plot-content plotly-plot">
                        <div id="plotly-container-${id}" data-plotly-json="${data.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")}"</div>
                    </div>
                </div>`;
                              
                setTimeout(() => {
                    const container = document.getElementById(`plotly-container-${id}`);
                    if (container) {
                        try {
                            const plotData = JSON.parse(container.dataset.plotlyJson.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"'));
                            Plotly.newPlot(container, plotData.data, plotData.layout, {
                                responsive: true,
                                useResizeHandler: true,
                                displayModeBar: true
                            }).catch(error => {
                                console.error('Plot rendering failed:', error);
                                container.innerHTML = `
                                    <div class="plot-error">
                                        Failed to render plot. Please try refreshing the page.
                                        <br><small>${error.message}</small>
                                    </div>
                                `;
                            });
                        } catch (error) {
                            console.error('Error processing plot data:', error);
                            container.innerHTML = `
                                <div class="plot-error">
                                    Failed to process plot data. Please try refreshing the page.
                                    <br><small>${error.message}</small>
                                </div>
                            `;
                        }
                    }
                }, 100);
            }
            else if (format === 'png') {
                content = `${baseContainer}
                    <div class="plot-content">
                        <img src="data:image/png;base64,${data}" alt="Plot ${id ? id.split('_')[1] : ''}" class="plot-image">
                    </div>
                </div>`;
            }

            break;
        case 'answer': {
            console.log('Processing answer case');
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            
            // First protect LaTeX content
            const { text: protectedContent, placeholders } = protectLatexDelimiters(data);
            
            // Parse markdown
            let parsedContent = marked.parse(protectedContent);
            
            // Process interactive items if needed
            if (answerTabInteractive) {
                // Transform numbered list items into interactive pills
                parsedContent = transformNumberedListToInteractivePills(parsedContent);
                
                // Reset the interactive flag after processing
                answerTabInteractive = false;
            }
            
            // Restore LaTeX content
            const finalContent = restoreLatexDelimiters(parsedContent, placeholders);
            
            // Add the content to the DOM
            content += '<div class="markdown-content">' + finalContent + '</div>';
            
            // Queue LaTeX rendering after content is in DOM
            setTimeout(() => {
                const contentElement = document.querySelector(`#content-${type} .markdown-content`);
                if (contentElement) {
                    renderLatex(contentElement);
                    
                    // Add event listeners to the interactive pills if they exist
                    attachPillEventListeners(contentElement);
                }
            }, 100);
            
            break;
        }   
        default:
            console.log(`Unknown data type: ${type}`);
            return;
    }

    if (type === 'plot' && id) {
        // For plots, we append new plots instead of replacing
        tabContent.innerHTML += content;
        // Get ALL plot containers and attach listeners to each one
        const plotContainers = tabContent.querySelectorAll('.plot-container');
        plotContainers.forEach(container => {
            attachPlotQueryListeners(container);
        });
    } else {
        tabContent.innerHTML = content;
        if (type === 'plot') {
            const allPlotContainers = tabContent.querySelectorAll('.plot-container');
            allPlotContainers.forEach(container => {
                attachPlotQueryListeners(container);
            });
        }
    }
  
    // Highlight code blocks
    if (['query', 'model', 'plan', 'code', 'mermaid'].includes(type)) {
        tabContent.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightBlock(block);
        });
    }
    // Add listener to update highlights on scroll
    tabContent.removeEventListener('scroll', handleScroll);
    tabContent.addEventListener('scroll', handleScroll);
    console.log('Scroll listener added for', type, 'tab');
}

// Function to build the tabs like plan and model that include mermaid diagrams
function buildDiagramTab(type, data) {
    // normalise + validate
    const mermaidSrc = typeof data?.visualization === 'string'
                       ? data.visualization.trim()
                       : '';
    const hasDiagram =
          mermaidSrc !== '' && !/\[object Object\]/.test(mermaidSrc);
  
    // YAML is required; fall back to stringified object
    const yamlBlock = data?.yaml ??
                      (typeof data === 'string'
                        ? data
                        : JSON.stringify(data, null, 2));
  
    // header (Plan: / Model:)
    let html = `<h3>${type[0].toUpperCase() + type.slice(1)}:</h3>`;
  
    // diagram or notice
    if (hasDiagram) {
      html += `
        <div class="diagram-container">
          <button class="view-toggle" title="Toggle syntax">
            <svg class="code-icon" width="16" height="16" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
          </button>
  
          <div class="mermaid-view"><div class="mermaid">${mermaidSrc}</div></div>
  
          <div class="syntax-view" hidden>
            <div class="code-header">
              <span class="language-label">MERMAID</span>
              <button class="copy-button" title="Copy code">
                <svg class="copy-icon" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <svg class="check-icon" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" style="display:none">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </button>
            </div>
            <pre><code>${mermaidSrc}</code></pre>
          </div>
        </div>`;
    } else {
      html += `
        <p class="size-error-notice">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path fill="none" stroke="currentColor" stroke-linecap="round"
                  stroke-linejoin="round" stroke-width="2"
                  d="M12 9v2m0 4h.01M5.062 19h13.876c1.54 0 2.502-1.667
                  1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16
                  c-.77 1.333.192 3 1.722 3z"/>
          </svg>
          Diagram visualisation not available – YAML shown below.
        </p>`;
    }
  
    // YAML section
    html += `<div class="markdown-content">${
        marked.parse(`\`\`\`yaml\n${yamlBlock}\n\`\`\``)
    }</div>`;
  
    return { html, hasDiagram, mermaidSrc };
}

function ensureMermaid() {
    if (!mermaidReady) {
        mermaid.initialize({ startOnLoad: false, ...mermaidTheme });
        mermaidReady = true;
    }
}

function activateTab(type) {
    const tabs = document.getElementsByClassName('tab');
    const tabContents = document.getElementsByClassName('tab-content');

    for (let i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove('active');
        tabContents[i].classList.remove('active');
    }

    const activeTab = document.getElementById(`tab-${type}`);
    const activeContent = document.getElementById(`content-${type}`);

    if (activeTab && activeContent) {
        activeTab.classList.add('active');
        activeContent.classList.add('active');
    } else {
        console.warn(`Tab or content for type "${type}" not found`);
    }
}

function clearAllTabs() {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    tabContainer.innerHTML = '';
    contentOutput.innerHTML = '';
}

function showRankModal() {
    if (currentRankData) {
        const modal = document.getElementById('rankModal');
        const submitButton = document.getElementById('submit-rank');
        const statusMessage = document.getElementById('rankStatusMessage');
        
        // Reset modal state when showing
        submitButton.disabled = false;
        statusMessage.textContent = '';
        statusMessage.style.display = 'none';
        statusMessage.style.color = '#35c477'; // Reset color to default
        
        modal.style.display = 'flex';
    }
}

function closeRankModal() {
    const modal = document.getElementById('rankModal');
    modal.style.display = 'none';
}

function submitRank() {
    const starRating = document.getElementById('starRating');
    const selectedStar = starRating.querySelector('input[name="rating"]:checked');
    // Ensure userRank is a number
    const userRank = selectedStar ? parseInt(selectedStar.value, 10) : null;
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

    // Start the submission process
    submitButton.disabled = true;
    statusMessage.textContent = "Storing your rating...";
    statusMessage.style.display = 'block';
    statusMessage.style.color = '#35c477'; // Green status for processing

    console.log('Current rank data:', currentRankData);

    // Step 1: Submit to vector DB
    fetch('/submit_rank', {
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
                            if (userRank >= 8) {
                                storeInFavorites(userRank, statusMessage, submitButton, starRating);
                            } else {
                                // For ranks < 8, just close the modal after vector DB response
                                setTimeout(() => {
                                    closeRankModal();
                                    document.getElementById('rankButton').style.display = 'none';
                                    statusMessage.textContent = '';
                                    statusMessage.style.display = 'none';
                                    submitButton.disabled = false;
                                    if (selectedStar) selectedStar.checked = false;
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

// Helper function to store chain in favorites
async function storeInFavorites(userRank, statusMessage, submitButton, starRating) {
    // Step 2: Get current responses from localStorage
    let responses;
    try {
        // Use the variable we actually have - no need to parse
        responses = await localforage.getItem('responses');
        
        if (!responses || !Array.isArray(responses)) {
            throw new Error('No valid responses found in storage');
        }
    } catch (error) {
        console.error('Error loading responses:', error);
        statusMessage.textContent = `Error: ${error.message}. Unable to save to favorites.`;
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        return;
    }

    // Step 3: Validate thread_id and chain_id
    const threadId = currentData.thread_id;
    const chainId = currentData.chain_id;

    if (!threadId || !chainId) {
        statusMessage.textContent = "Error: Missing thread or chain ID.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        return;
    }
    
    // Step 4: Find the index of the response that matches both IDs
    const index = responses.findIndex(response => 
        response && response.thread_id === threadId && response.chain_id === chainId
    );

    if (index === -1) {
        // Debug output if no matching response found
        console.error('No matching response found. Available responses:', 
            responses.map(r => ({ thread: r.thread_id, chain: r.chain_id })));
        statusMessage.textContent = "Error: Could not find matching response data.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        return;
    }

    const chainData = responses[index];
    
    // Step 5: Validate chainData structure and ensure we have all required fields
    if (!chainData) {
        statusMessage.textContent = "Error: Chain data is null or undefined.";
        statusMessage.style.color = '#ff0000';
        submitButton.disabled = false;
        return;
    }

    // Create content object with safeguards for missing properties
    const content = {
        tabContent: chainData.tabContent || '',
        contentOutput: chainData.contentOutput || '',
        streamOutput: chainData.streamOutput || '',
        taskContents: chainData.taskContents || {}
    };

    // Extract the intent_breakdown from the Query tab content
    let task = '';
    try {
        // Find the Query tab content
        const contentOutput = document.getElementById('contentOutput');
        const queryTab = contentOutput.querySelector('#content-query');
        
        if (queryTab) {
            // Try to find the intent_breakdown text in the query tab
            const intentText = queryTab.innerHTML.match(/intent_breakdown:\s*"([^"]*)"/);
            if (intentText && intentText[1]) {
                task = intentText[1].trim();
            } else {
                console.warn('Could not find intent_breakdown in Query tab');
                
                // Alternative: try to extract from YAML content
                const yamlContent = queryTab.querySelector('.yaml-wrapper');
                if (yamlContent) {
                    const yamlText = yamlContent.textContent;
                    const intentMatch = yamlText.match(/intent_breakdown:\s*"([^"]*)"/);
                    if (intentMatch && intentMatch[1]) {
                        task = intentMatch[1].trim();
                    }
                }
            }
        } else {
            console.warn('Query tab not found');
        }
    } catch (error) {
        console.error('Error extracting task information:', error);
        // Continue with empty task rather than failing
    }

    // Step 7: Send to favourites endpoint
    fetch('/storage/favourites', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            thread_id: threadId,
            chain_id: chainId,
            dataset_name: currentDatasetName,
            index: index,
            rank: userRank,
            task: task,  // Added task field
            content: content
        }),
    })
    .then(response => {
        // Enhanced error handling
        if (!response.ok) {
            // Try to get detailed error from server
            return response.json().then(errData => {
                console.error('Server error details:', errData);
                throw new Error(errData.error || `Server responded with status: ${response.status}`);
            }).catch(e => {
                if (e instanceof SyntaxError) {
                    // If the response is not valid JSON
                    throw new Error(`Server responded with status: ${response.status}`);
                }
                throw e;
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        statusMessage.textContent = "Solution added to favourites!";
        statusMessage.style.color = '#35c477';
    })
    .catch(error => {
        console.error('Error saving to favourites:', error);
        statusMessage.textContent = `Error saving to favourites: ${error.message}`;
        statusMessage.style.color = '#ff0000';
    })
    .finally(() => {
        // Clean up regardless of outcome
        setTimeout(() => {
            closeRankModal();
            document.getElementById('rankButton').style.display = 'none';
            statusMessage.textContent = '';
            statusMessage.style.display = 'none';
            submitButton.disabled = false;
            const checkedStar = starRating.querySelector('input[name="rating"]:checked');
            if (checkedStar) checkedStar.checked = false;
        }, 2000);
    });
}

// Helper function to protect LaTeX from markdown processing
function protectLatexDelimiters(text) {
    // Create temporary placeholders for LaTeX content
    let counter = 0;
    const placeholders = [];

    // Helper function to replace LaTeX content with placeholders
    function replacer(match) {
        const placeholder = `LATEXPLACEHOLDER${counter}`;
        placeholders.push({ placeholder, content: match });
        counter++;
        return placeholder;
    }

    // More permissive patterns that better handle whitespace
    const patterns = [
        // Display math mode with escaped brackets
        /\\\[[^\]]*?\\\]/gs,
        // Inline math mode with escaped parentheses - more permissive pattern
        /\\\([^]*?\\\)/gs,
        // Display math mode with double dollars
        /\$\$[^]*?\$\$/gs,
        // Inline math mode with single dollars - more careful with boundaries
        /\$[^$\n]+?\$/g
    ];

    let protectedText = text;
    patterns.forEach(pattern => {
        protectedText = protectedText.replace(pattern, replacer);
    });

    return { text: protectedText, placeholders };
}

// Helper function to restore LaTeX content
function restoreLatexDelimiters(text, placeholders) {
    let restoredText = text;
    for (const { placeholder, content } of placeholders) {
        restoredText = restoredText.replace(placeholder, content);
    }
    return restoredText;
}

// Function to safely render LaTeX in an element
function renderLatex(element) {
    if (!element) return;
    
    renderMathInElement(element, {
        delimiters: [
            {left: "\\[", right: "\\]", display: true},
            {left: "\\(", right: "\\)", display: false},
            {left: "$$", right: "$$", display: true},
            {left: "$", right: "$", display: false}
        ],
        throwOnError: false,
        output: 'html',
        strict: false,
        trust: true,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
        errorCallback: function(msg) {
            console.warn('KaTeX error:', msg);
        }
    });
}

// Function to initialize the threads UI in the menu
function initializeThreadsUI() {
    const menuPopup = document.querySelector('.menu-popup');
    
    if (!menuPopup) {
        console.error('Menu popup element not found');
        return;
    }
    
    // Check if threads section already exists (to avoid duplicating)
    if (document.querySelector('.threads-header')) {
        console.log('Threads UI already initialized');
        return;
    }
    
    // Create and append the divider and header
    const dividerAndHeaderHTML = `
        <hr class="menu-divider">
        <h3 class="threads-header">Workflows:</h3>
        <div id="threads-list" class="threads-list">
            <div class="thread-loading">Loading workflows...</div>
        </div>
    `;
    
    menuPopup.insertAdjacentHTML('beforeend', dividerAndHeaderHTML);
    
    // Load threads from the backend
    loadThreadsList();
    
    console.log('Threads UI initialized');
}

// Function to load threads from the backend
function loadThreadsList() {
    const threadsList = document.getElementById('threads-list');
    
    if (!threadsList) {
        console.error('Threads list element not found');
        return;
    }
    
    // Show loading indicator
    threadsList.innerHTML = '<div class="thread-loading">Loading threads...</div>';
    
    // Fetch threads from the backend
    fetch('/get_threads')
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
            
            // Render the threads
            renderThreadsList(data.threads);
        })
        .catch(error => {
            console.error('Error loading threads:', error);
            threadsList.innerHTML = `<div class="no-threads">Error loading threads: ${error.message}</div>`;
        });
}

// Function to render the threads list
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

// Helper function to create a thread item
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
    
    // Create thread item container
    const threadItem = document.createElement('div');
    threadItem.className = isLatest ? 'thread-item' : 'thread-item chain-item';
    threadItem.setAttribute('data-thread-id', chain.thread_id);
    threadItem.setAttribute('data-chain-id', chain.chain_id);
    threadItem.setAttribute('data-dataset-name', chain.dataset_name);
    
    // Add timestamp
    const timestamp = document.createElement('span');
    timestamp.className = 'thread-timestamp';
    timestamp.textContent = formattedTimestamp;
    threadItem.appendChild(timestamp);
    
    // Add Thread ID only for the latest/main thread item (not for chain items)
    if (isLatest) {
        const threadId = document.createElement('span');
        threadId.className = 'thread-id';
        threadId.textContent = `Thread: ${chain.thread_id}`;
        threadItem.appendChild(threadId);

        const datasetName = document.createElement('span');
        datasetName.className = 'thread-dataset-name';
        datasetName.textContent = `Dataset: ${chain.dataset_name || 'None'}`;
        threadItem.appendChild(datasetName);
    }
    
    // Add task text with limited height
    const taskText = document.createElement('div');
    taskText.className = 'thread-task';
    taskText.textContent = chain.task || `Chain ${chain.chain_id}`;
    threadItem.appendChild(taskText);
    
    // Add delete button
    const deleteButton = document.createElement('button');
    deleteButton.className = 'thread-delete-btn';
    deleteButton.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path></svg>';
    deleteButton.title = 'Delete from favorites';
    
    // Add click handler for delete button
    deleteButton.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent opening the thread when clicking delete
        
        const threadId = chain.thread_id;
        const chainId = chain.chain_id;
        
        // Confirm deletion
        if (confirm(`Are you sure you want to delete this chain from favorites?`)) {
            deleteChain(threadId, chainId, threadItem);
        }
    });
    
    threadItem.appendChild(deleteButton);
    
    // Add click event listener for the thread item
    threadItem.addEventListener('click', () => {
        // Load the thread content
        loadThreadContent(chain.thread_id, chain.chain_id);
        
        // Close the menu and overlay when chain is clicked
        toggleMenu(false);
        
        // Make sure menu popup is completely hidden
        const menuPopup = document.querySelector('.menu-popup');
        if (menuPopup) {
            menuPopup.classList.remove('active');
            menuPopup.style.display = 'none';
        }
    });

   // After creating the threadItem element, add mouseover and mouseout events
   threadItem.addEventListener('mouseenter', function(e) {
        const threadId = this.getAttribute('data-thread-id');
        const chainId = this.getAttribute('data-chain-id');
        
        // Initialize preview element
        initializePreviewElement();
        
        // Position the preview element
        const rect = this.getBoundingClientRect();
        previewElement.style.top = `${rect.top + window.scrollY}px`;
        previewElement.style.left = `${rect.right + window.scrollX + 10}px`;
        
        // Show loading state
        previewElement.innerHTML = '<div class="preview-loading">Loading preview...</div>';
        previewElement.style.display = 'block';
        
        // Fetch and show the preview
        getChainPreview(threadId, chainId).then(data => {
            if (data && data.hasPlotly) {
                previewElement.innerHTML = '';
                const plotContainer = renderPlotlyPreview(data.plotlyData);
                previewElement.appendChild(plotContainer);
            } else {
                previewElement.innerHTML = '<div class="preview-error">No preview available</div>';
            }
        }).catch(() => {
            previewElement.innerHTML = '<div class="preview-error">Error loading preview</div>';
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

// Function to delete a chain
function deleteChain(threadId, chainId, element) {
    fetch(`/delete_chain/${threadId}/${chainId}`, {
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

// Function to toggle showing/hiding chains
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

// Function to check for text overflow and add appropriate class
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

// Function to load a thread's content
async function loadThreadContent(threadId, chainId) {
    console.log(`Loading thread ${threadId} with chain ${chainId}`);
    
    // Show loading indicator
    const streamOutput = document.getElementById('streamOutput');
    if (streamOutput) {
        streamOutput.innerHTML = '<div>Loading thread content...</div>';
    }
    
    try {
        // Fetch thread content from the backend
        const response = await fetch(`/load_thread/${threadId}/${chainId}`);
        
        if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update global variables
        currentData.thread_id = threadId;
        currentData.chain_id = chainId;
        
        // Replace localStorage content with localforage
        await localforage.setItem('responses', data.responses);
        
        // Set the current response index to the last response
        responses = data.responses;
        currentResponseIndex = responses.length - 1;
        
        // Load the content
        loadResponseContent(responses[currentResponseIndex]);
        
        // Update navigation buttons
        updateNavigationButtons();
        
        console.log(`Thread ${threadId} loaded successfully`);
    } catch (error) {
        console.error('Error loading thread content:', error);
        if (streamOutput) {
            streamOutput.innerHTML = `<div class="error">Error loading thread content: ${error.message}</div>`;
        }
    }
}

// Function to initialize the menu overlay
function initializeMenuOverlay() {
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
        toggleMenu(true);
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
    
    console.log('Menu overlay initialized');
}

// Function to toggle the menu and overlay
function toggleMenu(show) {
    const menuPopup = document.querySelector('.menu-popup');
    const overlay = document.querySelector('.menu-overlay');
    
    if (!menuPopup || !overlay) {
        console.error('Menu elements not found');
        return;
    }
    
    if (show) {
        menuPopup.classList.add('active');
        menuPopup.style.display = 'flex';
        overlay.classList.add('active');
        
        // Load threads when opening the menu
        loadThreadsList();
    } else {
        menuPopup.classList.remove('active');
        overlay.classList.remove('active');
        
        // Add a slight delay before hiding completely to allow for the transition effect
        setTimeout(() => {
            if (!menuPopup.classList.contains('active')) {
                menuPopup.style.display = 'none';
            }
        }, 200); // Match this to your CSS transition duration
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

// Function to get preview data for a chain
function getChainPreview(threadId, chainId) {
    return fetch(`/get_chain_preview/${threadId}/${chainId}`)
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

// Function to render a static image preview from Plotly data
function renderPlotlyPreview(plotlyData) {
    // Create container
    const previewContainer = document.createElement('div');
    previewContainer.className = 'plotly-preview-container';
    
    try {
        // Parse the data
        const plotData = JSON.parse(plotlyData);
        
        // Create a temporary div for generating the image
        const tempPlot = document.createElement('div');
        tempPlot.style.width = '800px';  // Larger size for quality
        tempPlot.style.height = '500px';
        tempPlot.style.position = 'absolute';
        tempPlot.style.left = '-9999px';  // Off-screen
        document.body.appendChild(tempPlot);
        
        // Create the plot at higher resolution
        Plotly.newPlot(
            tempPlot, 
            plotData.data, 
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
            Plotly.purge(tempPlot);
            document.body.removeChild(tempPlot);
            
            // Create image element with the URL
            const img = document.createElement('img');
            img.src = imgUrl;
            img.style.width = '100%';
            img.style.height = 'auto';
            img.style.maxHeight = '100%';
            img.alt = 'Plot preview';
            
            // Add to container
            previewContainer.appendChild(img);
        }).catch(err => {
            console.error('Error generating image:', err);
            previewContainer.innerHTML = '<div class="preview-error">Error creating preview</div>';
            
            // Clean up if needed
            if (document.body.contains(tempPlot)) {
                document.body.removeChild(tempPlot);
            }
        });
    } catch (e) {
        console.error('Error with plot data:', e);
        previewContainer.innerHTML = '<div class="preview-error">Error parsing plot data</div>';
    }
    
    return previewContainer;
}

// Helper function to update ontology state
function updateOntologyState(file) {
    const formData = new FormData();
    if (file) {
        formData.append('ontology_file', file);
    } else {
        formData.append('ontology_path', ''); // Send empty string to clear
    }

    fetch('/update_ontology', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Ontology state updated:', data);
        const ontologySwitch = document.getElementById('ontologySwitch');
        if (data.current_state) {
            ontologySwitch.classList.add('active');
        } else {
            ontologySwitch.classList.remove('active');
        }
    })
    .catch(error => {
        console.error('Error updating ontology state:', error);
        const ontologySwitch = document.getElementById('ontologySwitch');
        ontologySwitch.classList.remove('active');
    });
}

// Function to transform a numbered list into interactive pills
function transformNumberedListToInteractivePills(htmlContent) {
    // Create a temporary container to manipulate the HTML
    const tempContainer = document.createElement('div');
    tempContainer.innerHTML = htmlContent;
    
    // Find all ordered lists that might contain the numbered items
    const orderedLists = tempContainer.querySelectorAll('ol');
    
    // Process each list
    orderedLists.forEach(list => {
        // Create a container for the interactive pills
        const pillsContainer = document.createElement('div');
        pillsContainer.className = 'interactive-pills-container';
        
        // Process each list item
        const listItems = list.querySelectorAll('li');
        listItems.forEach((item, index) => {
            // Extract the clean text content for data-query
            const rawQuery = item.textContent.trim();
            // Store a clean version of the query without nested quotes
            const cleanQuery = rawQuery.replace(/['"]/g, '').replace(/\s+/g, ' ').trim();
            
            // Create a pill element
            const pill = document.createElement('div');
            pill.className = 'interactive-pill';
            // Store sanitized query as data attribute
            pill.setAttribute('data-query', cleanQuery);
            pill.innerHTML = `
                <span class="pill-number">${index + 1}</span>
                <span class="pill-content">${item.innerHTML}</span>
                <span class="pill-icon">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </span>
            `;
            
            pillsContainer.appendChild(pill);
        });
        
        // Replace the original list with our pills container
        list.parentNode.replaceChild(pillsContainer, list);
    });
    
    return tempContainer.innerHTML;
}

// Function to attach event listeners to interactive pills
function attachPillEventListeners(contentElement) {
    const pills = contentElement.querySelectorAll('.interactive-pill');
    
    pills.forEach(pill => {
        pill.addEventListener('click', function() {
            const query = this.getAttribute('data-query');
            
            // Set the query to the input field
            const queryInput = document.getElementById('queryInput');
            if (queryInput) {
                queryInput.value = query;
                
                // Submit the query
                handleQuerySubmit();
                
                // Scroll to the top of the output area
                const streamOutput = document.getElementById('streamOutput');
                if (streamOutput) {
                    streamOutput.scrollTop = 0;
                }
            }
        });
    });
}