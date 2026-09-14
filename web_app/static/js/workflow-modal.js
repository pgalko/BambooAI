// workflow-modal.js
(function() {
    'use strict';
    
    let isModalOpen = false;
    let currentFilter = null;
    let isThreadView = false;
    let currentThreadId = null;
    let allThreadsBackup = null;
    let isReplayView = false;
    let modalStateSnapshot = null;
    
    // Initialize the workflow modal
    function initializeWorkflowModal() {
        setupPillButton();
        setupModalControls();
        setupSearchControls();
        setupLabelControls();
    }
    
    // Setup pill button to open modal
    function setupPillButton() {
        const pill = document.getElementById('workflowManagerPill');
        if (pill) {
            pill.addEventListener('click', openWorkflowModal);
        }
    }

    // Capture current modal state
    function captureModalState() {
        const modalLeft = document.querySelector('.workflow-modal-left');
        const modalRight = document.querySelector('.workflow-modal-right');
        const chainsGrid = document.getElementById('workflowChainsGrid');
        const searchContainer = document.querySelector('.workflow-search-container');
        const threadNav = document.querySelector('.workflow-thread-nav');
        
        return {
            leftPanelHTML: modalLeft.innerHTML,
            rightHeaderHTML: modalRight.querySelector('.workflow-section-header').outerHTML,
            searchVisible: searchContainer.style.display !== 'none',
            searchValue: document.getElementById('workflowSearchInput')?.value || '',
            gridHTML: chainsGrid.innerHTML,
            threadNavHTML: threadNav ? threadNav.outerHTML : null,
            currentFilter: currentFilter
        };
    }

    // Restore modal state
    function restoreModalState(state) {
        if (!state) return;
        
        const modalLeft = document.querySelector('.workflow-modal-left');
        const modalRight = document.querySelector('.workflow-modal-right');
        const chainsGrid = document.getElementById('workflowChainsGrid');
        const searchContainer = document.querySelector('.workflow-search-container');
        
        // Restore left panel
        modalLeft.innerHTML = state.leftPanelHTML;
        
        // Restore right header
        const currentHeader = modalRight.querySelector('.workflow-section-header');
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = state.rightHeaderHTML;
        currentHeader.replaceWith(tempDiv.firstChild);
        
        // Restore search
        searchContainer.style.display = state.searchVisible ? 'flex' : 'none';
        const searchInput = document.getElementById('workflowSearchInput');
        if (searchInput) searchInput.value = state.searchValue;
        
        // Restore thread nav if it existed
        const existingNav = document.querySelector('.workflow-thread-nav');
        if (existingNav) existingNav.remove();
        
        if (state.threadNavHTML) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = state.threadNavHTML;
            const threadNav = tempDiv.firstChild;
            chainsGrid.parentNode.insertBefore(threadNav, chainsGrid);
            
            // Extract thread ID from the nav and restore thread view state
            const threadTitle = threadNav.querySelector('.workflow-thread-title');
            if (threadTitle) {
                const match = threadTitle.textContent.match(/Thread: (.+)/);
                if (match) {
                    isThreadView = true;
                    currentThreadId = match[1];
                }
            }
        } else {
            // Not in thread view
            isThreadView = false;
            currentThreadId = null;
        }
        
        // Restore grid
        chainsGrid.innerHTML = state.gridHTML;
        
        // Restore filter state
        currentFilter = state.currentFilter;
        
        // Re-initialize all handlers
        reinitializeHandlers();
    }

    // Reinitialize all handlers after state restore
    function reinitializeHandlers() {
        // Re-setup label controls
        setupLabelControls();
        
        // Re-setup label item click handlers
        const labelsList = document.getElementById('workflowLabelsList');
        if (labelsList) {
            labelsList.querySelectorAll('.workflow-label-item').forEach(item => {
                const labelName = item.querySelector('.workflow-label-name');
                const deleteBtn = item.querySelector('.workflow-label-delete');
                
                if (labelName) {
                    labelName.style.cursor = 'pointer';
                    labelName.addEventListener('click', function(e) {
                        e.stopPropagation();
                        const labelId = item.dataset.labelId;
                        const name = labelName.textContent;
                        window.LabelsManager.filterChainsByLabel(labelId, name);
                    });
                }
                
                if (deleteBtn) {
                    deleteBtn.addEventListener('click', async function(e) {
                        e.stopPropagation();
                        const labelId = item.dataset.labelId;
                        const name = item.querySelector('.workflow-label-name').textContent;
                        
                        if (confirm(`Delete label "${name}"?\nThis will remove it from all chains.`)) {
                            try {
                                const response = await window.authService.fetch(`/api/labels/${labelId}`, { 
                                    method: 'DELETE' 
                                });
                                
                                if (response.ok) {
                                    loadWorkflowLabels();
                                    loadWorkflowChains();
                                    if (window.showSystemMessage) {
                                        window.showSystemMessage(`Label "${name}" deleted`, 'success');
                                    }
                                }
                            } catch (error) {
                                console.error('Error deleting label:', error);
                            }
                        }
                    });
                }
            });
        }
        
        // Re-setup search controls
        setupSearchControls();
        
        // Re-setup thread nav if present
        const threadNav = document.querySelector('.workflow-thread-nav:not(.workflow-replay-nav)');
        if (threadNav) {
            const backBtn = threadNav.querySelector('.workflow-back-btn');
            if (backBtn) {
                backBtn.addEventListener('click', () => {
                    exitThreadView();
                });
            }
        }
        
        // Re-setup all card handlers
        const cards = document.querySelectorAll('.workflow-card');
        cards.forEach(card => {
            const chain = {
                chain_id: card.dataset.chainId,
                thread_id: card.dataset.threadId,
                label_id: card.dataset.labelId,
                label_name: card.dataset.labelName
            };
            // If we're in thread view, cards are individual chains; otherwise thread-level
            setupCardHandlers(card, chain, !isThreadView);
            
            // Re-setup view chains button
            const viewBtn = card.querySelector('.workflow-view-chains-btn');
            if (viewBtn) {
                viewBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    try {
                        const response = await window.authService.fetch(`/get_threads?include_previews=true&t=${Date.now()}`);
                        const data = await response.json();
                        const thread = data.threads?.find(t => t.thread_id === chain.thread_id);
                        if (thread?.chains) {
                            showThreadChains(thread.thread_id, thread.chains);
                        }
                    } catch (error) {
                        console.error('Error loading thread chains:', error);
                    }
                });
            }
        });
    }
    
    // Setup modal controls
    function setupModalControls() {
        const modal = document.getElementById('workflowManagerModal');
        const closeBtn = modal?.querySelector('.workflow-modal-close');
        
        if (closeBtn) {
            closeBtn.addEventListener('click', closeWorkflowModal);
        }
        
        // Close on background click
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    closeWorkflowModal();
                }
            });
        }
    }
    
    // Setup label controls - inline input version
    function setupLabelControls() {
        const input = document.getElementById('workflowNewLabelInput');
        const addBtn = document.getElementById('workflowAddLabelBtn');
        
        if (!input || !addBtn) return;
        
        const createLabel = async () => {
            const labelName = input.value.trim();
            
            if (!labelName) {
                input.focus();
                return;
            }
            
            addBtn.disabled = true;
            
            try {
                const response = await window.authService.fetch('/api/labels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: labelName })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    input.value = '';
                    loadWorkflowLabels(); // Refresh the list
                    if (window.showSystemMessage) {
                        window.showSystemMessage(`Label "${labelName}" created`, 'success');
                    }
                } else {
                    if (window.showSystemMessage) {
                        window.showSystemMessage(data.error || 'Failed to create label', 'error');
                    }
                }
            } catch (error) {
                console.error('Error creating label:', error);
                if (window.showSystemMessage) {
                    window.showSystemMessage('Failed to create label', 'error');
                }
            } finally {
                addBtn.disabled = false;
            }
        };
        
        // Add event listeners
        addBtn.addEventListener('click', createLabel);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                createLabel();
            }
        });
    }
    
    // Setup search controls
    function setupSearchControls() {
        const searchInput = document.getElementById('workflowSearchInput');
        const searchSubmit = document.getElementById('workflowSearchSubmit');
        const searchClear = document.getElementById('workflowSearchClear');
        
        if (!searchInput || !searchSubmit || !searchClear) return;
        
        // Set default placeholder - search should always be enabled
        searchInput.placeholder = 'Search workflows...';
        searchInput.disabled = false;
        searchSubmit.disabled = false;
        
        // Search input handler
        searchInput.addEventListener('input', () => {
            if (searchInput.value.length > 0) {
                searchClear.style.display = 'flex';
            } else {
                searchClear.style.display = 'none';
                loadWorkflowChains();
            }
        });
        
        // Clear button handler
        searchClear.addEventListener('click', () => {
            searchInput.value = '';
            searchInput.disabled = false;
            searchClear.style.display = 'none';
            searchSubmit.disabled = false;
            currentFilter = null;
            loadWorkflowChains();
        });
        
        // Search submit handler
        const performSearch = async () => {
            const query = searchInput.value.trim();
            if (!query) {
                loadWorkflowChains();
                return;
            }
            
            const chainsGrid = document.getElementById('workflowChainsGrid');
            
            performTextSearch(query);
        };
        
        // Text-based search function
        const performTextSearch = (query) => {
            const chainsGrid = document.getElementById('workflowChainsGrid');
            const allCards = chainsGrid.querySelectorAll('.workflow-card');
            const searchTerm = query.toLowerCase();
            let visibleCount = 0;
            
            allCards.forEach(card => {
                const task = card.querySelector('.workflow-card-task')?.textContent.toLowerCase() || '';
                const threadId = card.dataset.threadId?.toLowerCase() || '';
                const labelName = card.dataset.labelName?.toLowerCase() || '';
                const dataset = card.querySelector('.workflow-card-dataset')?.textContent.toLowerCase() || '';
                
                if (task.includes(searchTerm) || 
                    threadId.includes(searchTerm) || 
                    labelName.includes(searchTerm) || 
                    dataset.includes(searchTerm)) {
                    card.style.display = 'block';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });
            
            if (visibleCount === 0) {
                chainsGrid.innerHTML = '<div class="workflow-no-chains">No matches found.</div>';
            }
        };
        
        searchSubmit.addEventListener('click', performSearch);
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                performSearch();
            }
        });
    }
    
    // Open modal
    function openWorkflowModal() {
        const modal = document.getElementById('workflowManagerModal');
        if (modal) {
            modal.style.display = 'flex';
            isModalOpen = true;
            loadWorkflowLabels();
            loadWorkflowChains();
        }
    }
    
    // Close modal
    function closeWorkflowModal() {
        const modal = document.getElementById('workflowManagerModal');
        if (modal) {
            // Exit thread view if active
            if (isThreadView) {
                exitThreadView();
            }
            // Exit replay view if active (does full restore)
            if (isReplayView) {
                exitReplayView();
            }

            // Safety: ensure no stale snapshot remains even if above paths change later
            modalStateSnapshot = null;

            modal.style.display = 'none';
            isModalOpen = false;
            currentFilter = null;

            const searchInput = document.getElementById('workflowSearchInput');
            const searchClear = document.getElementById('workflowSearchClear');
            if (searchInput) {
                searchInput.value = '';
                searchInput.disabled = false;
            }
            if (searchClear) {
                searchClear.style.display = 'none';
            }
        }
    }
    

    // Load labels
    async function loadWorkflowLabels() {
        try {
            const response = await window.authService.fetch('/api/labels');
            if (!response.ok) throw new Error('Failed to fetch labels');
            
            const data = await response.json();
            const labels = data.labels || [];
            renderWorkflowLabels(labels);
        } catch (error) {
            console.error('Error loading labels:', error);
        }
    }
    
    // Render labels
    function renderWorkflowLabels(labels) {
        const labelsList = document.getElementById('workflowLabelsList');
        if (!labelsList) return;
        
        if (labels.length === 0) {
            labelsList.innerHTML = '<div class="workflow-no-labels">No labels yet</div>';
            return;
        }
        
        labelsList.innerHTML = labels.map(label => `
            <div class="workflow-label-item" data-label-id="${label.id}">
                <svg class="workflow-label-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                    <line x1="7" y1="7" x2="7.01" y2="7"/>
                </svg>
                <span class="workflow-label-name">${escapeHtml(label.label)}</span>
                <button class="workflow-label-delete" title="Delete label">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
        `).join('');
        
        // Add click handlers
        labelsList.querySelectorAll('.workflow-label-item').forEach(item => {
            const labelName = item.querySelector('.workflow-label-name');
            const deleteBtn = item.querySelector('.workflow-label-delete');
            
            if (labelName) {
                labelName.style.cursor = 'pointer';
                labelName.addEventListener('click', function(e) {
                    e.stopPropagation();
                    const labelId = item.dataset.labelId;
                    const name = labelName.textContent;
                    window.LabelsManager.filterChainsByLabel(labelId, name);
                });
            }
            
            if (deleteBtn) {
                deleteBtn.addEventListener('click', async function(e) {
                    e.stopPropagation();
                    const labelId = item.dataset.labelId;
                    const name = item.querySelector('.workflow-label-name').textContent;
                    
                    if (confirm(`Delete label "${name}"?\nThis will remove it from all chains.`)) {
                        try {
                            const response = await window.authService.fetch(`/api/labels/${labelId}`, { 
                                method: 'DELETE' 
                            });
                            
                            if (response.ok) {
                                loadWorkflowLabels();
                                loadWorkflowChains();
                                if (window.showSystemMessage) {
                                    window.showSystemMessage(`Label "${name}" deleted`, 'success');
                                }
                            }
                        } catch (error) {
                            console.error('Error deleting label:', error);
                        }
                    }
                });
            }
        });
    }
    
    // Load chains
    async function loadWorkflowChains() {
        const chainsGrid = document.getElementById('workflowChainsGrid');
        if (!chainsGrid) return;
        
        chainsGrid.innerHTML = '<div class="workflow-loading">Loading workflows...</div>';
        
        try {
            // Add include_previews parameter
            const response = await window.authService.fetch(`/get_threads?include_previews=true&t=${Date.now()}`);
            if (!response.ok) throw new Error('Failed to fetch threads');
            
            const data = await response.json();
            if (!data.threads || data.threads.length === 0) {
                chainsGrid.innerHTML = '<div class="workflow-no-chains">No saved workflows found</div>';
                return;
            }
            
            renderWorkflowChains(data.threads);
        } catch (error) {
            console.error('Error loading chains:', error);
            chainsGrid.innerHTML = '<div class="workflow-error">Error loading workflows</div>';
        }
    }
    
    // Render chains
    function renderWorkflowChains(threads) {
        const chainsGrid = document.getElementById('workflowChainsGrid');
        if (!chainsGrid) return;
        
        chainsGrid.innerHTML = '';
        
        threads.forEach(thread => {
            if (!thread.chains || thread.chains.length === 0) return;
            
            const chain = thread.chains[0];
            const card = createWorkflowCard(chain, thread.chains.length, true);
            
            // If multiple chains, add the view chains button
            if (thread.chains.length > 1) {
                const viewChainsBtn = document.createElement('button');
                viewChainsBtn.className = 'workflow-view-chains-btn';
                viewChainsBtn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path>
                    </svg>
                    ${thread.chains.length} chains
                `;
                viewChainsBtn.title = 'View all chains in this thread';
                
                viewChainsBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showThreadChains(thread.thread_id, thread.chains);
                });
                
                // Add button to card header
                const cardHeader = card.querySelector('.workflow-card-header');
                const deleteBtn = cardHeader.querySelector('.workflow-card-delete');
                cardHeader.insertBefore(viewChainsBtn, deleteBtn);
            }
            
            chainsGrid.appendChild(card);
        });
    }

    // Determine preview content based on chain type
    function getPreviewContent(chain) {
        // If plot preview exists, use it
        if (chain.plotPreview) {
            return `<img src="${chain.plotPreview}" class="workflow-preview-image" alt="Workflow preview">`;
        }
        
        const task = (chain.task || '').toLowerCase();
        const queryText = (chain.queryText || '').toLowerCase();
        
        // Synthesis chain
        if (task.includes('synthesis') || queryText.includes('synthesis')) {
            // Use infographic thumbnail if available
            if (chain.synthesisImage && chain.synthesisImage.data) {
                const mimeType = chain.synthesisImage.mime_type || 'image/png';
                return `<img src="data:${mimeType};base64,${chain.synthesisImage.data}" class="workflow-preview-image" alt="Synthesis infographic">`;
            }
            return `
                <div class="workflow-preview-typed synthesis">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                    <span>Synthesis</span>
                </div>`;
        }
        
        // Branching chain
        if (task.includes('variations') || queryText.includes('variations')) {
            return `
                <div class="workflow-preview-typed branching">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="6" y1="3" x2="6" y2="15"></line>
                        <circle cx="18" cy="6" r="3"></circle>
                        <circle cx="6" cy="18" r="3"></circle>
                        <path d="M18 9a9 9 0 0 1-9 9"></path>
                    </svg>
                    <span>Branching</span>
                </div>`;
        }
        
        // Default — text/analytical without plot
        return `
            <div class="workflow-preview-typed default">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 7V4h16v3"></path>
                    <path d="M9 20h6"></path>
                    <path d="M12 4v16"></path>
                </svg>
                <span>Text</span>
            </div>`;
    }
    
    // Create workflow card
    function createWorkflowCard(chain, chainCount, isThreadLevel = false) {
        const card = document.createElement('div');
        card.className = 'workflow-card';
        card.setAttribute('data-chain-id', chain.chain_id);
        card.setAttribute('data-thread-id', chain.thread_id);
        card.setAttribute('data-label-id', chain.label_id || '');
        card.setAttribute('data-label-name', chain.label_name || '');
        
        // Format timestamp
        let formattedTime = 'No date';
        if (chain.chain_id && !isNaN(chain.chain_id)) {
            try {
                const date = new Date(Number(chain.chain_id) * 1000);
                formattedTime = date.toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {}
        } else if (chain.timestamp) {
            try {
                const date = new Date(chain.timestamp);
                formattedTime = date.toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {}
        }
        
        card.innerHTML = `
            <div class="workflow-card-header">
                <button class="workflow-card-label ${chain.label_id ? 'labeled' : ''}" 
                        title="${chain.label_name || 'Add label'}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
                        <line x1="7" y1="7" x2="7.01" y2="7"/>
                    </svg>
                </button>
                <span class="workflow-card-time">${formattedTime}</span>
                <button class="workflow-card-delete" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
            <div class="workflow-card-body">
                <div class="workflow-card-preview" data-chain-id="${chain.chain_id}" 
                    data-thread-id="${chain.thread_id}">
                    ${getPreviewContent(chain)}
                </div>
                <div class="workflow-card-info">
                    <span class="workflow-card-thread">Thread: ${chain.thread_id}</span>
                    ${chain.label_name ? `<span class="workflow-card-label-name">Label: ${chain.label_name}</span>` : ''}
                    <span class="workflow-card-dataset">Dataset: ${chain.dataset_name || 'None'}</span>
                </div>
                <div class="workflow-card-task">${chain.task || `Chain ${chain.chain_id}`}</div>
            </div>
            <div class="workflow-card-footer">
                <button class="workflow-card-replay" title="Re-run analysis">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="17 1 21 5 17 9"></polyline>
                        <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
                        <polyline points="7 23 3 19 7 15"></polyline>
                        <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
                    </svg>
                </button>
                ${chain.bookmark_type ? `
                    <span class="workflow-card-memory-badge ${chain.bookmark_type}" 
                          title="${chain.bookmark_type === 'individual' ? 'Saved to agent memory' : 'Saved to agent memory (trajectory)'}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
                        </svg>
                    </span>
                ` : ''}
            </div>
        `;
        
        setupCardHandlers(card, chain, isThreadLevel);
        
        // Only load preview if not included in chain data and not explicitly empty
        if (!chain.hasOwnProperty('plotPreview')) {
            loadCardPreview(card, chain.thread_id, chain.chain_id);
        }
        
        return card;
    }

    // Add this function to show chains for a specific thread
    function showThreadChains(threadId, threadChains) {
        const chainsGrid = document.getElementById('workflowChainsGrid');
        const searchContainer = document.querySelector('.workflow-search-container');
        
        // Store current state
        isThreadView = true;
        currentThreadId = threadId;
        allThreadsBackup = chainsGrid.innerHTML;
        
        // Hide search temporarily in thread view
        if (searchContainer) {
            searchContainer.style.display = 'none';
        }
        
        // Add back navigation
        const backNav = document.createElement('div');
        backNav.className = 'workflow-thread-nav';
        backNav.innerHTML = `
            <button class="workflow-back-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="19" y1="12" x2="5" y2="12"></line>
                    <polyline points="12 19 5 12 12 5"></polyline>
                </svg>
                Back to all workflows
            </button>
            <span class="workflow-thread-title">Thread: ${threadId}</span>
        `;
        
        // Insert navigation before grid
        chainsGrid.parentNode.insertBefore(backNav, chainsGrid);

        // Sort by original exploration order
        threadChains.sort((a, b) => (b.index || 0) - (a.index || 0));
        
        // Clear grid and show only this thread's chains
        chainsGrid.innerHTML = '';
        
        threadChains.forEach(chain => {
            const card = createWorkflowCard(chain, 1, false); // Pass 1 to not show chain count
            chainsGrid.appendChild(card);
        });
        
        // Setup back button
        backNav.querySelector('.workflow-back-btn').addEventListener('click', () => {
            exitThreadView();
        });
    }

    // Function to exit thread view
    function exitThreadView() {
        const searchContainer = document.querySelector('.workflow-search-container');
        const backNav = document.querySelector('.workflow-thread-nav');
        
        if (backNav) backNav.remove();
        if (searchContainer) searchContainer.style.display = 'flex';
        
        loadWorkflowChains();
    }
    
    // Setup card handlers
    function setupCardHandlers(card, chain, isThreadLevel = false) {
        // Label button
        const labelBtn = card.querySelector('.workflow-card-label');
        if (labelBtn) {
            labelBtn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const currentLabelId = card.getAttribute('data-label-id');
                await showWorkflowLabelSelector(chain.chain_id, currentLabelId, labelBtn, card);
            });
        }

        // Replay button
        const replayBtn = card.querySelector('.workflow-card-replay');
        if (replayBtn) {
            replayBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                enterReplayView(chain.thread_id, chain.chain_id);
            });
        }
        
        // Delete button
        const deleteBtn = card.querySelector('.workflow-card-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', async function(e) {
                e.stopPropagation();
                
                if (isThreadLevel) {
                    // Main view — delete entire thread
                    if (confirm('Delete this entire workflow and all its chains from favorites?')) {
                        try {
                            const response = await window.authService.fetch(
                                `/delete_thread/${chain.thread_id}`, 
                                { method: 'DELETE' }
                            );
                            
                            if (response.ok) {
                                card.remove();
                                if (window.showSystemMessage) {
                                    window.showSystemMessage('Workflow deleted', 'success');
                                }
                            }
                        } catch (error) {
                            console.error('Error deleting thread:', error);
                            if (window.showSystemMessage) {
                                window.showSystemMessage('Failed to delete workflow', 'error');
                            }
                        }
                    }
                } else {
                    // Thread view — delete single chain
                    if (confirm('Delete this chain from favorites?')) {
                        try {
                            const response = await window.authService.fetch(
                                `/delete_chain/${chain.thread_id}/${chain.chain_id}`, 
                                { method: 'DELETE' }
                            );
                            
                            if (response.ok) {
                                card.remove();
                                if (window.showSystemMessage) {
                                    window.showSystemMessage('Chain deleted', 'success');
                                }
                            }
                        } catch (error) {
                            console.error('Error deleting chain:', error);
                            if (window.showSystemMessage) {
                                window.showSystemMessage('Failed to delete chain', 'error');
                            }
                        }
                    }
                }
            });
        }
        
        // Card click to load
        card.addEventListener('click', function(e) {
            if (!e.target.closest('button')) {
                if (window.loadThreadContent) {
                    window.loadThreadContent(chain.thread_id, chain.chain_id);
                    closeWorkflowModal();
                } else {
                    console.error('loadThreadContent function not available');
                }
            }
        });
    }

    function enterReplayView(threadId, chainId) {
        // Capture complete state before any changes
        modalStateSnapshot = captureModalState();
        console.log('Replay clicked - Thread ID:', threadId, 'Chain ID:', chainId);

        isReplayView = true;
        
        const modalLeft = document.querySelector('.workflow-modal-left');
        const modalRight = document.querySelector('.workflow-modal-right');
        const searchContainer = document.querySelector('.workflow-search-container');
        const chainsGrid = document.getElementById('workflowChainsGrid');
        
        // Hide search
        if (searchContainer) {
            searchContainer.style.display = 'none';
        }
        
        // Update left panel
        const leftTitle = modalLeft.querySelector('.workflow-modal-section-title');
        leftTitle.className = 'workflow-modal-section-title workflow-replay-theme';
        leftTitle.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
            </svg>
            Datasets
        `;
        
        // Clear labels content
        const addLabelContainer = modalLeft.querySelector('.workflow-add-label-container');
        const labelsList = document.getElementById('workflowLabelsList');
        if (addLabelContainer) addLabelContainer.style.display = 'none';
        if (labelsList) labelsList.innerHTML = '<div class="workflow-no-labels">Dataset information will appear here</div>';
        
        // Update right panel header
        const rightHeader = modalRight.querySelector('.workflow-section-header');
        rightHeader.className = 'workflow-section-header workflow-replay-theme';
        rightHeader.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="17 1 21 5 17 9"></polyline>
                <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
                <polyline points="7 23 3 19 7 15"></polyline>
                <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
            </svg>
            <span>Replays</span>
        `;
        
        // Theme close button
        const closeBtn = modalRight.querySelector('.workflow-modal-close');
        if (closeBtn) closeBtn.classList.add('workflow-replay-theme');
        
        // Remove any existing nav
        const existingNav = document.querySelector('.workflow-thread-nav');
        if (existingNav) existingNav.remove();
        
        // Add replay navigation
        const backNav = document.createElement('div');
        backNav.className = 'workflow-thread-nav workflow-replay-nav';
        backNav.innerHTML = `
            <button class="workflow-back-btn workflow-back-replay">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="19" y1="12" x2="5" y2="12"></line>
                    <polyline points="12 19 5 12 12 5"></polyline>
                </svg>
                Back to workflows
            </button>
            <span class="workflow-thread-title workflow-replay-title">Chain: ${chainId}</span>
        `;
        
        chainsGrid.parentNode.insertBefore(backNav, chainsGrid);
        chainsGrid.innerHTML = '<div class="workflow-loading">Preparing replay view...</div>';
    
        // Initialize replay module to load datasets
        if (window.WorkflowReplay) {
            window.WorkflowReplay.initialize(threadId, chainId);
        }
        
        backNav.querySelector('.workflow-back-btn').addEventListener('click', () => {
            exitReplayView();
        });
    }

    // Exit replay view
    function exitReplayView() {
        // Remove replay theme from close button
        const closeBtn = document.querySelector('.workflow-modal-close');
        if (closeBtn) closeBtn.classList.remove('workflow-replay-theme');
        
        // Remove replay nav
        const replayNav = document.querySelector('.workflow-replay-nav');
        if (replayNav) replayNav.remove();
        
        // Reset replay state flag
        isReplayView = false;
        
        // Restore complete previous state
        if (modalStateSnapshot) {
            restoreModalState(modalStateSnapshot);
            modalStateSnapshot = null;
        } else {
            // Fallback if no snapshot
            loadWorkflowChains();
        }
    }

    // Load card preview
    async function loadCardPreview(card, threadId, chainId) {
        const previewDiv = card.querySelector('.workflow-card-preview');
        if (!previewDiv) return;
        
        try {
            const response = await window.authService.fetch(`/get_chain_preview/${threadId}/${chainId}`);
            const data = await response.json();
            
            if (data && data.hasPlotly && data.plotPreview) {
                const img = document.createElement('img');
                img.src = data.plotPreview;
                img.className = 'workflow-preview-image';
                img.alt = 'Workflow preview';
                previewDiv.innerHTML = '';
                previewDiv.appendChild(img);
            } else {
                previewDiv.innerHTML = '<div class="workflow-preview-empty">No preview</div>';
            }
        } catch (error) {
            previewDiv.innerHTML = '<div class="workflow-preview-error">Preview unavailable</div>';
        }
    }
    
    // Show label selector for workflow cards
    async function showWorkflowLabelSelector(chainId, currentLabelId, labelBtn, card) {
        // Remove any existing selector
        const existingSelector = document.querySelector('.workflow-label-selector');
        if (existingSelector) existingSelector.remove();
        
        // Get available labels
        let labels = [];
        try {
            const response = await window.authService.fetch('/api/labels');
            const data = await response.json();
            labels = data.labels || [];
        } catch (error) {
            console.error('Error fetching labels:', error);
            return;
        }
        
        // Create dropdown
        const dropdown = document.createElement('div');
        dropdown.className = 'workflow-label-selector';
        
        // Add "Remove label" option
        const removeOption = document.createElement('div');
        removeOption.className = `workflow-label-option ${!currentLabelId ? 'selected' : ''}`;
        removeOption.innerHTML = '× Remove label';
        removeOption.addEventListener('click', async (e) => {
            e.stopPropagation();
            await updateWorkflowCardLabel(chainId, null, null, labelBtn, card);
            dropdown.remove();
        });
        dropdown.appendChild(removeOption);
        
        // Add separator if there are labels
        if (labels.length > 0) {
            const separator = document.createElement('div');
            separator.className = 'workflow-label-separator';
            dropdown.appendChild(separator);
        }
        
        // Add each label option
        labels.forEach(label => {
            const option = document.createElement('div');
            option.className = `workflow-label-option ${label.id == currentLabelId ? 'selected' : ''}`;
            option.textContent = label.label;
            option.addEventListener('click', async (e) => {
                e.stopPropagation();
                await updateWorkflowCardLabel(chainId, label.id, label.label, labelBtn, card);
                dropdown.remove();
            });
            dropdown.appendChild(option);
        });
        
        // Position the dropdown
        const rect = labelBtn.getBoundingClientRect();
        dropdown.style.position = 'fixed';
        dropdown.style.top = `${rect.bottom + 5}px`;
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.zIndex = '10001';
        
        document.body.appendChild(dropdown);
        
        // Close dropdown when clicking outside
        setTimeout(() => {
            const closeDropdown = (e) => {
                if (!dropdown.contains(e.target) && e.target !== labelBtn) {
                    dropdown.remove();
                    document.removeEventListener('click', closeDropdown);
                }
            };
            document.addEventListener('click', closeDropdown);
        }, 0);
    }
    
    // Update workflow card label
    async function updateWorkflowCardLabel(chainId, labelId, labelName, labelBtn, card) {
        try {
            const response = await window.authService.fetch(`/api/chains/${chainId}/label`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label_id: labelId })
            });
            
            if (!response.ok) throw new Error('Failed to update label');
            
            // Update button appearance
            if (labelId) {
                labelBtn.classList.add('labeled');
                labelBtn.title = labelName;
            } else {
                labelBtn.classList.remove('labeled');
                labelBtn.title = 'Add label';
            }
            
            // Update card data attributes
            card.setAttribute('data-label-id', labelId || '');
            card.setAttribute('data-label-name', labelName || '');
            
            // Update label display in card
            let labelDisplay = card.querySelector('.workflow-card-label-name');
            
            if (labelName) {
                if (!labelDisplay) {
                    const infoDiv = card.querySelector('.workflow-card-info');
                    const threadSpan = infoDiv.querySelector('.workflow-card-thread');
                    labelDisplay = document.createElement('span');
                    labelDisplay.className = 'workflow-card-label-name';
                    labelDisplay.textContent = `Label: ${labelName}`;
                    if (threadSpan && threadSpan.nextSibling) {
                        infoDiv.insertBefore(labelDisplay, threadSpan.nextSibling);
                    } else {
                        infoDiv.appendChild(labelDisplay);
                    }
                } else {
                    labelDisplay.textContent = `Label: ${labelName}`;
                }
            } else if (labelDisplay) {
                labelDisplay.remove();
            }
            
            if (window.showSystemMessage) {
                window.showSystemMessage(
                    labelName ? `Label "${labelName}" assigned` : 'Label removed', 
                    'success'
                );
            }
            
        } catch (error) {
            console.error('Error updating label:', error);
            if (window.showSystemMessage) {
                window.showSystemMessage('Failed to update label', 'error');
            }
        }
    }
    
    
    // Helper function
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Export public API
    window.WorkflowModal = {
        open: openWorkflowModal,
        close: closeWorkflowModal,
        refresh: loadWorkflowChains,
        refreshLabels: loadWorkflowLabels
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWorkflowModal);
    } else {
        initializeWorkflowModal();
    }
})();