//--------------------
//  FILE MANAGEMENT MODULE
//--------------------

window.lastAuxiliaryUploadPath = null;

function initializeFileManagement() {
    console.log('Initializing file management...');
    
    initializePrimaryDatasetUpload();
    initializeAuxiliaryDatasetUpload();
    
    console.log('File management initialized');
}

//--------------------
//  PRIMARY DATASET UPLOAD
//--------------------

function initializePrimaryDatasetUpload() {
    const primaryDatasetButton = document.querySelector('.primary-dataset-option');
    const primaryFileInput = document.getElementById('primaryFile');
    
    if (!primaryDatasetButton || !primaryFileInput) {
        console.warn('Primary dataset upload elements not found');
        return;
    }
    
    primaryDatasetButton.addEventListener('click', function() {
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
        
        primaryFileInput.click();
    });
    
    primaryFileInput.addEventListener('change', handlePrimaryFileUpload);
}

function handlePrimaryFileUpload() {
    const file = this.files[0];
    if (!file) return;

    const pillId = 'primary-dataset-pill-' + Date.now();
    currentDatasetName = file.name;

    createOrUpdateDatasetPill(pillId, `Uploading Primary: "${file.name}"...`, 'primary', 'loading', true, null);

    const formData = new FormData();
    formData.append('file', file);

    window.authService.fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.message || 'Network response was not ok');
            }).catch(() => {
                throw new Error('Network response was not ok and no error details provided.');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.dataframe && typeof createOrUpdateTab === 'function') {
            const dfData = JSON.parse(data.dataframe);
            createOrUpdateTab('dataframe', dfData.data);
        }
        createOrUpdateDatasetPill(pillId, `Primary (${file.name}) loaded`, 'primary', 'success', false, null);
    })
    .catch(error => {
        console.error('Error uploading primary dataset:', error);
        createOrUpdateDatasetPill(pillId, `Error Primary: ${error.message}`, 'primary', 'error', false, null);
        // Reset currentDatasetName on error
        currentDatasetName = null;
    })
    .finally(() => {
        this.value = '';
    });
}

//--------------------
//  AUXILIARY DATASET UPLOAD
//--------------------

function initializeAuxiliaryDatasetUpload() {
    const auxiliaryDatasetButton = document.querySelector('.auxiliary-dataset-option');
    const auxiliaryFileInput = document.getElementById('auxiliaryFile');
    
    if (!auxiliaryDatasetButton || !auxiliaryFileInput) {
        console.warn('Auxiliary dataset upload elements not found');
        return;
    }
    
    auxiliaryDatasetButton.addEventListener('click', function() {
        if (auxiliaryDatasetCount < 3) {
            auxiliaryFileInput.click();
        } else {
            showUploadLimitMessage('Maximum 3 auxiliary datasets allowed.');
        }
    });
    
    auxiliaryFileInput.addEventListener('change', handleAuxiliaryDatasetUpload);
}

function handleAuxiliaryDatasetUpload() {
    if (auxiliaryDatasetCount >= 3) {
        const pillsContainer = document.getElementById('datasetStatusPillsContainer');
        let errorMsgPill = document.getElementById('aux-max-error-pill');
        if (!errorMsgPill) {
            errorMsgPill = document.createElement('div');
            errorMsgPill.id = 'aux-max-error-pill';
            errorMsgPill.className = 'dataset-status-pill auxiliary-dataset-pill error';
            pillsContainer.appendChild(errorMsgPill);
        }
        errorMsgPill.innerHTML = `<div class="dataset-pill-content"><span>Max 3 auxiliary datasets.</span></div>`;
        setTimeout(() => errorMsgPill?.remove(), 3000);
        this.value = '';
        return;
    }

    const file = this.files[0];
    if (!file) return;

    const currentAuxIndex = auxiliaryDatasetCount + 1;
    const pillId = `aux-dataset-pill-${currentAuxIndex}-${Date.now()}`;

    createOrUpdateDatasetPill(pillId, `Uploading Auxiliary ${currentAuxIndex}: "${file.name}"...`, 'auxiliary', 'loading', true, null);

    const formData = new FormData();
    formData.append('file', file);

    window.authService.fetch('/upload_auxiliary_dataset', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.message || 'Network response was not ok');
            }).catch(() => {
                throw new Error('Network response was not ok and no error details provided.');
            });
        }
        return response.json();
    })
    .then(data => {
        auxiliaryDatasetCount = data.aux_dataset_count;
        window.lastAuxiliaryUploadPath = data.filepath;
        createOrUpdateDatasetPill(pillId, `Auxiliary ${auxiliaryDatasetCount} (${file.name}) loaded`, 'auxiliary', 'success', false, data.filepath);
    })
    .catch(error => {
        console.error('Error uploading auxiliary dataset:', error);
        createOrUpdateDatasetPill(pillId, `Error Auxiliary: ${error.message}`, 'auxiliary', 'error', false, null);
    })
    .finally(() => {
        this.value = '';
    });
}





//--------------------
//  DATASET PILL MANAGEMENT
//--------------------

function createOrUpdateDatasetPill(id, text, type, state, isLoading = false, identifier = null) {
    const container = document.getElementById('datasetStatusPillsContainer');
    let pill = document.getElementById(id);

    if (!pill) {
        pill = document.createElement('div');
        pill.id = id;
        container.appendChild(pill);
    }

    pill.className = `dataset-status-pill ${type}-dataset-pill ${state}`;
    if (identifier) {
        pill.dataset.identifier = identifier;
    }
    pill.dataset.datasetType = type;

    pill.innerHTML = `
        <span class="dataset-pill-content ${state === 'success' ? 'clickable-pill-content' : ''}"
              title="${state === 'success' ? 'Click to view ' + text.split('(')[0] : text}">
            <span>${text}</span>
            ${isLoading ? '<div class="file-upload-spinner"></div>' : ''}
        </span>
        ${state === 'success' ? `
            <span class="dataset-pill-remove-icon" data-pill-id="${id}" title="Remove ${type}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="8" y1="12" x2="16" y2="12"></line>
                </svg>
            </span>` : ''
        }
    `;

    const contentSpan = pill.querySelector('.dataset-pill-content');
    if (state === 'success' && contentSpan) {
        contentSpan.addEventListener('click', handleDatasetPillClick);
    }

    const removeIcon = pill.querySelector('.dataset-pill-remove-icon');
    if (removeIcon) {
        removeIcon.addEventListener('click', handleRemoveDatasetPill);
    }
}

async function handleDatasetPillClick(event) {
    const pillContent = event.currentTarget;
    const pillElement = pillContent.closest('.dataset-status-pill');
    const datasetType = pillElement.dataset.datasetType;
    const identifier = pillElement.dataset.identifier;

    const textSpan = pillContent.querySelector('span');
    if (!textSpan) {
        console.error("Could not find text span in pill content.");
        return;
    }

    const originalPillText = textSpan.textContent;
    textSpan.textContent = 'Loading preview...';

    let fetchUrl = '';
    let fetchBody = {};

    if (datasetType === 'primary') {
        fetchUrl = '/get_primary_dataset_preview';
        fetchBody = {};
    } else if (datasetType === 'auxiliary' && identifier) {
        fetchUrl = '/get_dataset_preview';
        fetchBody = { file_path: identifier };
    } else if (datasetType === 'sweatstack') {
        fetchUrl = '/get_primary_dataset_preview';
        fetchBody = {};
    } else if (datasetType === 'intervals') {
        fetchUrl = '/get_primary_dataset_preview';
        fetchBody = {};
    } else if (datasetType === 'endura') {
        fetchUrl = '/get_primary_dataset_preview';
        fetchBody = {};
    } else {
        console.warn('Unknown dataset type or missing identifier.');
        textSpan.textContent = originalPillText;
        if (typeof createOrUpdateTab === 'function') {
            createOrUpdateTab('dataframe', '<div class="error-message" style="padding:10px;">Cannot load preview: Invalid dataset information.</div>');
            activateTab('dataframe');
        }
        return;
    }

    try {
        const response = await window.authService.fetch(fetchUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(fetchBody),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: "Network error or non-JSON response." }));
            throw new Error(errorData.message || `Server error: ${response.status}`);
        }

        const data = await response.json();
        if (data.dataframe_html && typeof createOrUpdateTab === 'function') {
            const dfData = JSON.parse(data.dataframe_html);
            createOrUpdateTab('dataframe', dfData.data);
            if (typeof activateTab === 'function') {
                activateTab('dataframe');
            }
        } else {
            throw new Error(`No dataframe HTML received from server for ${datasetType} dataset.`);
        }
    } catch (error) {
        console.error(`Error fetching ${datasetType} dataset preview:`, error);
        const errorHtml = `<div class="error-message" style="padding:10px;">Failed to load preview: ${error.message}</div>`;
        if (typeof createOrUpdateTab === 'function') {
            createOrUpdateTab('dataframe', errorHtml);
            if (typeof activateTab === 'function') {
                activateTab('dataframe');
            }
        }
    } finally {
        if (textSpan) {
             textSpan.textContent = originalPillText;
        }
    }
}

async function handleRemoveDatasetPill(event) {
    event.stopPropagation();

    const removeButton = event.currentTarget;
    const pillId = removeButton.dataset.pillId;
    const pillElement = document.getElementById(pillId);

    if (!pillElement) return;

    const datasetType = pillElement.dataset.datasetType;
    const identifier = pillElement.dataset.identifier;

    removeButton.style.opacity = '0.3';
    removeButton.style.pointerEvents = 'none';
    const pillContentSpan = pillElement.querySelector('.dataset-pill-content > span');
    const originalText = pillContentSpan ? pillContentSpan.textContent : '';
    if (pillContentSpan) pillContentSpan.textContent = 'Removing...';

    let fetchUrl = '';
    let fetchPayload = null;
    let isPrimaryRemoval = false;
    let isAuxiliaryRemoval = false;
    let isSweatStackRemoval = false;
    let isIntervalsRemoval = false;
    let isEnduraRemoval = false;

    if (datasetType === 'primary') {
        fetchUrl = '/remove_primary_dataset';
        fetchPayload = JSON.stringify({});
        isPrimaryRemoval = true;
    } else if (datasetType === 'auxiliary' && identifier) {
        fetchUrl = '/remove_auxiliary_dataset';
        fetchPayload = JSON.stringify({ file_path: identifier });
        // Pre-existing copy-paste bug set the ONTOLOGY flag here, routing
        // every auxiliary removal through the ontology response branch -
        // silently harmless while that state object existed, a visible
        // ReferenceError once it retired. Auxiliary now routes as itself.
        isAuxiliaryRemoval = true;
    } else if (datasetType === 'sweatstack') {
        fetchUrl = '/sweatstack/remove_data';
        fetchPayload = JSON.stringify({});
        isSweatStackRemoval = true;
    } else if (datasetType === 'intervals') {
        fetchUrl = '/intervals/remove_data';
        fetchPayload = JSON.stringify({});
        isIntervalsRemoval = true;
    } else if (datasetType === 'endura') {
        fetchUrl = '/endura/remove_data';
        fetchPayload = JSON.stringify({});
        isEnduraRemoval = true;
    } else {
        console.error('Cannot remove: Unknown dataset type or missing identifier.');
        if (pillContentSpan) pillContentSpan.textContent = originalText;
        removeButton.style.opacity = '0.6';
        removeButton.style.pointerEvents = 'auto';
        return;
    }

    try {
        const fetchOptions = {
            method: 'POST',
            body: fetchPayload
        };
        if (!(fetchPayload instanceof FormData)) {
            fetchOptions.headers = { 'Content-Type': 'application/json' };
        }

        const response = await window.authService.fetch(fetchUrl, fetchOptions);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || `Server error: ${response.status}`);
        }

        pillElement.remove();

        if (isPrimaryRemoval) {
            currentDatasetName = null;
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('dataframe', '<div style="padding:10px; text-align:center; color:var(--text-secondary);">Primary dataset removed.</div>');
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
        } else if (isAuxiliaryRemoval) {
            auxiliaryDatasetCount = data.aux_count
                ?? Math.max(0, auxiliaryDatasetCount - 1);
            console.log(data.message);
        } else if (isSweatStackRemoval) {
            // Use SweatStack module function
            if (window.SweatStack && typeof window.SweatStack.removePill === 'function') {
                window.SweatStack.removePill();
            }
            currentDatasetName = null;
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('dataframe', '<div style="padding:10px; text-align:center; color:var(--text-secondary);">SweatStack dataset removed.</div>');
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            console.log(data.message);
        } else if (isIntervalsRemoval) {
            // Use Intervals module function
            if (window.Intervals && typeof window.Intervals.removePill === 'function') {
                window.Intervals.removePill();
            }
            currentDatasetName = null;
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('dataframe', '<div style="padding:10px; text-align:center; color:var(--text-secondary);">Intervals ICU dataset removed.</div>');
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            console.log(data.message);
        } else if (isEnduraRemoval) {  // Add Endura removal handling
            // Use Endura module function
            if (window.Endura && typeof window.Endura.removePill === 'function') {
                window.Endura.removePill();
            }
            currentDatasetName = null;
            if (typeof createOrUpdateTab === 'function') {
                createOrUpdateTab('dataframe', '<div style="padding:10px; text-align:center; color:var(--text-secondary);">Endura dataset removed.</div>');
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            console.log(data.message);
        } else {
            auxiliaryDatasetCount = data.remaining_aux_count !== undefined ? data.remaining_aux_count : Math.max(0, auxiliaryDatasetCount - 1);
        }

    } catch (error) {
        console.error(`Error removing ${datasetType}:`, error);
        alert(`Failed to remove ${datasetType}: ${error.message}`);
        if (pillContentSpan) pillContentSpan.textContent = originalText;
        removeButton.style.opacity = '0.6';
        removeButton.style.pointerEvents = 'auto';
    }
}

//--------------------
//  UPLOAD LIMIT MESSAGING
//--------------------

function showUploadLimitMessage(message) {
    const messageDiv = document.getElementById('uploadLimitMessage');
    if (!messageDiv) return;

    messageDiv.textContent = message;
    messageDiv.classList.add('visible');

    if (limitMessageTimeout) {
        clearTimeout(limitMessageTimeout);
    }

    limitMessageTimeout = setTimeout(() => {
        messageDiv.classList.remove('visible');
        limitMessageTimeout = null;
    }, 3000);
}