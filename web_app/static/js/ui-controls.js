//--------------------
//  UI CONTROLS MODULE
//--------------------

function initializeUIControls() {
    console.log('Initializing UI controls...');
    
    initializeScrollBehavior();
    initializeMenuOverlay();
    initializePanelCollapse();
    initializeNavigationButtons();
    initializePlanningSwitch();
    initializeSuggestQuestions();
    initializeTextareaResize();
    initializeKeyboardShortcuts();
    
    console.log('UI controls initialized');
}

//--------------------
//  SCROLL BEHAVIOR
//--------------------

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

//--------------------
//  MENU SYSTEM
//--------------------

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
        
        // Initialize threads UI first, then load threads when opening the menu
        if (typeof initializeThreadsUI === 'function') {
            initializeThreadsUI();
        }
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
        navContainer.style.display = 'block';
        prevButton.disabled = currentResponseIndex <= 0;
        nextButton.disabled = currentResponseIndex >= responses.length - 1;
    }

    console.log('Navigation buttons updated:', {
        prevDisabled: prevButton.disabled,
        nextDisabled: nextButton.disabled
    });
}

//--------------------
//  PLANNING SWITCH
//--------------------

function initializePlanningSwitch() {
    const planningSwitch = document.getElementById('planningSwitch');
    
    if (!planningSwitch) {
        console.warn('Planning switch element not found');
        return;
    }
    
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
}

//--------------------
//  SUGGEST QUESTIONS
//--------------------

function initializeSuggestQuestions() {
    const suggestQuestions = document.getElementById('suggestQuestions');
    
    if (!suggestQuestions) {
        console.warn('Suggest questions element not found');
        return;
    }
    
    suggestQuestions.addEventListener('click', function() {
        const queryInput = document.getElementById('queryInput');
        if (!queryInput) return;
        
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
        
        if (typeof handleQuerySubmit === 'function') {
            handleQuerySubmit();
        }
        answerTabInteractive = true;
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
        const newHeight = Math.max(60, this.scrollHeight); // Don't go below 60px
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
}

//--------------------
//  NEW CONVERSATION
//--------------------

async function handleNewConversation() {
    try {
        const response = await fetch('/new_conversation', {
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
        
        // Clear local JS state variables
        responses = [];
        await localforage.removeItem('responses');
        currentResponseIndex = -1;
        currentDatasetName = null; 
        auxiliaryDatasetCount = 0; 

        currentOntologyState.isActive = false;
        currentOntologyState.fileName = null;
        currentOntologyState.pillId = null;

        // Clear the visual pills container
        const pillsContainer = document.getElementById('datasetStatusPillsContainer');
        if (pillsContainer) {
            pillsContainer.innerHTML = ''; 
        }

        updateNavigationButtons();
        
        // Reload the page with a flag indicating new conversation
        window.location.href = window.location.pathname + '?new=true';
    } catch (error) {
        console.error('Error starting new conversation:', error);
        alert('Error starting new conversation: ' + error.message);
    }
}