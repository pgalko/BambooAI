// workflow-replay.js
(function() {
    'use strict';
    
    let currentChainId = null;
    let currentThreadId = null;
    let datasetsLoaded = {
        primary: false,
        auxiliary: []
    };
    let auxiliaryMappings = {};
    
    // Initialize replay module
    function initialize(threadId, chainId) {
        currentThreadId = threadId;
        currentChainId = chainId;
        
        // Reset state
        datasetsLoaded.primary = false;
        datasetsLoaded.auxiliary = [];
        auxiliaryMappings = {};
        
        // Load dataset metadata (left pane)
        loadDatasetMetadata();
        
        // Load replay cards (right pane)
        loadReplayCards();
    }

    // Check if primary dataset upload is allowed
    function checkPrimaryDatasetLimit() {
        if (currentDatasetName) {
            return { allowed: false, reason: 'Primary dataset already loaded. Remove current to upload new.' };
        }
        if (window.SweatStack && window.SweatStack.state.isLoaded) {
            return { allowed: false, reason: 'SweatStack data already loaded. Remove current to upload primary dataset.' };
        }
        if (window.Intervals && window.Intervals.state.isLoaded) {
            return { allowed: false, reason: 'Intervals data already loaded. Remove current to upload primary dataset.' };
        }
        if (window.Endura && window.Endura.state.isLoaded) {
            return { allowed: false, reason: 'Endura data already loaded. Remove current to upload primary dataset.' };
        }
        return { allowed: true };
    }

    // Handle dataset upload based on source type
    function handleDatasetUpload(button) {
        const card = button.closest('.replay-dataset-card');
        const datasetType = button.dataset.datasetType;
        const source = card.dataset.source;
        const isPrimary = datasetType === 'primary';
        
        // Check primary dataset limit
        if (isPrimary) {
            const check = checkPrimaryDatasetLimit();
            if (!check.allowed) {
                showReplayMessage(check.reason, 'error');
                return;
            }
        }
        
        if (source === 'Intervals') {
            handleIntervalsUpload(card, datasetType);
        } else if (source === 'Endura') {
            handleEnduraUpload(card, datasetType);
        } else {
            handleDirectUpload(card, datasetType);
        }
    }

    // Handle direct file upload (CSV/PARQUET/JSON)
    function handleDirectUpload(card, datasetType) {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.csv,.parquet,.json';
        
        fileInput.onchange = function() {
            const file = this.files[0];
            if (!file) return;
            
            // Mark card as loading
            updateCardState(card, 'loading');
            
            // Get the original identifier
            const originalIdentifier = card.dataset.originalIdentifier;
            console.log('Original identifier to replace:', originalIdentifier);
            
            const uploadedFileName = file.name;
            console.log('New file uploaded:', uploadedFileName);
            
            // Reuse existing upload handlers
            if (datasetType === 'primary') {
                const primaryInput = document.getElementById('primaryFile');
                if (primaryInput) {
                    primaryInput.files = this.files;
                    primaryInput.dispatchEvent(new Event('change'));
                }
            } else {
                if (window.auxiliaryDatasetCount >= 3) {
                    showReplayMessage('Maximum 3 auxiliary datasets allowed.', 'error');
                    updateCardState(card, 'ready');
                    return;
                }
                const auxInput = document.getElementById('auxiliaryFile');
                if (auxInput) {
                    auxInput.files = this.files;
                    auxInput.dispatchEvent(new Event('change'));
                }
            }
            
            // Monitor for completion
            checkDirectUploadCompletion(card, datasetType, uploadedFileName, originalIdentifier);
        };
        
        fileInput.click();
    }

    // Handle Intervals data upload
    function handleIntervalsUpload(card, datasetType) {
        const isPrimary = datasetType === 'primary';
        
        // Check if date pickers already exist
        let pickerContainer = card.querySelector('.replay-date-picker-container');
        if (pickerContainer) return;
        
        // Create inline date picker UI
        pickerContainer = document.createElement('div');
        pickerContainer.className = 'replay-date-picker-container';
        pickerContainer.innerHTML = `
            <div class="replay-date-row">
                <label>Start:</label>
                <input type="date" class="replay-date-input" id="replay-start-${card.dataset.cardId}">
            </div>
            <div class="replay-date-row">
                <label>End:</label>
                <input type="date" class="replay-date-input" id="replay-end-${card.dataset.cardId}">
            </div>
            <div class="replay-date-info" id="replay-days-${card.dataset.cardId}"></div>
            <button class="replay-upload-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Upload
            </button>
        `;
        
        card.appendChild(pickerContainer);
        
        // Apply date limits
        applyReplayDateLimits(card.dataset.cardId);
        
        // Add date validation on change
        const startInput = document.getElementById(`replay-start-${card.dataset.cardId}`);
        const endInput = document.getElementById(`replay-end-${card.dataset.cardId}`);
        const daysInfo = document.getElementById(`replay-days-${card.dataset.cardId}`);
        
        const validateDates = async () => {
            if (startInput.value && endInput.value) {
                // Parse the date values from the input (YYYY-MM-DD format from date picker)
                const start = new Date(startInput.value);
                const end = new Date(endInput.value);
                
                // Calculate days WITHOUT the +1
                const daysDiff = Math.round((end - start) / (1000 * 60 * 60 * 24));
                
                try {
                    const response = await window.authService.fetch('/intervals/get_data_limits');
                    const limits = await response.json();
                    const maxDays = limits.max_days || 14;
                    
                    if (daysDiff > maxDays) {
                        daysInfo.innerHTML = `<span style="color: var(--error-color)">⚠ ${daysDiff} days selected (max: ${maxDays})</span>`;
                    } else if (daysDiff >= 0) {
                        daysInfo.innerHTML = `<span style="color: var(--text-secondary)">${daysDiff} days selected</span>`;
                    }
                } catch (error) {
                    console.error('Error checking limits:', error);
                }
            }
        };
        
        startInput.addEventListener('change', validateDates);
        endInput.addEventListener('change', validateDates);
        
        // Setup upload button
        const uploadBtn = pickerContainer.querySelector('.replay-upload-btn');
        uploadBtn.addEventListener('click', () => {
            const startDate = startInput.value;
            const endDate = endInput.value;
            
            if (!startDate || !endDate) {
                showReplayMessage('Please select both dates', 'error');
                return;
            }
            
            // Start Intervals load (validation will happen in submitIntervalsData)
            submitIntervalsData(card, startDate, endDate, isPrimary);
        });
    }

    // Submit Intervals data request
    async function submitIntervalsData(card, startDate, endDate, isPrimary) {
        const uploadBtn = card.querySelector('.replay-upload-btn');
        
        // Validate date range against limits
        try {
            const limitsResponse = await window.authService.fetch('/intervals/get_data_limits');
            const limits = await limitsResponse.json();
            const maxDays = limits.max_days || 14;
            
            // Parse DD/MM/YYYY format explicitly
            const [startDay, startMonth, startYear] = startDate.split('/').map(Number);
            const [endDay, endMonth, endYear] = endDate.split('/').map(Number);
            
            const start = new Date(startYear, startMonth - 1, startDay);
            const end = new Date(endYear, endMonth - 1, endDay);
            
            // Calculate actual days selected (without +1)
            const daysDiff = Math.round((end - start) / (1000 * 60 * 60 * 24));
            
            if (daysDiff > maxDays) {
                showReplayMessage(`Date range exceeds limit: ${daysDiff} days selected, maximum ${maxDays} days allowed`, 'error');
                return;
            }
            
            // Also check that dates aren't in the future
            const today = new Date();
            today.setHours(23, 59, 59, 999); // End of today
            
            if (end > today) {
                showReplayMessage('End date cannot be in the future', 'error');
                return;
            }
            
            // Check minimum date
            const earliestAllowed = new Date(today);
            earliestAllowed.setDate(earliestAllowed.getDate() - (maxDays - 1));
            earliestAllowed.setHours(0, 0, 0, 0); // Start of day
            
            if (start < earliestAllowed) {
                const formattedDate = `${String(earliestAllowed.getDate()).padStart(2, '0')}/${String(earliestAllowed.getMonth() + 1).padStart(2, '0')}/${earliestAllowed.getFullYear()}`;
                showReplayMessage(`Start date too early. Earliest allowed: ${formattedDate}`, 'error');
                return;
            }
            
        } catch (error) {
            console.error('Error validating date limits:', error);
            showReplayMessage('Failed to validate date limits', 'error');
            return;
        }
        
        // If validation passes, proceed with upload
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = `
            <div class="replay-loading-spinner"></div>
            Loading...
        `;
        
        // Disable ALL Intervals + buttons immediately
        document.querySelectorAll('.replay-dataset-card[data-source="Intervals"] .replay-dataset-upload').forEach(btn => {
            btn.disabled = true;
        });
        
        // Detect auxiliary datasets
        const auxDatasets = [];
        document.querySelectorAll('.replay-dataset-card[data-source="Intervals"]').forEach(auxCard => {
            if (auxCard.dataset.datasetType === 'primary') return;
            
            const filename = auxCard.querySelector('.replay-dataset-name').textContent.toLowerCase();
            
            // More explicit matching
            if ((filename.includes('wellness') || filename.includes('wellness_data')) && !auxDatasets.includes('wellness')) {
                auxDatasets.push('wellness');
            }
            if ((filename.includes('activity_summary') || filename.includes('summary')) && !auxDatasets.includes('summary')) {
                auxDatasets.push('summary');
            }
            if ((filename.includes('activity_intervals') || filename.includes('intervals')) && !auxDatasets.includes('intervals')) {
                auxDatasets.push('intervals');
            }
        });

        console.log('Detected auxiliary datasets for Intervals replay:', auxDatasets);
        
        try {
            const response = await window.authService.fetch('/intervals/load_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    metrics: [],
                    aux_datasets: auxDatasets
                })
            });
            
            const data = await response.json();
            if (data.job_id && window.Intervals && window.Intervals.pollJob) {
                // Use the EXISTING polling function from intervals.js
                window.Intervals.pollJob(data.job_id, 
                    {start: startDate, end: endDate}, 
                    auxDatasets
                );
                
                // Just monitor for completion to update replay cards
                monitorIntervalsStateOnly();
            }
        } catch (error) {
            showReplayMessage(`Failed to load Intervals data: ${error.message}`, 'error');
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload';
            
            // Re-enable all Intervals buttons on error
            document.querySelectorAll('.replay-dataset-card[data-source="Intervals"] .replay-dataset-upload').forEach(btn => {
                btn.disabled = false;
            });
        }
    }
    
    // Simple state monitor - doesn't poll job, just watches for completion
    function monitorIntervalsStateOnly() {
        const checkInterval = setInterval(() => {
            if (window.Intervals && window.Intervals.state.isLoaded) {
                clearInterval(checkInterval);
                
                // Capture Intervals auxiliary mappings
                document.querySelectorAll('.replay-dataset-card[data-source="Intervals"]').forEach(card => {
                    if (card.dataset.datasetType !== 'primary') {
                        const originalFile = card.dataset.originalFilename;
                        
                        // Find corresponding pill to get new filename
                        const pills = document.querySelectorAll('.auxiliary-dataset-pill.success');
                        pills.forEach(pill => {
                            const identifier = pill.dataset.identifier;
                            if (identifier && identifier.includes('wellness') && originalFile.includes('wellness')) {
                                auxiliaryMappings[originalFile] = identifier;
                            } else if (identifier && identifier.includes('activity_summary') && originalFile.includes('activity_summary')) {
                                auxiliaryMappings[originalFile] = identifier;
                            } else if (identifier && identifier.includes('activity_intervals') && originalFile.includes('activity_intervals')) {
                                auxiliaryMappings[originalFile] = identifier;
                            }
                        });
                    }
                });
                
                markIntervalsCardsLoaded();
            }
        }, 1000);
        
        setTimeout(() => clearInterval(checkInterval), 300000);
    }


    // Apply date limits for replay
    async function applyReplayDateLimits(cardId) {
        try {
            const response = await window.authService.fetch('/intervals/get_data_limits');
            const limits = await response.json();
            
            const today = new Date();
            const maxDays = limits.max_days || 14;
            const earliestDate = new Date(today);
            earliestDate.setDate(today.getDate() - maxDays);
            
            const startInput = document.getElementById(`replay-start-${cardId}`);
            const endInput = document.getElementById(`replay-end-${cardId}`);
            
            if (startInput && endInput) {
                endInput.value = today.toISOString().split('T')[0];
                endInput.max = today.toISOString().split('T')[0];
                startInput.value = earliestDate.toISOString().split('T')[0];
                startInput.min = earliestDate.toISOString().split('T')[0];
                startInput.max = today.toISOString().split('T')[0];
                endInput.min = earliestDate.toISOString().split('T')[0];
            }
        } catch (error) {
            console.error('Error applying date limits:', error);
        }
    }

    // Update card visual state
    function updateCardState(card, state) {
        const uploadBtn = card.querySelector('.replay-dataset-upload');
        
        if (state === 'loading') {
            uploadBtn.innerHTML = '<div class="replay-loading-spinner"></div>';
            uploadBtn.disabled = true;
        } else if (state === 'loaded') {
            uploadBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1E90FF" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
            `;
            uploadBtn.disabled = true;
            uploadBtn.classList.add('loaded');
            card.classList.add('dataset-loaded');
        } else if (state === 'ready') {
            uploadBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
            `;
            uploadBtn.disabled = false;
        }
        
        checkExecuteReady();
    }

    function checkDirectUploadCompletion(card, datasetType, uploadedFileName, originalIdentifier) {
        let checkCount = 0;
        const startingAuxPath = window.lastAuxiliaryUploadPath;
        
        const checkInterval = setInterval(() => {
            let uploadCompleted = false;
            
            if (datasetType === 'primary') {
                // Check for SUCCESS pill with our filename
                const pills = document.querySelectorAll('.primary-dataset-pill.success');
                pills.forEach(pill => {
                    if (pill.textContent.includes(uploadedFileName)) {
                        uploadCompleted = true;
                    }
                });
            } else {
                // Check if auxiliary path changed
                uploadCompleted = window.lastAuxiliaryUploadPath && window.lastAuxiliaryUploadPath !== startingAuxPath;
                
                // If completed, capture the mapping
                if (uploadCompleted && originalIdentifier) {
                    auxiliaryMappings[originalIdentifier] = window.lastAuxiliaryUploadPath;
                    console.log('Mapping captured:', originalIdentifier, '->', window.lastAuxiliaryUploadPath);
                }
            }
            
            if (uploadCompleted) {
                clearInterval(checkInterval);
                updateCardState(card, 'loaded');
                console.log('Upload complete. Current mappings:', auxiliaryMappings);
                return;
            }
            
            checkCount++;
            if (checkCount > 600) {  // 5 minutes max
                clearInterval(checkInterval);
                updateCardState(card, 'ready');
                showReplayMessage('Upload timed out after 5 minutes.', 'error');
            }
        }, 500);
    }

    // Mark all Intervals cards as loaded
    function markIntervalsCardsLoaded() {
        // Only mark as loaded if Intervals state shows loaded
        if (!window.Intervals || !window.Intervals.state.isLoaded) {
            // Wait a bit more for state to update
            setTimeout(() => {
                if (window.Intervals && window.Intervals.state.isLoaded) {
                    document.querySelectorAll('.replay-dataset-card[data-source="Intervals"]').forEach(card => {
                        updateCardState(card, 'loaded');
                        const pickerContainer = card.querySelector('.replay-date-picker-container');
                        if (pickerContainer) pickerContainer.remove();
                    });
                }
            }, 1000);
            return;
        }
        
        document.querySelectorAll('.replay-dataset-card[data-source="Intervals"]').forEach(card => {
            updateCardState(card, 'loaded');
            const pickerContainer = card.querySelector('.replay-date-picker-container');
            if (pickerContainer) pickerContainer.remove();
        });
    }

    // Check if Execute button should be enabled
    function checkExecuteReady() {
        const executeBtn = document.querySelector('.replay-execute-btn');
        if (!executeBtn) return;
        
        const primaryCard = document.querySelector('.replay-dataset-card[data-dataset-type="primary"]');
        const isPrimaryLoaded = primaryCard && primaryCard.classList.contains('dataset-loaded');
        
        executeBtn.disabled = !isPrimaryLoaded;
        if (isPrimaryLoaded) {
            executeBtn.classList.add('ready');
        }
    }

    // Handle Endura data upload
    function handleEnduraUpload(card, datasetType) {
        const isPrimary = datasetType === 'primary';
        
        // Check if race picker already exists
        let pickerContainer = card.querySelector('.replay-race-picker-container');
        if (pickerContainer) return;
        
        // Create inline race picker UI
        pickerContainer = document.createElement('div');
        pickerContainer.className = 'replay-race-picker-container';
        pickerContainer.innerHTML = `
            <div class="replay-race-row">
                <label>Select Race:</label>
                <select class="replay-race-select" id="replay-race-${card.dataset.cardId}">
                    <option value="">Loading races...</option>
                </select>
            </div>
            <div class="replay-race-info" id="replay-race-info-${card.dataset.cardId}"></div>
            <button class="replay-upload-btn" disabled>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Load Race
            </button>
        `;
        
        card.appendChild(pickerContainer);
        
        // Load races
        loadEnduraRaces(card);
        
        // Setup upload button
        const uploadBtn = pickerContainer.querySelector('.replay-upload-btn');
        const raceSelect = pickerContainer.querySelector('.replay-race-select');
        
        raceSelect.addEventListener('change', function() {
            uploadBtn.disabled = !this.value;
            if (this.value) {
                const selectedOption = this.options[this.selectedIndex];
                const raceInfo = document.getElementById(`replay-race-info-${card.dataset.cardId}`);
                raceInfo.innerHTML = `<span style="color: var(--text-secondary)">${selectedOption.dataset.raceDate || ''}</span>`;
            }
        });
        
        uploadBtn.addEventListener('click', () => {
            const raceId = raceSelect.value;
            
            if (!raceId) {
                showReplayMessage('Please select a race', 'error');
                return;
            }
            
            const raceTitle = raceSelect.options[raceSelect.selectedIndex].text;
            submitEnduraData(card, raceId, raceTitle, isPrimary);
        });
    }
    
    // Load Endura races for replay
    async function loadEnduraRaces(card) {
        const raceSelect = card.querySelector('.replay-race-select');
        const uploadBtn = card.querySelector('.replay-upload-btn');
        
        if (!raceSelect) return;
        
        try {
            // Check if user has API key configured
            const statusResponse = await window.authService.fetch('/endura/status');
            const statusData = await statusResponse.json();
            
            if (!statusData.has_api_key) {
                raceSelect.innerHTML = '<option value="">No API key configured</option>';
                showReplayMessage('Please configure your Endura API key first', 'error');
                
                // Add link to configuration
                const raceInfo = card.querySelector('.replay-race-info');
                raceInfo.innerHTML = '<a href="#" onclick="window.Endura.handleEndura(); return false;">Configure API Key</a>';
                return;
            }
            
            // Fetch races
            const response = await window.authService.fetch('/endura/get_races');
            const data = await response.json();
            
            if (response.status === 401) {
                raceSelect.innerHTML = '<option value="">Invalid API key</option>';
                showReplayMessage('Invalid API key. Please reconfigure.', 'error');
                return;
            }
            
            const races = data.races || [];
            
            if (races.length === 0) {
                raceSelect.innerHTML = '<option value="">No races available</option>';
                return;
            }
            
            raceSelect.innerHTML = '<option value="">Select a race</option>';
            races.forEach(race => {
                const option = document.createElement('option');
                option.value = race.race_data_id;
                option.textContent = race.race_title;
                option.dataset.raceDate = race.race_date;
                raceSelect.appendChild(option);
            });
            
        } catch (error) {
            console.error('Error loading races:', error);
            raceSelect.innerHTML = '<option value="">Failed to load races</option>';
            showReplayMessage('Failed to load races', 'error');
        }
    }

    // Submit Endura data request
    async function submitEnduraData(card, raceId, raceTitle, isPrimary) {
        const uploadBtn = card.querySelector('.replay-upload-btn');
        
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = `
            <div class="replay-loading-spinner"></div>
            Loading...
        `;
        
        // Disable ALL Endura + buttons
        document.querySelectorAll('.replay-dataset-card[data-source="Endura"] .replay-dataset-upload').forEach(btn => {
            btn.disabled = true;
        });
        
        // Detect auxiliary datasets
        const auxDatasets = ['profile'];
        document.querySelectorAll('.replay-dataset-card[data-source="Endura"]').forEach(auxCard => {
            if (auxCard.dataset.datasetType === 'primary') return;
            
            const filename = auxCard.querySelector('.replay-dataset-name').textContent.toLowerCase();
            
            if (filename.includes('turns') && !auxDatasets.includes('turns')) {
                auxDatasets.push('turns');
            }
            if (filename.includes('climbs') && !auxDatasets.includes('climbs')) {
                auxDatasets.push('climbs');
            }
            if (filename.includes('waymarkers') && !auxDatasets.includes('waymarkers')) {
                auxDatasets.push('waymarkers');
            }
        });
        
        try {
            // Get the original race ID from the dataset card to build mappings
            const originalFilename = card.dataset.originalFilename || '';
            let originalRaceId = null;
            
            // Extract original race ID from filename (e.g., "race_turns_race_12.csv" -> "12")
            const raceIdMatch = originalFilename.match(/race_(\d+)/);
            if (raceIdMatch) {
                originalRaceId = raceIdMatch[1];
            }
            
            // Use Endura module's function
            if (window.Endura && window.Endura.loadDataForReplay) {
                await window.Endura.loadDataForReplay(raceId, auxDatasets);
                
                // Set replay context
                if (!window.currentRankData) {
                    window.currentRankData = {};
                }
                window.currentRankData.replay = currentChainId;
                
                // Build auxiliary mappings for Endura datasets
                if (originalRaceId && originalRaceId !== raceId) {
                    // Map old race files to new race files
                    document.querySelectorAll('.replay-dataset-card[data-source="Endura"]').forEach(auxCard => {
                        if (auxCard.dataset.datasetType === 'primary') return;
                        
                        const oldFile = auxCard.dataset.originalFilename;
                        if (!oldFile) return;
                        
                        // Create the new filename by replacing the race ID
                        const newFile = oldFile.replace(`race_${originalRaceId}`, `race_${raceId}`);
                        
                        // Add to mappings
                        auxiliaryMappings[oldFile] = newFile;
                        console.log(`Endura mapping: ${oldFile} -> ${newFile}`);
                    });
                }
                
                // Also capture mappings from actual pill creation
                document.querySelectorAll('.auxiliary-dataset-pill.success').forEach(pill => {
                    const identifier = pill.dataset.identifier;
                    if (!identifier) return;
                    
                    // Extract filename from identifier path
                    const filename = identifier.split('/').pop();
                    
                    // Find matching original file
                    document.querySelectorAll('.replay-dataset-card[data-source="Endura"]').forEach(auxCard => {
                        if (auxCard.dataset.datasetType === 'primary') return;
                        
                        const originalFile = auxCard.dataset.originalFilename;
                        if (!originalFile) return;
                        
                        // Match by dataset type (turns, climbs, etc.)
                        if ((filename.includes('race_turns') && originalFile.includes('race_turns')) ||
                            (filename.includes('race_climbs') && originalFile.includes('race_climbs')) ||
                            (filename.includes('race_waymarkers') && originalFile.includes('race_waymarkers')) ||
                            (filename.includes('athlete_profiles') && originalFile.includes('athlete_profiles'))) {
                            
                            // Update or confirm mapping
                            auxiliaryMappings[originalFile] = filename;
                            console.log(`Endura mapping confirmed: ${originalFile} -> ${filename}`);
                        }
                    });
                });
                
                console.log('Final Endura mappings:', auxiliaryMappings);
                
                markEnduraCardsLoaded();
                showReplayMessage(`Endura race "${raceTitle}" loaded successfully`, 'success');
            } else {
                throw new Error('Endura module not available');
            }
        } catch (error) {
            showReplayMessage(`Failed to load Endura data: ${error.message}`, 'error');
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Load Race
            `;
            
            // Re-enable all Endura buttons on error
            document.querySelectorAll('.replay-dataset-card[data-source="Endura"] .replay-dataset-upload').forEach(btn => {
                btn.disabled = false;
            });
        }
    }

    // Mark all Endura cards as loaded
    function markEnduraCardsLoaded() {
        document.querySelectorAll('.replay-dataset-card[data-source="Endura"]').forEach(card => {
            updateCardState(card, 'loaded');
            const pickerContainer = card.querySelector('.replay-race-picker-container');
            if (pickerContainer) pickerContainer.remove();
        });
    }



    // Show replay message
    function showReplayMessage(message, type = 'info') {
        const messageArea = document.getElementById('replayMessageArea');
        
        if (messageArea) {
            // Clear any existing timeout
            if (window.replayMessageTimeout) {
                clearTimeout(window.replayMessageTimeout);
            }
            
            // Set message with appropriate styling
            messageArea.className = `replay-message-area ${type}`;
            messageArea.textContent = message;
            messageArea.style.display = 'block';
            
            // Auto-hide after 5 seconds for non-error messages
            if (type !== 'error') {
                window.replayMessageTimeout = setTimeout(() => {
                    messageArea.style.display = 'none';
                }, 5000);
            } else {
                // Errors stay visible for 10 seconds
                window.replayMessageTimeout = setTimeout(() => {
                    messageArea.style.display = 'none';
                }, 10000);
            }
        } else {
            // Fallback to console if message area not found
            console.log(`[Replay ${type}]:`, message);
        }
    }
    
    // Load dataset metadata from backend
    async function loadDatasetMetadata() {
        const leftPane = document.querySelector('.workflow-modal-left');
        const labelsList = document.getElementById('workflowLabelsList');
        
        if (!labelsList) return;
        
        // Show loading state
        labelsList.innerHTML = '<div class="workflow-loading">Loading dataset information...</div>';
        
        try {
            const response = await window.authService.fetch(`/api/chains/${currentChainId}/datasets`);
            if (!response.ok) throw new Error('Failed to fetch datasets');
            
            const data = await response.json();
            renderDatasetPanels(data.primary, data.auxiliary);
            
        } catch (error) {
            console.error('Error loading dataset metadata:', error);
            labelsList.innerHTML = '<div class="workflow-error">Failed to load dataset information</div>';
        }
    }
    
    // Render dataset panels in left pane
    function renderDatasetPanels(primary, auxiliary) {
        const labelsList = document.getElementById('workflowLabelsList');
        if (!labelsList) return;
        
        let html = '';

        // Add message area at the top
        html += '<div id="replayMessageArea" class="replay-message-area"></div>';
        
        // Primary dataset section
        html += '<div class="replay-dataset-section">';
        html += '<div class="replay-dataset-header">';
        html += '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">';
        html += '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>';
        html += '<line x1="9" y1="3" x2="9" y2="21"></line>';
        html += '<line x1="3" y1="9" x2="21" y2="9"></line>';
        html += '</svg>';
        html += '<span>Primary Dataset</span>';
        html += '</div>';
        
        if (primary) {
            html += renderDatasetCard(primary, 'primary');
        } else {
            html += '<div class="replay-dataset-empty">No primary dataset</div>';
        }
        html += '</div>';
        
        // Auxiliary datasets section
        html += '<div class="replay-dataset-section">';
        html += '<div class="replay-dataset-header">';
        html += '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">';
        html += '<path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"></path>';
        html += '<polyline points="13 2 13 9 20 9"></polyline>';
        html += '</svg>';
        html += '<span>Auxiliary Datasets</span>';
        html += '</div>';
        
        if (auxiliary && auxiliary.length > 0) {
            auxiliary.forEach((dataset, index) => {
                html += renderDatasetCard(dataset, `auxiliary-${index}`);
            });
        } else {
            html += '<div class="replay-dataset-empty">No auxiliary datasets</div>';
        }
        html += '</div>';
        
        // Execute button footer
        html += '<div class="replay-execute-footer">';
        html += '<button class="replay-execute-btn" disabled>';
        html += '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">';
        html += '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
        html += '</svg>';
        html += 'Execute';
        html += '</button>';
        html += '</div>';
        
        labelsList.innerHTML = html;
        
        // Setup handlers for upload buttons (placeholders for now)
        setupDatasetHandlers();
    }
    
    // Render individual dataset card
    function renderDatasetCard(dataset, datasetType) {
        const filename = dataset.original_filename || dataset.source || 'Dataset';
        const shape = dataset.shape ? `${dataset.shape[0].toLocaleString()} rows × ${dataset.shape[1]} cols` : 'Unknown size';
        const cardId = `card-${datasetType}-${Date.now()}`;
        const isSweatStack = dataset.source === 'SweatStack';
        
        // For auxiliary datasets, the identifier might be the full path we need to replace
        const originalIdentifier = dataset.identifier || dataset.original_filename || filename;
        
        let html = `<div class="replay-dataset-card" 
                         data-dataset-type="${datasetType}" 
                         data-source="${dataset.source}" 
                         data-card-id="${cardId}"
                         data-original-identifier="${originalIdentifier}"
                         data-original-filename="${filename}">`;
        html += `<div class="replay-dataset-name">${escapeHtml(filename)}</div>`;
        html += '<div class="replay-dataset-info">';
        html += `<span class="replay-dataset-source">Source: ${escapeHtml(dataset.source)}</span>`;
        html += `<span class="replay-dataset-shape">${shape}</span>`;
        if (dataset.date_range) {
            html += `<span class="replay-dataset-dates">${escapeHtml(dataset.date_range)}</span>`;
        }
        
        if (isSweatStack) {
            html += '<span class="replay-dataset-notice">SweatStack replay coming soon</span>';
        }
        
        html += '</div>';
        
        html += `<button class="replay-dataset-upload" data-dataset-type="${datasetType}" ${isSweatStack ? 'disabled' : ''}>`;
        if (isSweatStack) {
            html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" opacity="0.3">';
        } else {
            html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">';
        }
        html += '<line x1="12" y1="5" x2="12" y2="19"></line>';
        html += '<line x1="5" y1="12" x2="19" y2="12"></line>';
        html += '</svg>';
        html += '</button>';
        html += '</div>';
        
        return html;
    }
    
    // Setup dataset handlers (placeholders)
    function setupDatasetHandlers() {
        const uploadButtons = document.querySelectorAll('.replay-dataset-upload');
        uploadButtons.forEach(btn => {
            const card = btn.closest('.replay-dataset-card');
            
            if (card.dataset.source === 'SweatStack') {
                btn.disabled = true;
                btn.title = 'SweatStack replay coming soon';
            } else {
                btn.disabled = false;
                btn.addEventListener('click', function() {
                    handleDatasetUpload(this);
                });
            }
        });
        
        const executeBtn = document.querySelector('.replay-execute-btn');
        if (executeBtn) {
            executeBtn.addEventListener('click', function() {
                executeReplay();
            });
        }
    }

    async function executeReplay() {
        if (!currentChainId || !currentThreadId) {
            showReplayMessage('Missing chain or thread information', 'error');
            return;
        }
        
        const primaryCard = document.querySelector('.replay-dataset-card[data-dataset-type="primary"]');
        if (!primaryCard || !primaryCard.classList.contains('dataset-loaded')) {
            showReplayMessage('Primary dataset must be loaded before execution', 'error');
            return;
        }
        
        const executeBtn = document.querySelector('.replay-execute-btn');
        executeBtn.disabled = true;
        executeBtn.innerHTML = `
            <div class="replay-loading-spinner"></div>
            Executing...
        `;
        
        try {
            const streamOutputDiv = document.getElementById('streamOutput');
            if (streamOutputDiv) {
                streamOutputDiv.innerHTML = '';
            }
            
            if (typeof clearAllTabs === 'function') {
                clearAllTabs();
            }

            const rankButton = document.getElementById('rankButton');
            if (rankButton) {
                rankButton.style.display = 'none';
                rankButton.classList.remove('replay', 'replay-success');
            }
            
            if (window.currentData) {
                window.currentData.queryText = 'Replay code execution';
                window.currentData.chain_id = currentChainId;
                window.currentData.thread_id = currentThreadId;
            }
            
            if (window.WorkflowModal && window.WorkflowModal.close) {
                window.WorkflowModal.close();
            }
            
            console.log('Executing replay with mappings:', auxiliaryMappings);
            
            const response = await window.authService.fetch('/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: null,
                    chain_id: currentChainId,
                    thread_id: currentThreadId,
                    user_code: "replay_code_execution",
                    dataset_mappings: auxiliaryMappings  // Include mappings
                }),
            });
            
            if (response.status === 403) {
                const errorData = await response.json();
                
                if (typeof showQueryLimitModal === 'function') {
                    showQueryLimitModal(errorData.message, errorData.remaining_queries);
                }
                
                executeBtn.disabled = false;
                executeBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                    Execute
                `;
                
                return;
            }
            
            if (!response.ok) {
                throw new Error('Failed to execute replay');
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const {done, value} = await reader.read();
                if (done) {
                    console.log('Replay execution stream complete');
                    if (typeof saveCurrentResponse === 'function') {
                        saveCurrentResponse();
                    }
                    break;
                }
                const chunk = decoder.decode(value);
                if (typeof processChunk === 'function') {
                    processChunk(chunk);
                }
            }
            
            if (typeof updateQueryCounter === 'function') {
                updateQueryCounter();
            }
            
        } catch (error) {
            console.error('Error executing replay:', error);
            
            showReplayMessage(`Execution failed: ${error.message}`, 'error');
            
            executeBtn.disabled = false;
            executeBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Execute
            `;
        }
    }

    // Load replay cards for the parent chain
    async function loadReplayCards() {
        const chainsGrid = document.getElementById('workflowChainsGrid');
        if (!chainsGrid) return;
        
        chainsGrid.innerHTML = '<div class="workflow-loading">Loading replays...</div>';
        
        try {
            const response = await window.authService.fetch(
                `/storage/replay_favourites/${currentThreadId}/${currentChainId}`
            );
            
            if (!response.ok) throw new Error('Failed to load replays');
            
            const data = await response.json();
            const replays = data.replays || [];
            
            if (replays.length === 0) {
                chainsGrid.innerHTML = '<div class="workflow-no-chains">No replays yet</div>';
                return;
            }
            
            renderReplayCards(replays);
            
        } catch (error) {
            console.error('Error loading replay cards:', error);
            chainsGrid.innerHTML = '<div class="workflow-error">Failed to load replays</div>';
        }
    }

    // Render replay cards
    function renderReplayCards(replays) {
        const chainsGrid = document.getElementById('workflowChainsGrid');
        if (!chainsGrid) return;
        
        chainsGrid.innerHTML = '';
        
        // Sort by timestamp (newest first)
        replays.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        replays.forEach(replay => {
            const card = createReplayCard(replay);
            chainsGrid.appendChild(card);
        });
    }

    // Create individual replay card
    function createReplayCard(replay) {
        const card = document.createElement('div');
        card.className = 'workflow-card replay-card';
        card.setAttribute('data-chain-id', replay.chain_id);
        card.setAttribute('data-thread-id', replay.thread_id);
        card.setAttribute('data-parent-chain-id', replay.parent_chain_id);
        
        // Format timestamp
        let formattedTime = 'No date';
        if (replay.timestamp) {
            try {
                const date = new Date(replay.timestamp);
                formattedTime = date.toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {}
        }
        
        card.innerHTML = `
            <div class="workflow-card-header replay-card-header">
                <span class="workflow-card-time">${formattedTime}</span>
                <button class="workflow-card-delete replay-card-delete" title="Delete replay">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
            <div class="workflow-card-body">
                <div class="workflow-card-preview replay-card-preview">
                    ${replay.plotPreview 
                        ? `<img src="${replay.plotPreview}" class="workflow-preview-image" alt="Replay preview">`
                        : '<div class="workflow-preview-empty">No preview</div>'
                    }
                </div>
                <div class="workflow-card-info replay-card-info">
                    <span class="replay-card-thread">Thread: ${replay.thread_id}</span>
                    <span class="replay-card-chain">Chain: ${replay.chain_id}</span>
                    <span class="workflow-card-dataset">Dataset: ${replay.dataset_name || 'None'}</span>
                </div>
            </div>
        `;
        
        setupReplayCardHandlers(card, replay);
        
        return card;
    }

    // Setup replay card handlers
    function setupReplayCardHandlers(card, replay) {
        // Delete button
        const deleteBtn = card.querySelector('.replay-card-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', async function(e) {
                e.stopPropagation();
                if (confirm('Delete this replay?')) {
                    try {
                        const response = await window.authService.fetch(
                            `/storage/replay_favourites/${replay.thread_id}/${replay.parent_chain_id}/${replay.chain_id}`, 
                            { method: 'DELETE' }
                        );
                        
                        if (response.ok) {
                            card.remove();
                            
                            // Check if no replays left
                            const chainsGrid = document.getElementById('workflowChainsGrid');
                            if (chainsGrid && chainsGrid.children.length === 0) {
                                chainsGrid.innerHTML = '<div class="workflow-no-chains">No replays yet</div>';
                            }
                            
                            if (window.showSystemMessage) {
                                window.showSystemMessage('Replay deleted', 'success');
                            }
                        }
                    } catch (error) {
                        console.error('Error deleting replay:', error);
                        if (window.showSystemMessage) {
                            window.showSystemMessage('Failed to delete replay', 'error');
                        }
                    }
                }
            });
        }
        
        // Card click to load - USE NEW LOADER
        card.addEventListener('click', function(e) {
            if (!e.target.closest('button')) {
                // Use the new replay loader instead of generic loadThreadContent
                loadReplayContent(replay.thread_id, replay.parent_chain_id, replay.chain_id);
                
                // Close modal
                if (window.WorkflowModal && window.WorkflowModal.close) {
                    window.WorkflowModal.close();
                }
            }
        });
    }

    // Load replay content into main UI
    async function loadReplayContent(threadId, parentChainId, chainId) {
        const streamOutput = document.getElementById('streamOutput');
        
        if (streamOutput) {
            streamOutput.innerHTML = '<div>Loading replay content...</div>';
        }
        
        try {
            const response = await window.authService.fetch(
                `/load_replay/${threadId}/${parentChainId}/${chainId}`
            );
            
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            
            const data = await response.json();
            const replayData = data.content;
            
            // Backend already set chain_id to parent, but ensure it's set
            replayData.chain_id = data.parent_chain_id;
            replayData.thread_id = data.parent_thread_id;
            
            // Set global state to PARENT chain for follow-ups and context restoration
            currentData.thread_id = data.parent_thread_id;
            currentData.chain_id = data.parent_chain_id;
            
            console.log('Global state set to parent:', {
                thread_id: currentData.thread_id,
                chain_id: currentData.chain_id,
                original_replay_chain: data.replay_chain_id
            });
            
            // Process the replay data - decompress if needed
            let processedReplay = replayData;
            if (replayData.compressed) {
                console.log('Decompressing replay content...');
                
                const decompressedContentOutput = await decompressContent(replayData.contentOutput);
                const decompressedStreamOutput = await decompressContent(replayData.streamOutput);
                
                processedReplay = {
                    ...replayData,
                    contentOutput: decompressedContentOutput,
                    streamOutput: decompressedStreamOutput,
                    compressed: false
                };
            }
            
            // Ensure parent chain IDs are in the processed replay
            processedReplay.chain_id = data.parent_chain_id;
            processedReplay.thread_id = data.parent_thread_id;
            
            // Store in responses array for navigation (single item)
            responses = [processedReplay];
            currentResponseIndex = 0;
            
            // Save to localforage
            await localforage.setItem('responses', responses);
            
            // Load the content using existing function
            loadResponseContent(processedReplay);
            
            // Update navigation buttons if function exists
            if (typeof updateNavigationButtons === 'function') {
                updateNavigationButtons();
            }
            
            console.log('Replay content loaded. Context restored to parent chain:', data.parent_chain_id);
            
        } catch (error) {
            console.error('Error loading replay content:', error);
            if (streamOutput) {
                streamOutput.innerHTML = `<div class="error">Error loading replay content: ${error.message}</div>`;
            }
            if (window.showSystemMessage) {
                window.showSystemMessage('Failed to load replay content', 'error');
            }
        }
    }

    // Export the function
    window.loadReplayContent = loadReplayContent;
    
    // Helper function
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Public API
    window.WorkflowReplay = {
        initialize: initialize
    };
})();