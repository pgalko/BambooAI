// agent-instructions.js
(function() {
    'use strict';
    
    // Initialize modal
    function initializeModal() {
        if (!document.getElementById('agentInstructionsModal')) {
            const modalHtml = `
                <div id="agentInstructionsModal" class="agent-instructions-modal-container ui-modal-plain">
                    <div class="agent-instructions-modal-content ui-dlg lg">
                        <div class="agent-instructions-header ui-dlg-h">
                            <div><div id="agentInstructionsTitle" class="title">The prompt</div><div class="sub">what the seat received for this chain, from the run log</div></div>
                            <span class="sp"></span>
                            <button class="agent-instructions-close x">&times;</button>
                        </div>
                        <div class="agent-instructions-body ui-dlg-b">
                            <div class="instructions-section">
                                <div class="section-header" data-section="system">
                                    <svg class="expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                    <span>System prompt (the contract)</span>
                                    <button class="copy-btn" data-section="system" title="Copy to clipboard">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                                        </svg>
                                    </button>
                                </div>
                                <div class="section-content" id="systemInstructions"></div>
                            </div>
                            <div class="instructions-section">
                                <div class="section-header" data-section="user">
                                    <svg class="expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                    <span>Turn prompt (data, question, note, cells, task)</span>
                                    <button class="copy-btn" data-section="user" title="Copy to clipboard">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                                        </svg>
                                    </button>
                                </div>
                                <div class="section-content" id="userInstructions"></div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            setupModalControls();
        }
    }
    
    // Setup modal controls
    function setupModalControls() {
        const modal = document.getElementById('agentInstructionsModal');
        const closeBtn = modal.querySelector('.agent-instructions-close');
        
        // Close button
        closeBtn.addEventListener('click', closeModal);
        
        // Background click
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeModal();
            }
        });
        
        // Section expand/collapse
        modal.querySelectorAll('.section-header').forEach(header => {
            header.addEventListener('click', function(e) {
                if (!e.target.closest('.copy-btn')) {
                    const section = header.closest('.instructions-section');
                    section.classList.toggle('collapsed');
                }
            });
        });
        
        // Copy buttons
        modal.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const section = btn.dataset.section;
                copyToClipboard(section);
            });
        });
    }
    
    // Fetch and display instructions
    async function showInstructions(agent, chainId, call) {
        if (!chainId) {
            console.error('No chain ID available');
            if (window.showSystemMessage) {
                window.showSystemMessage('Chain ID not available yet. Please try again.', 'error');
            }
            return;
        }
        
        const modal = document.getElementById('agentInstructionsModal');
        const systemContent = document.getElementById('systemInstructions');
        const userContent = document.getElementById('userInstructions');
        const title = document.getElementById('agentInstructionsTitle');
        
        // Show loading state
        modal.style.display = 'flex';
        title.textContent = `Loading ${agent} Instructions...`;
        systemContent.innerHTML = '<div class="loading">Loading...</div>';
        userContent.innerHTML = '<div class="loading">Loading...</div>';
        
        try {
            const response = await window.authService.fetch(
                `/api/agent-instructions/${chainId}/${agent}` + (call ? `?call=${encodeURIComponent(call)}` : '')
            );
            
            if (!response.ok) throw new Error('Failed to fetch instructions');
            
            const data = await response.json();
            
            // Update title
            title.textContent = `The prompt - ${agent}` + (data.call ? ` (call ${data.call} of ${data.calls})` : '');
            
            // Format and display content
            systemContent.innerHTML = formatInstructionContent(data.system);
            userContent.innerHTML = formatInstructionContent(data.user);
            
            // Store raw content for copying
            systemContent.dataset.rawContent = data.system;
            userContent.dataset.rawContent = data.user;
            
        } catch (error) {
            console.error('Error fetching instructions:', error);
            systemContent.innerHTML = '<div class="error">Failed to load instructions</div>';
            userContent.innerHTML = '<div class="error">Failed to load instructions</div>';
        }
    }
    
    // Format instruction content with special handling
    function formatInstructionContent(content) {
        if (!content) return '<div class="empty">No instructions available</div>';
        
        // Escape HTML first to prevent XSS
        let formatted = escapeHtml(content);
        
        // Highlight XML-like tags
        formatted = highlightXmlTags(formatted);
        
        // Format data sections (no tables, just aligned text)
        formatted = formatDataSections(formatted);
        
        // Convert line breaks for readability - but don't double them
        formatted = formatted.replace(/\n/g, '<br>');
        
        return `<div class="instruction-content">${formatted}</div>`;
    }
    
    // Highlight XML tags
    function highlightXmlTags(content) {
        // Match escaped XML-like tags and wrap them
        return content.replace(
            /&lt;([^&]+)&gt;/g,
            '<span class="xml-tag">&lt;$1&gt;</span>'
        );
    }
    
    function formatDataSections(content) {
        // Split content into lines
        const lines = content.split('\n');
        let result = [];
        let dataLines = [];
        let inDataSection = false;
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            
            // Check if this line looks like structured data
            const hasMultipleColons = (line.match(/:/g) || []).length >= 2;
            const hasMultiplePipes = (line.match(/\|/g) || []).length >= 2;
            const hasMultipleSpaces = line.includes('  '); // Multiple spaces indicate columns
            
            if (hasMultipleColons || hasMultiplePipes || (hasMultipleSpaces && line.split(/\s{2,}/).length > 2)) {
                if (!inDataSection) {
                    inDataSection = true;
                    dataLines = [];
                }
                dataLines.push(line);
            } else if (inDataSection) {
                // End of data section - format collected lines
                if (dataLines.length > 0) {
                    // Just add the lines with preserved spacing, no special formatting
                    dataLines.forEach(dataLine => {
                        result.push(dataLine);
                    });
                }
                inDataSection = false;
                dataLines = [];
                result.push(lines[i]); // Add current non-data line
            } else {
                result.push(lines[i]);
            }
        }
        
        // Handle any remaining data lines
        if (dataLines.length > 0) {
            dataLines.forEach(dataLine => {
                result.push(dataLine);
            });
        }
        
        return result.join('\n');
    }
    
    // Copy to clipboard
    function copyToClipboard(section) {
        const content = document.getElementById(`${section}Instructions`);
        const rawContent = content.dataset.rawContent;
        
        if (!rawContent) return;
        
        navigator.clipboard.writeText(rawContent).then(() => {
            if (window.showSystemMessage) {
                window.showSystemMessage(`${section} instructions copied to clipboard`, 'success');
            }
        }).catch(err => {
            console.error('Failed to copy:', err);
            if (window.showSystemMessage) {
                window.showSystemMessage('Failed to copy to clipboard', 'error');
            }
        });
    }
    
    // Close modal
    function closeModal() {
        const modal = document.getElementById('agentInstructionsModal');
        modal.style.display = 'none';
        
        // Reset expanded/collapsed states
        modal.querySelectorAll('.instructions-section.collapsed').forEach(section => {
            section.classList.remove('collapsed');
        });
    }
    
    // Helper function to escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // the restored-chain path (workflow-management.js) rebinds its buttons and calls this name (2026-09-10)
    window.showAgentInstructions = showInstructions;

    // Setup event delegation for instruction buttons
    function setupButtonHandlers() {
        document.addEventListener('click', function(e) {
            const btn = e.target.closest('.agent-instructions-btn');
            if (btn) {
                const agent = btn.dataset.agent;
                const chainId = btn.dataset.chain;
                const call = btn.dataset.call;
                console.log('Clicked instructions for agent:', agent, 'Chain:', chainId, 'call:', call);
                showInstructions(agent, chainId, call);
            }
        });
    }
    
    // Export for external use if needed
    window.AgentInstructions = {
        showInstructions: showInstructions,
        initialize: function() {
            console.log('Initializing Agent Instructions module...');
            initializeModal();
            setupButtonHandlers();
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.AgentInstructions.initialize);
    } else {
        window.AgentInstructions.initialize();
    }
})();