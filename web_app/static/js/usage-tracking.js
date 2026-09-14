//--------------------
//  USAGE TRACKING MANAGEMENT MODULE - STREAMLINED
//--------------------

window.currentUsageData = null;

function initializeUsageTracking() {
    console.log('Initializing usage tracking...');
    
    const modal = document.getElementById('usageTrackingModal');
    if (!modal) return;
    
    // Event listeners
    modal.querySelector('.close')?.addEventListener('click', closeUsageModal);
    modal.querySelector('#usagePeriodSelector')?.addEventListener('change', handlePeriodChange);
    modal.querySelector('#usageViewSelector')?.addEventListener('change', handleViewChange);
    
    // Close on outside click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeUsageModal();
    });
    
    // Settings trigger
    document.querySelector('.usage-tracking-option')?.addEventListener('click', showUsageModal);
    
    // Handle resize with debounce
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (modal.style.display === 'flex') resizeCharts();
        }, 250);
    });
    
    console.log('Usage tracking initialized');
}

//--------------------
//  MODAL CONTROL
//--------------------

function showUsageModal() {
    const modal = document.getElementById('usageTrackingModal');
    if (!modal) return;
    
    // Ensure modal is in body
    if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }
    
    // Reset to defaults
    document.getElementById('usagePeriodSelector').value = '30_days';
    document.getElementById('usageViewSelector').value = 'agents';
    
    modal.style.display = 'flex';
    
    // Load data after modal renders
    setTimeout(() => loadUsageData('30_days'), 100);
}

function closeUsageModal() {
    const modal = document.getElementById('usageTrackingModal');
    if (!modal) return;
    
    modal.style.display = 'none';
    
    // Clean up charts
    ['costChartData', 'tokenChartData'].forEach(id => {
        const container = document.getElementById(id);
        if (container?.children.length > 0) {
            Plotly.purge(container);
        }
    });
}

function handlePeriodChange(e) {
    loadUsageData(e.target.value);
}

function handleViewChange(e) {
    const period = document.getElementById('usagePeriodSelector').value;
    
    if (window.currentUsageData) {
        displayUsageData(window.currentUsageData, period);
    } else {
        loadUsageData(period);
    }
}

//--------------------
//  DATA LOADING
//--------------------

async function loadUsageData(period) {
    const containers = {
        loading: document.getElementById('usageLoadingContainer'),
        data: document.getElementById('usageDataContainer'),
        error: document.getElementById('usageErrorContainer')
    };
    
    // Show loading
    setContainerVisibility(containers, 'loading');
    
    try {
        if (!window.authService) {
            throw new Error('Authentication service not available');
        }
        
        const response = await window.authService.fetch(`/usage_tracking?period=${period}`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        const usageData = await response.json();
        window.currentUsageData = usageData;  // Store globally
        displayUsageData(usageData, period);
        
    } catch (error) {
        console.error('Error loading usage data:', error);
        displayError(error.message, containers);
    } finally {
        containers.loading.style.display = 'none';
    }
}

function setContainerVisibility(containers, show) {
    Object.entries(containers).forEach(([key, container]) => {
        if (container) {
            container.style.display = key === show ? (show === 'data' ? 'flex' : 'block') : 'none';
        }
    });
}

//--------------------
//  DATA DISPLAY
//--------------------

function displayUsageData(data, period) {
    setContainerVisibility({
        data: document.getElementById('usageDataContainer'),
        error: document.getElementById('usageErrorContainer')
    }, 'data');
    
    // Update period description
    const periodDesc = document.getElementById('usagePeriodDescription');
    if (periodDesc && data.summary) {
        periodDesc.textContent = data.summary.period_description || `Usage for ${period.replace('_', ' ')}`;
    }
    
    // Get current view
    const view = document.getElementById('usageViewSelector')?.value || 'agents';
    
    // Reset labels based on view
    resetSummaryLabels(view);
    
    // Update summary based on view
    if (view === 'queries') {
        updateQuerySummary(data);
    } else {
        updateSummary(data.summary);
    }
    
    // Render charts after container is visible
    setTimeout(() => {
        if (view === 'queries' && data.queries_chart) {
            createQueryCountChart(data.queries_chart);
            createQueryElapsedChart(data.queries_chart);
        } else {
            createCostChart(data.cost_chart);
            createTokenChart(data.token_chart);
        }
    }, 100);
}

function updateSummary(summary) {
    if (!summary) return;
    
    const updates = {
        totalCost: `$${(summary.total_cost || 0).toFixed(2)}`,
        totalInputTokens: (summary.total_input_tokens || 0).toLocaleString(),
        totalOutputTokens: (summary.total_output_tokens || 0).toLocaleString(),
        totalQueries: (summary.total_queries || 0).toLocaleString()
    };
    
    Object.entries(updates).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });
}

function displayError(message, containers) {
    setContainerVisibility(containers, 'error');
    const errorEl = document.getElementById('usageErrorMessage');
    if (errorEl) errorEl.textContent = message;
}

function updateQuerySummary(data) {
    if (!data.queries_chart || !data.summary) return;
    
    // Calculate totals from queries_chart
    const totalQueries = data.queries_chart.counts.reduce((a, b) => a + b, 0);
    const totalQueryCost = data.summary.total_query_cost || 0;
    const totalElapsed = data.queries_chart.elapsed_times.reduce((a, b) => a + b, 0);
    const avgElapsed = totalQueries > 0 ? totalElapsed / totalQueries : 0;
    
    // Update summary cards with appropriate values for queries view
    const updates = {
        totalCost: `$${totalQueryCost.toFixed(2)}`,
        totalQueries: totalQueries.toLocaleString(),
        totalInputTokens: formatSecondsToMinSec(avgElapsed),  // Avg time in MM:SS
        totalOutputTokens: formatSecondsToMinSec(totalElapsed)  // Total time in MM:SS
    };
    
    Object.entries(updates).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });
}

// Helper function to format seconds to MM:SS
function formatSecondsToMinSec(seconds) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Function to properly reset labels when switching views
function resetSummaryLabels(view) {
    const inputCard = document.querySelector('#totalInputTokens')?.closest('.summary-card');
    const outputCard = document.querySelector('#totalOutputTokens')?.closest('.summary-card');
    const costCard = document.querySelector('#totalCost')?.closest('.summary-card');
    
    if (view === 'queries') {
        // Set labels for queries view
        if (costCard) {
            const h4 = costCard.querySelector('h4');
            if (h4) h4.textContent = 'Total Compute Cost';
        }
        
        if (inputCard) {
            const h4 = inputCard.querySelector('h4');
            if (h4) h4.textContent = 'Avg Time/Query';
        }
        
        if (outputCard) {
            const h4 = outputCard.querySelector('h4');
            if (h4) h4.textContent = 'Total Time';
        }
    } else {
        // Reset labels for agents/models view
        if (costCard) {
            const h4 = costCard.querySelector('h4');
            if (h4) h4.textContent = 'Total Model Cost';
        }
        
        if (inputCard) {
            const h4 = inputCard.querySelector('h4');
            if (h4) h4.textContent = 'Input Tokens';
        }
        
        if (outputCard) {
            const h4 = outputCard.querySelector('h4');
            if (h4) h4.textContent = 'Output Tokens';
        }
    }
}


//--------------------
//  CHART CREATION
//--------------------

function getChartConfig() {
    // colours from the theme tokens (2026-09-08), so the charts match the dialog in both themes
    const css = getComputedStyle(document.documentElement);
    const v = (name, fallback) => (css.getPropertyValue(name) || fallback).trim();
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const model = v('--accent-color', '#50fa7b'), kernel = v('--c-kernel', v('--yaml-key', '#d1bd98')), lookup = v('--accent-replay', '#1E90FF'), fail = v('--error-color', '#ff6b6b');
    const muted = isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)';
    return {
        colors: {
            bg: 'rgba(0,0,0,0)',
            text: v('--text-secondary', isDark ? 'rgba(255,255,255,0.6)' : '#555'),
            grid: v('--border-color', isDark ? 'rgba(255,255,255,0.12)' : '#ddd'),
            agents: {
                'Analyst': model,
                'Investigator': model,
                'Image Generator': kernel,
                'Google Search Executor': lookup,
                'Google Search Summarizer': lookup,
                'Knowledge Distiller': isDark ? '#bd93f9' : '#7b1fa2',
                'Error Corrector': fail,
                'default': muted
            },
            models: [model, kernel, lookup, isDark ? '#bd93f9' : '#7b1fa2', fail, isDark ? '#8be9fd' : '#00838f', isDark ? '#ffb86c' : '#ef6c00', muted, isDark ? '#f1fa8c' : '#9e9d24', isDark ? '#ff79c6' : '#ad1457'],
            tokens: {
                input: model,
                output: kernel
            }
        },
        height: calculateChartHeight()
    };
}

function calculateChartHeight() {
    const chartsSection = document.querySelector('#usageTrackingModal .charts-section');
    if (!chartsSection) return 250;
    
    const sectionHeight = chartsSection.getBoundingClientRect().height;
    return Math.max((sectionHeight - 8) / 2 - 16, 200);
}

function formatLabels(labels) {
    return labels.map(label => {
        if (label.includes(' ')) {
            // Hourly format: show time only
            return label.split(' ')[1] || label;
        }
        // Daily format: show short date
        try {
            const date = new Date(label);
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } catch {
            return label;
        }
    });
}

function createCostChart(costData) {
    const container = document.getElementById('costChartData');
    if (!container || !costData) return;
    
    container.innerHTML = '';
    
    const config = getChartConfig();
    const view = document.getElementById('usageViewSelector')?.value || 'agents';
    const formattedLabels = formatLabels(costData.labels || []);
    
    let traces = [];
    let title = 'Cost Over Time';
    
    // Build traces based on view
    if (view === 'models' && costData.models && Object.keys(costData.models).length > 0) {
        title = 'Cost Over Time by Model';
        Object.entries(costData.models).forEach(([model, data], i) => {
            traces.push({
                x: formattedLabels,
                y: data || [],
                type: 'bar',
                name: model,
                marker: { 
                    color: config.colors.models[i % config.colors.models.length],
                    opacity: 0.9 
                },
                hovertemplate: `<b>${model}</b><br>%{x}<br>Cost: $%{y:.2f}<extra></extra>`
            });
        });
    } else if (view === 'agents' && costData.agents && Object.keys(costData.agents).length > 0) {
        title = 'Cost Over Time by Agent';
        Object.entries(costData.agents).forEach(([agent, data]) => {
            traces.push({
                x: formattedLabels,
                y: data || [],
                type: 'bar',
                name: agent,
                marker: { 
                    color: config.colors.agents[agent] || config.colors.agents.default,
                    opacity: 0.9 
                },
                hovertemplate: `<b>${agent}</b><br>%{x}<br>Cost: $%{y:.2f}<extra></extra>`
            });
        });
    } else {
        // Fallback to simple chart
        traces.push({
            x: formattedLabels,
            y: costData.data || [],
            type: 'bar',
            marker: { color: config.colors.agents['Planner'], opacity: 0.9 },
            hovertemplate: '<b>%{x}</b><br>Cost: $%{y:.2f}<extra></extra>'
        });
    }
    
    const layout = {
        title: {
            text: title,
            font: { color: config.colors.text, size: 14 },
            x: 0.5,
            y: 0.95
        },
        xaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickfont: { size: 10 },
            tickangle: costData.labels?.length > 10 ? -45 : 0
        },
        yaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickformat: '$,.2f',
            tickfont: { size: 10 }
        },
        plot_bgcolor: config.colors.bg,
        paper_bgcolor: config.colors.bg,
        font: { color: config.colors.text, size: 10 },
        margin: { 
            l: 60,  // Increased left margin for y-axis labels
            r: 20,  // Increased right margin
            t: 50, 
            b: costData.labels?.length > 10 ? 60 : 40  // Increased bottom margin for rotated labels
        },
        barmode: 'stack',
        showlegend: traces.length > 1,
        legend: traces.length > 1 ? {
            font: { color: config.colors.text, size: 10 },
            bgcolor: 'rgba(0,0,0,0)',
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: 1.05
        } : undefined,
        height: config.height,
        autosize: true
    };
    
    Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
}

function createTokenChart(tokenData) {
    const container = document.getElementById('tokenChartData');
    if (!container || !tokenData) return;
    
    container.innerHTML = '';
    
    const config = getChartConfig();
    const formattedLabels = formatLabels(tokenData.labels || []);
    
    const traces = [
        {
            x: formattedLabels,
            y: tokenData.input_tokens || [],
            type: 'bar',
            name: 'Input Tokens',
            marker: { color: config.colors.tokens.input, opacity: 0.9 },
            hovertemplate: '<b>%{x}</b><br>Input: %{y:,}<extra></extra>'
        },
        {
            x: formattedLabels,
            y: tokenData.output_tokens || [],
            type: 'bar',
            name: 'Output Tokens',
            marker: { color: config.colors.tokens.output, opacity: 0.9 },
            hovertemplate: '<b>%{x}</b><br>Output: %{y:,}<extra></extra>'
        }
    ];
    
    const layout = {
        title: {
            text: 'Token Usage Over Time',
            font: { color: config.colors.text, size: 14 },
            x: 0.5,
            y: 0.95
        },
        xaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickfont: { size: 10 },
            tickangle: tokenData.labels?.length > 10 ? -45 : 0
        },
        yaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickformat: ',d',
            tickfont: { size: 10 }
        },
        plot_bgcolor: config.colors.bg,
        paper_bgcolor: config.colors.bg,
        font: { color: config.colors.text, size: 10 },
        margin: { 
            l: 70,
            r: 20,
            t: 50, 
            b: tokenData.labels?.length > 10 ? 60 : 40  // Increased for rotated labels
        },
        barmode: 'group',
        legend: {
            font: { color: config.colors.text, size: 10 },
            bgcolor: 'rgba(0,0,0,0)',
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: 1.05
        },
        height: config.height,
        autosize: true
    };
    
    Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
}

function resizeCharts() {
    const newHeight = calculateChartHeight();
    
    ['costChartData', 'tokenChartData'].forEach(id => {
        const container = document.getElementById(id);
        if (container?.children.length > 0) {
            Plotly.relayout(container, { height: newHeight });
        }
    });
}

function createQueryCountChart(queryData) {
    const container = document.getElementById('costChartData');
    if (!container || !queryData) return;
    
    container.innerHTML = '';
    
    const config = getChartConfig();
    const formattedLabels = formatLabels(queryData.labels || []);
    
    // Define tier colors
    const tierColors = {
        free: '#9e9e9e',  // Gray
        plus: '#2196f3',  // Blue
        pro: '#4caf50'    // Green
    };
    
    // Build stacked traces for each tier
    let traces = [];
    
    if (queryData.tiers) {
        // Add trace for each tier
        ['free', 'plus', 'pro'].forEach(tier => {
            if (queryData.tiers[tier] && queryData.tiers[tier].some(v => v > 0)) {
                traces.push({
                    x: formattedLabels,
                    y: queryData.tiers[tier] || [],
                    type: 'bar',
                    name: tier.charAt(0).toUpperCase() + tier.slice(1),
                    marker: { 
                        color: tierColors[tier],
                        opacity: 0.9 
                    },
                    hovertemplate: `<b>${tier.charAt(0).toUpperCase() + tier.slice(1)}</b><br>%{x}<br>Queries: %{y}<br>Cost: $%{customdata:.2f}<extra></extra>`,
                    customdata: queryData.tier_costs ? queryData.tier_costs[tier] : []
                });
            }
        });
    }
    
    // Fallback to simple bar if no tier data
    if (traces.length === 0) {
        traces.push({
            x: formattedLabels,
            y: queryData.counts || [],
            type: 'bar',
            name: 'Queries',
            marker: { 
                color: config.colors.agents['Planner'] || '#4CAF50',
                opacity: 0.9 
            },
            hovertemplate: '<b>%{x}</b><br>Queries: %{y}<br>Cost: $%{customdata:.2f}<extra></extra>',
            customdata: queryData.costs || []
        });
    }
    
    const layout = {
        title: {
            text: 'Query Count by Tier',
            font: { color: config.colors.text, size: 14 },
            x: 0.5,
            y: 0.95
        },
        xaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickfont: { size: 10 },
            tickangle: queryData.labels?.length > 10 ? -45 : 0
        },
        yaxis: {
            title: 'Number of Queries',
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickformat: 'd',
            tickfont: { size: 10 }
        },
        plot_bgcolor: config.colors.bg,
        paper_bgcolor: config.colors.bg,
        font: { color: config.colors.text, size: 10 },
        margin: { 
            l: 70,
            r: 20,
            t: 50, 
            b: queryData.labels?.length > 10 ? 60 : 40
        },
        barmode: 'stack',  // Stack the bars
        showlegend: traces.length > 1,
        legend: traces.length > 1 ? {
            font: { color: config.colors.text, size: 10 },
            bgcolor: 'rgba(0,0,0,0)',
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: 1.05
        } : undefined,
        height: config.height,
        autosize: true
    };
    
    Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
}

function createQueryElapsedChart(queryData) {
    const container = document.getElementById('tokenChartData');
    if (!container || !queryData) return;
    
    container.innerHTML = '';
    
    const config = getChartConfig();
    const formattedLabels = formatLabels(queryData.labels || []);
    
    const traces = [{
        x: formattedLabels,
        y: queryData.elapsed_times || [],
        type: 'bar',
        marker: { 
            color: config.colors.tokens.output || '#42A5F5',
            opacity: 0.9 
        },
        hovertemplate: '<b>%{x}</b><br>Total Time: %{y:.1f}s<extra></extra>'
    }];
    
    const layout = {
        title: {
            text: 'Total Elapsed Time',
            font: { color: config.colors.text, size: 14 },
            x: 0.5,
            y: 0.95
        },
        xaxis: {
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickfont: { size: 10 },
            tickangle: queryData.labels?.length > 10 ? -45 : 0
        },
        yaxis: {
            title: 'Time (seconds)',
            color: config.colors.text,
            gridcolor: config.colors.grid,
            showgrid: true,
            zeroline: false,
            tickformat: '.1f',
            tickfont: { size: 10 }
        },
        plot_bgcolor: config.colors.bg,
        paper_bgcolor: config.colors.bg,
        font: { color: config.colors.text, size: 10 },
        margin: { 
            l: 70,
            r: 20,
            t: 50, 
            b: queryData.labels?.length > 10 ? 60 : 40
        },
        showlegend: false,
        height: config.height,
        autosize: true
    };
    
    Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
}