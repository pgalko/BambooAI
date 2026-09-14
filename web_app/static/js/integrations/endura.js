// Endura Integration Module
window.Endura = (function() {
    'use strict';
    
    // State management
    let state = {
        isLoaded: false,
        pillId: null,
        raceInfo: null,
        maxAuxDatasets: 3
    };
    
    function initialize() {
        console.log('Initializing Endura integration...');
        initializeDataOption();
        initializeModals();
    }
    
    function initializeDataOption() {
        const enduraButton = document.querySelector('.endura-data-option');
        if (!enduraButton) return;
        
        enduraButton.addEventListener('click', function() {
            // Check primary dataset limits
            if (currentDatasetName) {
                showUploadLimitMessage('Primary dataset already loaded. Remove current to upload new.');
                return;
            }
            if (window.SweatStack?.state.isLoaded) {
                showUploadLimitMessage('SweatStack data already loaded. Remove current to upload primary dataset.');
                return;
            }
            if (window.Intervals?.state.isLoaded) {
                showUploadLimitMessage('Intervals ICU data already loaded. Remove current to upload primary dataset.');
                return;
            }

            if (window.Endura && window.Endura.state.isLoaded) {
                showUploadLimitMessage('Endura data already loaded. Remove current to upload primary dataset.');
                return;
            }
            
            showMainModal();
        });
    }
    
    function initializeModals() {
        initializeMainModal();
        initializeConfigModal();
    }
    
    function initializeMainModal() {
        const modal = document.getElementById('enduraModal');
        const closeButton = modal?.querySelector('.close');
        const loadButton = document.getElementById('loadEnduraData');
        
        if (!modal || !closeButton || !loadButton) return;
        
        closeButton.addEventListener('click', hideMainModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) hideMainModal();
        });
        
        loadButton.addEventListener('click', handleLoadData);
    }
    
    function initializeConfigModal() {
        const modal = document.getElementById('enduraConfigModal');
        const closeButton = modal?.querySelector('.close');
        const saveButton = document.getElementById('saveEnduraApiKey');
        const removeButton = document.getElementById('removeEnduraApiKey');
        const apiKeyInput = document.getElementById('enduraApiKeyInput');
        
        if (!modal || !closeButton) return;
        
        closeButton.addEventListener('click', () => modal.style.display = 'none');
        modal.addEventListener('click', function(e) {
            if (e.target === modal) modal.style.display = 'none';
        });
        
        if (saveButton) {
            saveButton.addEventListener('click', async function() {
                const apiKey = apiKeyInput?.value?.trim();
                
                if (!apiKey) {
                    showConfigMessage('Please enter your API key', 'error');
                    return;
                }
                
                saveButton.disabled = true;
                saveButton.textContent = 'Saving...';
                
                try {
                    const response = await window.authService.fetch('/endura/store_api_key', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ api_key: apiKey })
                    });
                    
                    if (response.ok) {
                        showConfigMessage('API key saved successfully!', 'success');
                        apiKeyInput.value = '';
                        await updateApiKeyStatus();
                        
                        setTimeout(() => {
                            modal.style.display = 'none';
                            window.location.reload();
                        }, 1500);
                    } else {
                        throw new Error('Failed to save API key');
                    }
                } catch (error) {
                    showConfigMessage(`Failed to save: ${error.message}`, 'error');
                } finally {
                    saveButton.disabled = false;
                    saveButton.textContent = 'Save';
                }
            });
        }
        
        if (removeButton) {
            removeButton.addEventListener('click', async function() {
                if (!confirm('Remove your Endura API key?')) return;
                
                removeButton.disabled = true;
                removeButton.textContent = 'Removing...';
                
                try {
                    const response = await window.authService.fetch('/endura/remove_api_key', {
                        method: 'POST'
                    });
                    
                    if (response.ok) {
                        showConfigMessage('API key removed', 'success');
                        await updateApiKeyStatus();
                        
                        setTimeout(() => {
                            modal.style.display = 'none';
                            window.location.reload();
                        }, 1500);
                    }
                } catch (error) {
                    showConfigMessage(`Failed to remove: ${error.message}`, 'error');
                } finally {
                    removeButton.disabled = false;
                    removeButton.textContent = 'Remove';
                }
            });
        }
    }
    
    async function showMainModal() {
        // Check API key first
        const hasKey = await checkApiKey();
        if (!hasKey) {
            showConfigModal();
            return;
        }
        
        const modal = document.getElementById('enduraModal');
        if (modal) {
            modal.style.display = 'flex';
            showMainMessage('', 'default');
            loadRaces();
            initializeAuxOptions();
        }
    }
    
    function hideMainModal() {
        const modal = document.getElementById('enduraModal');
        if (modal) modal.style.display = 'none';
    }
    
    async function showConfigModal() {
        const modal = document.getElementById('enduraConfigModal');
        if (modal) {
            await updateApiKeyStatus();
            modal.style.display = 'flex';
        }
    }
    
    async function loadRaces() {
        const raceSelect = document.getElementById('enduraRaceSelect');
        if (!raceSelect) {
            console.error('Race select element not found');
            return;
        }
        
        raceSelect.innerHTML = '<option value="">Loading races...</option>';
        raceSelect.disabled = true;
        
        try {
            console.log('Fetching races from /endura/get_races...');
            const response = await window.authService.fetch('/endura/get_races');
            console.log('Response status:', response.status);
            
            if (!response.ok) {
                if (response.status === 401) {
                    showMainMessage('Invalid API key. Please reconfigure.', 'error');
                    setTimeout(showConfigModal, 2000);
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Races data:', data);
            
            const races = data.races || [];
            console.log('Number of races:', races.length);
            
            if (races.length === 0) {
                raceSelect.innerHTML = '<option value="">No races available</option>';
                showMainMessage('No races found', 'info');
                return;
            }
            
            raceSelect.innerHTML = '<option value="">Select a race</option>';
            
            races.forEach(race => {
                const option = document.createElement('option');
                // Use the correct field names from Endura API
                option.value = race.race_data_id;
                option.textContent = race.race_title;
                option.dataset.raceTitle = race.race_title;
                option.dataset.raceDate = race.race_date;
                
                raceSelect.appendChild(option);
            });
            
            raceSelect.disabled = false;
            console.log('Races loaded successfully');
            
        } catch (error) {
            console.error('Error loading races:', error);
            raceSelect.innerHTML = '<option value="">Failed to load races</option>';
            showMainMessage(`Failed to load races: ${error.message}`, 'error');
        }
    }
    
    function initializeAuxOptions() {
        const options = document.querySelectorAll('.endura-aux-option');
        let selectedCount = 1; // Profile is always selected
        
        options.forEach(option => {
            const checkbox = option.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            
            // Profile is always checked and disabled
            if (checkbox.value === 'profile') {
                checkbox.checked = true;
                checkbox.disabled = true;
                option.classList.add('selected', 'always-selected');
                return;
            }
            
            option.addEventListener('click', function(e) {
                e.preventDefault();
                
                if (checkbox.checked) {
                    checkbox.checked = false;
                    option.classList.remove('selected');
                    selectedCount--;
                } else if (selectedCount < state.maxAuxDatasets) {
                    checkbox.checked = true;
                    option.classList.add('selected');
                    selectedCount++;
                }
                
                // Update disabled state
                options.forEach(opt => {
                    const cb = opt.querySelector('input[type="checkbox"]');
                    if (cb && cb.value !== 'profile' && !cb.checked) {
                        opt.classList.toggle('disabled', selectedCount >= state.maxAuxDatasets);
                    }
                });
            });
        });
    }
    
    // Core function to handle data loading
    async function handleLoadData() {
        const raceSelect = document.getElementById('enduraRaceSelect');
        const raceId = raceSelect?.value;
        
        if (!raceId) {
            showMainMessage('Please select a race', 'error');
            return;
        }
        
        const auxDatasets = ['profile']; // Always include profile
        document.querySelectorAll('.endura-aux-option input:checked').forEach(cb => {
            if (cb.value !== 'profile' && !auxDatasets.includes(cb.value)) {
                auxDatasets.push(cb.value);
            }
        });
        
        await loadRaceData(raceId, auxDatasets);
    }
    
    // Extract the core loading logic into a separate internal function
    async function loadRaceData(raceId, auxDatasets) {
        const loadButton = document.getElementById('loadEnduraData');
        if (loadButton) {
            loadButton.disabled = true;
            loadButton.classList.add('loading');
        }
        
        showMainMessage('Loading race data...', 'loading');
        
        try {
            const response = await window.authService.fetch('/endura/load_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    race_id: raceId,
                    aux_datasets: auxDatasets
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load data');
            }
            
            const result = await response.json();
            
            showMainMessage('Data loaded successfully!', 'success');
            
            // Create pills
            createPrimaryPill(result);
            if (result.aux_datasets?.length > 0) {
                createAuxiliaryPills(result.aux_datasets);
            }
            
            // Update dataframe preview
            if (result.dataframe) {
                const dfData = JSON.parse(result.dataframe);
                if (typeof createOrUpdateTab === 'function') {
                    createOrUpdateTab('dataframe', dfData.data);
                    if (typeof activateTab === 'function') {
                        activateTab('dataframe');
                    }
                }
            }
            
            // Update global state
            if (typeof currentDatasetName !== 'undefined') {
                currentDatasetName = `Endura Race Data`;
            }
            
            setTimeout(hideMainModal, 2000);
            return result;
            
        } catch (error) {
            console.error('Error loading data:', error);
            showMainMessage(`Failed: ${error.message}`, 'error');
            throw error;
        } finally {
            if (loadButton) {
                loadButton.disabled = false;
                loadButton.classList.remove('loading');
            }
        }
    }
    
    function createPrimaryPill(data) {
        const pillId = 'endura-pill-' + Date.now();
        const raceTitle = data.race_title || 'Race';  // Use race_title instead of title
        const displayText = `Endura (${raceTitle}) loaded`;
        
        if (typeof createOrUpdateDatasetPill === 'function') {
            createOrUpdateDatasetPill(pillId, displayText, 'endura', 'success', false, null);
        }
        
        state.isLoaded = true;
        state.pillId = pillId;
        state.raceInfo = data;
    }
    
    function createAuxiliaryPills(auxDatasets) {
        auxDatasets.forEach((filepath, index) => {
            const filename = filepath.split('/').pop();
            let displayName = filename.replace('.csv', '').replace(/_/g, ' ');
            
            if (filename.includes('athlete_profiles')) displayName = 'Athlete Profiles';
            else if (filename.includes('race_turns')) displayName = 'Race Turns';
            else if (filename.includes('race_climbs')) displayName = 'Race Climbs';
            else if (filename.includes('race_waymarkers')) displayName = 'Race Waymarkers';
            
            const pillId = `endura-aux-pill-${Date.now()}-${index}`;
            
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
    
    function removePill() {
        if (state.pillId) {
            const pill = document.getElementById(state.pillId);
            if (pill) pill.remove();
            
            state.isLoaded = false;
            state.pillId = null;
            state.raceInfo = null;
        }
    }
    
    async function checkApiKey() {
        try {
            const response = await window.authService.fetch('/endura/status');
            const data = await response.json();
            return data.has_api_key || false;
        } catch (error) {
            console.error('Error checking Endura API key:', error);
            return false;
        }
    }
    
    async function updateApiKeyStatus() {
        const statusElement = document.getElementById('enduraApiKeyStatus');
        const removeButton = document.getElementById('removeEnduraApiKey');
        const apiKeyInput = document.getElementById('enduraApiKeyInput');
        
        if (!statusElement) return;
        
        try {
            const hasKey = await checkApiKey();
            
            if (hasKey) {
                statusElement.innerHTML = `
                    <svg class="status-icon success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>API key configured</span>
                `;
                statusElement.className = 'api-key-status has-key';
                if (apiKeyInput) apiKeyInput.placeholder = '••••••••••••••••';
                if (removeButton) removeButton.style.display = 'inline-block';
            } else {
                statusElement.innerHTML = `
                    <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <span>No API key configured</span>
                `;
                statusElement.className = 'api-key-status no-key';
                if (apiKeyInput) apiKeyInput.placeholder = 'Enter your Endura API key';
                if (removeButton) removeButton.style.display = 'none';
            }
        } catch (error) {
            statusElement.innerHTML = '<span>Unable to check status</span>';
            statusElement.className = 'api-key-status error';
        }
    }
    
    function showMainMessage(message, type = 'default') {
        const messageElement = document.getElementById('endura-modal-message');
        if (!messageElement) return;
        
        messageElement.className = `endura-status-message ${type}-message`;
        messageElement.textContent = type === 'success' ? '✓ ' + message : 
                                   type === 'error' ? '✗ ' + message : message;
    }
    
    function showConfigMessage(message, type = 'default') {
        const messageElement = document.getElementById('endura-config-message');
        if (!messageElement) return;
        
        messageElement.className = `endura-status-message ${type}-message`;
        messageElement.textContent = type === 'success' ? '✓ ' + message : 
                                   type === 'error' ? '✗ ' + message : message;
        messageElement.style.display = 'block';
        
        if (type === 'success') {
            setTimeout(() => {
                messageElement.style.display = 'none';
            }, 3000);
        }
    }
    
    function handleEndura() {
        showConfigModal();
    }
    
    // Public API
    return {
        initialize: initialize,
        handleEndura: handleEndura,
        removePill: removePill,
        state: state,
        loadDataForReplay: loadRaceData
    };
})();