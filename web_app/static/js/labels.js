// labels.js
/**
 * Labels Management Module for BambooAI
 */

window.LabelsManager = (function() {
    'use strict';

    let labels = [];
    let isModalOpen = false;

    /**
     * Initialize the labels module
     */
    function initialize() {
        console.log('Initializing Labels Manager...');
        loadLabels();
        setupEventListeners();
        initializeResizableDivider();
    }

    /**
     * Initialize resizable divider functionality
     */
    function initializeResizableDivider() {
        const divider = document.querySelector('.menu-divider');
        
        if (!divider) {
            return;
        }
        
        let isResizing = false;
        let startY = 0;
        let startHeight = 300;
        
        // Apply saved height
        const savedHeight = localStorage.getItem('labels-height');
        if (savedHeight) {
            startHeight = parseInt(savedHeight);
            const labelsList = document.querySelector('.labels-list');
            if (labelsList) {
                labelsList.style.height = `${startHeight}px`;
                labelsList.style.overflow = 'auto';
            }
        }
        
        divider.addEventListener('mousedown', function(e) {
            isResizing = true;
            startY = e.clientY;
            
            const labelsList = document.querySelector('.labels-list');
            if (labelsList) {
                // Use current computed height as starting point for smooth dragging
                startHeight = labelsList.offsetHeight;
            }
            
            divider.classList.add('dragging');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none'; // Prevent text selection while dragging
            e.preventDefault();
            e.stopPropagation();
        });
        
        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            
            // Calculate delta from the original mouse position (anchored to divider)
            const deltaY = e.clientY - startY;
            let newHeight = startHeight + deltaY;
            
            // Constrain within reasonable bounds
            newHeight = Math.max(100, Math.min(500, newHeight));
            
            const labelsList = document.querySelector('.labels-list');
            if (labelsList) {
                labelsList.style.height = `${newHeight}px`;
                labelsList.style.overflow = 'auto';
            }
            
            e.preventDefault();
        });
        
        document.addEventListener('mouseup', function() {
            if (!isResizing) return;
            
            isResizing = false;
            divider.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = ''; // Restore text selection
            
            // Save the current height
            const labelsList = document.querySelector('.labels-list');
            if (labelsList) {
                const currentHeight = labelsList.style.height.replace('px', '');
                localStorage.setItem('labels-height', currentHeight);
            }
        });
    }

    /**
     * Set up event listeners
     */
    function setupEventListeners() {
        // Add label button
        const addBtn = document.querySelector('.add-label-btn');
        if (addBtn) {
            addBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                showAddLabelModal();
            });
        }

        // Delegate events for dynamic label items
        const labelsList = document.getElementById('labelsList');
        if (labelsList) {
            labelsList.addEventListener('click', function(e) {
                const deleteBtn = e.target.closest('.label-delete-btn');
                if (deleteBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const labelItem = deleteBtn.closest('.label-item');
                    const labelId = labelItem.dataset.labelId;
                    const labelName = labelItem.querySelector('.label-name').textContent;
                    deleteLabel(labelId, labelName);
                }
            });
        }
    }

    /**
     * Load labels from server
     */
    async function loadLabels() {
        try {
            const response = await window.authService.fetch('/api/labels');
            if (!response.ok) throw new Error('Failed to fetch labels');
            
            const data = await response.json();
            labels = data.labels || [];
            renderLabels();
        } catch (error) {
            console.error('Error loading labels:', error);
            document.getElementById('labelsList').innerHTML = 
                '<div class="no-labels-message">Failed to load labels</div>';
        }
    }

    /**
     * Render labels in the menu
     */
    function renderLabels() {
        const labelsList = document.getElementById('labelsList');
        if (!labelsList) return;
    
        if (labels.length === 0) {
            labelsList.innerHTML = '<div class="no-labels-message">No labels yet</div>';
            return;
        }
    
        labelsList.innerHTML = labels.map(label => `
            <div class="label-item" data-label-id="${label.id}">
                <svg class="label-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
                    <line x1="7" y1="7" x2="7.01" y2="7"></line>
                </svg>
                <span class="label-name">${escapeHtml(label.label)}</span>
                <button class="label-delete-btn" title="Delete label">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
        `).join('');
        
        // Add click handlers for filtering
        labelsList.querySelectorAll('.label-item').forEach(item => {
            const labelName = item.querySelector('.label-name');
            if (labelName) {
                labelName.style.cursor = 'pointer';
                labelName.addEventListener('click', function(e) {
                    e.stopPropagation();
                    const labelId = item.dataset.labelId;
                    const name = labelName.textContent;
                    filterChainsByLabel(labelId, name);
                });
            }
        });
    }
    

    /**
     * Show add label modal
     */
    function showAddLabelModal() {
        if (isModalOpen) return;
    
        // Use unique class names that won't conflict with rank modal
        const modalHTML = `
            <div id="labelModal" class="label-modal-container" style="display: flex;">
                <div class="label-modal-dialog">
                    <button class="label-modal-close">&times;</button>
                    <div class="label-modal-header">
                        <h3>Create New Label</h3>
                    </div>
                    <div class="label-modal-body">
                        <input type="text" id="labelNameInput" class="label-input" 
                               placeholder="Enter label name..." maxlength="50" autocomplete="off">
                        <div class="label-input-hint">Max 50 characters</div>
                    </div>
                    <div class="label-modal-footer">
                        <button class="circular-button" id="createLabelBtn">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M9 11l3 3L22 4"></path>
                                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"></path>
                            </svg>
                        </button>
                        <div class="button-label">Create Label</div>
                    </div>
                </div>
            </div>
        `;
    
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        isModalOpen = true;
    
        // Setup modal events with new selectors
        const modal = document.getElementById('labelModal');
        const closeBtn = modal.querySelector('.label-modal-close');
        const createBtn = document.getElementById('createLabelBtn');
        const input = document.getElementById('labelNameInput');
    
        closeBtn.addEventListener('click', closeModal);
        createBtn.addEventListener('click', createLabel);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') createLabel();
        });
    
        // Click outside to close
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    
        input.focus();
    }

    /**
     * Close modal
     */
    function closeModal() {
        const modal = document.getElementById('labelModal');
        if (modal) {
            modal.remove();
            isModalOpen = false;
        }
    }

    /**
     * Create new label
     */
    async function createLabel() {
        const input = document.getElementById('labelNameInput');
        const labelName = input.value.trim();

        if (!labelName) {
            input.focus();
            return;
        }

        const createBtn = document.getElementById('createLabelBtn');
        createBtn.disabled = true;
        createBtn.classList.add('loading');

        try {
            const response = await window.authService.fetch('/api/labels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label: labelName })
            });

            const data = await response.json();

            if (response.ok) {
                labels.push(data.label);
                labels.sort((a, b) => a.label.localeCompare(b.label));
                renderLabels();
                closeModal();
            } else {
                showMessage(data.error || 'Failed to create label', 'error');
            }
        } catch (error) {
            console.error('Error creating label:', error);
            showMessage('Failed to create label', 'error');
        } finally {
            createBtn.disabled = false;
            createBtn.classList.remove('loading');
        }
    }

    /**
     * Delete label
     */
    async function deleteLabel(labelId, labelName) {
        if (!confirm(`Delete label "${labelName}"?\nThis will remove it from all chains.`)) {
            return;
        }

        try {
            const response = await window.authService.fetch(`/api/labels/${labelId}`, { method: 'DELETE' });

            if (response.ok) {
                labels = labels.filter(l => l.id !== parseInt(labelId));
                renderLabels();
            } else {
                showMessage('Failed to delete label', 'error');
            }
        } catch (error) {
            console.error('Error deleting label:', error);
            showMessage('Failed to delete label', 'error');
        }
    }

    async function filterChainsByLabel(labelId, labelName) {
        const isModalOpen = document.getElementById('workflowManagerModal')?.style.display === 'flex';
        
        // Get appropriate search controls
        const searchInput = document.getElementById(isModalOpen ? 'workflowSearchInput' : 'threadsSearchInput');
        const searchClear = document.getElementById(isModalOpen ? 'workflowSearchClear' : 'threadsSearchClear');
        const searchSubmit = document.getElementById(isModalOpen ? 'workflowSearchSubmit' : 'threadsSearchSubmit');
        
        // Update search input
        if (searchInput) {
            searchInput.value = `Label: ${labelName}`;
            searchInput.disabled = true;
            if (searchClear) searchClear.style.display = 'flex';
        }
        if (searchSubmit) searchSubmit.disabled = true;
        
        try {
            // Fetch chains with this label
            const response = await window.authService.fetch(`/api/labels/${labelId}/chains`);
            if (!response.ok) throw new Error('Failed to fetch chains');
            
            const data = await response.json();
            
            if (!data.chain_ids || data.chain_ids.length === 0) {
                if (isModalOpen) {
                    document.getElementById('workflowChainsGrid').innerHTML = 
                        `<div class="workflow-no-chains">No workflows with label "${labelName}"</div>`;
                }
                return;
            }
            
            // Ensure threads DOM exists
            let threadsList = document.getElementById('threads-list');
            if (!threadsList) {
                if (typeof initializeThreadsUI === 'function') {
                    initializeThreadsUI();
                }
                if (typeof loadThreadsList === 'function') {
                    await loadThreadsList();
                }
                threadsList = document.getElementById('threads-list');
                
                if (!threadsList) return;
            }
            
            // Collect matching thread IDs
            const threadsToShow = new Set();
            
            // Hide containers only in threads view
            if (!isModalOpen) {
                threadsList.querySelectorAll('.thread-container').forEach(container => {
                    container.style.display = 'none';
                });
            }
            
            // Find threads containing matching chains
            data.chain_ids.forEach(chainId => {
                const chainElement = threadsList.querySelector(`[data-chain-id="${chainId}"]`);
                if (chainElement) {
                    const parentContainer = chainElement.closest('.thread-container');
                    if (parentContainer) {
                        if (!isModalOpen) {
                            parentContainer.style.display = 'block';
                        }
                        threadsToShow.add(parentContainer.dataset.threadId);
                    }
                }
            });
            
            // Filter modal cards
            if (isModalOpen) {
                const allCards = document.getElementById('workflowChainsGrid')?.querySelectorAll('.workflow-card');
                let visibleCount = 0;
                
                allCards?.forEach(card => {
                    if (threadsToShow.has(card.dataset.threadId)) {
                        card.style.display = 'block';
                        visibleCount++;
                    } else {
                        card.style.display = 'none';
                    }
                });
                
                if (window.showSystemMessage) {
                    window.showSystemMessage(`Showing ${visibleCount} workflow(s) with label "${labelName}"`, 'success');
                }
            }
            
            // Setup clear button
            if (searchClear) {
                searchClear.onclick = () => {
                    searchInput.value = '';
                    searchInput.disabled = false;
                    searchClear.style.display = 'none';
                    if (searchSubmit) searchSubmit.disabled = false;
                    
                    // Reset views
                    if (!isModalOpen) {
                        threadsList?.querySelectorAll('.thread-container').forEach(container => {
                            container.style.display = 'block';
                        });
                    } else {
                        document.getElementById('workflowChainsGrid')?.querySelectorAll('.workflow-card').forEach(card => {
                            card.style.display = 'block';
                        });
                    }
                };
            }
            
        } catch (error) {
            console.error('Error filtering by label:', error);
            if (searchInput) searchInput.value = '';
            if (searchInput) searchInput.disabled = false;
            if (searchClear) searchClear.style.display = 'none';
            if (searchSubmit) searchSubmit.disabled = false;
        }
    }

    /**
     * Show message (uses existing system or console)
     */
    function showMessage(message, type = 'success') {
        if (window.showSystemMessage) {
            window.showSystemMessage(message, type);
        } else {
            console[type === 'error' ? 'error' : 'log'](message);
        }
    }

    /**
     * Escape HTML
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public API
    return {
        initialize,
        refreshLabels: loadLabels,
        filterChainsByLabel,
        initializeResizableDivider,
        showAddLabelModal
    };

})();