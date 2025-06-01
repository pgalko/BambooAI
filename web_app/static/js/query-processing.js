//--------------------
//  QUERY PROCESSING MODULE
//--------------------

function initializeQueryProcessing() {
    console.log('Initializing query processing...');
    
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

function handleQuerySubmit() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();
    if (!query) {
        return;
    }

    // Store the query text in currentData for later use
    currentData.queryText = query;

    const streamOutputDiv = document.getElementById('streamOutput');
    streamOutputDiv.innerHTML = '';
    if (typeof clearAllTabs === 'function') {
        clearAllTabs();
    }

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

        return readStream();
    })
    .catch(error => {
        console.error('Error:', error);
        streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
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
            try {
                const data = JSON.parse(line);
                if (data.type === "html") {
                    processHtmlContent(data.content);
                }
                else if (data.type === "request_user_context") {
                    processUserContextRequest(data);
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
                else if (data.type === "generated_datasets") {
                    streamOutputDiv.innerHTML += formatGeneratedDatasets(data.data);
                }
                else if (data.type === "semantic_search") {
                    streamOutputDiv.innerHTML += formatSemanticSearch(data.data);
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
                    if (typeof createOrUpdateTab === 'function') {
                        createOrUpdateTab(data.type, data.data, data.id, data.format);
                    }
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

//--------------------
//  CONTENT PROCESSORS
//--------------------

function processHtmlContent(content) {
    const streamOutputDiv = document.getElementById('streamOutput');
    const uniqueId = `related-searches-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    
    const parser = new DOMParser();
    const doc = parser.parseFromString(content, 'text/html');
    
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
        console.warn('No recognizable content found in HTML:', content);
    }
}

function processUserContextRequest(data) {
    const streamOutputDiv = document.getElementById('streamOutput');
    // Generate a unique ID for this specific form instance
    const formId = `feedback-form-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    
    console.log('Received feedback request:', {
        query_clarification: data.query_clarification,
        context_needed: data.context_needed,
        chain_id: currentData.chain_id,
        formId: formId
    });
    
    // Format the query text for better readability
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
                    <div class="feedback-label">
                        <svg class="question-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <circle cx="12" cy="12" r="10" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M12 17h.01" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        <span style="color: var(--accent-color)">Feedback needed:</span>
                    </div>
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
    
    // Add event listener for the form
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

//--------------------
//  TOOL CALL HANDLING
//--------------------

function finishToolCall() {
    if (currentToolCallId) {
        completeToolCall(currentToolCallId, toolCallStartTime);
        currentToolCallId = null;
        toolCallStartTime = null;
    }
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

//--------------------
//  FEEDBACK SYSTEM
//--------------------

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
        rankButton.addEventListener('click', showRankModal);
        rankButton.style.display = 'none'; // Hide the button initially
    }

    if (submitRankButton) {
        submitRankButton.addEventListener('click', submitRank);
    }

    if (closeModalButton) {
        closeModalButton.addEventListener('click', closeRankModal);
    }

    // Close the modal if user clicks outside of it
    if (modal && modalContent) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                closeRankModal();
            }
        });

        // Prevent clicks inside the modal from closing it
        modalContent.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
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
                            if (userRank) {
                                storeInFavorites(userRank, statusMessage, submitButton, starRating);
                            } else {
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
        taskContents: chainData.taskContents || {},
        queryText: chainData.queryText || '',
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

//--------------------
//  POPUP SYSTEM
//--------------------

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
    
    if (!popup || !content) return;
    
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
        const popup = document.getElementById('summaryPopup');
        if (popup) {
            popup.style.display = 'none';
        }
    }, 5000);  // Hide after 5 seconds
}

function processSummary(data) {
    if (data && data.call_summary) {
        showSummaryPopup(data.call_summary);
    }
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

function formatGeneratedDatasets(datasetsArray) {
    const headerFileIcon = `
        <svg class="file-icon-header" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
          <polyline points="13 2 13 9 20 9"></polyline>
        </svg>
    `;

    if (!datasetsArray || datasetsArray.length === 0) {
        return `
            <div class="generated-datasets-container">
                <h4 class="generated-datasets-header">
                    ${headerFileIcon}
                    <span>Generated Files</span>
                </h4>
                <ul class="generated-datasets-list">
                    <li class="generated-dataset-item no-datasets-message">No datasets generated.</li>
                </ul>
            </div>`;
    }

    const downloadIconPill = `
        <svg class="download-icon-pill" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
    `;

    let listItemsHtml = datasetsArray.map(datasetPath => {
        const filename = datasetPath.split('/').pop() || 'dataset_file';
        const downloadUrl = `/download_generated_dataset?path=${encodeURIComponent(datasetPath)}`;

        return `
            <li class="generated-dataset-item">
                <a href="${downloadUrl}" class="dataset-link" download="${filename}" title="Download ${filename}">
                    ${downloadIconPill}
                    <span class="dataset-path">${datasetPath}</span>
                </a>
            </li>
        `;
    }).join('');

    return `
        <div class="generated-datasets-container">
            <h4 class="generated-datasets-header">
                ${headerFileIcon}
                <span>Generated Datasets</span>
            </h4>
            <ul class="generated-datasets-list">
                ${listItemsHtml}
            </ul>
        </div>
    `;
}

function formatSemanticSearch(data) {
    const vectorIconMinimal = `
        <svg class="vector-icon-minimal" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
        </svg>
     `;

    const id = data?.id || 'N/A';
    const similarityScore = data?.similarity_score || 'N/A';
    const rank = data?.rank || 'N/A';
    const matchingTask = data?.matching_task;
    const additionalData = data?.data;

    const escapeHTMLDirect = (text) => {
        if (text === undefined || text === null) return '';
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    };

    let taskHtml = '';
    if (matchingTask) {
        taskHtml = `
            <div class="ss-additional-info">
                <span class="ss-info-label">Matching Task:</span>
                <span class="ss-info-value">${escapeHTMLDirect(matchingTask)}</span>
            </div>
        `;
    }

    let dataHtml = '';
    if (additionalData !== undefined && additionalData !== null) {
        let dataDisplayValue;
        if (typeof additionalData === 'object') {
            try {
                const jsonString = JSON.stringify(additionalData);
                dataDisplayValue = jsonString.length > 100 ? jsonString.substring(0, 97) + '...' : jsonString;
                dataDisplayValue = `<code class="ss-data-code-preview">${escapeHTMLDirect(dataDisplayValue)}</code>`;
            } catch (e) {
                dataDisplayValue = escapeHTMLDirect(String(additionalData));
            }
        } else {
            dataDisplayValue = escapeHTMLDirect(String(additionalData));
        }
        dataHtml = `
            <div class="ss-additional-info">
                <span class="ss-info-label">Data:</span>
                <span class="ss-info-value">${dataDisplayValue}</span>
            </div>
        `;
    }

    return `
        <div class="semantic-search-minimal">
            <div class="vector-header">
                ${vectorIconMinimal}
                Relevant Memory Found
            </div>
            <div class="search-details">
                Chain ID: ${escapeHTMLDirect(id)}, Similarity Score: ${escapeHTMLDirect(similarityScore)}%, Rank: ${escapeHTMLDirect(rank)}
            </div>
            ${taskHtml}
            ${dataHtml}
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