//--------------------
//  SWEATSTACK INTEGRATION MODULE
//--------------------

// SweatStack-specific state
let currentSweatStackState = {
    isLoaded: false,
    pillId: null,
    dataInfo: null
};

function initializeSweatStackIntegration() {
    console.log('Initializing SweatStack integration...');
    
    initializeSweatStackDataOption();
    initializeSweatStackModals();
    
    console.log('SweatStack integration initialized');
}

//--------------------
//  SWEATSTACK DATA LOADING
//--------------------

function initializeSweatStackDataOption() {
    const sweatstackDataButton = document.querySelector('.sweatstack-data-option');

    if (!sweatstackDataButton) {
        console.log('SweatStack data option not found (user may not be authenticated)');
        return;
    }

    sweatstackDataButton.addEventListener('click', function() {
        console.log('SweatStack data option clicked');
        
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
        
        showSweatStackModal();
    });
}

function createSweatStackPill(dataInfo) {
    const pillId = 'sweatstack-pill-' + Date.now();
    const displayText = `SweatStack (${dataInfo.sports.join(', ')}, ${dataInfo.days} days) loaded`;

    if (typeof createOrUpdateDatasetPill === 'function') {
        createOrUpdateDatasetPill(pillId, displayText, 'sweatstack', 'success', false, 'sweatstack_data');
    }

    // Update global state
    currentSweatStackState.isLoaded = true;
    currentSweatStackState.pillId = pillId;
    currentSweatStackState.dataInfo = dataInfo;

    console.log('SweatStack data pill created successfully');
}

function removeSweatStackPill() {
    if (currentSweatStackState.pillId) {
        const pill = document.getElementById(currentSweatStackState.pillId);
        if (pill) {
            pill.remove();
        }

        // Reset global state
        currentSweatStackState.isLoaded = false;
        currentSweatStackState.pillId = null;
        currentSweatStackState.dataInfo = null;

        console.log('SweatStack data pill removed');
    }
}

//--------------------
//  SWEATSTACK MODAL SYSTEM
//--------------------

function initializeSweatStackModals() {
    initializeSweatStackMainModal();
    initializeSweatStackConfigModal();
    initializeSweatStackAuthenticatedModal();
}

function initializeSweatStackMainModal() {
    const modal = document.getElementById('sweatstackModal');
    const closeButton = modal?.querySelector('.close');
    const connectButton = document.getElementById('connectSweatstack');

    if (!modal || !closeButton || !connectButton) {
        console.warn('SweatStack modal elements not found');
        return;
    }

    closeButton.addEventListener('click', hideSweatStackModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) hideSweatStackModal();
    });

    initializeMetricSelection();
    initializeSportSelection();

    connectButton.addEventListener('click', function() {
        const selectedSports = getSelectedSports();
        if (selectedSports.length === 0) {
            showModalMessage('Please select at least one sport.', 'error');
            return;
        }
    
        const selectedMetrics = getSelectedMetrics();
        if (selectedMetrics.length === 0) {
            showModalMessage('Please select at least one metric.', 'error');
            return;
        }
    
        const selectedUsers = getSelectedUsers();
        if (selectedUsers.length === 0) {
            showModalMessage('Please select at least one user.', 'error');
            return;
        }
    
        const dateRange = getSelectedDateRange();
    
        setButtonLoading(true);
        showModalMessage('Loading SweatStack data...', 'loading');
    
        window.authService.fetch('/sweatstack/load_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sports: selectedSports,
                metrics: selectedMetrics,
                users: selectedUsers,
                days: dateRange.days,
                start_date: dateRange.start,
                end_date: dateRange.end
            })
        })
        .then(response => {
            if (response.status === 401) {
                window.location.href = `/sweatstack/authorize`;
            } else if (response.ok) {
                return response.json();
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        })
        .then(data => {
            if (data) {
                console.log('SweatStack data loaded successfully:', data.message);
                
                setButtonLoading(false);
                showModalMessage('Data loaded successfully!', 'success');
    
                setTimeout(() => {
                    hideSweatStackModal();
                    showModalMessage('Note: More metrics and longer time windows may slow down the application due to longer loading and processing times.');
                }, 2000);
    
                const dataInfo = {
                    sports: selectedSports,
                    metrics: selectedMetrics,
                    users: selectedUsers,
                    days: dateRange.days,
                    start_date: dateRange.start,
                    end_date: dateRange.end
                };
                createSweatStackPill(dataInfo);
    
                if (data.dataframe) {
                    try {
                        const dfData = JSON.parse(data.dataframe);
                        if (typeof createOrUpdateTab === 'function') {
                            createOrUpdateTab('dataframe', dfData.data);
                            if (typeof activateTab === 'function') {
                                activateTab('dataframe');
                            }
                        }
    
                        if (typeof window !== 'undefined' && typeof currentDatasetName !== 'undefined') {
                            //Total number of days
                            currentDatasetName = `SweatStack Data`;
                        }
                    } catch (error) {
                        console.error('Error parsing SweatStack dataframe:', error);
                    }
                }
            }
        })
        .catch(error => {
            console.error('Error loading SweatStack data:', error);
            setButtonLoading(false);
            showModalMessage('Failed to load data. Please try again.', 'error');
        });
    });
}

function initializeSweatStackConfigModal() {
    const modal = document.getElementById('sweatstackConfigModal');
    const closeButton = modal?.querySelector('.close');

    if (!modal || !closeButton) {
        console.warn('SweatStack config modal elements not found');
        return;
    }

    closeButton.addEventListener('click', () => modal.style.display = 'none');
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.style.display = 'none';
    });
}

function initializeSweatStackAuthenticatedModal() {
    const modal = document.getElementById('sweatstackAuthenticatedModal');
    const closeButton = modal?.querySelector('.close');
    const logoutButton = document.getElementById('logoutSweatstack');

    if (!modal || !closeButton || !logoutButton) {
        console.warn('SweatStack authenticated modal elements not found');
        return;
    }

    closeButton.addEventListener('click', () => modal.style.display = 'none');
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.style.display = 'none';
    });

    logoutButton.addEventListener('click', function() {
        window.authService.fetch('/sweatstack/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            modal.style.display = 'none';
            window.location.reload();
        })
        .catch(error => {
            console.error('Error logging out from SweatStack:', error);
            modal.style.display = 'none';
        });
    });
}

//--------------------
//  MODAL DISPLAY FUNCTIONS
//--------------------

function showSweatStackModal() {
    const modal = document.getElementById('sweatstackModal');
    if (modal) {
        modal.style.display = 'flex';
        initializeDatePickers();  // This now applies limits
        setTimeout(() => {
            initializeMetricSelection();
            initializeSportSelection();
        }, 100);
        fetchSweatStackUsers();
    }
}

function showSweatStackConfigModal() {
    const modal = document.getElementById('sweatstackConfigModal');
    if (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.style.display = 'flex';
    }
}

function showSweatStackAuthenticatedModal() {
    const modal = document.getElementById('sweatstackAuthenticatedModal');
    if (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.style.display = 'flex';
    }
}

function hideSweatStackModal() {
    const modal = document.getElementById('sweatstackModal');
    if (modal) modal.style.display = 'none';
}

//--------------------
//  FORM HANDLING
//--------------------

async function applySubscriptionDateLimits() {
    try {
        const response = await window.authService.fetch('/sweatstack/get_data_limits');
        const limits = await response.json();
        
        const today = new Date();
        const maxDays = limits.max_days || 14;
        
        // Calculate earliest allowed date
        const earliestDate = new Date(today);
        earliestDate.setDate(today.getDate() - maxDays);
        
        const startDateInput = document.getElementById('startDate');
        const endDateInput = document.getElementById('endDate');
        
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
        
        document.getElementById('startDate').value = twoWeeksAgo.toISOString().split('T')[0];
        document.getElementById('endDate').value = today.toISOString().split('T')[0];
    }
}

function initializeDatePickers() {
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    
    if (!startDateInput || !endDateInput) return;
    
    // Apply subscription limits immediately
    applySubscriptionDateLimits();
    
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

async function fetchSweatStackUsers() {
    const usersContainer = document.getElementById('users-selection');
    if (!usersContainer) return;

    usersContainer.innerHTML = '<div class="loading-spinner">Loading users...</div>';

    try {
        const response = await window.authService.fetch('/sweatstack/get_users');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();
        usersContainer.innerHTML = '';

        if (data.users && data.users.length > 0) {
            data.users.forEach((user, index) => {
                const userOption = document.createElement('label');
                userOption.className = 'user-option';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.id = `user-${user.id}`;
                checkbox.value = user.id;

                if (user.is_current || index === 0) {
                    checkbox.checked = true;
                }

                const checkIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                checkIcon.setAttribute('class', 'check-icon');
                checkIcon.setAttribute('viewBox', '0 0 24 24');
                checkIcon.setAttribute('fill', 'none');
                checkIcon.setAttribute('stroke', 'currentColor');
                checkIcon.setAttribute('stroke-width', '3');
                checkIcon.setAttribute('stroke-linecap', 'round');
                checkIcon.setAttribute('stroke-linejoin', 'round');
                checkIcon.innerHTML = '<polyline points="20 6 9 17 4 12"></polyline>';

                const span = document.createElement('span');
                span.textContent = user.name || user.username || `User ${user.id}`;

                userOption.appendChild(checkbox);
                userOption.appendChild(checkIcon);
                userOption.appendChild(span);

                usersContainer.appendChild(userOption);
            });

            usersContainer.addEventListener('change', function(e) {
                if (e.target.type === 'checkbox') {
                    const label = e.target.closest('.user-option');
                    if (label) {
                        label.classList.toggle('selected', e.target.checked);
                    }
                }
            });

            usersContainer.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
                const label = checkbox.closest('.user-option');
                if (label) label.classList.add('selected');
            });
        } else {
            usersContainer.innerHTML = '<p style="color: var(--text-secondary); font-size: 14px;">No users found</p>';
        }
    } catch (error) {
        console.error('Error fetching users:', error);
        usersContainer.innerHTML = '<p style="color: var(--error-color); font-size: 14px;">Error loading users</p>';
    }
}

//--------------------
//  SELECTION FUNCTIONS
//--------------------

function getSelectedSports() {
    const cyclingCheckbox = document.getElementById('cycling-checkbox');
    const runningCheckbox = document.getElementById('running-checkbox');
    const selectedSports = [];

    if (cyclingCheckbox?.checked) selectedSports.push('cycling');
    if (runningCheckbox?.checked) selectedSports.push('running');

    return selectedSports;
}

function getSelectedMetrics() {
    const metricCheckboxes = document.querySelectorAll('.metrics-selection input[type="checkbox"]:checked');
    return Array.from(metricCheckboxes).map(checkbox => checkbox.value);
}

function getSelectedUsers() {
    const userCheckboxes = document.querySelectorAll('.users-selection input[type="checkbox"]:checked');
    return Array.from(userCheckboxes).map(checkbox => checkbox.value);
}

function getSelectedDateRange() {
    const startDate = document.getElementById('startDate')?.value;
    const endDate = document.getElementById('endDate')?.value;
    
    if (!startDate || !endDate) {
        const end = new Date();
        const start = new Date();
        start.setMonth(start.getMonth() - 3);
        
        return {
            start: start.toISOString().split('T')[0],
            end: end.toISOString().split('T')[0],
            days: 90
        };
    }
    
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffTime = Math.abs(end - start);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    return { start: startDate, end: endDate, days: diffDays };
}

function initializeMetricSelection() {
    const metricsContainer = document.querySelector('.metrics-selection');
    if (!metricsContainer) return;

    const metricOptions = metricsContainer.querySelectorAll('.metric-option');

    metricOptions.forEach((metricOption) => {
        const existingListener = metricOption._clickListener;
        if (existingListener) {
            metricOption.removeEventListener('click', existingListener);
        }

        const clickListener = function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const checkbox = metricOption.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            
            checkbox.checked = !checkbox.checked;
            metricOption.classList.toggle('selected', checkbox.checked);
        };

        metricOption._clickListener = clickListener;
        metricOption.addEventListener('click', clickListener);
    });

    metricsContainer.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
        const label = checkbox.closest('.metric-option');
        if (label) label.classList.add('selected');
    });
}

function initializeSportSelection() {
    const sportsContainer = document.querySelector('.sports-selection');
    if (!sportsContainer) return;

    const sportOptions = sportsContainer.querySelectorAll('.sport-option');

    sportOptions.forEach((sportOption) => {
        const existingListener = sportOption._clickListener;
        if (existingListener) {
            sportOption.removeEventListener('click', existingListener);
        }

        const clickListener = function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const checkbox = sportOption.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            
            checkbox.checked = !checkbox.checked;
            sportOption.classList.toggle('selected', checkbox.checked);
        };

        sportOption._clickListener = clickListener;
        sportOption.addEventListener('click', clickListener);
    });

    sportsContainer.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
        const label = checkbox.closest('.sport-option');
        if (label) label.classList.add('selected');
    });
}

//--------------------
//  UI HELPER FUNCTIONS
//--------------------

function showModalMessage(message, type = 'default') {
    const messageElement = document.getElementById('modal-message');
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

function setButtonLoading(isLoading) {
    const connectButton = document.getElementById('connectSweatstack');
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

function handleSweatStack() {
    const sweatstackOption = document.querySelector('.sweatstack-option');
    const isEnabled = sweatstackOption?.getAttribute('data-enabled') === 'true';

    if (!isEnabled) {
        showSweatStackConfigModal();
        return;
    }

    window.authService.fetch('/sweatstack/load_data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(response => {
        if (response.status === 401) {
            window.location.href = '/sweatstack/authorize?sports=cycling&days=90';
        } else {
            showSweatStackAuthenticatedModal();
        }
    })
    .catch(error => {
        console.error('Error checking SweatStack auth status:', error);
        window.location.href = '/sweatstack/authorize?sports=cycling&days=90';
    });
}

// Export functions for use by other modules
if (typeof window !== 'undefined') {
    window.SweatStack = {
        initialize: initializeSweatStackIntegration,
        handleSweatStack: handleSweatStack,
        createPill: createSweatStackPill,
        removePill: removeSweatStackPill,
        showModal: showSweatStackModal,
        hideModal: hideSweatStackModal,
        state: currentSweatStackState
    };
}