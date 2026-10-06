//--------------------
//  CONTENT RENDERING MODULE
//--------------------

function initializeContentRendering() {
    console.log('Initializing content rendering...');
    
    initializeSelectionPopup();
    initializeTextSelection();
    initializePlotFullscreenModal();
    
    console.log('Content rendering initialized');
}

//--------------------
//  SELECTION POPUP SYSTEM
//--------------------

function initializeSelectionPopup() {
    // Create and inject the popup HTML
    const popupHtml = `
    <div id="selectionPopup" class="selection-popup" style="display: none;">
        <form id="selectionForm">
        <input type="text" id="selectionQuery" placeholder="Enter your query">
        <button type="submit" id="selectionRunButton" aria-label="Run query">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
        </button>
        </form>
        <div id="selectedTextDisplay" class="selected-text-display" style="display: none;"></div>
    </div>
    `;

    document.body.insertAdjacentHTML('beforeend', popupHtml);

    // Get references to popup elements
    const selectionPopup = document.getElementById('selectionPopup');
    const selectionQuery = document.getElementById('selectionQuery');
    const selectionForm = document.getElementById('selectionForm');

    // Handle form submission
    if (selectionForm) {
        selectionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleQuerySubmission(e);
        });
    }
    
    // Handle Enter key
    if (selectionQuery) {
        selectionQuery.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleQuerySubmission(e);
            }
        });
    }

    // Handle click outside popup
    document.addEventListener('mousedown', handleClickOutside);
}

function initializeTextSelection() {
    const contentOutput = document.getElementById('contentOutput');
    
    if (contentOutput) {
        contentOutput.addEventListener('mouseup', (e) => {
            // Check if the click is within a plot tab
            const plotTab = e.target.closest('#content-plot');
            if (!plotTab) {
                handleTextSelection(e);
            }
        });
    }

    // Update highlights on scroll
    window.addEventListener('scroll', handleScroll);
}

//--------------------
//  TEXT SELECTION HANDLERS
//--------------------

function handleTextSelection(e) {
    // Check if code is being edited
    const editButton = document.querySelector('#content-code .edit-button');
    if (editButton && editButton.hasAttribute('data-editing')) {
        return; // Don't handle text selection when editing code
    }
    
    const selection = window.getSelection();
    selectedText = selection.toString().trim();
    
    if (selectedText) {
        currentRange = selection.getRangeAt(0).cloneRange();
        console.log('New selection made:', selectedText);
        
        showPopupAtPosition(e.clientX, e.clientY);
        const selectionQuery = document.getElementById('selectionQuery');
        if (selectionQuery) {
            selectionQuery.value = '';
            selectionQuery.focus();
        }
    }
}

function handleClickOutside(e) {
    // Check if code is being edited
    const editButton = document.querySelector('#content-code .edit-button');
    if (editButton && editButton.hasAttribute('data-editing')) {
        return; // Don't interfere when editing code
    }
    
    if (e.target.closest('#content-plot')) return;
    
    if (e.target.closest('#selectionForm') || 
        e.target.closest('#selectionRunButton') || 
        e.target.closest('#selectionQuery')) return;
    
    const selectionPopup = document.getElementById('selectionPopup');
    if (!selectionPopup.contains(e.target) && e.target !== selectionPopup) {
        selectionPopup.style.display = 'none';
        removeHighlights(); // This will clear the selection
        currentRange = null;
        selectedText = '';
    }
}

function removeHighlights() {
    // Clear the browser selection
    const selection = window.getSelection();
    selection.removeAllRanges();
    highlightElements = [];
}

function showPopupAtPosition(x, y) {
    const selectionPopup = document.getElementById('selectionPopup');
    const selectedTextDisplay = document.getElementById('selectedTextDisplay');
    
    selectionPopup.style.display = 'block';
    
    // Display the selected text below the input
    if (selectedText && selectedTextDisplay) {
        selectedTextDisplay.style.display = 'block';
        selectedTextDisplay.innerHTML = `<strong>Selected:</strong> "${selectedText.length > 1000 ? selectedText.substring(0, 1000) + '...' : selectedText}"`;
    }
    
    // Position popup (after content is set so size calculations are accurate)
    setTimeout(() => {
        const popupX = x + 10;
        const popupY = y + 10;
        
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const popupWidth = selectionPopup.offsetWidth;
        const popupHeight = selectionPopup.offsetHeight;
        
        const finalX = Math.min(popupX, viewportWidth - popupWidth - 10);
        const finalY = Math.min(popupY, viewportHeight - popupHeight - 10);
        
        selectionPopup.style.left = finalX + 'px';
        selectionPopup.style.top = finalY + 'px';
    }, 0);
}

function handleScroll() {
}

async function handleQuerySubmission(e) {
    if (e) e.preventDefault();

    const selectionQuery = document.getElementById('selectionQuery');
    const query = selectionQuery.value.trim();

    if (!query || !selectedText) return;

    const queryWithContext = `${query}\n**Task Context:**\n${selectedText}`;

    // Dismiss popup before submitting
    document.getElementById('selectionPopup').style.display = 'none';
    removeHighlights();

    // Delegate to main handler
    const queryInput = document.getElementById('queryInput');
    queryInput.value = queryWithContext;
    handleQuerySubmit();

    // Clean up selection state after
    currentSelection = null;
    selectedText = '';
}

//--------------------
//  TAB MANAGEMENT
//--------------------

function createOrUpdateTab(type, data, id = null, format = null) {
    if (type === 'query' || type === 'generated_datasets') {
        return;   // the Query tab is retired (2026-09-05): the question is the chain's own text; generated datasets are
                  // the pane's download pills, not a tab (2026-10-06: the tab the type made was empty)
    }

    const _lt = (typeof liveTargets === 'function') ? liveTargets() : null;
    const tabContainer = _lt ? _lt.tabs : document.getElementById('tabContainer');
    const contentOutput = _lt ? _lt.content : document.getElementById('contentOutput');
    let tab = tabContainer.querySelector(`#tab-${type}`);
    let tabContent = contentOutput.querySelector(`#content-${type}`);

    if (!tab) {
        // Create new tab
        tab = document.createElement('div');
        tab.id = `tab-${type}`;
        tab.className = 'tab';

        // Determine tab name based on mode
        let tabName;
        if (type === 'answer') {
            if (answerTabSynthesis) {
                tabName = 'Synthesis';
            } else if (answerTabInteractive) {
                tabName = 'Explore';
            } else {
                tabName = 'Answer';
            }
        } else if (type === 'plan') {
            // Renamed 2026-08-30 (user ruling): this tab holds the
            // INVESTIGATION's briefing; the single-shot YAML plan it was
            // named for retired with the delve rebuild. Internal 'plan'
            // keys stay, so stored responses and the PDF export are
            // untouched.
            tabName = 'Investigation';
        } else if (type === 'code_exec_results') {
            tabName = 'Results';           // the reproduction script's own output (2026-09-06)
        } else if (type === 'dataframe') {
            tabName = 'Data';
        } else if (type === 'plot') {
            tabName = 'Plots';
        } else {
            tabName = type.charAt(0).toUpperCase() + type.slice(1);
        }
        tab.textContent = tabName;

        tab.onclick = () => (typeof activateTabInView === 'function' ? activateTabInView(type) : activateTab(type));
        tabContainer.appendChild(tab);

        // Create new tab content
        tabContent = document.createElement('div');
        tabContent.id = `content-${type}`;
        tabContent.className = 'tab-content';
        contentOutput.appendChild(tabContent);
    }
    if (type === 'answer') tab.textContent = answerTabInteractive ? 'Explore' : (answerTabSynthesis ? 'Synthesis' : 'Answer');   // the label follows the kind of answer (2026-09-08)

    updateTabContent(type, data, id, format);
    activateTab(type);
}

function activateTab(type) {
    const _lt = (typeof liveTargets === 'function') ? liveTargets() : null;
    const tabsRoot = _lt ? _lt.tabs : document.getElementById('tabContainer');
    const contentRoot = _lt ? _lt.content : document.getElementById('contentOutput');
    const tabs = tabsRoot.querySelectorAll('.tab');
    const tabContents = contentRoot.querySelectorAll('.tab-content');

    for (let i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
    for (let i = 0; i < tabContents.length; i++) tabContents[i].classList.remove('active');

    const activeTab = tabsRoot.querySelector(`#tab-${type}`);
    const activeContent = contentRoot.querySelector(`#content-${type}`);

    if (activeTab && activeContent) {
        activeTab.classList.add('active');
        activeContent.classList.add('active');
    } else {
        console.warn(`Tab or content for type "${type}" not found`);
    }
}

function clearAllTabs() {
    const _lt = (typeof liveTargets === 'function') ? liveTargets() : null;
    const tabContainer = _lt ? _lt.tabs : document.getElementById('tabContainer');
    const contentOutput = _lt ? _lt.content : document.getElementById('contentOutput');
    tabContainer.innerHTML = '';
    contentOutput.innerHTML = '';
}

//--------------------
//  CONTENT RENDERING
//--------------------

async function updateTabContent(type, data, id = null, format = null) {
    const _root = (typeof liveTargets === 'function') ? liveTargets().content : document.getElementById('contentOutput');
    const tabContent = _root.querySelector(`#content-${type}`);
    let content = '';

    switch(type) {
        case 'dataframe':
            // a page object (the grid) or a legacy HTML preview (older favourites)
            content = (data && typeof data === 'object') ? '' : data;
            break;
        case 'plan':
        case 'model': {
            const { html, hasDiagram, mermaidSrc } = buildDiagramTab(type, data);
            tabContent.innerHTML = html;
        
            if (hasDiagram) {
                ensureMermaid();
                const host = tabContent.querySelector('.mermaid');
                mermaid.render('m-' + Date.now(), mermaidSrc)
                    .then(function (result) {
                        if (host) {
                            host.innerHTML = result.svg;
        
                            // Force SVG to scale to container width
                            var svg = host.querySelector('svg');
                            if (svg) {
                                if (!svg.getAttribute('viewBox')) {
                                    var w = parseFloat(svg.getAttribute('width')) || 800;
                                    var h = parseFloat(svg.getAttribute('height')) || 600;
                                    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
                                }
                                svg.removeAttribute('width');
                                svg.removeAttribute('height');
                                svg.removeAttribute('style');
                                svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
                            }
        
                            // Zoom/fullscreen controls retired with the
                            // graph viewer (graphControls.js) - see
                            // memory_pack_design.md.
                        }
                    })
                    .catch(function (err) {
                        console.warn('Mermaid render failed:', err);
                    });
            }
        
            tabContent.querySelectorAll('pre code').forEach(hljs.highlightElement);
            tabContent.removeEventListener('scroll', handleScroll);
            tabContent.addEventListener('scroll', handleScroll);
            return;
        }
        case 'review':
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            content += '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            break;
        case 'code':
            content = renderCodeTab(data);
            break;
        case 'plot':
            content = renderPlotTab(data, id, format);
            break;
        case 'answer': {
            console.log('Processing answer case');
        
            // Change header text based on mode
            let headerText;
            if (answerTabSynthesis) {
                headerText = 'Synthesis';
            } else if (answerTabInteractive) {
                headerText = 'Explore';
            } else {
                headerText = type.charAt(0).toUpperCase() + type.slice(1);
            }
            // The default 'Answer:' label is gone (user ruling
            // 2026-08-29), but the heading ELEMENT stays, empty: the PDF
            // and Simplified buttons anchor to the tab's first h3, and
            // removing it outright sent them to the first markdown
            // heading mid-page. The dual-summary Synthesis/Explore
            // labels stay as they were.
            content = (answerTabSynthesis || answerTabInteractive)
                ? `<h3>${headerText}:</h3>`
                : '<h3 class="answer-tab-anchor"></h3>';
            
            // First protect LaTeX content
            const { text: protectedContent, placeholders } = protectLatexDelimiters(data);
            
            // Parse markdown
            let parsedContent = marked.parse(protectedContent);
            
            // Process interactive items if needed (not for synthesis)
            if (answerTabInteractive) {
                parsedContent = transformNumberedListToInteractivePills(parsedContent);
                answerTabInteractive = false;
            }
            
            // Transform chain ID references to clickable links (for synthesis)
            parsedContent = transformChainIdReferences(parsedContent);
            
            // Reset synthesis flag after processing
            if (answerTabSynthesis) {
                answerTabSynthesis = false;
            }
            
            // Restore LaTeX content; then the citation chips - [cell 7], [fig 7], [D1.17] - as part of the HTML itself, so
            // the stored technical answer carries them through toggles and re-renders (stream-pane.js, 2026-10-03)
            let finalContent = restoreLatexDelimiters(parsedContent, placeholders);
            if (type === 'answer' && typeof paneCiteHtml === 'function') finalContent = paneCiteHtml(finalContent);
            
            // Add the content to the DOM
            content += '<div class="markdown-content content-body">' + finalContent + '</div>';
            
            // Store technical answer for toggle functionality
            currentData.technicalAnswer = '<div class="markdown-content content-body">' + finalContent + '</div>';
            currentData.summaryViewMode = 'technical';
            
            // Queue LaTeX rendering after content is in DOM
            setTimeout(() => {
                const contentElement = document.querySelector(`#content-${type} .markdown-content`);
                if (contentElement) {
                    renderLatex(contentElement);
                    
                    // Add event listeners to the interactive pills if they exist
                    attachPillEventListeners(contentElement);
                    
                    // Add event listeners to chain ID references
                    attachChainRefListeners(contentElement);
                    
                    // Add PDF export button and simplified summary button to answer tab (not for the Explore page)
                    if (typeof handleAnswerTabUpdate === 'function' && !(typeof answerTabExplore !== 'undefined' && answerTabExplore)) {
                        handleAnswerTabUpdate();
                    }
                    if (typeof answerTabExplore !== 'undefined') answerTabExplore = false;
                }
            }, 100);
            
            break;
        }
        case 'code_exec_results': {
            // the reproduction script's printed output, verbatim, in the app's code block
            const escaped = String(data == null ? '' : data).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            content = '<h3>Results:</h3><div class="markdown-content"><pre><code class="language-plaintext">' + escaped + '</code></pre></div>';
            break;
        }
        default:
            console.log(`Unknown data type: ${type}`);
            return;
    }

    if (type === 'plot' && id) {
        // For plots, we append new plots instead of replacing
        tabContent.innerHTML += content;
        // Get ALL plot containers and attach listeners to each one
        const plotContainers = tabContent.querySelectorAll('.plot-container');
        plotContainers.forEach(container => {
            attachPlotQueryListeners(container);
        });
    } else if (type === 'dataframe' && data && typeof data === 'object' && typeof renderDataGrid === 'function') {
        renderDataGrid(tabContent, data);
    } else {
        tabContent.innerHTML = content;
        if (type === 'plot') {
            const allPlotContainers = tabContent.querySelectorAll('.plot-container');
            allPlotContainers.forEach(container => {
                attachPlotQueryListeners(container);
            });
        }
    }
  
    // Highlight code blocks
    if (['model', 'plan', 'code', 'mermaid'].includes(type)) {
        tabContent.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightBlock(block);
        });
    }
    // Add listener to update highlights on scroll
    tabContent.removeEventListener('scroll', handleScroll);
    tabContent.addEventListener('scroll', handleScroll);
    console.log('Scroll listener added for', type, 'tab');
}

//--------------------
//  CHAIN ID REFERENCES
//--------------------

function transformChainIdReferences(htmlContent) {
    // Build a map of unique chain_ids to reference numbers
    const chainIds = [...htmlContent.matchAll(/\[\[(\d+)\]\]/g)].map(m => m[1]);
    const uniqueChainIds = [...new Set(chainIds)];
    const refMap = {};
    uniqueChainIds.forEach((id, index) => {
        refMap[id] = index + 1;
    });

    return htmlContent.replace(/\[\[(\d+)\]\]/g, (match, chainId) => {
        const response = responses.find(r => r.chain_id == chainId);
        const queryText = response?.queryText || 'Analysis not found';
        const escaped = queryText
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, ' ');
        const refNum = refMap[chainId];
        return `<span class="chain-ref" data-chain-id="${chainId}" data-tooltip="${escaped}">[A${refNum}]</span>`;
    });
}

function attachChainRefListeners(contentElement) {
    // Create single tooltip element if it doesn't exist
    let tooltip = document.getElementById('chainRefTooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'chainRefTooltip';
        tooltip.className = 'chain-ref-tooltip';
        document.body.appendChild(tooltip);
    }

    const chainRefs = contentElement.querySelectorAll('.chain-ref');
    
    chainRefs.forEach(ref => {
        // Click handler for navigation
        ref.addEventListener('click', function() {
            const chainId = this.getAttribute('data-chain-id');
            tooltip.classList.remove('visible');
            navigateToChainId(chainId);
        });

        // Hover handlers for tooltip
        ref.addEventListener('mouseenter', function() {
            const tooltipText = this.getAttribute('data-tooltip');
            tooltip.textContent = tooltipText;
            
            const rect = this.getBoundingClientRect();
            const tooltipWidth = 300;
            const margin = 8;
            
            // Position above the element
            let top = rect.top - tooltip.offsetHeight - 6;
            let left = rect.left + (rect.width / 2) - (tooltipWidth / 2);
            
            // Keep within viewport horizontally
            if (left < margin) {
                left = margin;
            } else if (left + tooltipWidth > window.innerWidth - margin) {
                left = window.innerWidth - tooltipWidth - margin;
            }
            
            // If no room above, show below
            if (top < margin) {
                top = rect.bottom + 6;
            }
            
            tooltip.style.top = `${top}px`;
            tooltip.style.left = `${left}px`;
            tooltip.classList.add('visible');
        });

        ref.addEventListener('mouseleave', function() {
            tooltip.classList.remove('visible');
        });
    });
}

function navigateToChainId(chainId) {
    const targetIndex = responses.findIndex(r => r.chain_id == chainId);
    if (targetIndex >= 0) {
        currentResponseIndex = targetIndex;
        lastActiveChainId = responses[targetIndex].chain_id || null;
        loadResponseContent(responses[currentResponseIndex]);
        if (typeof updateNavigationButtons === 'function') {
            updateNavigationButtons();
        }
    } else {
        console.warn(`Chain ID ${chainId} not found in current session`);
    }
}

//--------------------
//  SPECIALIZED RENDERERS
//--------------------

function renderCodeTab(data) {
    let content = `<h3>Code:</h3>`;
    content += `<div class="markdown-content">
        <div class="code-header">
            <span class="language-label">PYTHON</span>
            <div class="header-actions">
                <button class="code-action-button edit-button" title="Edit">
                    <svg class="edit-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                    </svg>
                    <svg class="save-icon" style="display: none" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                        <polyline points="17 21 17 13 7 13 7 21" />
                    </svg>
                </button>
                <button class="code-action-button discard-button" style="display: none" title="Discard changes">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
                <button class="code-action-button execute-button" title="Execute">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                </button>
            </div>
        </div>
        <pre><code class="language-python">${data}</code></pre>
    </div>`;

    // Add event listeners after content is added to DOM
    setTimeout(() => {
        initializeCodeEditor();
    }, 0);

    return content;
}

// A figure caption in the synthesis text links to its chart: open the
// Plot tab and bring that figure into view. Delegated, so it covers
// streamed and restored answers alike.
document.addEventListener('click', (e) => {
    const ref = e.target.closest('.figure-ref');
    if (!ref) return;
    e.preventDefault();
    activateTab('plot');
    const target = document.querySelector(
        `#content-plot .plot-container[data-plot-id="${ref.dataset.plotId}"]`);
    if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        target.classList.add('plot-highlight');
        setTimeout(() => target.classList.remove('plot-highlight'), 1600);
    }
});

function renderPlotTab(data, id, format) {
    const baseContainer = `
        <div class="plot-container" data-plot-id="${id}">
            <div class="plot-header">
                <h3>${id && id.startsWith('synthfig_') ? 'Figure' : 'Plot'} ${id ? id.split('_')[1] : ''}:</h3>
                <div class="plot-header-actions">
                    <button class="plot-query-btn" aria-label="Ask AI about this plot" title="Ask AI about this plot">
                        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                        </svg>
                    </button>
                    <button class="plot-expand-btn" aria-label="Expand plot" title="Full screen">
                        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="15 3 21 3 21 9"/>
                            <polyline points="9 21 3 21 3 15"/>
                            <line x1="21" y1="3" x2="14" y2="10"/>
                            <line x1="3" y1="21" x2="10" y2="14"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="plot-query-form" style="display: none;">
                <input type="text" class="plot-query-input" placeholder="Enter your query about plot ${id ? id.split('_')[1] : ''}">
                <button type="submit" class="plot-query-submit">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </button>
            </div>`;
    
    if (format === 'html') {
        const content = `${baseContainer}
            <div class="plot-content plotly-plot">
                <div id="plotly-container-${id}"></div>
            </div>
        </div>`;
        
        setTimeout(() => {
            const container = ((typeof liveTargets === 'function') ? liveTargets().content : document).querySelector(`#plotly-container-${id}`);
            if (container) {
                container.innerHTML = data;
                const scripts = container.getElementsByTagName('script');
                Array.from(scripts).forEach(script => {
                    if (!script.src) {
                        eval(script.textContent);
                    }
                });
                // CHANGED: Force Plotly to fill container width + enable pan
                const plotDiv = container.querySelector('.js-plotly-plot');
                if (plotDiv) {
                    Plotly.relayout(plotDiv, { autosize: true, width: undefined, dragmode: 'pan' });
                }
            }
        }, 100);
        
        return content;
    } 
    else if (format === 'json') {
        const content = `${baseContainer}
            <div class="plot-content plotly-plot">
                <div id="plotly-container-${id}" data-plotly-json="${data.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")}"</div>
            </div>
        </div>`;
                      
        setTimeout(() => {
            const container = ((typeof liveTargets === 'function') ? liveTargets().content : document).querySelector(`#plotly-container-${id}`);
            if (container) {
                try {
                    const plotData = JSON.parse(container.dataset.plotlyJson.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"'));
                    // CHANGED: Override layout to force autosize + pan, add scrollZoom
                    Plotly.newPlot(container, plotData.data, 
                        Object.assign({}, plotData.layout, {
                            autosize: true,
                            width: undefined,
                            dragmode: 'pan'
                        }), {
                        responsive: true,
                        useResizeHandler: true,
                        displayModeBar: true,
                        scrollZoom: true
                    }).catch(error => {
                        console.error('Plot rendering failed:', error);
                        container.innerHTML = `
                            <div class="plot-error">
                                Failed to render plot. Please try refreshing the page.
                                <br><small>${error.message}</small>
                            </div>
                        `;
                    });
                } catch (error) {
                    console.error('Error processing plot data:', error);
                    container.innerHTML = `
                        <div class="plot-error">
                            Failed to process plot data. Please try refreshing the page.
                            <br><small>${error.message}</small>
                        </div>
                    `;
                }
            }
        }, 100);
        
        return content;
    }
    else if (format === 'png') {
        return `${baseContainer}
            <div class="plot-content">
                <img src="data:image/png;base64,${data}" alt="${id && id.startsWith('synthfig_') ? 'Figure' : 'Plot'} ${id ? id.split('_')[1] : ''}" class="plot-image">
            </div>
        </div>`;
    }

    return '';
}

function buildDiagramTab(type, data) {
    // A plain string means prose, not a diagram: after an investigation the
    // Plan tab carries the Editor's briefing, which has no mermaid source and
    // never will. Render it as markdown and return early - the fallback below
    // exists for a diagram that failed to build, and showing its warning
    // notice for a document that was never meant to have one told the reader
    // something had gone wrong when nothing had.
    if (typeof data === 'string') {
        return {
            html: '<div class="briefing-content">' + marked.parse(data) + '</div>',
            hasDiagram: false,
            mermaidSrc: ''
        };
    }

    // Normalise + validate
    var mermaidSrc = typeof data?.visualization === 'string'
                     ? data.visualization.trim()
                     : '';
    var hasDiagram = mermaidSrc !== '' && !/\[object Object\]/.test(mermaidSrc);

    // YAML fallback
    var yamlBlock = data?.yaml ??
                    (typeof data === 'string'
                      ? data
                      : JSON.stringify(data, null, 2));

    // Header
    var html = '<h3>' + type[0].toUpperCase() + type.slice(1) + ':</h3>';

    // Diagram or notice
    if (hasDiagram) {
        html += '<div class="diagram-container">' +
                    '<div class="mermaid-view">' +
                        '<div class="mermaid">' + mermaidSrc + '</div>' +
                    '</div>' +
                '</div>';
    } else {
        html += '<p class="size-error-notice">' +
                    '<svg viewBox="0 0 24 24" width="16" height="16">' +
                        '<path fill="none" stroke="currentColor" stroke-linecap="round" ' +
                              'stroke-linejoin="round" stroke-width="2" ' +
                              'd="M12 9v2m0 4h.01M5.062 19h13.876c1.54 0 2.502-1.667 ' +
                              '1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16' +
                              'c-.77 1.333.192 3 1.722 3z"/>' +
                    '</svg>' +
                    ' Diagram visualisation not available — YAML shown below.' +
                '</p>';
    }

    // YAML section (always shown)
    html += '<div class="markdown-content">' +
            marked.parse('```yaml\n' + yamlBlock + '\n```') +
            '</div>';

    return { html: html, hasDiagram: hasDiagram, mermaidSrc: mermaidSrc };
}

//--------------------
//  DATA FORMATTERS
//--------------------

//--------------------
//  LATEX RENDERING
//--------------------

function protectLatexDelimiters(text) {
    // Create temporary placeholders for LaTeX content
    let counter = 0;
    const placeholders = [];

    // Helper function to replace LaTeX content with placeholders
    function replacer(match) {
        const placeholder = `LATEXPLACEHOLDER${counter}`;
        placeholders.push({ placeholder, content: match });
        counter++;
        return placeholder;
    }

    // More permissive patterns that better handle whitespace
    const patterns = [
        // Display math mode with escaped brackets
        /\\\[[^\]]*?\\\]/gs,
        // Inline math mode with escaped parentheses - more permissive pattern
        /\\\([^]*?\\\)/gs,
        // Display math mode with double dollars
        /\$\$[^]*?\$\$/gs,
        // Inline math mode with single dollars - more careful with boundaries
        /\$[^$\n]+?\$/g
    ];

    let protectedText = text;
    patterns.forEach(pattern => {
        protectedText = protectedText.replace(pattern, replacer);
    });

    return { text: protectedText, placeholders };
}

function restoreLatexDelimiters(text, placeholders) {
    let restoredText = text;
    for (const { placeholder, content } of placeholders) {
        restoredText = restoredText.replace(placeholder, content);
    }
    return restoredText;
}

function renderLatex(element) {
    if (!element) return;
    
    renderMathInElement(element, {
        delimiters: [
            {left: "\\[", right: "\\]", display: true},
            {left: "\\(", right: "\\)", display: false},
            {left: "$$", right: "$$", display: true},
            {left: "$", right: "$", display: false}
        ],
        throwOnError: false,
        output: 'html',
        strict: false,
        trust: true,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
        errorCallback: function(msg) {
            console.warn('KaTeX error:', msg);
        }
    });
}

//--------------------
//  INTERACTIVE PILLS
//--------------------

function transformNumberedListToInteractivePills(htmlContent) {
    // Create a temporary container to manipulate the HTML
    const tempContainer = document.createElement('div');
    tempContainer.innerHTML = htmlContent;
    
    // Find all ordered lists that might contain the numbered items
    const orderedLists = tempContainer.querySelectorAll('ol');
    
    // Process each list
    orderedLists.forEach(list => {
        // Create a container for the interactive pills
        const pillsContainer = document.createElement('div');
        pillsContainer.className = 'interactive-pills-container';
        
        // Process each list item
        const listItems = list.querySelectorAll('li');
        listItems.forEach((item, index) => {
            // Extract the clean text content for data-query
            const rawQuery = item.textContent.trim();
            // Store a clean version of the query without nested quotes
            const cleanQuery = rawQuery.replace(/['"]/g, '').replace(/\s+/g, ' ').trim();
            
            // Create a pill element
            const pill = document.createElement('div');
            pill.className = 'interactive-pill';
            // Store sanitized query as data attribute
            pill.setAttribute('data-query', cleanQuery);
            pill.innerHTML = `
                <span class="pill-number">${index + 1}</span>
                <span class="pill-content">${item.innerHTML}</span>
                <textarea class="pill-edit-input" style="display: none;">${cleanQuery}</textarea>
                <button class="pill-edit-btn" title="Edit query">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                    </svg>
                </button>
                <span class="pill-icon">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </span>
            `;
            
            pillsContainer.appendChild(pill);
        });
        
        // Replace the original list with our pills container
        list.parentNode.replaceChild(pillsContainer, list);
    });
    
    return tempContainer.innerHTML;
}

function attachPillEventListeners(contentElement) {
    const pills = contentElement.querySelectorAll('.interactive-pill');
    
    pills.forEach(pill => {
        const editBtn = pill.querySelector('.pill-edit-btn');
        const editInput = pill.querySelector('.pill-edit-input');
        const pillContent = pill.querySelector('.pill-content');
        const pillIcon = pill.querySelector('.pill-icon');
        
        // Edit button click handler
        editBtn.addEventListener('click', function(e) {
            e.stopPropagation(); // Prevent pill click event
            
            const isEditing = pill.classList.contains('editing');
            
            if (!isEditing) {
                // Enter edit mode
                pill.classList.add('editing');
                pillContent.style.display = 'none';
                editInput.style.display = 'block';
                editInput.focus();
                editInput.select();
                
                // Auto-resize textarea
                editInput.style.height = 'auto';
                editInput.style.height = editInput.scrollHeight + 'px';
                
                // Change edit icon to save icon
                editBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                    </svg>
                `;
            } else {
                // Save and exit edit mode
                const newQuery = editInput.value.trim();
                if (newQuery) {
                    pill.setAttribute('data-query', newQuery);
                    // Update the visible content with plain text
                    pillContent.textContent = newQuery;
                }
                
                pill.classList.remove('editing');
                pillContent.style.display = 'block';
                editInput.style.display = 'none';
                
                // Change save icon back to edit icon
                editBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                    </svg>
                `;
            }
        });
        
        // Auto-resize textarea on input
        editInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });
        
        // Input keyboard handlers
        editInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                editBtn.click(); // Save with Ctrl+Enter
            } else if (e.key === 'Escape') {
                e.preventDefault();
                // Cancel edit without saving
                editInput.value = pill.getAttribute('data-query');
                editBtn.click();
            }
        });
        
        // Prevent all events from bubbling up from textarea
        editInput.addEventListener('click', function(e) {
            e.stopPropagation();
        });
        
        // CRITICAL: Stop mouseup from bubbling to prevent selection popup
        editInput.addEventListener('mouseup', function(e) {
            e.stopPropagation();
        });
        
        // Pill click handler (for submitting query)
        pill.addEventListener('click', function(e) {
            // Don't submit if in edit mode or clicking the edit button
            if (pill.classList.contains('editing') || e.target.closest('.pill-edit-btn')) {
                return;
            }
            
            const query = this.getAttribute('data-query');
            
            // Set the query to the input field
            const queryInput = document.getElementById('queryInput');
            if (queryInput) {
                queryInput.value = query;
                
                // Submit the query
                if (typeof handleQuerySubmit === 'function') {
                    handleQuerySubmit();
                }
                
                // Scroll to the top of the output area
                const streamOutput = document.getElementById('streamOutput');
                if (streamOutput) {
                    streamOutput.scrollTop = 0;
                }
            }
        });
    });
}

//--------------------
//  CODE EDITOR
//--------------------

function initializeCodeEditor() {
    const tabContent = ((typeof liveTargets === 'function') ? liveTargets().content : document.getElementById('contentOutput')).querySelector('#content-code');
    if (!tabContent) return;

    const header = tabContent.querySelector('.code-header');
    const editButton = header.querySelector('.edit-button');
    const discardButton = header.querySelector('.discard-button');
    const executeButton = header.querySelector('.execute-button');
    const editIcon = editButton.querySelector('.edit-icon');
    const saveIcon = editButton.querySelector('.save-icon');
    const preElement = header.nextElementSibling;
    const codeElement = preElement.querySelector('code');
    let originalCode = codeElement.textContent;

    // Apply initial syntax highlighting
    hljs.highlightElement(codeElement);

    // Function to restore code view with highlighting
    function restoreCodeView(code) {
        const newPre = document.createElement('pre');
        const newCode = document.createElement('code');
        newCode.className = 'language-python';
        newCode.textContent = code;
        newPre.appendChild(newCode);
        
        const editorWrapper = header.nextElementSibling;
        editorWrapper.replaceWith(newPre);
        
        // Apply syntax highlighting
        hljs.highlightElement(newCode);
        
        // Reset button states
        editButton.removeAttribute('data-editing');
        editIcon.style.display = 'block';
        saveIcon.style.display = 'none';
        discardButton.style.display = 'none';
    }

    editButton.addEventListener('click', () => {
        const isEditing = editButton.hasAttribute('data-editing');
        if (!isEditing) {
            // Enter edit mode
            const codeBlock = header.nextElementSibling;
            const currentCode = codeBlock.querySelector('code').textContent;
            
            // Create wrapper for CodeMirror
            const editorWrapper = document.createElement('div');
            editorWrapper.className = 'code-editor-wrapper';
            
            // Get the height of the original code block
            const codeHeight = codeBlock.offsetHeight;
            
            // Replace code block with wrapper
            codeBlock.replaceWith(editorWrapper);
            
            // Initialize CodeMirror
            const editor = CodeMirror(editorWrapper, {
                value: currentCode,
                mode: 'python',
                theme: 'default',
                lineNumbers: true,
                lineWrapping: true,
                viewportMargin: Infinity,
                indentUnit: 4,
                styleActiveLine: true,
                matchBrackets: true,
                extraKeys: {
                    Tab: (cm) => cm.replaceSelection('    ', 'end')
                }
            });
            
            // Set editor height to match original code block
            editor.setSize(null, codeHeight);
            
            // Store editor instance for later access
            editorWrapper.editor = editor;
            
            // Update button states
            editButton.setAttribute('data-editing', 'true');
            editIcon.style.display = 'none';
            saveIcon.style.display = 'block';
            discardButton.style.display = 'block';
            
            // Focus editor
            editor.focus();
        } else {
            // Save changes
            const editorWrapper = header.nextElementSibling;
            originalCode = editorWrapper.editor.getValue();
            restoreCodeView(originalCode);
        }
    });

    discardButton.addEventListener('click', () => {
        restoreCodeView(originalCode);
    });

    executeButton.addEventListener('click', async () => {
        const editorWrapper = header.nextElementSibling;
        const currentCode = editorWrapper.editor ? 
            editorWrapper.editor.getValue() : 
            editorWrapper.querySelector('code').textContent;
    
        handleQuerySubmit({ user_code: currentCode });
    });
}

//--------------------
//  SIMPLIFIED SUMMARY TOGGLE
//--------------------

function addSimplifiedSummaryButton(answerTabContent) {
    // Don't add if already exists
    if (answerTabContent.querySelector('.simplified-summary-btn')) return;
    
    const header = answerTabContent.querySelector('h3');
    if (!header) return;
    
    // Ensure header container exists (same pattern as PDF button)
    if (!header.parentElement.classList.contains('tab-header-container')) {
        const headerContainer = document.createElement('div');
        headerContainer.className = 'tab-header-container';
        header.parentElement.insertBefore(headerContainer, header);
        headerContainer.appendChild(header);
    }
    
    const headerContainer = header.parentElement;
    const simplifiedButton = createSimplifiedSummaryButton();
    
    // Insert before PDF button if it exists, otherwise append
    const pdfButton = headerContainer.querySelector('.pdf-export-btn');
    if (pdfButton) {
        headerContainer.insertBefore(simplifiedButton, pdfButton);
    } else {
        headerContainer.appendChild(simplifiedButton);
    }
}

function createSimplifiedSummaryButton() {
    const button = document.createElement('button');
    button.className = 'simplified-summary-btn loading';
    button.title = 'Accessible summary loading...';
    button.setAttribute('aria-label', 'Toggle accessible summary');
    button.disabled = true;
    button.style.display = 'none';
    
    // Lightbulb icon
    button.innerHTML = `
        <svg class="simplified-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 18h6"></path>
            <path d="M10 22h4"></path>
            <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"></path>
        </svg>
        <span class="simplified-text">Simplified</span>
        <div class="simplified-spinner"></div>
    `;
    
    button.addEventListener('click', handleSimplifiedSummaryToggle);
    return button;
}

function handleSimplifiedSummaryToggle() {
    const answerTab = document.getElementById('content-answer');
    if (!answerTab) return;
    
    const answerContent = answerTab.querySelector('.content-body');
    if (!answerContent) return;
    
    const button = document.querySelector('.simplified-summary-btn');
    if (!button || button.disabled) return;
    
    // Toggle view mode
    if (currentData.summaryViewMode === 'technical') {
        // Switch to simplified
        if (currentData.simplifiedAnswer) {
            // Format and display simplified content
            const { text: protectedContent, placeholders } = protectLatexDelimiters(currentData.simplifiedAnswer);
            let parsedContent = marked.parse(protectedContent);
            const finalContent = restoreLatexDelimiters(parsedContent, placeholders);
            
            answerContent.innerHTML = finalContent;
            currentData.summaryViewMode = 'simplified';
            
            // Re-render LaTeX in the new content
            renderLatex(answerContent);
        }
    } else {
        // Switch to technical
        if (currentData.technicalAnswer) {
            // technicalAnswer is already formatted HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = currentData.technicalAnswer;
            const innerContent = tempDiv.querySelector('.content-body');
            
            answerContent.innerHTML = innerContent ? innerContent.innerHTML : currentData.technicalAnswer;
            
            // Re-render LaTeX
            renderLatex(answerContent);
            
            // Re-attach pill listeners if any
            attachPillEventListeners(answerContent);
        }
        currentData.summaryViewMode = 'technical';
    }
    
    updateSimplifiedButtonLabel();
}

function updateSimplifiedButtonLabel() {
    const button = document.querySelector('.simplified-summary-btn');
    if (!button) return;
    
    const textSpan = button.querySelector('.simplified-text');
    if (!textSpan) return;
    
    if (currentData.summaryViewMode === 'simplified') {
        textSpan.textContent = 'Technical';
        button.title = 'Show technical summary';
    } else {
        textSpan.textContent = 'Simplified';
        button.title = 'Show simplified summary';
    }
}

//--------------------
//  PLOT QUERY LISTENERS
//--------------------

function attachPlotQueryListeners(element) {
    // Handle expand button clicks
    element.querySelectorAll('.plot-expand-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const plotContainer = e.target.closest('.plot-container');
            if (plotContainer) openPlotFullscreen(plotContainer);
        });
    });

    // Handle query button clicks
    element.querySelectorAll('.plot-query-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const plotContainer = e.target.closest('.plot-container');
            if (!plotContainer) return;
            
            const queryForm = plotContainer.querySelector('.plot-query-form');
            if (!queryForm) return;

            queryForm.style.display = queryForm.style.display === 'none' ? 'flex' : 'none';
            
            if (queryForm.style.display === 'flex') {
                const queryInput = queryForm.querySelector('.plot-query-input');
                if (queryInput) queryInput.focus();
            }
        });
    });

    // Handle form submissions
    element.querySelectorAll('.plot-query-form').forEach(form => {
        const submitQuery = async (e) => {
            e.preventDefault();
        
            const plotContainer = e.target.closest('.plot-container');
            if (!plotContainer) return;
        
            const queryInput = e.target.closest('.plot-query-form').querySelector('.plot-query-input');
            if (!queryInput || !queryInput.value.trim()) return;
        
            let imageData;
            const plotImage = plotContainer.querySelector('.plot-image');
            if (plotImage) {
                imageData = plotImage.src.split(',')[1];
            } else {
                const plotlyDiv = plotContainer.querySelector('.plotly-plot div');
                if (plotlyDiv) {
                    try {
                        const imgSrc = await Plotly.toImage(plotlyDiv, {format: 'png'});
                        imageData = imgSrc.split(',')[1];
                    } catch (err) {
                        console.error('Error converting Plotly plot to image:', err);
                        return;
                    }
                }
            }
        
            if (!imageData) return;
        
            // Set query into main input and delegate
            const mainInput = document.getElementById('queryInput');
            mainInput.value = queryInput.value;
            handleQuerySubmit({ image: imageData });
        
            // Clean up plot form
            form.style.display = 'none';
            queryInput.value = '';
        };

        // Add click handler to submit button
        const submitButton = form.querySelector('.plot-query-submit');
        if (submitButton) {
            submitButton.addEventListener('click', submitQuery);
        }

        // Handle form submit event
        form.addEventListener('submit', submitQuery);

        // Handle enter key in input
        const queryInput = form.querySelector('.plot-query-input');
        if (queryInput) {
            queryInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    submitQuery(e);
                }
            });
        }
    });
}

//--------------------
//  PLOT FULLSCREEN
//--------------------

let fullscreenSourceContainer = null;

function initializePlotFullscreenModal() {
    const modalHtml = `
    <div id="plotFullscreenModal" class="plot-fullscreen-modal">
        <div class="plot-fullscreen-header">
            <h3 id="plotFullscreenTitle"></h3>
            <button id="plotFullscreenClose" class="plot-fullscreen-close" aria-label="Close fullscreen">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        <div id="plotFullscreenBody" class="plot-fullscreen-body"></div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    document.getElementById('plotFullscreenClose')
        .addEventListener('click', closePlotFullscreen);

    // Click on backdrop (the modal itself, not its children) to close
    document.getElementById('plotFullscreenModal')
        .addEventListener('click', (e) => {
            if (e.target.id === 'plotFullscreenModal') closePlotFullscreen();
        });

    // Escape key — only when this modal is open
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('plotFullscreenModal');
            if (modal && modal.classList.contains('visible')) {
                closePlotFullscreen();
            }
        }
    });
}

function openPlotFullscreen(plotContainer) {
    const modal = document.getElementById('plotFullscreenModal');
    const body  = document.getElementById('plotFullscreenBody');
    const title = document.getElementById('plotFullscreenTitle');

    const plotId  = plotContainer.dataset.plotId;
    const plotNum = plotId ? plotId.split('_')[1] : '';
    title.textContent = `Plot ${plotNum}`;

    body.innerHTML = '';
    fullscreenSourceContainer = plotContainer;

    // ── Plotly (interactive) ──────────────────────────────
    const plotlyDiv = plotContainer.querySelector('.js-plotly-plot');
    if (plotlyDiv && plotlyDiv.data) {
        const fsDiv = document.createElement('div');
        fsDiv.id = 'plotFullscreenPlotly';
        body.appendChild(fsDiv);

        const layout = Object.assign({}, plotlyDiv.layout, {
            autosize: true,
            width:  undefined,
            height: undefined,
            dragmode: 'pan'                 // CHANGED: enable pan
        });

        modal.classList.add('visible');

        requestAnimationFrame(() => {
            Plotly.newPlot(fsDiv, plotlyDiv.data, layout, {
                responsive: true,
                displayModeBar: true,
                scrollZoom: true            // CHANGED: enable scroll zoom
            });
        });
        return;
    }

    // ── Static PNG ────────────────────────────────────────
    const plotImage = plotContainer.querySelector('.plot-image');
    if (plotImage) {
        body.innerHTML = `<img src="${plotImage.src}" alt="Plot ${plotNum}" class="plot-fullscreen-image">`;
    }

    modal.classList.add('visible');
}

function closePlotFullscreen() {
    const modal = document.getElementById('plotFullscreenModal');
    const body  = document.getElementById('plotFullscreenBody');

    // Clean up any Plotly instance to free memory
    const fsPlot = document.getElementById('plotFullscreenPlotly');
    if (fsPlot) {
        try { Plotly.purge(fsPlot); } catch (_) { /* ignore */ }
    }

    body.innerHTML = '';
    modal.classList.remove('visible');
    fullscreenSourceContainer = null;
}

//--------------------
//  SYNTHESIS INFOGRAPHIC
//--------------------

function appendSynthesisImage(imageBase64, mimeType) {
    const answerTab = document.getElementById('content-answer');
    if (!answerTab) {
        // Answer tab not ready yet, retry
        setTimeout(() => appendSynthesisImage(imageBase64, mimeType), 200);
        return;
    }
    
    // Don't add duplicate
    if (answerTab.querySelector('.synthesis-infographic-container')) return;
    
    const container = document.createElement('div');
    container.className = 'synthesis-infographic-container';
    container.innerHTML = `
        <div class="synthesis-infographic-header">
            <h3>Exploration Map (Beta)</h3>
            <div class="synthesis-infographic-actions">
                <button class="plot-expand-btn synthesis-expand-btn" aria-label="Expand infographic" title="Full screen">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="15 3 21 3 21 9"/>
                        <polyline points="9 21 3 21 3 15"/>
                        <line x1="21" y1="3" x2="14" y2="10"/>
                        <line x1="3" y1="21" x2="10" y2="14"/>
                    </svg>
                </button>
            </div>
        </div>
        <img src="data:${mimeType};base64,${imageBase64}" 
             alt="Synthesis infographic" 
             class="synthesis-infographic-image">
    `;
    
    answerTab.appendChild(container);
    
    // Attach fullscreen handler
    const expandBtn = container.querySelector('.synthesis-expand-btn');
    if (expandBtn) {
        expandBtn.addEventListener('click', () => {
            openSynthesisFullscreen(imageBase64, mimeType);
        });
    }
}

function openSynthesisFullscreen(imageBase64, mimeType) {
    const modal = document.getElementById('plotFullscreenModal');
    const body  = document.getElementById('plotFullscreenBody');
    const title = document.getElementById('plotFullscreenTitle');
    
    title.textContent = 'Exploration Map';
    body.innerHTML = `<img src="data:${mimeType};base64,${imageBase64}" 
                          alt="Synthesis infographic" 
                          class="plot-fullscreen-image">`;
    
    modal.classList.add('visible');
}