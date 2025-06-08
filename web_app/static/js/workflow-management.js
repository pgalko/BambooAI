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
    // Clean up event listeners when the page is unloaded
    window.addEventListener('unload', () => {
        console.log('Cleaning up workflow management...');
        localforage.removeItem('responses');
    });

    // Clear localStorage on tab close
    window.addEventListener('beforeunload', function() {
        localforage.removeItem('responses');
    });
}

function handlePageLoad() {
    const urlParams = new URLSearchParams(window.location.search);
    const streamOutputDiv = document.getElementById('streamOutput');
    
    // Check if this is a page refresh
    if (performance.navigation.type === 1) {
        console.log('This is a page refresh');
        // Clear the storage first before handling a new conversation
        localforage.removeItem('responses')
            .then(() => {
                console.log('Storage cleared on refresh');
                if (typeof handleNewConversation === 'function') {
                    handleNewConversation();
                }
            })
            .catch(err => {
                console.error('Error clearing storage on refresh:', err);
                if (typeof handleNewConversation === 'function') {
                    handleNewConversation();
                }
            });
    } else {
        // Check if we are coming from a new conversation
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
}

async function saveCurrentResponse() {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    const streamOutput = document.getElementById('streamOutput');
    
    // Simple tracking of parent-child relationship
    const newResponse = {
        tabContent: tabContainer.innerHTML,
        contentOutput: contentOutput.innerHTML,
        streamOutput: streamOutput.innerHTML,
        taskContents: taskContents,
        chain_id: currentData.chain_id || null,
        thread_id: currentData.thread_id || null,
        parentChainId: lastActiveChainId, // Store parent relationship
        queryText: currentData.queryText || 'No query'  // Store the query text
    };
    
    // Update lastActiveChainId for next interaction
    lastActiveChainId = currentData.chain_id || null;
    
    responses.push(newResponse);
    currentResponseIndex = responses.length - 1;

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
            if (typeof activateTab === 'function') {
                activateTab(tab.id.split('-')[1]);
            }
        };
    }

    // Re-render answer content if there's an answer tab
    const answerTab = document.getElementById('content-answer');
    if (answerTab) {
        const markdownContent = answerTab.querySelector('.markdown-content');
        if (markdownContent && typeof updateTabContent === 'function') {
            updateTabContent('answer', markdownContent.innerHTML);
        }
    }

    // Trigger the code case initialization if there's a code tab
    const codeTab = document.getElementById('content-code');
    if (codeTab && typeof updateTabContent === 'function') {
        updateTabContent('code', codeTab.querySelector('code').textContent);
    }

    // Trigger the dataframe case initialization if there's a dataframe tab
    const dataframeTab = document.getElementById('content-dataframe');
    if (dataframeTab) {
        const tableElement = dataframeTab.querySelector('table.dataframe');
        if (tableElement && typeof updateTabContent === 'function') {
            updateTabContent('dataframe', tableElement.outerHTML);
        }
    }

    // Reattach plot query listeners and plotly scripts if there's a plot tab
    const plotTab = document.getElementById('content-plot');
    if (plotTab) {
        if (typeof attachPlotQueryListeners === 'function') {
            attachPlotQueryListeners(plotTab);
        }

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
    
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            workflowMapModal.style.display = 'none';
        });
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
    const workflowMapModal = document.getElementById('workflowMapModal');
    const workflowMapContainer = document.getElementById('workflowMapContainer');
    const nodeTaskContent = document.getElementById('nodeTaskContent');
    const nodePlotPreview = document.getElementById('nodePlotPreview');
    
    workflowMapContainer.innerHTML = '<div class="loading-indicator">Generating workflow map...</div>';
    nodeTaskContent.innerHTML = 'Hover over a node to view details';
    nodePlotPreview.innerHTML = '<div class="plot-preview-message">Plot previews will appear here if available</div>';
    workflowMapModal.style.display = 'flex';
    
    // Simple mermaid diagram generation
    let diagram = 'flowchart TD\n';
    
    // Add nodes with query text and chain ID
    responses.forEach((response, index) => {
        const nodeId = `node${index}`;
        
        // Get query text from the response or use a fallback
        let queryText = response.queryText || 'No query';
        
        // Trim if too long (30 chars max)
        if (queryText.length > 30) {
            queryText = queryText.substring(0, 27) + '...';
        }
        
        // Format node text with query and chain ID
        const nodeText = `${queryText}<br>Chain ID: ${response.chain_id || 'N/A'}`;
        
        // Add node to diagram
        diagram += `    ${nodeId}["${nodeText}"]\n`;
    });
    
    // Add edges for parent-child relationships
    responses.forEach((response, index) => {
        if (response.parentChainId) {
            const parentIndex = responses.findIndex(r => 
                r.chain_id === response.parentChainId);
            
            if (parentIndex >= 0) {
                diagram += `    node${parentIndex} --> node${index}\n`;
            }
        }
    });
    
    // Highlight current node
    diagram += `    style node${currentResponseIndex} fill:#4CAF50,stroke:#388E3C,color:white,stroke-width:2px\n`;
    
    // Add clickable class to all nodes - generate dynamically based on responses length
    diagram += '    classDef clickable cursor:pointer;\n';
    
    // Dynamically generate node list
    if (responses.length > 0) {
        const nodeList = Array.from({length: Math.min(responses.length, 30)}, (_, i) => `node${i}`).join(',');
        diagram += `    class ${nodeList} clickable;\n`;
    }
    
    // Render the diagram
    ensureMermaid();
    mermaid.render(`workflow-${Date.now()}`, diagram)
        .then(({ svg }) => {
            workflowMapContainer.innerHTML = svg;
            
            // Extract task and original question for each node
            const nodeContents = responses.map((response, index) => {
                return extractTaskFromResponse(response);
            });
            
            // Extract plot data for each response (if available)
            const nodePlots = responses.map((response) => {
                return extractPlotDataFromResponse(response);
            });
            
            // Add hover and click handlers to nodes
            setTimeout(() => {
                const nodes = workflowMapContainer.querySelectorAll('g.node');
                nodes.forEach((node) => {
                    // Extract the index from the node id
                    const match = node.id.match(/flowchart-node(\d+)/);
                    if (match) {
                        const index = parseInt(match[1]);
                        
                        // Add hover handler
                        node.addEventListener('mouseenter', function() {
                            if (index >= 0 && index < responses.length) {
                                const nodeContent = nodeContents[index];
                                
                                // Build the content HTML
                                let contentHtml = '';
                                
                                if (nodeContent.task && nodeContent.task !== 'null' && nodeContent.task.trim() !== '') {
                                    // If task (intent_breakdown) is available and not "null", display it
                                    contentHtml = nodeContent.task;
                                } else if (nodeContent.originalQuestion && nodeContent.originalQuestion.trim() !== '') {
                                    // Use original_question as fallback, truncated to 200 characters
                                    if (nodeContent.originalQuestion.length > 200) {
                                        contentHtml = nodeContent.originalQuestion.substring(0, 200) + '...';
                                    } else {
                                        contentHtml = nodeContent.originalQuestion;
                                    }
                                } else {
                                    // If neither is available
                                    contentHtml = 'No content available for this node';
                                }
                                
                                // Update the task content area
                                nodeTaskContent.innerHTML = contentHtml;
                                
                                // Show plot preview if available
                                const plotData = nodePlots[index];
                                if (plotData) {
                                    nodePlotPreview.innerHTML = '';
                                    try {
                                        const plotContainer = renderPlotlyPreview(plotData);
                                        nodePlotPreview.appendChild(plotContainer);
                                    } catch (err) {
                                        console.error('Error rendering plot preview:', err);
                                        nodePlotPreview.innerHTML = '<div class="plot-preview-message">Error rendering plot preview</div>';
                                    }
                                } else {
                                    nodePlotPreview.innerHTML = '<div class="plot-preview-message">No plot available for this node</div>';
                                }
                            }
                        });
                        
                        // Add click handler
                        node.addEventListener('click', function() {
                            // Navigate to this response
                            if (index >= 0 && index < responses.length) {
                                currentResponseIndex = index;
                                
                                // Update lastActiveChainId to current chain_id
                                lastActiveChainId = responses[index].chain_id || null;
                                
                                loadResponseContent(responses[currentResponseIndex]);
                                if (typeof updateNavigationButtons === 'function') {
                                    updateNavigationButtons();
                                }
                                
                                // Close the modal
                                workflowMapModal.style.display = 'none';
                            }
                        });
                    }
                });
            }, 100);
        })
        .catch(err => {
            console.error('Mermaid render error:', err);
            workflowMapContainer.innerHTML = `<div class="error">Error generating workflow map: ${err.message}</div>`;
        });
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
    try {
        // Create a temporary div to parse HTML content
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = response.contentOutput || '';
        
        // Look for the Query tab content
        const queryTab = tempDiv.querySelector('#content-query');
        if (!queryTab) return { task: null, originalQuestion: null };
        
        let task = null;
        let originalQuestion = null;
        
        // Try to find the intent_breakdown text in the query tab
        const intentText = queryTab.innerHTML.match(/intent_breakdown:\s*"([^"]*)"/);
        if (intentText && intentText[1]) {
            task = intentText[1].trim();
        }
        
        // Try to find the original_question text in the query tab
        const originalQuestionText = queryTab.innerHTML.match(/original_question:\s*"([^"]*)"/);
        if (originalQuestionText && originalQuestionText[1]) {
            originalQuestion = originalQuestionText[1].trim();
        }
        
        // If we didn't find them in HTML, try extracting from YAML content
        if (!task || !originalQuestion) {
            const yamlContent = queryTab.querySelector('.yaml-wrapper');
            if (yamlContent) {
                const yamlText = yamlContent.textContent;
                
                if (!task) {
                    const intentMatch = yamlText.match(/intent_breakdown:\s*"([^"]*)"/);
                    if (intentMatch && intentMatch[1]) {
                        task = intentMatch[1].trim();
                    }
                }
                
                if (!originalQuestion) {
                    const originalQuestionMatch = yamlText.match(/original_question:\s*"([^"]*)"/);
                    if (originalQuestionMatch && originalQuestionMatch[1]) {
                        originalQuestion = originalQuestionMatch[1].trim();
                    }
                }
            }
        }
        
        return { task, originalQuestion };
    } catch (error) {
        console.error('Error extracting task and original question:', error);
        return { task: null, originalQuestion: null };
    }
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
        <h3 class="threads-header">Checkpoints:</h3>
        <div class="threads-search-container">
            <input type="text" id="threadsSearchInput" class="threads-search-input" placeholder="Search memory...">
            <button id="threadsSearchClear" class="threads-search-clear" style="display: none;" title="Clear search">
                <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            <button id="threadsSearchSubmit" class="threads-search-submit" title="Search">
                <svg class="search-arrow-icon" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                <div class="thread-search-spinner" style="display: none;"></div>
            </button>
        </div>
        <div id="threads-list" class="threads-list">
            <div class="thread-loading">Loading checkpoints...</div>
        </div>
    `;
    
    menuPopup.insertAdjacentHTML('beforeend', uiHTML);

    const searchInput = document.getElementById('threadsSearchInput');
    const searchSubmit = document.getElementById('threadsSearchSubmit');
    const searchClear = document.getElementById('threadsSearchClear');
    const threadsList = document.getElementById('threads-list');

    // Check if Vector DB is enabled and update UI accordingly
    fetch('/get_vector_db_status')
        .then(response => response.json())
        .then(data => {
            if (!data.vector_db_enabled) {
                searchInput.disabled = true;
                searchSubmit.disabled = true;
                searchInput.placeholder = 'Vector DB not enabled.';
                searchInput.parentElement.classList.add('disabled');
            }
        });

        const performSearch = () => {
            const query = searchInput.value.trim();
            if (!query) {
                loadThreadsList();
                return;
            }
    
            // Show spinner and disable button
            searchSubmit.querySelector('.search-arrow-icon').style.display = 'none';
            searchSubmit.querySelector('.thread-search-spinner').style.display = 'block';
            searchSubmit.disabled = true;
            searchInput.placeholder = 'Searching Memory...';
    
            fetch('/search_threads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }

                console.log('Search results:', data);
    
                const searchResults = data.search_results;
                const allContainers = threadsList.querySelectorAll('.thread-container');
                
                if (!searchResults || searchResults.length === 0) {
                    threadsList.innerHTML = '<div class="no-threads">No matches found.</div>';
                    return;
                }
    
                allContainers.forEach(container => {
                    container.style.display = 'none';
                });
    
                const addedContainers = new Set();
    
                // Loop through the new array of objects
                searchResults.forEach(result => {
                    const id = result.id; // Extract the ID from each result object
                    
                    const matchingItem = threadsList.querySelector(`.thread-item[data-chain-id="${id}"]`);
                    if (matchingItem) {
                        const container = matchingItem.closest('.thread-container');
                        
                        if (container && !addedContainers.has(container)) {
                            threadsList.appendChild(container);
                            container.style.display = 'block';
                            addedContainers.add(container);
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Search failed:', error);
                threadsList.innerHTML = `<div class="no-threads">Search failed: ${error.message}</div>`;
            })
            .finally(() => {
                // Hide spinner and re-enable button
                searchSubmit.querySelector('.search-arrow-icon').style.display = 'block';
                searchSubmit.querySelector('.thread-search-spinner').style.display = 'none';
                searchSubmit.disabled = false;
                searchInput.placeholder = 'Search memory...';
            });
        };

    searchInput.addEventListener('input', () => {
        if (searchInput.value.length > 0) {
            searchClear.style.display = 'flex';
        } else {
            searchClear.style.display = 'none';
            loadThreadsList(); 
        }
    });

    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    searchSubmit.addEventListener('click', performSearch);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });
    
    loadThreadsList();
    console.log('Threads UI initialized');
}

function loadThreadsList() {
    const threadsList = document.getElementById('threads-list');
    
    if (!threadsList) {
        console.error('Threads list element not found - UI may not be initialized yet');
        // Try to initialize the UI if it doesn't exist
        if (typeof initializeThreadsUI === 'function') {
            initializeThreadsUI();
            return; // initializeThreadsUI will call loadThreadsList again
        }
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
            if (previewElement && previewElement.style.display === 'block') { // Check if still hovering
                if (data && data.hasPlotly && data.plotlyData) {
                    previewElement.innerHTML = '';
                    try {
                        const plotContainer = renderPlotlyPreview(data.plotlyData);
                        previewElement.appendChild(plotContainer);
                    } catch (err) {
                        console.error('Error rendering plot preview:', err);
                        previewElement.innerHTML = '<div class="preview-error">Error rendering plot preview</div>';
                    }
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
        if (typeof updateNavigationButtons === 'function') {
            updateNavigationButtons();
        }
        
        console.log(`Thread ${threadId} loaded successfully`);
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