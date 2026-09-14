//--------------------
//  CONTAINER STATUS MODULE (FIXED)
//--------------------

let containerStatusData = {
    status: 'offline',
    ip: null,
    port: null,
    job_id: null,
    error: null,
    lastUpdated: null
};

let isExecuting = false;
const STATUS_TEXT = { ready: 'Ready', execution: 'Executing', spawning: 'Starting', restarting: 'Restarting', failed: 'Failed', offline: 'Offline' };
let isRestarting = false;
let restartJobId = null;
let statusPollingInterval = null;
const POLLING_INTERVAL = 7000; // 7 seconds

// Define the icon SVG
const BOX_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
    <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
    <line x1="12" y1="22.08" x2="12" y2="12"></line>
</svg>`;

function initializeContainerStatus() {
    console.log('Initializing container status monitoring...');
    
    // Start polling after a short delay to ensure auth is ready
    setTimeout(() => {
        startStatusPolling();
    }, 1000);
}

function startStatusPolling() {
    // Clear any existing interval
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
    }
    
    // Initial status check
    checkContainerStatus();
    
    // Start regular polling
    statusPollingInterval = setInterval(checkContainerStatus, POLLING_INTERVAL);
    console.log('Container status polling started');
}

function stopStatusPolling() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
        console.log('Container status polling stopped');
    }
}

async function checkContainerStatus() {
    try {
        const response = await window.authService.fetch('/api/container/status', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            updateContainerStatus(data);
        } else {
            updateContainerStatus({ status: 'offline', error: 'API request failed' });
        }
    } catch (error) {
        console.error('Container status check failed:', error);
        updateContainerStatus({ status: 'offline', error: error.message });
    }
}

function clearAllUploadedData() {
    // Reset SweatStack state
    currentSweatStackState.isLoaded = false;
    currentSweatStackState.pillId = null;
    currentSweatStackState.dataInfo = null;
    
    // Reset dataset counters and names
    auxiliaryDatasetCount = 0;
    currentDatasetName = null;
    
    // Clear the dataset pills container
    const pillsContainer = document.getElementById('datasetStatusPillsContainer');
    if (pillsContainer) {
        pillsContainer.innerHTML = '';
    }

    // Clear the dataset tab
    if (typeof createOrUpdateTab === 'function') {
        createOrUpdateTab('dataframe', '<div style="padding:10px; text-align:center; color:var(--text-secondary);">Dataset removed.</div>');
        if (typeof activateTab === 'function') {
            activateTab('dataframe');
        }
    }
    
    console.log('Cleared all uploaded data state - container offline/restarting');
}

async function restartContainer() {
    try {
        restartJobId = containerStatusData.job_id;
        
        // Change container status to orange "Restarting" (same pattern as execution)
        const containerStatus = document.getElementById('containerStatus');
        if (containerStatus) {
            // Set restart flag to prevent polling from overriding
            isRestarting = true;
            
            containerStatus.className = 'container-status status-restarting';
            const statusText = containerStatus.querySelector('.container-status-text');
            const statusIcon = containerStatus.querySelector('.container-status-icon');
            
            if (statusText) {
                statusText.textContent = 'Restarting';
            }
        }
        
        console.log('Initiating container restart...');
    
        try {
            const response = await window.authService.fetch('/api/container/restart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            // Always start waiting regardless of response status
            waitForReadyThenReload();
            
            if (response.ok) {
                const data = await response.json();
                console.log('Container restart initiated successfully:', data.message);
            } else {
                try {
                    const errorData = await response.json();
                    console.log('Restart API returned non-OK status, but restart may still be in progress:', errorData);
                } catch {
                    console.log('Restart API returned non-OK status, but restart may still be in progress');
                }
            }
        } catch (fetchError) {
            console.log('Restart API call failed, but monitoring for container status anyway:', fetchError.message);
            waitForReadyThenReload();
        }
        
    } catch (error) {
        console.error('Unexpected error in restartContainer:', error);
        waitForReadyThenReload();
    }
}

function waitForReadyThenReload() {
    const readyCheck = setInterval(() => {
        // Wait for status=ready AND a different job_id than when we started
        if (containerStatusData.status === 'ready' && 
            containerStatusData.job_id && 
            containerStatusData.job_id !== restartJobId) {
            
            clearInterval(readyCheck);
            console.log('Container restarted with new job_id, reloading...');
            
            // Reload window
            window.location.replace(window.location.pathname + '?new=true');
        }
    }, 1000);
    
    setTimeout(() => {
        clearInterval(readyCheck);
        isRestarting = false;
    }, 300000);
}

function updateContainerStatus(data) {
    containerStatusData = {
        ...containerStatusData,
        ...data,
        lastUpdated: new Date()
    };
    
    updateStatusUI();
}

// Then simplify your updateStatusUI function - remove the entire switch statement and replace with:
function updateStatusUI() {
    const statusElement = document.getElementById('containerStatus');
    const statusIcon = document.getElementById('containerStatusIcon');
    const statusText = document.getElementById('containerStatusText');
    
    if (!statusElement || !statusIcon || !statusText) return;

    // ALWAYS update the tooltip, even during execution or restart
    updateStatusTooltip();
    
    if (isRestarting) {
        return;
    }
    
    if (isExecuting) {
        return;
    }
    
    // Update status class
    statusElement.className = `container-status status-${containerStatusData.status}`;
    
    // Clear dataset pills when container is offline, restarting, or spawning
    if (containerStatusData.status === 'offline' || 
        containerStatusData.status === 'restarting' || 
        containerStatusData.status === 'spawning') {
        clearAllUploadedData();
    }
    
    // Set icon once (only if it's empty or different)
    if (statusIcon.innerHTML !== BOX_ICON) {
        statusIcon.innerHTML = BOX_ICON;
    }
    
    // Update text based on status
    const statusTextMap = {
        'ready': 'Ready',
        'spawning': 'Starting',
        'restarting': 'Restarting',
        'failed': 'Failed',
        'offline': 'Offline'
    };
    
    statusText.textContent = statusTextMap[containerStatusData.status] || 'Offline';
    // the self-hosted edition (2026-09-14): the kernel on this machine, or one executor named in .env
    if (containerStatusData.status === 'ready' && containerStatusData.tier === 'local') statusText.textContent = 'Local';
    if (containerStatusData.status === 'ready' && containerStatusData.tier === 'docker') statusText.textContent = 'Docker';
}

function updateStatusTooltip() {
    const statusElement = document.getElementById('containerStatus');
    if (!statusElement) return;
    
    let tooltipLines = [];
    
    // Show execution/restart status if currently executing or restarting
    if (isRestarting) {
        tooltipLines.push('Status: Restarting Container');
        tooltipLines.push('Please wait for page reload...');
    } else if (isExecuting) {
        tooltipLines.push('Status: Executing Code');
        tooltipLines.push('Long-running job in progress...');
    } else {
        // Normal status line
        tooltipLines.push(`Status: ${containerStatusData.status.charAt(0).toUpperCase() + containerStatusData.status.slice(1)}`);
    }
    
    // Container details for ready state (show even during execution)
    if (containerStatusData.status === 'ready') {
        if (containerStatusData.ram_allocated) {
            tooltipLines.push(`RAM: ${containerStatusData.ram_allocated}`);
        }
        
        if (containerStatusData.uptime_minutes !== undefined) {
            const uptimeText = containerStatusData.uptime_minutes < 60 
                ? `${containerStatusData.uptime_minutes}m`
                : `${Math.floor(containerStatusData.uptime_minutes / 60)}h ${containerStatusData.uptime_minutes % 60}m`;
            tooltipLines.push(`Uptime: ${uptimeText}`);
        }
    }
    
    // Error details for failed state
    if (containerStatusData.status === 'failed' && containerStatusData.error) {
        tooltipLines.push(`Error: ${containerStatusData.error}`);
    }
    
    // Spawning details
    if (containerStatusData.status === 'spawning') {
        tooltipLines.push('Starting container...');
    }
    
    // Restarting details
    if (containerStatusData.status === 'restarting') {
        tooltipLines.push('Restarting container...');
    }
    
    // Offline details
    if (containerStatusData.status === 'offline') {
        if (containerStatusData.error) {
            tooltipLines.push(`Reason: ${containerStatusData.error}`);
        } else {
            tooltipLines.push('No active container');
        }
    }
    
    // Last updated
    if (containerStatusData.lastUpdated) {
        tooltipLines.push(`Updated: ${containerStatusData.lastUpdated.toLocaleTimeString()}`);
    }
    
    // Show restart button ONLY for ready, failed states, or during execution
    // Never show for offline, spawning, or restarting states
    const shouldShowRestartButton = !isRestarting && (
        containerStatusData.status === 'ready' || 
        containerStatusData.status === 'failed' ||
        isExecuting
    );
    
    // Add note about interrupting execution if currently executing
    if (isExecuting && shouldShowRestartButton) {
        tooltipLines.push(''); // Empty line for spacing
        tooltipLines.push('Click restart to interrupt stale job');
    }
    
    // Always use the DOM-based tooltip approach
    createTooltip(statusElement, tooltipLines.join('\n'), shouldShowRestartButton);
}

function createTooltip(statusElement, tooltipText, showRestartButton = false) {
    let tooltip = document.querySelector('.container-status-tooltip[data-for="containerStatus"]');
    
    // Check if tooltip is currently visible (being hovered)
    const isCurrentlyVisible = tooltip && tooltip.style.visibility === 'visible';
    
    // Remove existing tooltip
    if (tooltip) {
        tooltip.remove();
    }
    
    // Create new tooltip
    tooltip = document.createElement('div');
    tooltip.className = 'container-status-tooltip';
    tooltip.setAttribute('data-for', 'containerStatus');
    
    if (showRestartButton) {
        tooltip.innerHTML = `
            <div class="tooltip-content">${tooltipText.replace(/\n/g, '<br>')}</div>
            <button class="container-restart-button" onclick="restartContainerFromTooltip(event)">
                Restart Container
            </button>
        `;
    } else {
        tooltip.innerHTML = `
            <div class="tooltip-content">${tooltipText.replace(/\n/g, '<br>')}</div>
        `;
    }
    
    document.body.appendChild(tooltip);
    
    // Position it
    const rect = statusElement.getBoundingClientRect();
    tooltip.style.position = 'fixed';
    tooltip.style.top = `${rect.bottom + 8}px`;
    tooltip.style.right = `${window.innerWidth - rect.right}px`;
    tooltip.style.zIndex = '2147483647';
    
    // IMPORTANT: Restore visibility if it was visible before
    tooltip.style.visibility = isCurrentlyVisible ? 'visible' : 'hidden';
    
    // Shared hover state
    let hoverTimeout = null;
    
    const showTooltip = () => {
        clearTimeout(hoverTimeout);
        const tooltip = document.querySelector('.container-status-tooltip[data-for="containerStatus"]');
        if (tooltip) {
            const rect = statusElement.getBoundingClientRect();
            tooltip.style.top = `${rect.bottom + 8}px`;
            tooltip.style.right = `${window.innerWidth - rect.right}px`;
            tooltip.style.visibility = 'visible';
        }
    };
    
    const hideTooltip = () => {
        clearTimeout(hoverTimeout);
        hoverTimeout = setTimeout(() => {
            const tooltip = document.querySelector('.container-status-tooltip[data-for="containerStatus"]');
            if (tooltip) {
                tooltip.style.visibility = 'hidden';
            }
        }, 100);
    };
    
    // Remove old listeners if they exist
    if (statusElement._tooltipListeners) {
        statusElement.removeEventListener('mouseenter', statusElement._tooltipListeners.mouseenter);
        statusElement.removeEventListener('mouseleave', statusElement._tooltipListeners.mouseleave);
    }
    
    // Store and add new listeners
    statusElement._tooltipListeners = {
        mouseenter: showTooltip,
        mouseleave: hideTooltip
    };
    
    statusElement.addEventListener('mouseenter', showTooltip);
    statusElement.addEventListener('mouseleave', hideTooltip);
    
    // Add listeners to tooltip itself
    tooltip.addEventListener('mouseenter', showTooltip);
    tooltip.addEventListener('mouseleave', hideTooltip);
}

function removeTooltipElement() {
    // Remove tooltip from body
    const existing = document.querySelector('.container-status-tooltip[data-for="containerStatus"]');
    if (existing) {
        existing.remove();
    }
}

function restartContainerFromTooltip(event) {
    event.preventDefault();
    event.stopPropagation();
    
    // Confirm restart
    if (confirm('Are you sure you want to restart the container? This will interrupt any running processes.')) {
        restartContainer();
    }
}

// Make restartContainerFromTooltip globally available
window.restartContainerFromTooltip = restartContainerFromTooltip;

// Export functions for external use
window.containerStatus = {
    initialize: initializeContainerStatus,
    start: startStatusPolling,
    stop: stopStatusPolling,
    restart: restartContainer,
    getCurrentStatus: () => containerStatusData,
    setExecuting: (executing) => { 
        isExecuting = executing;
        // the chip itself (2026-09-08): sand and "Executing" while a cell runs, then back to the polled status
        const el = document.getElementById('containerStatus'); const txt = el && el.querySelector('.container-status-text');
        if (el && !isRestarting) {
            if (executing) { el.className = 'container-status status-execution'; if (txt) txt.textContent = 'Executing'; }
            else if (containerStatusData && containerStatusData.status) { el.className = `container-status status-${containerStatusData.status}`; if (txt) txt.textContent = STATUS_TEXT[containerStatusData.status] || containerStatusData.status; }
        }
        // Update tooltip when execution state changes
        updateStatusTooltip();
    }
};