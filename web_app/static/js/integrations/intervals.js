//--------------------
//  INTERVALS ICU INTEGRATION MODULE
//--------------------

// Intervals-specific state
let currentIntervalsState = {
    isLoaded: false,
    pillId: null,
    dataInfo: null
};

function initializeIntervalsIntegration() {
    console.log('Initializing Intervals ICU integration...');
    
    initializeIntervalsDataOption();
    initializeIntervalsModals();
    
    console.log('Intervals ICU integration initialized');
}

//--------------------
//  INTERVALS DATA LOADING
//--------------------

function initializeIntervalsDataOption() {
    const intervalsDataButton = document.querySelector('.intervals-data-option');

    if (!intervalsDataButton) {
        console.log('Intervals ICU data option not found (not configured)');
        return;
    }

    intervalsDataButton.addEventListener('click', function() {
        console.log('Intervals ICU data option clicked');
        
        // Check if primary dataset already exists
        if (currentDatasetName) {
            showUploadLimitMessage('Primary dataset already loaded. Remove current to upload new.');
            return; 
        }
        
        // Check if SweatStack data is loaded
        if (window.SweatStack && window.SweatStack.state.isLoaded) {
            showUploadLimitMessage('SweatStack data already loaded. Remove current to upload primary dataset.');
            return;
        }

        // Check if Intervals data is loaded
        if (window.Intervals && window.Intervals.state.isLoaded) {
            showUploadLimitMessage('Intervals ICU data already loaded. Remove current to upload primary dataset.');
            return;
        }

        // Check if Endura data is loaded
        if (window.Endura && window.Endura.state.isLoaded) {
            showUploadLimitMessage('Endura data already loaded. Remove current to upload primary dataset.');
            return;
        }
    
        showIntervalsModal();
    });
}

async function applyIntervalsDateLimits() {
    try {
        const response = await window.authService.fetch('/intervals/get_data_limits');
        const limits = await response.json();
        
        const today = new Date();
        const maxDays = limits.max_days || 14;
        
        // Calculate earliest allowed date
        const earliestDate = new Date(today);
        earliestDate.setDate(today.getDate() - maxDays);
        
        const startDateInput = document.getElementById('intervalsStartDate');
        const endDateInput = document.getElementById('intervalsEndDate');
        
        // Set end date to today
        endDateInput.value = today.toISOString().split('T')[0];
        endDateInput.max = today.toISOString().split('T')[0];
        
        // Set start date to max allowed
        startDateInput.value = earliestDate.toISOString().split('T')[0];
        startDateInput.min = earliestDate.toISOString().split('T')[0];
        startDateInput.max = today.toISOString().split('T')[0];
        
        // Lock the inputs to prevent bypassing
        endDateInput.min = earliestDate.toISOString().split('T')[0];
        
    } catch (error) {
        console.error('Error fetching data limits:', error);
        // Default to 14 days on error
        const today = new Date();
        const twoWeeksAgo = new Date(today);
        twoWeeksAgo.setDate(today.getDate() - 14);
        
        document.getElementById('intervalsStartDate').value = twoWeeksAgo.toISOString().split('T')[0];
        document.getElementById('intervalsEndDate').value = today.toISOString().split('T')[0];
    }
}

function createIntervalsPill(dataInfo) {
    const pillId = 'intervals-pill-' + Date.now();
    const dayCount = Math.ceil((new Date(dataInfo.end_date) - new Date(dataInfo.start_date)) / (1000 * 60 * 60 * 24));
    const auxDatasets = dataInfo.aux_datasets || [];
    let auxText = '';
    if (auxDatasets.includes('wellness')) auxText += 'W';
    if (auxDatasets.includes('summary')) auxText += auxText ? '+S' : 'S';
    if (auxDatasets.includes('intervals')) auxText += auxText ? '+I' : 'I';
    if (auxText) auxText = ` [${auxText}]`;
    
    const displayText = `Intervals ICU (${dayCount} days${auxText}) loaded`;

    if (typeof createOrUpdateDatasetPill === 'function') {
        createOrUpdateDatasetPill(pillId, displayText, 'intervals', 'success', false, 'intervals_data');
    }

    // Update global state
    currentIntervalsState.isLoaded = true;
    currentIntervalsState.pillId = pillId;
    currentIntervalsState.dataInfo = dataInfo;

    console.log('Intervals ICU data pill created successfully');
}

function createIntervalsAuxiliaryPills(auxDatasets, dataInfo) {
    if (!auxDatasets || auxDatasets.length === 0) return;
    const dayCount = Math.ceil((new Date(dataInfo.end_date) - new Date(dataInfo.start_date)) / (1000 * 60 * 60 * 24));
    
    auxDatasets.forEach((filepath, index) => {
        const filename = filepath.split('/').pop();
        
        let displayName = '';
        if (filename.includes('wellness_data')) {
            displayName = `Wellness Summary (${dayCount} days)`;
        } else if (filename.includes('activity_summary')) {
            displayName = `Activity Summary (${dayCount} days)`;
        } else if (filename.includes('activity_intervals')) {
            displayName = `Activity Intervals (${dayCount} days)`;
        } else {    
            displayName = filename.replace('.csv', '');
        }
        
        const pillId = `intervals-aux-pill-${Date.now()}-${index}`;
        
        if (typeof createOrUpdateDatasetPill === 'function') {
            createOrUpdateDatasetPill(
                pillId, 
                `Auxiliary (${displayName})`, 
                'auxiliary', 
                'success', 
                false, 
                filepath
            );
        }
    });
    
    if (typeof window.auxiliaryDatasetCount !== 'undefined') {
        window.auxiliaryDatasetCount = (window.auxiliaryDatasetCount || 0) + auxDatasets.length;
    }
}

function removeIntervalsPill() {
    if (currentIntervalsState.pillId) {
        const pill = document.getElementById(currentIntervalsState.pillId);
        if (pill) {
            pill.remove();
        }

        // Reset global state
        currentIntervalsState.isLoaded = false;
        currentIntervalsState.pillId = null;
        currentIntervalsState.dataInfo = null;

        console.log('Intervals ICU data pill removed');
    }
}



//--------------------
//  API KEY MANAGEMENT
//--------------------

async function checkIntervalsApiKey() {
    try {
        const response = await window.authService.fetch('/intervals/status');
        const data = await response.json();
        return data.has_api_key || false;
    } catch (error) {
        console.error('Error checking Intervals API key:', error);
        return false;
    }
}

async function saveIntervalsApiKey(apiKey) {
    try {
        const response = await window.authService.fetch('/intervals/store_api_key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save API key');
        }
        
        return true;
    } catch (error) {
        console.error('Error saving Intervals API key:', error);
        throw error;
    }
}

async function removeIntervalsApiKey() {
    try {
        const response = await window.authService.fetch('/intervals/remove_api_key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to remove API key');
        }
        
        return true;
    } catch (error) {
        console.error('Error removing Intervals API key:', error);
        throw error;
    }
}

//--------------------
//  INTERVALS MODAL SYSTEM
//--------------------

function initializeIntervalsModals() {
    initializeIntervalsMainModal();
    initializeIntervalsConfigModal();
}

function initializeIntervalsMainModal() {
    const modal = document.getElementById('intervalsModal');
    const closeButton = modal?.querySelector('.close');
    const connectButton = document.getElementById('connectIntervals');

    if (!modal || !closeButton || !connectButton) {
        console.warn('Intervals modal elements not found');
        return;
    }

    closeButton.addEventListener('click', hideIntervalsModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) hideIntervalsModal();
    });

    connectButton.addEventListener('click', function() {
        const dateRange = getIntervalsDateRange();
        const auxDatasets = getSelectedAuxDatasets();
        
        // Validation
        const daysDiff = Math.ceil((new Date(dateRange.end) - new Date(dateRange.start)) / (1000 * 60 * 60 * 24));
        if (daysDiff > 365) {
            showIntervalsMessage('Date range cannot exceed 1 year.', 'error');
            return;
        }
        
        if (daysDiff <= 0) {
            showIntervalsMessage('Please select a valid date range.', 'error');
            return;
        }
    
        setIntervalsButtonLoading(true);
        
        // The ontology download option retired with the ontology; memory
        // packs attach from the Cache manager modal (see MEMORY_LEDGER.md).
        Promise.resolve().then(() => {
            showIntervalsMessage('Starting data load...', 'loading');
            
            // Start the job
            return window.authService.fetch('/intervals/load_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_date: dateRange.start,
                    end_date: dateRange.end,
                    metrics: [],
                    aux_datasets: auxDatasets
                })
            });
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || `Server error: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            // Start polling for job status
            pollIntervalsJob(data.job_id, dateRange, auxDatasets);
        })
        .catch(error => {
            console.error('Error starting Intervals load:', error);
            setIntervalsButtonLoading(false);
            showIntervalsMessage(`Failed to start: ${error.message}`, 'error');
        });
    });
}

function pollIntervalsJob(jobId, dateRange, auxDatasets) {
    let jobCompleted = false;  // Add flag to prevent multiple completions
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await window.authService.fetch(`/intervals/job/${jobId}`);
            const job = await response.json();
            
            if (job.status === 'processing' || job.status === 'starting') {
                // Update progress message
                let message = job.message || 'Processing...';
                if (job.percent !== undefined) {
                    message += ` (${job.percent}%)`;
                }
                showIntervalsMessage(message, 'loading');
                
            } else if (job.status === 'completed' && !jobCompleted) {  // Check flag
                jobCompleted = true;  // Set flag immediately
                clearInterval(pollInterval);  // Clear interval first
                
                console.log('Intervals ICU data loaded successfully');
                setIntervalsButtonLoading(false);
                showIntervalsMessage('Data loaded successfully!', 'success');

                setTimeout(() => {
                    hideIntervalsModal();
                }, 2000);

                // Create pill ONLY ONCE
                const dataInfo = {
                    start_date: dateRange.start,
                    end_date: dateRange.end,
                    aux_datasets: auxDatasets,
                    shape: job.result.shape,
                    columns: job.result.columns
                };
                createIntervalsPill(dataInfo);

                if (job.result && job.result.aux_datasets && job.result.aux_datasets.length > 0) {
                    createIntervalsAuxiliaryPills(job.result.aux_datasets, dataInfo);
                }

                // Update dataframe tab if available
                if (job.dataframe) {
                    try {
                        const dfData = JSON.parse(job.dataframe);
                        if (typeof createOrUpdateTab === 'function') {
                            createOrUpdateTab('dataframe', dfData.data);
                            if (typeof activateTab === 'function') {
                                activateTab('dataframe');
                            }
                        }

                        if (typeof window !== 'undefined' && typeof currentDatasetName !== 'undefined') {
                            //Total number of days
                            currentDatasetName = `Intervals ICU Data`;
                        }
                    } catch (error) {
                        console.error('Error parsing Intervals dataframe:', error);
                    }
                }
                
            } else if (job.status === 'error' && !jobCompleted) {  // Also check flag for errors
                jobCompleted = true;  // Set flag
                clearInterval(pollInterval);
                
                console.error('Intervals job failed:', job.error);
                setIntervalsButtonLoading(false);
                showIntervalsMessage(`Failed: ${job.error}`, 'error');
                
            } else if (job.status === 'not_found') {
                clearInterval(pollInterval);
                
                console.error('Job not found');
                setIntervalsButtonLoading(false);
                showIntervalsMessage('Job expired or not found', 'error');
            }
            
        } catch (error) {
            // Keep polling even if one request fails
            console.error('Error polling job status:', error);
        }
    }, 1000); // Poll every 1 seconds
    
    // Safety timeout after 5 minutes
    setTimeout(() => {
        if (!jobCompleted) {  // Only timeout if not completed
            clearInterval(pollInterval);
            setIntervalsButtonLoading(false);
            showIntervalsMessage('Operation timed out', 'error');
        }
    }, 300000);
}

function initializeIntervalsConfigModal() {
    const modal = document.getElementById('intervalsConfigModal');
    const closeButton = modal?.querySelector('.close');
    const apiKeyInput = document.getElementById('intervalsApiKeyInput');
    const saveButton = document.getElementById('saveIntervalsApiKey');
    const removeButton = document.getElementById('removeIntervalsApiKey');
    const statusIndicator = document.getElementById('intervalsApiKeyStatus');

    if (!modal || !closeButton) {
        console.warn('Intervals config modal elements not found');
        return;
    }

    closeButton.addEventListener('click', () => modal.style.display = 'none');
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.style.display = 'none';
    });
    
    // Initialize API key status when modal opens
    modal.addEventListener('show', updateApiKeyStatus);
    
    // Save API key
    if (saveButton) {
        saveButton.addEventListener('click', async function() {
            const apiKey = apiKeyInput?.value?.trim();
            
            if (!apiKey) {
                showIntervalsConfigMessage('Please enter your API key', 'error');
                return;
            }
            
            // Show loading state
            saveButton.disabled = true;
            saveButton.textContent = 'Saving...';
            
            try {
                await saveIntervalsApiKey(apiKey);
                showIntervalsConfigMessage('API key saved successfully!', 'success');
                
                // Update status indicator
                await updateApiKeyStatus();
                
                // Clear input for security
                apiKeyInput.value = '';
                
                // Close modal after success
                setTimeout(() => {
                    modal.style.display = 'none';
                    // Reload to update button visibility
                    window.location.reload();
                }, 1500);
                
            } catch (error) {
                showIntervalsConfigMessage(`Failed to save API key: ${error.message}`, 'error');
            } finally {
                saveButton.disabled = false;
                saveButton.textContent = 'Save';
            }
        });
    }
    
    // Remove API key
    if (removeButton) {
        removeButton.addEventListener('click', async function() {
            if (!confirm('Are you sure you want to remove your Intervals.icu API key?')) {
                return;
            }
            
            // Show loading state
            removeButton.disabled = true;
            removeButton.textContent = 'Removing...';
            
            try {
                await removeIntervalsApiKey();
                showIntervalsConfigMessage('API key removed successfully', 'success');
                
                // Update status indicator
                await updateApiKeyStatus();
                
                // Close modal after success
                setTimeout(() => {
                    modal.style.display = 'none';
                    // Reload to update button visibility
                    window.location.reload();
                }, 1500);
                
            } catch (error) {
                showIntervalsConfigMessage(`Failed to remove API key: ${error.message}`, 'error');
            } finally {
                removeButton.disabled = false;
                removeButton.textContent = 'Remove';
            }
        });
    }
}

async function updateApiKeyStatus() {
    const statusIndicator = document.getElementById('intervalsApiKeyStatus');
    const apiKeyInput = document.getElementById('intervalsApiKeyInput');
    const removeButton = document.getElementById('removeIntervalsApiKey');
    
    if (!statusIndicator) return;
    
    try {
        const hasKey = await checkIntervalsApiKey();
        
        if (hasKey) {
            statusIndicator.innerHTML = `
                <svg class="status-icon success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span>API key is configured</span>
            `;
            statusIndicator.className = 'api-key-status has-key';
            
            // Show masked placeholder
            if (apiKeyInput) {
                apiKeyInput.placeholder = '••••••••••••••••••••••••••••••••';
            }
            
            // Show remove button
            if (removeButton) {
                removeButton.style.display = 'inline-block';
            }
        } else {
            statusIndicator.innerHTML = `
                <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                <span>No API key configured</span>
            `;
            statusIndicator.className = 'api-key-status no-key';
            
            // Show regular placeholder
            if (apiKeyInput) {
                apiKeyInput.placeholder = 'Enter your Intervals.icu API key';
            }
            
            // Hide remove button
            if (removeButton) {
                removeButton.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error updating API key status:', error);
        statusIndicator.innerHTML = '<span>Unable to check API key status</span>';
        statusIndicator.className = 'api-key-status error';
    }
}

function showIntervalsConfigMessage(message, type = 'default') {
    const messageElement = document.getElementById('intervals-config-message');
    if (!messageElement) return;
    
    messageElement.classList.remove('success-message', 'error-message', 'loading-message');
    
    switch(type) {
        case 'loading':
            messageElement.classList.add('loading-message');
            messageElement.textContent = message;
            break;
        case 'success':
            messageElement.classList.add('success-message');
            messageElement.textContent = '✓ ' + message;
            break;
        case 'error':
            messageElement.classList.add('error-message');
            messageElement.textContent = '✗ ' + message;
            break;
        default:
            messageElement.textContent = message;
    }
    
    messageElement.style.display = 'block';
    
    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            messageElement.style.display = 'none';
        }, 3000);
    }
}

//--------------------
//  MODAL DISPLAY FUNCTIONS
//--------------------

function showIntervalsModal() {
    const modal = document.getElementById('intervalsModal');
    if (modal) {
        modal.style.display = 'flex';
        showIntervalsMessage('', 'default');
        initializeIntervalsDatePickers();
        initializeAuxDatasetOptions();
    }
}

async function showIntervalsConfigModal() {
    const modal = document.getElementById('intervalsConfigModal');
    if (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        // Update API key status before showing
        await updateApiKeyStatus();
        
        modal.style.display = 'flex';
        
        // Trigger custom event for modal show
        const event = new Event('show');
        modal.dispatchEvent(event);
    }
}

function hideIntervalsModal() {
    const modal = document.getElementById('intervalsModal');
    if (modal) modal.style.display = 'none';
}

//--------------------
//  FORM HANDLING
//--------------------

function initializeIntervalsDatePickers() {
    const startDateInput = document.getElementById('intervalsStartDate');
    const endDateInput = document.getElementById('intervalsEndDate');
    
    if (!startDateInput || !endDateInput) return;
    
    // Apply subscription limits immediately
    applyIntervalsDateLimits();
    
    // Simple validation - dates are already constrained by min/max
    startDateInput.addEventListener('change', function() {
        if (endDateInput.value && this.value > endDateInput.value) {
            this.value = endDateInput.value;
        }
    });
    
    endDateInput.addEventListener('change', function() {
        if (startDateInput.value && this.value < startDateInput.value) {
            this.value = startDateInput.value;
        }
    });
}

function initializeAuxDatasetOptions() {
    // Handle auxiliary dataset options
    const auxOptions = document.querySelectorAll('.intervals-aux-option');
    
    auxOptions.forEach((option) => {
        // Remove any existing listeners
        const existingListener = option._clickListener;
        if (existingListener) {
            option.removeEventListener('click', existingListener);
        }

        const clickListener = function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const checkbox = option.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            
            checkbox.checked = !checkbox.checked;
            option.classList.toggle('selected', checkbox.checked);
        };

        option._clickListener = clickListener;
        option.addEventListener('click', clickListener);
    });

    // Initialize selected state for aux datasets
    document.querySelectorAll('.intervals-aux-option input[type="checkbox"]:checked').forEach(checkbox => {
        const label = checkbox.closest('.intervals-aux-option');
        if (label) label.classList.add('selected');
    });
}

//--------------------
//  SELECTION FUNCTIONS
//--------------------

function getIntervalsDateRange() {
    const startDate = document.getElementById('intervalsStartDate')?.value;
    const endDate = document.getElementById('intervalsEndDate')?.value;
    
    if (!startDate || !endDate) {
        const end = new Date();
        const start = new Date();
        start.setMonth(start.getMonth() - 3);
        
        return {
            start: start.toISOString().split('T')[0],
            end: end.toISOString().split('T')[0]
        };
    }
    
    return { start: startDate, end: endDate };
}

function getSelectedAuxDatasets() {
    const auxDatasets = [];
    const wellnessCheckbox = document.getElementById('wellness-checkbox');
    const summaryCheckbox = document.getElementById('summary-checkbox');
    const intervalsCheckbox = document.getElementById('intervals-checkbox');
    
    if (wellnessCheckbox?.checked) auxDatasets.push('wellness');
    if (summaryCheckbox?.checked) auxDatasets.push('summary');
    if (intervalsCheckbox?.checked) auxDatasets.push('intervals');
    
    return auxDatasets;
}

//--------------------
//  UI HELPER FUNCTIONS
//--------------------

function showIntervalsMessage(message, type = 'default') {
    const messageElement = document.getElementById('intervals-modal-message');
    if (!messageElement) return;
    
    messageElement.classList.remove('success-message', 'error-message', 'loading-message');
    
    switch(type) {
        case 'loading':
            messageElement.classList.add('loading-message');
            messageElement.textContent = message;
            break;
        case 'success':
            messageElement.classList.add('success-message');
            messageElement.textContent = '✓ ' + message;
            break;
        case 'error':
            messageElement.classList.add('error-message');
            messageElement.textContent = '✗ ' + message;
            break;
        default:
            messageElement.innerHTML = message;
    }
}

function setIntervalsButtonLoading(isLoading) {
    const connectButton = document.getElementById('connectIntervals');
    const buttonLabel = connectButton?.parentElement?.querySelector('.button-label');
    
    if (!connectButton) return;
    
    if (isLoading) {
        connectButton.classList.add('loading');
        connectButton.disabled = true;
        if (buttonLabel) buttonLabel.textContent = 'Loading Data...';
    } else {
        connectButton.classList.remove('loading');
        connectButton.disabled = false;
        if (buttonLabel) buttonLabel.textContent = 'Load Data';
    }
}

//--------------------
//  INTEGRATION WITH MAIN APP
//--------------------

function handleIntervals() {
    const intervalsOption = document.querySelector('.intervals-option');
    const isEnabled = intervalsOption?.getAttribute('data-enabled') === 'true';

    if (!isEnabled) {
        showIntervalsConfigModal();
    } else {
        // For now, just show the config modal since we don't have OAuth
        // In the future, this could handle OAuth flow
        showIntervalsConfigModal();
    }
}

// Export functions for use by other modules
if (typeof window !== 'undefined') {
    window.Intervals = {
        initialize: initializeIntervalsIntegration,
        handleIntervals: handleIntervals,
        createPill: createIntervalsPill,
        removePill: removeIntervalsPill,
        showModal: showIntervalsModal,
        hideModal: hideIntervalsModal,
        state: currentIntervalsState,
        pollJob: pollIntervalsJob
    };
}