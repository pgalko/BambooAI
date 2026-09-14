// subscription.js - PAYG version (cleaned and fixed)

let subscriptionState = {
    modelTier: 'free',
    computeTier: 'free',
    modelPreference: 'cost',  // Added model preference
    perQueryCost: 0.00,
    maxQueries: 20,
    maxDataDays: 14
};

let integrationState = {
    sweatstackExtended: false
};

// Tier pricing configuration
const TIER_CONFIG = {
    free: {
        cost: 0.00,
        maxQueries: 20,
        maxDataDays: 14,
        description: '20 queries/month, 4GB RAM Container, 80MB Data Upload'
    },
    plus: {
        cost: 0.02,
        maxQueries: null,  // unlimited
        maxDataDays: 180,
        description: 'Unlimited queries, 8GB RAM Container, 160MB Data Upload'
    },
    pro: {
        cost: 0.03,
        maxQueries: null,
        maxDataDays: 365,
        description: 'Unlimited queries, 16GB RAM Container, 320MB Data Upload'
    }
};

// Initialize subscription modal
function initializeSubscriptionModal() {
    console.log('Initializing subscription modal...');
    
    // Tab switching
    const tabs = document.querySelectorAll('.subscription-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
    
    // Model tier selection
    const modelRadios = document.querySelectorAll('input[name="model-tier"]');
    modelRadios.forEach(radio => {
        radio.addEventListener('change', handleModelTierChange);
    });
    
    // Model configuration toggle buttons (NEW STYLE)
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('toggle-option')) {
            e.stopPropagation();
            handleModelConfigToggle(e.target.dataset.value);
            
            // Update active state
            document.querySelectorAll('.toggle-option').forEach(btn => {
                btn.classList.remove('active');
            });
            e.target.classList.add('active');
        }
    });
    
    // Compute tier selection
    const computeRadios = document.querySelectorAll('input[name="compute-tier"]');
    computeRadios.forEach(radio => {
        radio.addEventListener('change', handleComputeTierChange);
    });
    
    // Close button
    const closeBtn = document.querySelector('#subscriptionModal .close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            const modal = document.getElementById('subscriptionModal');
            if (!modal.classList.contains('mandatory')) {
                closeSubscriptionModal();
            }
        });
    }
    
    // Save button
    const saveBtn = document.getElementById('saveSubscription');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveSubscription);
    }
    
    // Add funds button
    const addFundsBtn = document.getElementById('addFundsBtn');
    if (addFundsBtn) {
        addFundsBtn.addEventListener('click', showAddFundsModal);
    }
    
    // Initialize displays
    updateQueryCostDisplay();
    updateQueryCounter();
    generateIntegrationGrid();
    initializeFundsTabHandlers();
}

// Handle model tier change
function handleModelTierChange(event) {
    const tier = event.target.value;
    subscriptionState.modelTier = tier;
    
    const configSection = document.getElementById('modelConfigSection');
    
    if (tier === 'free') {
        // Hide config section for free tier
        if (configSection) configSection.style.display = 'none';
        
        // Force free compute tier
        subscriptionState.computeTier = 'free';
        subscriptionState.perQueryCost = 0;
        subscriptionState.modelPreference = 'cost';
        
        // Update UI
        document.querySelector('input[name="compute-tier"][value="free"]').checked = true;
        
        // Disable Plus and Pro options
        disableComputeTiers(['plus', 'pro']);
        enableComputeTiers(['free']);
        
        // Reset integrations
        integrationState.sweatstackExtended = false;
        generateIntegrationGrid();
        
    } else if (tier === 'managed') {
        // Show config section for managed tier
        if (configSection) configSection.style.display = 'block';
        
        // Set the correct button as active based on current preference
        document.querySelectorAll('.toggle-option').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === subscriptionState.modelPreference);
        });
        updateConfigDescription(subscriptionState.modelPreference);
        
        // Disable Free, enable Plus/Pro
        disableComputeTiers(['free']);
        enableComputeTiers(['plus', 'pro']);
        
        // If currently on free, switch to plus
        if (subscriptionState.computeTier === 'free') {
            subscriptionState.computeTier = 'plus';
            subscriptionState.perQueryCost = TIER_CONFIG.plus.cost;
            document.querySelector('input[name="compute-tier"][value="plus"]').checked = true;
        }
        
        generateIntegrationGrid();
    }
    
    updateQueryCostDisplay();
    updateQueryCounter();
}

// Handle compute tier change
function handleComputeTierChange(event) {
    const tier = event.target.value;
    subscriptionState.computeTier = tier;
    
    // Update pricing based on tier
    const tierConfig = TIER_CONFIG[tier];
    subscriptionState.perQueryCost = tierConfig.cost;
    subscriptionState.maxQueries = tierConfig.maxQueries;
    subscriptionState.maxDataDays = tierConfig.maxDataDays;
    
    // Reset SweatStack for free tier
    if (tier === 'free') {
        integrationState.sweatstackExtended = false;
    }
    
    generateIntegrationGrid();
    updateQueryCostDisplay();
    updateQueryCounter();
}

// Update query cost display
function updateQueryCostDisplay() {
    let totalCost = subscriptionState.perQueryCost;
    
    // Update integration cost display FIRST (before adding to total)
    const integrationCostEl = document.getElementById('integrationCost');
    if (integrationCostEl) {
        if (integrationState.sweatstackExtended) {
            integrationCostEl.textContent = '+$0.01/query';
        } else {
            integrationCostEl.textContent = '$0';
        }
    }
    
    // Now add SweatStack cost to total if enabled
    if (integrationState.sweatstackExtended) {
        totalCost += 0.01;
    }
    
    // Update main cost display
    const costElement = document.getElementById('queryPriceDisplay');
    if (costElement) {
        if (totalCost === 0) {
            costElement.textContent = 'Free';
            costElement.className = 'cost-amount cost-free';
        } else {
            costElement.textContent = `$${totalCost.toFixed(2)}/query`;
            costElement.className = 'cost-amount cost-paid';
        }
    }
}

function disableComputeTiers(tiers) {
    tiers.forEach(tier => {
        const option = document.querySelector(`input[name="compute-tier"][value="${tier}"]`);
        if (option) {
            const container = option.closest('.tier-option');
            if (container) {
                container.classList.add('disabled');
                option.disabled = true;
            }
        }
    });
}

function enableComputeTiers(tiers) {
    tiers.forEach(tier => {
        const option = document.querySelector(`input[name="compute-tier"][value="${tier}"]`);
        if (option) {
            const container = option.closest('.tier-option');
            if (container) {
                container.classList.remove('disabled');
                option.disabled = false;
            }
        }
    });
}

// Update query counter display
async function updateQueryCounter() {
    try {
        // Get usage data
        const usageResponse = await window.authService.fetch('/api/monthly-usage');
        if (!usageResponse.ok) return;
        
        const usageData = await usageResponse.json();
        const data = usageData.data || {};
        
        // Get balance
        const balanceResponse = await window.authService.fetch('/api/balance');
        let currentBalance = 0;
        if (balanceResponse.ok) {
            const balanceData = await balanceResponse.json();
            currentBalance = balanceData.data?.balance || 0;
        }
        
        const queriesUsed = data.queries_used || 0;
        const maxQueries = data.max_queries;
        const computeTier = subscriptionState.computeTier;
        
        // Calculate total cost per query including SweatStack
        let costPerQuery = subscriptionState.perQueryCost;
        if (integrationState.sweatstackExtended) {
            costPerQuery += 0.01;
        }
        
        // Update display elements
        const countElement = document.getElementById('queryUsageCount');
        const labelElement = document.querySelector('.balance-row span:first-child');
        const badgeElement = document.getElementById('queryUsageBadge');
        const indicatorElement = document.getElementById('limitIndicator');
        
        if (labelElement) {
            labelElement.textContent = 'Remaining Queries:';
        }
        
        if (countElement) {
            countElement.classList.remove('near-limit', 'at-limit');
            if (indicatorElement) {
                indicatorElement.classList.remove('show-near', 'show-at');
                indicatorElement.textContent = '';
            }
            
            if (computeTier === 'free') {
                if (labelElement) {
                    labelElement.textContent = 'Remaining Queries:';
                }
                // Free tier: show remaining out of 20
                const remaining = Math.max(0, 20 - queriesUsed);
                countElement.textContent = `${remaining}`;
                
                if (remaining === 0) {
                    countElement.classList.add('at-limit');
                    if (indicatorElement) {
                        indicatorElement.classList.add('show-at');
                        indicatorElement.textContent = 'Query limit reached - upgrade to continue';
                    }
                } else if (remaining <= 4) {
                    countElement.classList.add('near-limit');
                }
            } else {
                // Plus/Pro tiers: calculate from balance
                let remaining;
                if (costPerQuery > 0) {
                    if (labelElement) {
                        labelElement.textContent = 'Compute Limit (Queries):';
                    }
                    remaining = Math.floor(currentBalance / costPerQuery);
                    countElement.textContent = 'Unlimited';
                    
                    if (remaining === 0) {
                        countElement.textContent = '0';
                        countElement.classList.add('at-limit');
                        if (indicatorElement) {
                            indicatorElement.classList.add('show-at');
                            indicatorElement.textContent = 'Insufficient funds - add funds to continue';
                        }
                    } else if (remaining <= 10) {
                        countElement.textContent = 'Low Funds';
                        countElement.classList.add('near-limit');
                    }
                } else {
                    // Shouldn't happen, but handle edge case
                    countElement.textContent = 'Unlimited';
                }
            }
        }
        
        if (badgeElement) {
            badgeElement.textContent = computeTier.charAt(0).toUpperCase() + computeTier.slice(1);
            badgeElement.className = `tier-badge tier-${computeTier}`;
        }
        
    } catch (error) {
        console.error('Error updating query counter:', error);
    }
}

// Load current subscription
async function loadCurrentSubscription() {
    if (!window.authService) {
        console.error('Auth service not available');
        return;
    }
    
    try {
        // Get subscription
        const subResponse = await window.authService.fetch('/api/subscription');
        if (subResponse.ok) {
            const subData = await subResponse.json();
            if (subData.data) {
                subscriptionState.modelTier = subData.data.model_tier || 'free';
                subscriptionState.computeTier = subData.data.compute_tier || 'free';
                subscriptionState.perQueryCost = subData.data.per_query_cost || 0;
                subscriptionState.maxQueries = subData.data.max_queries;
                subscriptionState.maxDataDays = subData.data.max_data_days || 14;
                
                const config = subData.data.integration_config || {};
                integrationState.sweatstackExtended = config.sweatstack_extended || false;
                
                // Fix: Recalculate per_query_cost based on actual tier
                const tierConfig = TIER_CONFIG[subscriptionState.computeTier];
                if (tierConfig) {
                    subscriptionState.perQueryCost = tierConfig.cost;
                }
                
                // Update UI
                const modelRadio = document.querySelector(`input[name="model-tier"][value="${subscriptionState.modelTier}"]`);
                if (modelRadio) modelRadio.checked = true;
                const computeRadio = document.querySelector(`input[name="compute-tier"][value="${subscriptionState.computeTier}"]`);
                if (computeRadio) computeRadio.checked = true;          // the self-hosted edition's 'local' compute has no card
                
                // Handle managed tier preference loading
                if (subscriptionState.modelTier === 'managed') {
                    const configSection = document.getElementById('modelConfigSection');
                    if (configSection) {
                        configSection.style.display = 'block';
                        
                        // Load model preference
                        const prefResponse = await window.authService.fetch('/api/llm-config');
                        if (prefResponse.ok) {
                            const prefData = await prefResponse.json();
                            const preference = prefData.config?.model_preference || 'cost';
                            subscriptionState.modelPreference = preference;
                            
                            // Set the correct button as active
                            document.querySelectorAll('.toggle-option').forEach(btn => {
                                btn.classList.toggle('active', btn.dataset.value === preference);
                            });
                            updateConfigDescription(preference);
                        }
                    }
                    
                    disableComputeTiers(['free']);
                    enableComputeTiers(['plus', 'pro']);
                } else if (subscriptionState.modelTier === 'free') {
                    disableComputeTiers(['plus', 'pro']);
                    enableComputeTiers(['free']);
                }
                
                generateIntegrationGrid();
            }
        }
        
        // Get balance
        const balanceResponse = await window.authService.fetch('/api/balance');
        if (balanceResponse.ok) {
            const balanceData = await balanceResponse.json();
            const balanceElement = document.getElementById('accountBalance');
            if (balanceElement && balanceData.data) {
                balanceElement.textContent = `$${balanceData.data.balance.toFixed(2)}`;
            }
        }
        
        updateQueryCostDisplay();
        await updateQueryCounter();
        
    } catch (error) {
        console.error('Error loading subscription:', error);
    }
}

// Save subscription
async function saveSubscription() {
    const saveBtn = document.getElementById('saveSubscription');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    
    try {
        // Save subscription
        const response = await window.authService.fetch('/api/subscription', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_tier: subscriptionState.modelTier,
                compute_tier: subscriptionState.computeTier,
                integration_config: {
                    sweatstack_extended: integrationState.sweatstackExtended
                }
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to save subscription');
        }
        
        const responseData = await response.json();
        
        // Update state with server response
        subscriptionState.perQueryCost = responseData.per_query_cost || 0;
        
        // Handle model preference for 'managed' tier
        const prefResponse = await window.authService.fetch('/api/llm-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_preference: subscriptionState.modelPreference || 'free'
            })
        });
        
        if (!prefResponse.ok) {
            throw new Error('Failed to save model preference');
        }
        
        // Update displays
        updateQueryCostDisplay();
        await updateQueryCounter();
        
        // Update localStorage cache
        localStorage.setItem('subscriptionTiers', JSON.stringify({
            modelTier: subscriptionState.modelTier,
            computeTier: subscriptionState.computeTier,
            modelPreference: subscriptionState.modelPreference,
            perQueryCost: subscriptionState.perQueryCost,
            timestamp: Date.now()
        }));
        
        saveBtn.textContent = 'Saved!';
        
        // Handle mandatory modal
        const modal = document.getElementById('subscriptionModal');
        if (modal && modal.classList.contains('mandatory')) {
            modal.classList.remove('mandatory');
            window.isWaitingForSubscription = false;
            
            setTimeout(() => {
                closeSubscriptionModal();
                if (typeof continueAppInitialization === 'function') {
                    continueAppInitialization();
                }
            }, 1000);
        } else {
            setTimeout(() => {
                saveBtn.textContent = 'Save';
                saveBtn.disabled = false;
            }, 2000);
        }

        // Start a new conversation to apply changes
        handleNewConversation()
        
    } catch (error) {
        console.error('Error saving subscription:', error);
        alert('Failed to save subscription. Please try again.');
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    }
}

async function checkSubscriptionOnLoad() {
    console.log('Checking subscription on load...');
    
    const blockAccess = () => {
        console.log('Access blocked - showing mandatory subscription modal');
        subscriptionState.modelTier = 'free';
        subscriptionState.computeTier = 'free';
        subscriptionState.perQueryCost = 0;
        
        setTimeout(() => {
            document.querySelector('input[name="model-tier"][value="free"]').checked = true;
            document.querySelector('input[name="compute-tier"][value="free"]').checked = true;
            disableComputeTiers(['plus', 'pro']);
            enableComputeTiers(['free']);
            generateIntegrationGrid();
        }, 0);
        
        showSubscriptionModal(true);
    };
    
    if (!window.authService) {
        blockAccess();
        return;
    }
    
    try {
        // Check auth status
        const authStatusResponse = await window.authService.fetch('/api/auth/status');
        if (!authStatusResponse.ok) {
            blockAccess();
            return;
        }
        
        const authStatus = await authStatusResponse.json();
        
        // Skip in single-user mode
        if (!authStatus.auth_enabled) {
            console.log('Single-user mode, allowing access');
            if (typeof continueAppInitialization === 'function') {
                continueAppInitialization();
            }
            return;
        }
        
        // Check subscription
        const response = await window.authService.fetch('/api/subscription');
        if (!response.ok) {
            blockAccess();
            return;
        }
        
        const data = await response.json();
        
        // New user or no subscription
        if (!data.data) {
            blockAccess();
            return;
        }
        
        // Just check that tiers are set - no API key check needed for managed tier
        if (!data.data.model_tier || !data.data.compute_tier) {
            blockAccess();
            return;
        }
        subscriptionState.computeTier = data.data.compute_tier;      // the workspace gate shows it (2026-09-09)
        
        // All checks passed
        console.log('Subscription valid, continuing initialization');
        if (typeof continueAppInitialization === 'function') {
            continueAppInitialization();
        }
        
    } catch (error) {
        console.error('Error checking subscription:', error);
        blockAccess();
    }
}

// The self-hosted edition (docs/OSS_DESIGN.md D7, O7): no funds, no tiers, no prices - the level comes from
// BAMBOO_LEVEL in .env until it can be saved locally (phase 3). The dialog keeps the Models and Integrations
// tabs and hides what belongs to the hosted service.
function applyLocalEditionToDialog() {
    if (!(typeof authConfig !== 'undefined' && authConfig && authConfig.mode === 'single')) return;   // auth.js's top-level `let`
    const modal = document.getElementById('subscriptionModal');
    if (!modal || modal.classList.contains('edition-local')) return;
    modal.classList.add('edition-local');
    const sub = modal.querySelector('.ui-dlg-h .sub');
    if (sub) sub.textContent = 'single-user edition: the level is set by BAMBOO_LEVEL in .env; model keys are read from .env';
    const funds = modal.querySelector('.subscription-tab[data-tab="funds"]'); if (funds) funds.style.display = 'none';
    const compute = modal.querySelector('.subscription-tab[data-tab="compute"]'); if (compute) compute.style.display = 'none';
    modal.querySelectorAll('.tier-price, .balance-info, #addFundsBtn, #saveSubscription, .subscription-footer').forEach(e => { e.style.display = 'none'; });
    const seg = modal.querySelector('#modelConfigSection'); if (seg) { seg.style.pointerEvents = 'none'; seg.title = 'set by BAMBOO_LEVEL in .env'; }
    const freeInput = modal.querySelector('input[name="model-tier"][value="free"]'); const free = freeInput && freeInput.closest('.tier-option'); if (free) free.style.display = 'none';
}

function showSubscriptionModal(mandatory = false) {
    applyLocalEditionToDialog();
    console.log('Showing subscription modal...', mandatory ? '(MANDATORY)' : '(optional)');
    const modal = document.getElementById('subscriptionModal');
    if (modal) {
        if (mandatory) {
            modal.classList.add('mandatory');
            window.isWaitingForSubscription = true;
        } else {
            modal.classList.remove('mandatory');
            window.isWaitingForSubscription = false;
        }
        
        modal.style.display = 'flex';
        loadCurrentSubscription();
    } else {
        console.error('Subscription modal not found in DOM!');
    }
}

function closeSubscriptionModal() {
    const modal = document.getElementById('subscriptionModal');
    if (modal) {
        if (!modal.classList.contains('mandatory')) {
            modal.style.display = 'none';
        }
    }
}


function showTemporaryMessage(message, isError = false) {
    const saveBtn = document.getElementById('saveSubscription');
    const originalText = 'Save';
    const wasDisabled = saveBtn.disabled;
    
    saveBtn.textContent = message;
    if (isError) {
        saveBtn.style.backgroundColor = '#ff4444';
    }
    
    setTimeout(() => {
        saveBtn.textContent = originalText;
        saveBtn.style.backgroundColor = '';
        if (!wasDisabled) {
            saveBtn.disabled = false;
        }
    }, 3000);
}

// Generate integration grid
function generateIntegrationGrid() {
    const computeTier = subscriptionState.computeTier || 'free';
    const grid = document.getElementById('integrationGrid');
    if (!grid) return;
    
    const periods = ['14D', '6M', '12M'];
    const providers = ['SweatStack', 'Intervals ICU', 'Endura'];
    
    const access = {
        'free': [true, false, false],
        'plus': [true, true, false],
        'pro': [true, true, true],
        'local': [true, true, true]          // the self-hosted edition: your own machine, every period
    };
    if (!access[computeTier]) computeTier = 'local';
    
    let html = '<table class="integration-table"><thead><tr><th>Provider</th>';
    periods.forEach(p => html += `<th>${p}</th>`);
    html += '</tr></thead><tbody>';
    
    providers.forEach(provider => {
        html += `<tr><td>${provider}</td>`;
        periods.forEach((period, idx) => {
            const isIncluded = access[computeTier][idx];
            const isSweatstack = provider === 'SweatStack';
            
            if (!isIncluded) {
                html += '<td class="locked">🔒</td>';
            } else if (isSweatstack && idx > 0) {
                const isChecked = integrationState.sweatstackExtended && 
                                 (computeTier === 'pro' || (computeTier === 'plus' && idx === 1));
                html += `<td class="optional">
                    <input type="checkbox" data-period="${period}" 
                        ${isChecked ? 'checked' : ''}>
                </td>`;
            } else {
                html += '<td class="included">✓</td>';
            }
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    
    grid.innerHTML = html;
    
    // Handle checkbox events
    const checkboxes = grid.querySelectorAll('.optional input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                checkboxes.forEach(cb => cb.checked = e.target.checked);
                integrationState.sweatstackExtended = true;
            } else {
                checkboxes.forEach(cb => cb.checked = false);
                integrationState.sweatstackExtended = false;
            }
            updateQueryCostDisplay();
            updateQueryCounter();
        });
    });
}

// Show query limit modal (enhanced for PAYG)
function showQueryLimitModal(message, details = {}) {
    const modalOverlay = document.createElement('div');
    modalOverlay.className = 'query-limit-modal-overlay';
    
    const modalContent = document.createElement('div');
    modalContent.className = 'query-limit-modal-content';
    
    // Build details HTML - with null checks
    let detailsHTML = '';
    if (details.balance !== undefined && details.balance !== null) {
        detailsHTML += `
            <div class="query-limit-info">
                <span>Current Balance:</span>
                <span class="balance-display">$${details.balance.toFixed(2)}</span>
            </div>
        `;
    }
    if (details.query_cost !== undefined && details.query_cost !== null && details.query_cost > 0) {
        detailsHTML += `
            <div class="query-limit-info">
                <span>Compute Cost per Query:</span>
                <span class="cost-display">$${details.query_cost.toFixed(3)}</span>
            </div>
        `;
    }
    
    modalContent.innerHTML = `
        <div class="query-limit-header">
            <div class="query-limit-icon-simple">i</div>
            <h3 class="query-limit-title">Query Limit Reached</h3>
        </div>
        
        <div class="query-limit-body">
            <p class="query-limit-message">${message}</p>
            ${detailsHTML}
        </div>
        
        <div class="query-limit-actions">
            <button class="query-limit-btn query-limit-cancel-btn">Cancel</button>
            <button class="query-limit-btn query-limit-upgrade-btn">
                ${details.balance === 0 ? 'Add Funds' : 'Upgrade Tier'}
            </button>
        </div>
    `;
    
    // Add event listeners
    const cancelBtn = modalContent.querySelector('.query-limit-cancel-btn');
    const upgradeBtn = modalContent.querySelector('.query-limit-upgrade-btn');
    
    cancelBtn.addEventListener('click', () => modalOverlay.remove());
    
    upgradeBtn.addEventListener('click', () => {
        modalOverlay.remove();
        showSubscriptionModal();
    });
    
    modalOverlay.appendChild(modalContent);
    document.body.appendChild(modalOverlay);
}

// Switch tabs (single definition)
function switchTab(tabName) {
    document.querySelectorAll('.subscription-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tabName}-tab`);
    });
    
    // Hide/show Add Funds button based on current tab
    const addFundsBtn = document.getElementById('addFundsBtn');
    if (addFundsBtn) {
        if (tabName === 'funds') {
            addFundsBtn.style.display = 'none';
        } else {
            addFundsBtn.style.display = '';
        }
    }
}

// Disable non-free tiers (single definition)
function disableNonFreeTiers(disable) {
    const plusOption = document.querySelector('input[name="compute-tier"][value="plus"]');
    const proOption = document.querySelector('input[name="compute-tier"][value="pro"]');
    
    [plusOption, proOption].forEach(option => {
        if (option) {
            const container = option.closest('.tier-option');
            if (container) {
                if (disable) {
                    container.classList.add('disabled');
                    option.disabled = true;
                } else {
                    container.classList.remove('disabled');
                    option.disabled = false;
                }
            }
        }
    });
}

function handleModelConfigToggle(value) {
    subscriptionState.modelPreference = value;
    updateConfigDescription(value);
}

function updateConfigDescription(preference) {
    const description = document.getElementById('configDescription');
    if (description) {
        // the levels by their shape, not their current models (2026-09-10): the seats change, this text should not
        if (preference === 'performance') {
            description.innerHTML = '<strong>Performance:</strong> A frontier model at full effort, reviewed by a stronger one. Under a dollar for most runs, a few for the longest.';
        } else if (preference === 'max') {
            description.innerHTML = '<strong>Max:</strong> The strongest frontier models throughout. A few dollars a run; the mode\'s budget caps it.';
        } else {
            description.innerHTML = '<strong>Cost optimised:</strong> A fast open model at full effort, reviewed by a frontier model. Cents a run.';
        }
    }
}

// Stripe payments 20251010

// Add Funds Modal Functions
function showAddFundsModal() {
    switchTab('funds')
}

function initializeFundsTabHandlers() {
    let selectedAmount = 10;
    
    // Amount button clicks
    document.querySelectorAll('#funds-tab .amount-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('#funds-tab .amount-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            selectedAmount = parseInt(e.target.dataset.amount);
            document.getElementById('customAmount').value = '';
            updateTotalDisplay(selectedAmount);
            
            // Enable proceed button
            const proceedBtn = document.getElementById('proceedToPayment');
            if (proceedBtn) proceedBtn.disabled = false;
        });
    });
    
    // Custom amount input
    const customInput = document.getElementById('customAmount');
    if (customInput) {
        customInput.addEventListener('input', (e) => {
            const value = parseInt(e.target.value) || 0;
            const proceedBtn = document.getElementById('proceedToPayment');
            
            // Remove active class from all preset buttons when typing custom amount
            document.querySelectorAll('#funds-tab .amount-btn').forEach(b => b.classList.remove('active'));
            
            if (value >= 10) {
                selectedAmount = value;
                updateTotalDisplay(selectedAmount);
                if (proceedBtn) proceedBtn.disabled = false;
            } else {
                // Show minimum amount if less than 10
                updateTotalDisplay(0); // or show an error message
                if (proceedBtn) proceedBtn.disabled = true;
            }
        });
        
        // Handle focus to clear button selection
        customInput.addEventListener('focus', () => {
            document.querySelectorAll('#funds-tab .amount-btn').forEach(b => b.classList.remove('active'));
        });
    }
    
    // Proceed button
    const proceedBtn = document.getElementById('proceedToPayment');
    if (proceedBtn) {
        proceedBtn.addEventListener('click', async () => {
            // Double-check minimum amount
            if (selectedAmount < 10) {
                alert('Minimum amount is $10');
                return;
            }
            await initiateStripeCheckout(selectedAmount);
        });
    }
}

function updateTotalDisplay(amount) {
    const totalElement = document.getElementById('totalAmount');
    if (totalElement) {
        if (amount === 0 || amount < 10) {
            totalElement.textContent = 'Min $10.00';
            totalElement.style.color = 'var(--error-color, #ff4444)';
        } else {
            totalElement.textContent = `$${amount.toFixed(2)}`;
            totalElement.style.color = 'var(--accent-color)';
        }
    }
}

async function initiateStripeCheckout(amount) {
    const btn = document.getElementById('proceedToPayment');
    btn.disabled = true;
    btn.textContent = 'Redirecting...';
    
    try {
        const response = await window.authService.fetch('/api/create-checkout-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount })
        });
        
        if (!response.ok) throw new Error('Failed to create checkout session');
        
        const data = await response.json();
        
        // Redirect to Stripe Checkout
        window.location.href = data.checkout_url;
        
    } catch (error) {
        console.error('Error creating checkout:', error);
        alert('Failed to initiate payment. Please try again.');
        btn.disabled = false;
        btn.textContent = 'Proceed to Payment';
    }
}

// Export functions
if (typeof window !== 'undefined') {
    window.initializeSubscriptionModal = initializeSubscriptionModal;
    window.checkSubscriptionOnLoad = checkSubscriptionOnLoad;
    window.showSubscriptionModal = showSubscriptionModal;
    window.updateQueryCounter = updateQueryCounter;
    window.showQueryLimitModal = showQueryLimitModal;
}