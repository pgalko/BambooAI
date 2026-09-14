// Dataset Manager Module - Updated with Generated Datasets Support
window.DatasetManager = (function() {
    'use strict';
    
    let currentDatasets = {
        cached: [],
        auxiliary: [],
        generated: []
    };
    let selectedDataset = null;
    
    function initialize() {
        console.log('Initializing Dataset Manager...');
        
        // Create modal
        createModal();
        
        // Set up event handlers
        setupEventHandlers();
        
        // Set up button handlers
        setupButtonHandlers();
    }
    
    function createModal() {
        const modal = document.createElement('div');
        modal.id = 'datasetManagerModal';
        modal.className = 'modal ui-modal';
        modal.innerHTML = `
            <div class="modal-content ui-dlg lg">
                <div class="dataset-modal-header ui-dlg-h">
                    <div><div class="dataset-modal-title title">Dataset cache</div><div class="sub">datasets held on your executor - primary, auxiliary and generated</div></div>
                    <span class="sp"></span>
                    <button class="close x" aria-label="Close">×</button>
                </div>
                <div class="dataset-modal-body">
                    <div class="dataset-list-panel">
                        <div class="dataset-category">
                            <h4>Primary</h4>
                            <div id="primaryDatasetList"></div>
                        </div>
                        <div class="dataset-category">
                            <h4>Auxiliary</h4>
                            <div id="auxiliaryDatasetList"></div>
                        </div>
                        <div class="dataset-category">
                            <h4>Generated</h4>
                            <div id="generatedDatasetList"></div>
                        </div>
                    </div>
                    <div class="dataset-details-panel">
                        <div id="datasetDetails" class="dataset-details-empty">Select a dataset to see its details</div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    function setupEventHandlers() {
        // Pill click handler
        const pill = document.getElementById('datasetManagerPill');
        if (pill) {
            pill.addEventListener('click', showModal);
        }
        
        // Modal close handlers
        const modal = document.getElementById('datasetManagerModal');
        const closeButton = modal?.querySelector('.close');
        
        if (closeButton) {
            closeButton.addEventListener('click', hideModal);
        }
        
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) hideModal();
            });
        }
    }
    
    function setupButtonHandlers() {
        // Use event delegation for dynamically created buttons
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('dataset-load-btn')) {
                handleLoadDataset(e.target);
            } else if (e.target.classList.contains('dataset-remove-btn')) {
                handleRemoveDataset(e.target);
            } else if (e.target.classList.contains('dataset-download-btn')) {
                handleDownloadDataset(e.target);
            }
        });
    }
    
    async function handleLoadDataset(button) {
        const dfId = button.dataset.dfId;
        const filePath = button.dataset.path;
        
        if (dfId) {
            await loadPrimaryDataset(dfId);
        } else if (filePath) {
            // Load both auxiliary and generated datasets as auxiliary
            await loadAuxiliaryDataset(filePath);
        }
    }

    async function handleRemoveDataset(button) {
        const dfId = button.dataset.dfId;
        const filePath = button.dataset.path;
        
        if (dfId) {
            await removePrimaryDataset(dfId);
        } else if (filePath) {
            await removeAuxiliaryDataset(filePath);
        }
    }
    
    async function handleDownloadDataset(button) {
        const filePath = button.dataset.path;
        
        if (filePath) {
            // Use the existing main app download endpoint
            window.authService.fetch(`/download_generated_dataset?path=${encodeURIComponent(filePath)}`)
                .then(response => {
                    if (!response.ok) throw new Error('Download failed');
                    return response.blob();
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filePath.split('/').pop();
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                })
                .catch(error => {
                    console.error('Error downloading dataset:', error);
                    alert('Failed to download dataset');
                });
        }
    }

    function showModal() {
        const modal = document.getElementById('datasetManagerModal');
        if (modal) {
            modal.style.display = 'flex';
            loadDatasets();
        }
    }
    
    function hideModal() {
        const modal = document.getElementById('datasetManagerModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    function loadDatasets() {
        // Show loading state
        showLoadingState();
        
        // Fetch cache data from backend
        window.authService.fetch('/cache/inspect', { method: 'GET' })
        .then(cacheResponse => {
            if (!cacheResponse.ok) {
                throw new Error(`Failed to fetch datasets: ${cacheResponse.status}`);
            }
            return cacheResponse.json();
        })
        .then(cacheData => {
            currentDatasets.cached = cacheData.cached_dataframes || [];
            currentDatasets.auxiliary = cacheData.auxiliary_datasets || [];
            currentDatasets.generated = cacheData.generated_datasets || [];
            displayDatasets();
        })
        .catch(error => {
            console.error('Error loading datasets:', error);
            showErrorState('Failed to load datasets');
        });
    }
    
    function displayDatasets() {
        // Display primary datasets
        const primaryList = document.getElementById('primaryDatasetList');
        if (primaryList) {
            primaryList.innerHTML = '';
            
            if (currentDatasets.cached.length === 0) {
                primaryList.innerHTML = '<div class="dataset-empty">No cached datasets</div>';
            } else {
                currentDatasets.cached.forEach(dataset => {
                    const item = createDatasetItem(dataset, 'primary');
                    primaryList.appendChild(item);
                });
            }
        }
        
        // Display auxiliary datasets
        const auxList = document.getElementById('auxiliaryDatasetList');
        if (auxList) {
            auxList.innerHTML = '';
            
            if (currentDatasets.auxiliary.length === 0) {
                auxList.innerHTML = '<div class="dataset-empty">No auxiliary datasets</div>';
            } else {
                currentDatasets.auxiliary.forEach(dataset => {
                    const item = createDatasetItem(dataset, 'auxiliary');
                    auxList.appendChild(item);
                });
            }
        }

        // Display generated datasets
        const genList = document.getElementById('generatedDatasetList');
        if (genList) {
            genList.innerHTML = '';
            
            if (currentDatasets.generated.length === 0) {
                genList.innerHTML = '<div class="dataset-empty">No generated datasets</div>';
            } else {
                currentDatasets.generated.forEach(dataset => {
                    const item = createDatasetItem(dataset, 'generated');
                    genList.appendChild(item);
                });
            }
        }
    }
    
    function createDatasetItem(dataset, type) {
        const item = document.createElement('div');
        item.className = 'dataset-item';
        
        // Add type-specific class for styling
        if (type === 'generated') {
            item.classList.add('generated-type');
        }
        
        if (type === 'primary') {
            const name = dataset.source === 'csv' ? 
                (dataset.original_filename || 'Dataset') : 
                `${dataset.source || 'Dataset'} (${dataset.shape[0]} rows)`;
            
            item.innerHTML = `
                <span class="dataset-item-name">${name}</span>
                <span class="dataset-size">${dataset.memory_mb.toFixed(3)} MB</span>
            `;
            item.dataset.id = dataset.df_id;
            item.dataset.type = 'primary';
        } else if (type === 'generated') {
            // Generated datasets with download icon
            item.innerHTML = `
                <svg class="dataset-icon-download" viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
                    <path d="M8 2a.5.5 0 0 1 .5.5v8.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 1 1 .708-.708L7.5 11.293V2.5A.5.5 0 0 1 8 2z"/>
                    <path d="M2.5 14a.5.5 0 0 1 0-1h11a.5.5 0 0 1 0 1h-11z"/>
                </svg>
                <span class="dataset-item-name">${dataset.filename}</span>
                <span class="dataset-size">${dataset.size_mb.toFixed(3)} MB</span>
            `;
            item.dataset.path = dataset.path;
            item.dataset.type = 'generated';
        } else {
            item.innerHTML = `
                <span class="dataset-item-name">${dataset.filename}</span>
                <span class="dataset-size">${dataset.size_mb.toFixed(3)} MB</span>
            `;
            item.dataset.path = dataset.path;
            item.dataset.type = 'auxiliary';
        }
        
        item.addEventListener('click', () => selectDataset(dataset, type));
        
        return item;
    }

    function selectDataset(dataset, type) {
        // Update active state
        document.querySelectorAll('.dataset-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');
        
        // Store selected dataset
        selectedDataset = { dataset, type };
        
        // Load and display details
        if (type === 'primary') {
            loadPrimaryDatasetDetails(dataset);
        } else if (type === 'generated') {
            loadGeneratedDatasetDetails(dataset);
        } else {
            loadAuxiliaryDatasetDetails(dataset);
        }
    }
    
    function loadPrimaryDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Fetch detailed preview
        window.authService.fetch(`/cache/preview/${dataset.df_id}`, {
            method: 'GET'
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayPrimaryDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }
    
    function loadAuxiliaryDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Fetch auxiliary dataset preview
        window.authService.fetch('/cache/preview_aux', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: dataset.path })
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayAuxiliaryDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }

    function loadGeneratedDatasetDetails(dataset) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.innerHTML = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading details...</div>';
        
        // Use same preview endpoint as auxiliary (they're both files)
        window.authService.fetch('/cache/preview_aux', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: dataset.path })
        })
        .then(response => {
            if (!response.ok) throw new Error('Failed to load details');
            return response.json();
        })
        .then(details => {
            displayGeneratedDetails(details);
        })
        .catch(error => {
            console.error('Error loading dataset details:', error);
            detailsPanel.innerHTML = '<div class="dataset-details-empty">Failed to load dataset details</div>';
        });
    }
    
    function displayPrimaryDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>Dataset Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">ID:</span>
                        <span class="metadata-value">${details.df_id}</span>
                        
                        <span class="metadata-label">Shape:</span>
                        <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
        `;
        
        if (details.metadata) {
            if (details.metadata.source) {
                html += `
                    <span class="metadata-label">Source:</span>
                    <span class="metadata-value">${details.metadata.source}</span>
                `;
            }
            
            // Add Endura-specific metadata
            if (details.metadata.source === 'endura') {
                if (details.metadata.race_title) {
                    html += `
                        <span class="metadata-label">Race:</span>
                        <span class="metadata-value">${details.metadata.race_title}</span>
                    `;
                }
                if (details.metadata.race_date) {
                    html += `
                        <span class="metadata-label">Race Date:</span>
                        <span class="metadata-value">${details.metadata.race_date}</span>
                    `;
                }
                if (details.metadata.athletes_count) {
                    html += `
                        <span class="metadata-label">Athletes:</span>
                        <span class="metadata-value">${details.metadata.athletes_count}</span>
                    `;
                }
            }
            
            // Existing date_range and cached_at handling
            if (details.metadata.date_range) {
                html += `
                    <span class="metadata-label">Date Range:</span>
                    <span class="metadata-value">${details.metadata.date_range}</span>
                `;
            }
            if (details.metadata.cached_at) {
                html += `
                    <span class="metadata-label">Cached:</span>
                    <span class="metadata-value">${new Date(details.metadata.cached_at).toLocaleString()}</span>
                `;
            }
        }
        
        html += `
                    </div>
                </div>
                
                <div class="dataset-info-section">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
        `;
        
        details.columns.forEach(col => {
            html += `<span class="column-chip">${col}</span>`;
        });
        
        html += `
                        </div>
                    </div>
                </div>
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-df-id="${details.df_id}">Load</button>
                <button class="dataset-action-btn dataset-remove-btn" data-df-id="${details.df_id}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }
    
    function displayAuxiliaryDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>File Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">Filename:</span>
                        <span class="metadata-value">${details.filename}</span>
                        
                        <span class="metadata-label">Path:</span>
                        <span class="metadata-value">${details.path}</span>
                        
                        <span class="metadata-label">Size:</span>
                        <span class="metadata-value">${details.size_mb.toFixed(3)} MB</span>
        `;
        
        if (details.shape) {
            html += `
                <span class="metadata-label">Shape:</span>
                <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
            `;
        }
        
        html += `
                        <span class="metadata-label">Created:</span>
                        <span class="metadata-value">${new Date(details.created_at).toLocaleString()}</span>
                        
                        <span class="metadata-label">Modified:</span>
                        <span class="metadata-value">${new Date(details.modified_at).toLocaleString()}</span>
                    </div>
                </div>
        `;
        
        if (details.columns && details.columns.length > 0) {
            html += `
                <div class="dataset-info-section">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
            `;
            
            details.columns.forEach(col => {
                html += `<span class="column-chip">${col}</span>`;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += `
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-path="${details.path}">Load</button>
                <button class="dataset-action-btn dataset-remove-btn" data-path="${details.path}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }
    
    function displayGeneratedDetails(details) {
        const detailsPanel = document.getElementById('datasetDetails');
        detailsPanel.classList.remove('dataset-details-empty');
        
        let html = `
            <div class="dataset-details-content">
                <div class="dataset-info-section">
                    <h3>Generated File Information</h3>
                    <div class="dataset-metadata">
                        <span class="metadata-label">Filename:</span>
                        <span class="metadata-value">${details.filename}</span>
                        
                        <span class="metadata-label">Path:</span>
                        <span class="metadata-value">${details.path}</span>
                        
                        <span class="metadata-label">Size:</span>
                        <span class="metadata-value">${details.size_mb.toFixed(3)} MB</span>
        `;
        
        if (details.shape) {
            html += `
                <span class="metadata-label">Shape:</span>
                <span class="metadata-value">${details.shape[0]} rows × ${details.shape[1]} columns</span>
            `;
        }
        
        html += `
                        <span class="metadata-label">Generated:</span>
                        <span class="metadata-value">${new Date(details.created_at).toLocaleString()}</span>
                    </div>
                </div>
        `;
        
        if (details.columns && details.columns.length > 0) {
            html += `
                <div class="dataset-info-section">
                    <h3>Columns (${details.columns.length})</h3>
                    <div class="dataset-columns">
                        <div class="column-list">
            `;
            
            details.columns.forEach(col => {
                html += `<span class="column-chip">${col}</span>`;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += `
            </div>
            <div class="dataset-actions">
                <button class="dataset-action-btn dataset-load-btn" data-path="${details.path}">Load</button>
                <button class="dataset-action-btn dataset-download-btn" data-path="${details.path}">Download</button>
                <button class="dataset-action-btn dataset-remove-btn" data-path="${details.path}">Remove</button>
            </div>
        `;
        
        detailsPanel.innerHTML = html;
    }

    async function removePrimaryDataset(dfId) {
        // Update button state
        const removeButton = document.querySelector(`.dataset-remove-btn[data-df-id="${dfId}"]`);
        const originalText = removeButton ? removeButton.textContent : 'Remove';
        
        if (removeButton) {
            removeButton.textContent = 'Removing...';
            removeButton.classList.add('loading');
            removeButton.disabled = true;
        }
        
        try {
            const response = await window.authService.fetch('/cache/remove_primary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ df_id: dfId })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to remove dataset');
            }
            
            // Get dataset info to determine source
            const dataset = currentDatasets.cached.find(d => d.df_id === dfId);
            
            // Remove pills based on dataset source
            if (dataset) {
                if (dataset.source === 'sweatstack') {
                    // Remove SweatStack pill
                    if (window.SweatStack && window.SweatStack.state.pillId) {
                        const pill = document.getElementById(window.SweatStack.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear SweatStack state
                    if (window.SweatStack) {
                        window.SweatStack.state.isLoaded = false;
                        window.SweatStack.state.pillId = null;
                    }
                } else if (dataset.source === 'intervals') {
                    // Remove Intervals pill
                    if (window.Intervals && window.Intervals.state.pillId) {
                        const pill = document.getElementById(window.Intervals.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear Intervals state
                    if (window.Intervals) {
                        window.Intervals.state.isLoaded = false;
                        window.Intervals.state.pillId = null;
                    }
                } else if (dataset.source === 'endura') {
                    // Remove Endura pill
                    if (window.Endura && window.Endura.state.pillId) {
                        const pill = document.getElementById(window.Endura.state.pillId);
                        if (pill) pill.remove();
                    }
                    // Clear Endura state
                    if (window.Endura) {
                        window.Endura.state.isLoaded = false;
                        window.Endura.state.pillId = null;
                        window.Endura.state.raceInfo = null;
                    }
                } else {
                    // Remove regular primary dataset pills
                    const pills = document.querySelectorAll('.primary-dataset-pill');
                    pills.forEach(pill => {
                        // Check if it's a cache-loaded pill
                        if (pill.id && (pill.id.startsWith('cache-primary-pill-') || pill.id.startsWith('gen-primary-pill-'))) {
                            pill.remove();
                        }
                    });
                }
            } else {
                // Fallback: remove any primary pills if dataset info not found
                const pills = document.querySelectorAll('.primary-dataset-pill');
                pills.forEach(pill => {
                    if (pill.id && (pill.id.startsWith('cache-primary-pill-') || pill.id.startsWith('gen-primary-pill-'))) {
                        pill.remove();
                    }
                });
            }
            
            // Clear global state
           currentDatasetName = null;
            
            // Clear the details pane if this was the selected dataset
            if (selectedDataset && selectedDataset.dataset.df_id === dfId) {
                const detailsPanel = document.getElementById('datasetDetails');
                if (detailsPanel) {
                    detailsPanel.className = 'dataset-details-empty';
                    detailsPanel.innerHTML = 'Select a dataset to view details';
                }
                selectedDataset = null;
            }
            
            // Refresh cache display
            loadDatasets();
            
            console.log('Primary dataset removed from cache');
            
        } catch (error) {
            console.error('Error removing primary dataset:', error);
            alert(`Failed to remove dataset: ${error.message}`);
        } finally {
            if (removeButton) {
                removeButton.textContent = originalText;
                removeButton.classList.remove('loading');
                removeButton.disabled = false;
            }
        }
    }
    
    async function removeAuxiliaryDataset(filePath) {
        // Update button state
        const removeButton = document.querySelector(`.dataset-remove-btn[data-path="${filePath}"]`);
        const originalText = removeButton ? removeButton.textContent : 'Remove';
        
        if (removeButton) {
            removeButton.textContent = 'Removing...';
            removeButton.classList.add('loading');
            removeButton.disabled = true;
        }
        
        try {
            const response = await window.authService.fetch('/cache/remove_auxiliary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to remove dataset');
            }
            
            const data = await response.json();
            
            // Find and remove the pill if it exists
            const pills = document.querySelectorAll('.auxiliary-dataset-pill');
            pills.forEach(pill => {
                if (pill.dataset.identifier === filePath) {
                    pill.remove();
                }
            });
            
            // Update auxiliary count
            auxiliaryDatasetCount = data.aux_count || Math.max(0, auxiliaryDatasetCount - 1);
            
            // Clear the details pane if this was the selected dataset
            if (selectedDataset && selectedDataset.dataset.path === filePath) {
                const detailsPanel = document.getElementById('datasetDetails');
                if (detailsPanel) {
                    detailsPanel.className = 'dataset-details-empty';
                    detailsPanel.innerHTML = 'Select a dataset to view details';
                }
                selectedDataset = null;
            }
            
            // Refresh cache display
            loadDatasets();
            
            console.log('Auxiliary dataset removed from cache');
            
        } catch (error) {
            console.error('Error removing auxiliary dataset:', error);
            alert(`Failed to remove dataset: ${error.message}`);
        } finally {
            if (removeButton) {
                removeButton.textContent = originalText;
                removeButton.classList.remove('loading');
                removeButton.disabled = false;
            }
        }
    }
    
    async function loadPrimaryDataset(dfId) {
        // Check if primary dataset already exists
        if (currentDatasetName) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('Primary dataset already loaded. Remove current to load new.');
            }
            return;
        }
        
        // Check if SweatStack data is loaded
        if (window.SweatStack && window.SweatStack.state.isLoaded) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('SweatStack data already loaded. Remove current to load primary dataset.');
            }
            return;
        }
        
        // Check if Intervals data is loaded
        if (window.Intervals && window.Intervals.state.isLoaded) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('Intervals ICU data already loaded. Remove current to load primary dataset.');
            }
            return;
        }

        // Check if Endura data is loaded
        if (window.Endura && window.Endura.state.isLoaded) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('Endura data already loaded. Remove current to load primary dataset.');
            }
            return;
        }
        
        // Find and update the load button
        const loadButton = document.querySelector(`.dataset-load-btn[data-df-id="${dfId}"]`);
        const originalText = loadButton ? loadButton.textContent : 'Load';
        
        if (loadButton) {
            loadButton.textContent = 'Loading...';
            loadButton.classList.add('loading');
            loadButton.disabled = true;
        }
        
        try {
            // Call backend to load the dataset
            const response = await window.authService.fetch('/cache/load_primary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ df_id: dfId })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load dataset');
            }
            
            const data = await response.json();

            // Handle dataframe preview - render tab
            if (data.dataframe && typeof createOrUpdateTab === 'function') {
                const dfData = JSON.parse(data.dataframe);
                createOrUpdateTab('dataframe', dfData.data);
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            
            // Get dataset info from cache for pill creation
            const dataset = currentDatasets.cached.find(d => d.df_id === dfId);
            if (dataset) {
                const pillId = 'cache-primary-pill-' + Date.now();
                let displayText = '';
                let pillType = 'primary';
                
                // Determine display text based on source
                if (dataset.source === 'csv') {
                    displayText = `Primary (${dataset.original_filename || 'Dataset'}) loaded`;
                    currentDatasetName = dataset.original_filename || 'Dataset';
                    pillType = 'primary'
                } else if (dataset.source === 'intervals') {
                    displayText = `Intervals ICU (${dataset.activities_count} activities) loaded`;
                    currentDatasetName = `Intervals ICU Data`;
                    pillType = 'intervals';
                    
                    // Update Intervals state if module exists
                    if (window.Intervals) {
                        window.Intervals.state.isLoaded = true;
                        window.Intervals.state.pillId = pillId;
                    }
                } else if (dataset.source === 'sweatstack') {
                    // List sports
                    displayText = `SweatStack (${dataset.sports.join(', ')}) loaded`;
                    currentDatasetName = `SweatStack Data`;
                    pillType = 'sweatstack';

                    // Update SweatStack state if module exists
                    if (window.SweatStack) {
                        window.SweatStack.state.isLoaded = true;
                        window.SweatStack.state.pillId = pillId;
                    }
                } else if (dataset.source === 'endura') {
                    // Handle Endura dataset
                    displayText = `Endura (${dataset.race_title || 'Race'}) loaded`;
                    currentDatasetName = `Endura Race Data`;
                    pillType = 'endura';
                    
                    // Update Endura state if module exists
                    if (window.Endura) {
                        window.Endura.state.isLoaded = true;
                        window.Endura.state.pillId = pillId;
                        window.Endura.state.raceInfo = {
                            race_id: dataset.race_id,
                            race_title: dataset.race_title,
                            race_date: dataset.race_date
                        };
                    }
                } else {
                    displayText = `Primary (${dataset.source || 'Dataset'}) loaded`;
                    currentDatasetName = dataset.source || 'Dataset';
                    pillType = 'primary';
                }
                
                // Create pill using file-management function
                if (typeof createOrUpdateDatasetPill === 'function') {
                    createOrUpdateDatasetPill(pillId, displayText, pillType, 'success', false, null);
                }
            }
            
            // Close modal
            hideModal();
            
            // Show success message
            console.log('Primary dataset loaded successfully from cache');
            
        } catch (error) {
            console.error('Error loading primary dataset:', error);
            alert(`Failed to load dataset: ${error.message}`);
        } finally {
            // Restore button state
            if (loadButton) {
                loadButton.textContent = originalText;
                loadButton.classList.remove('loading');
                loadButton.disabled = false;
            }
        }
    }
    
    async function loadAuxiliaryDataset(filePath) {
        // Check auxiliary limit
        if (auxiliaryDatasetCount >= 3) {
            if (typeof showUploadLimitMessage === 'function') {
                showUploadLimitMessage('Maximum 3 auxiliary datasets allowed.');
            }
            return;
        }
        
        // Find and update the load button
        const loadButton = document.querySelector(`.dataset-load-btn[data-path="${filePath}"]`);
        const originalText = loadButton ? loadButton.textContent : 'Load';
        
        if (loadButton) {
            loadButton.textContent = 'Loading...';
            loadButton.classList.add('loading');
            loadButton.disabled = true;
        }
        
        try {
            // Call backend to load the dataset
            const response = await window.authService.fetch('/cache/load_auxiliary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load dataset');
            }
            
            const data = await response.json();
            
            // Handle dataframe preview - same as primary
            if (data.dataframe && typeof createOrUpdateTab === 'function') {
                const dfData = JSON.parse(data.dataframe);
                createOrUpdateTab('dataframe', dfData.data);
                if (typeof activateTab === 'function') {
                    activateTab('dataframe');
                }
            }
            
            // Determine dataset source for proper naming
            const isGenerated = filePath.includes('/generated/');
            const datasetList = isGenerated ? currentDatasets.generated : currentDatasets.auxiliary;
            const dataset = datasetList.find(d => d.path === filePath);
            
            if (dataset) {
                const filename = dataset.filename;
                const pillId = isGenerated ? 'gen-aux-pill-' + Date.now() : 'cache-aux-pill-' + Date.now();
                let displayName = filename;
                
                // Special handling for Intervals auxiliary datasets
                if (filename.includes('wellness_data')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Wellness Summary (${days} days)`;
                    }
                } else if (filename.includes('activity_summary')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Activity Summary (${days} days)`;
                    }
                } else if (filename.includes('activity_intervals')) {
                    const dateMatch = filename.match(/(\d{8})_to_(\d{8})/);
                    if (dateMatch) {
                        const start = dateMatch[1];
                        const end = dateMatch[2];
                        const startDate = new Date(start.slice(0,4), start.slice(4,6)-1, start.slice(6,8));
                        const endDate = new Date(end.slice(0,4), end.slice(4,6)-1, end.slice(6,8));
                        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
                        displayName = `Activity Intervals (${days} days)`;
                    }
                }
                
                const pillLabel = isGenerated ? `Generated (${displayName})` : `Auxiliary (${displayName})`;
                
                // Create pill using file-management function
                if (typeof createOrUpdateDatasetPill === 'function') {
                    createOrUpdateDatasetPill(
                        pillId,
                        pillLabel,
                        'auxiliary',
                        'success',
                        false,
                        filePath
                    );
                }
                
                // Update auxiliary count
                auxiliaryDatasetCount = data.aux_count || (auxiliaryDatasetCount + 1);
            }
            
            // Close modal
            hideModal();
            
            // Show success message
            console.log(isGenerated ? 'Generated dataset loaded as auxiliary' : 'Auxiliary dataset loaded successfully from cache');
            
        } catch (error) {
            console.error('Error loading dataset:', error);
            alert(`Failed to load dataset: ${error.message}`);
        } finally {
            // Restore button state
            if (loadButton) {
                loadButton.textContent = originalText;
                loadButton.classList.remove('loading');
                loadButton.disabled = false;
            }
        }
    }
    
    function showLoadingState() {
        const primaryList = document.getElementById('primaryDatasetList');
        const auxList = document.getElementById('auxiliaryDatasetList');
        const genList = document.getElementById('generatedDatasetList');
        
        const loadingHtml = '<div class="dataset-loading"><div class="dataset-loading-spinner"></div>Loading...</div>';
        
        if (primaryList) primaryList.innerHTML = loadingHtml;
        if (auxList) auxList.innerHTML = loadingHtml;
        if (genList) genList.innerHTML = loadingHtml;
    }
    
    function showErrorState(message) {
        const primaryList = document.getElementById('primaryDatasetList');
        const auxList = document.getElementById('auxiliaryDatasetList');
        const genList = document.getElementById('generatedDatasetList');
        
        const errorHtml = `<div style="color: var(--error-color); font-size: 13px;">${message}</div>`;
        
        if (primaryList) primaryList.innerHTML = errorHtml;
        if (auxList) auxList.innerHTML = '';
        if (genList) genList.innerHTML = '';
    }
    
    // Public API
    return {
        initialize: initialize,
        refresh: loadDatasets,
        loadPrimary: loadPrimaryDataset,
        loadAuxiliary: loadAuxiliaryDataset
    };
})();