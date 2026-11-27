//--------------------
//  CONTENT RENDERING MODULE
//--------------------

function initializeContentRendering() {
    console.log('Initializing content rendering...');

    initializePlotFullscreenModal();

    console.log('Content rendering initialized');
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
            tabName = answerTabSynthesis ? 'Synthesis' : 'Answer';
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
        } else if (type === 'comparison') {
            tabName = 'Trend';             // a routine's run against the one before, and the line over the units (docs/ROUTINES_DESIGN.md §14.6, 2026-11-06)
        } else {
            tabName = type.charAt(0).toUpperCase() + type.slice(1);
        }
        tab.textContent = tabName;

        tab.onclick = () => (typeof activateTabInView === 'function' ? activateTabInView(type) : activateTab(type));
        if (type === 'comparison' && tabContainer.firstChild) tabContainer.insertBefore(tab, tabContainer.firstChild);   // a routine's run opens on its comparison (2026-10-10)
        else tabContainer.appendChild(tab);

        // Create new tab content
        tabContent = document.createElement('div');
        tabContent.id = `content-${type}`;
        tabContent.className = 'tab-content';
        contentOutput.appendChild(tabContent);
    }
    if (type === 'answer') tab.textContent = answerTabSynthesis ? 'Synthesis' : 'Answer';   // the label follows the kind of answer (2026-09-08)

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
        // a Plotly figure drawn while its tab was hidden took Plotly's default width (2026-10-13: every run opened on a
        // plot filling half the tab); shown now, it is sized to the tab, as liveComeBack does when the view returns
        if (window.Plotly) activeContent.querySelectorAll('.js-plotly-plot').forEach(el => { try { Plotly.Plots.resize(el); } catch (e) { /* a static copy of a plot, not a live one */ } });
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
                            // graph viewer (graphControls.js).
                        }
                    })
                    .catch(function (err) {
                        console.warn('Mermaid render failed:', err);
                    });
            }
        
            tabContent.querySelectorAll('pre code').forEach(hljs.highlightElement);
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
        
            // The default 'Answer:' label is gone (user ruling
            // 2026-08-29), but the heading ELEMENT stays, empty: the PDF
            // and Simplified buttons anchor to the tab's first h3, and
            // removing it outright sent them to the first markdown
            // heading mid-page. The Synthesis label stays as it was.
            content = answerTabSynthesis ? '<h3>Synthesis:</h3>' : '<h3 class="answer-tab-anchor"></h3>';
            
            // The markdown as HTML, its chain ids as links (for a synthesis); then the citation chips - [cell 7], [fig 7],
            // [D1.17] - as part of the HTML itself, so the stored technical answer carries them through toggles and
            // re-renders (stream-pane.js, 2026-10-03)
            let finalContent = markdownToHtml(data, transformChainIdReferences);

            // Reset synthesis flag after processing
            if (answerTabSynthesis) {
                answerTabSynthesis = false;
            }

            // the report's sources (0340): the host sends them with the report's head, as data - the chips in the text and the list
            // under it are drawn from them
            const sources = (currentData.reportHead && currentData.reportHead.sources) || [];
            if (type === 'answer' && typeof paneCiteHtml === 'function') finalContent = paneCiteHtml(finalContent, sources);
            // what the report says against its brief is not the answer's: it goes to the run's Brief tab (architect.js, 0312)
            if (window.ArchitectUI) {
                const cut = window.ArchitectUI.cutAnswer(finalContent);
                finalContent = cut.html;
                window.ArchitectUI.turnedOut(_root, cut.against);
            }
            if (type === 'answer' && typeof paneSourcesHtml === 'function') finalContent += paneSourcesHtml(sources);
            
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
                    
                    // Add event listeners to chain ID references
                    attachChainRefListeners(contentElement);
                    
                    // Add PDF export button and simplified summary button to answer tab
                    if (typeof handleAnswerTabUpdate === 'function') {
                        handleAnswerTabUpdate();
                    }
                }
            }, 100);
            
            break;
        }
        case 'comparison':                                       // a routine's run against the run before (routines.js builds it)
        case 'brief':                                            // the brief a run was started with (architect.js builds it)
            content = String(data == null ? '' : data);
            break;
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
        // a plot is appended to the tab's others - inserted, not written back through innerHTML, which re-parsed the earlier
        // plots into static copies Plotly no longer knew (2026-10-13: they could not be resized or asked about)
        tabContent.insertAdjacentHTML('beforeend', content);
        const added = tabContent.querySelector(`.plot-container[data-plot-id="${id}"]:last-of-type`) || tabContent.lastElementChild;
        if (added) attachPlotQueryListeners(added);
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
    // the chain's script, read or taken away: Copy and the .py download (2026-10-11, docs/ROUTINES_DESIGN.md S10 - Edit
    // and run on this tab is retired: a routine's run is how a chain runs again, and nobody edits scripts here)
    let content = `<h3>Code:</h3>`;
    content += `<div class="markdown-content">
        <div class="code-header">
            <span class="language-label">PYTHON</span>
            <div class="header-actions">
                <button class="code-action-button copy-button" type="button" title="Copy the code">
                    <svg class="copy-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    <svg class="check-icon" style="display: none" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </button>
                <button class="code-action-button download-button" type="button" title="Download as a .py file">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                </button>
            </div>
        </div>
        <pre><code class="language-python">${data}</code></pre>
    </div>`;

    // Add event listeners after content is added to DOM
    setTimeout(() => {
        initializeCodeTab();
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

// Markdown as the page's HTML, its formulas left for KaTeX: what stands between LaTeX delimiters is kept from the
// markdown parser. `then`: what is done to the HTML before the formulas are put back
function markdownToHtml(text, then) {
    const { text: guarded, placeholders } = protectLatexDelimiters(text);
    const html = marked.parse(guarded);
    return restoreLatexDelimiters(typeof then === 'function' ? then(html) : html, placeholders);
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
        ignoredClasses: ['answer-sources'],      // a source's title is text: a pair of $ in it is no formula (0340)
        errorCallback: function(msg) {
            console.warn('KaTeX error:', msg);
        }
    });
}

//--------------------
//  CODE TAB
//--------------------

function initializeCodeTab() {
    const tabContent = ((typeof liveTargets === 'function') ? liveTargets().content : document.getElementById('contentOutput')).querySelector('#content-code');
    if (!tabContent) return;

    const header = tabContent.querySelector('.code-header');
    const copyButton = header.querySelector('.copy-button');
    const downloadButton = header.querySelector('.download-button');
    const codeElement = header.nextElementSibling.querySelector('code');
    const source = codeElement.textContent;      // the script as it was drawn: a note opened in it later (explain.js) is no part of it

    hljs.highlightElement(codeElement);

    copyButton.addEventListener('click', () => {
        navigator.clipboard.writeText(source)
            .then(() => {
                const copyIcon = copyButton.querySelector('.copy-icon');
                const checkIcon = copyButton.querySelector('.check-icon');
                copyIcon.style.display = 'none';
                checkIcon.style.display = 'block';
                setTimeout(() => {
                    copyIcon.style.display = 'block';
                    checkIcon.style.display = 'none';
                }, 2000);
            })
            .catch(err => console.error('Failed to copy:', err));
    });

    downloadButton.addEventListener('click', () => {
        // the script as a file, named after the chain (the question's first words) when there is one
        const words = ((typeof currentData !== 'undefined' && currentData && currentData.queryText) || '').toLowerCase()
            .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').split('_').filter(Boolean).slice(0, 5).join('_');
        const url = URL.createObjectURL(new Blob([source], { type: 'text/x-python' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = (words || 'analysis') + '.py';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
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
            let finalContent = markdownToHtml(currentData.simplifiedAnswer);
            // the figure citations the rewrite keeps become chips, as in the technical answer (2026-10-11)
            const sources = (currentData.reportHead && currentData.reportHead.sources) || [];      // the report's, under both versions (0340)
            if (typeof paneCiteHtml === 'function') finalContent = paneCiteHtml(finalContent, sources);
            if (window.ArchitectUI) finalContent = window.ArchitectUI.cutAnswer(finalContent).html;      // the rewrite keeps the part "Against the brief": not in the answer
            if (typeof paneSourcesHtml === 'function') finalContent += paneSourcesHtml(sources);
            
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