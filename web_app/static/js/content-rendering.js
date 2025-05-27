//--------------------
//  CONTENT RENDERING MODULE
//--------------------

function initializeContentRendering() {
    console.log('Initializing content rendering...');
    
    initializeSelectionPopup();
    initializeTextSelection();
    
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
    const selection = window.getSelection();
    selectedText = selection.toString().trim();
    
    if (selectedText) {
        currentRange = selection.getRangeAt(0).cloneRange();
        console.log('New selection made:', selectedText);
        
        createHighlightOverlay(currentRange);
        showPopupAtPosition(e.clientX, e.clientY);
        const selectionQuery = document.getElementById('selectionQuery');
        if (selectionQuery) {
            selectionQuery.value = '';
            selectionQuery.focus();
        }
    }
}

function handleClickOutside(e) {
    if (e.target.closest('#content-plot')) return;
    if (e.target.closest('#selectionForm') || e.target.closest('#selectionRunButton')) return;
    
    const selectionPopup = document.getElementById('selectionPopup');
    if (!selectionPopup.contains(e.target) && e.target !== selectionPopup) {
        selectionPopup.style.display = 'none';
        removeHighlights();
        currentRange = null;
        selectedText = '';
    }
}

function createHighlightOverlay(range) {
    removeHighlights();

    const rects = range.getClientRects();
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;

    for (const rect of rects) {
        const highlight = document.createElement('div');
        highlight.className = 'highlight-overlay';
        highlight.style.left = (rect.left + scrollX) + 'px';
        highlight.style.top = (rect.top + scrollY) + 'px';
        highlight.style.width = rect.width + 'px';
        highlight.style.height = rect.height + 'px';
        document.body.appendChild(highlight);
        highlightElements.push(highlight);
    }
}

function removeHighlights() {
    highlightElements.forEach(element => {
        if (element.parentNode) {
            element.parentNode.removeChild(element);
        }
    });
    highlightElements = [];
}

function showPopupAtPosition(x, y) {
    const selectionPopup = document.getElementById('selectionPopup');
    
    selectionPopup.style.display = 'block';
    
    // Position popup near but not directly under the mouse
    const popupX = x + 10;
    const popupY = y + 10;
    
    // Keep popup within viewport bounds
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const popupWidth = selectionPopup.offsetWidth;
    const popupHeight = selectionPopup.offsetHeight;
    
    const finalX = Math.min(popupX, viewportWidth - popupWidth - 10);
    const finalY = Math.min(popupY, viewportHeight - popupHeight - 10);
    
    selectionPopup.style.left = finalX + 'px';
    selectionPopup.style.top = finalY + 'px';
}

function handleScroll() {
    if (selectedText && currentRange) {
        createHighlightOverlay(currentRange);
    } else {
        removeHighlights();
    }
}

async function handleQuerySubmission(e) {
    if (e) {
        e.preventDefault();
    }
    
    const selectionQuery = document.getElementById('selectionQuery');
    const query = selectionQuery.value.trim();
    console.log('Query value:', query);
    console.log('Selected text at submission:', selectedText);
    
    if (!query || !selectedText) {
        console.log('Missing query or selection:', { query, selectedText });
        return;
    }
    
    const queryWithContext = `${query}\n**Task Context:**\n${selectedText}`;
    
    try {
        console.log('Sending fetch request...');
        const response = await fetch('/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: queryWithContext,
                chain_id: currentData.chain_id,
                thread_id: currentData.thread_id
            }),
        });
        
        if (!response.ok) {
            throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
        }
        
        // Only clear UI elements after successful submission start
        const selectionPopup = document.getElementById('selectionPopup');
        selectionPopup.style.display = 'none';
        removeHighlights();
        
        // Handle streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        // Clear previous output
        const streamOutputDiv = document.getElementById('streamOutput');
        if (streamOutputDiv) {
            streamOutputDiv.innerHTML = '';
            clearAllTabs();
        } else {
            console.error('streamOutput div not found');
            return;
        }
        
        // Read and process the stream
        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                console.log('Stream complete');
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
        
        // Clear selection only after successful completion
        currentSelection = null;
        selectedText = '';
        
    } catch (error) {
        console.error('Error in query submission:', error);
        const streamOutputDiv = document.getElementById('streamOutput');
        if (streamOutputDiv) {
            streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
        }
    }
}

//--------------------
//  TAB MANAGEMENT
//--------------------

function createOrUpdateTab(type, data, id = null, format = null) {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    let tab = document.getElementById(`tab-${type}`);
    let tabContent = document.getElementById(`content-${type}`);

    if (!tab) {
        // Create new tab
        tab = document.createElement('div');
        tab.id = `tab-${type}`;
        tab.className = 'tab';
        tab.textContent = type.charAt(0).toUpperCase() + type.slice(1);
        tab.onclick = () => activateTab(type);
        tabContainer.appendChild(tab);

        // Create new tab content
        tabContent = document.createElement('div');
        tabContent.id = `content-${type}`;
        tabContent.className = 'tab-content';
        contentOutput.appendChild(tabContent);
    }

    updateTabContent(type, data, id, format);
    activateTab(type);
}

function activateTab(type) {
    const tabs = document.getElementsByClassName('tab');
    const tabContents = document.getElementsByClassName('tab-content');

    for (let i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove('active');
        tabContents[i].classList.remove('active');
    }

    const activeTab = document.getElementById(`tab-${type}`);
    const activeContent = document.getElementById(`content-${type}`);

    if (activeTab && activeContent) {
        activeTab.classList.add('active');
        activeContent.classList.add('active');
    } else {
        console.warn(`Tab or content for type "${type}" not found`);
    }
}

function clearAllTabs() {
    const tabContainer = document.getElementById('tabContainer');
    const contentOutput = document.getElementById('contentOutput');
    tabContainer.innerHTML = '';
    contentOutput.innerHTML = '';
}

//--------------------
//  CONTENT RENDERING
//--------------------

async function updateTabContent(type, data, id = null, format = null) {
    const tabContent = document.getElementById(`content-${type}`);
    let content = '';

    switch(type) {
        case 'dataframe':
            content = data;
            break;
        case 'query':
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            const yamlData = formatQueryDataAsYAML(data);
            content += '<div class="markdown-content yaml-wrapper">' + marked.parse('```yaml\n' + yamlData + '\n```') + '</div>';
            break;
        case 'plan':
        case 'model': {
            const { html, hasDiagram, mermaidSrc } = buildDiagramTab(type, data);
            tabContent.innerHTML = html;
        
            if (hasDiagram) {
                ensureMermaid();
                const host = tabContent.querySelector('.mermaid');
                mermaid.render(`m-${Date.now()}`, mermaidSrc)
                        .then(({ svg }) => host && (host.innerHTML = svg))
                        .catch(err => console.warn('Mermaid render failed:', err));
            }
        
            // highlight YAML, attach scroll handler, etc.
            tabContent.querySelectorAll('pre code').forEach(hljs.highlightElement);
            tabContent.removeEventListener('scroll', handleScroll);
            tabContent.addEventListener('scroll', handleScroll);
        
            return;
        }
        case 'research':
            // Parse JSON for research data
            let parsedResearchData;
            try {
                parsedResearchData = typeof data === 'string' ? JSON.parse(data) : data;
                if (Array.isArray(parsedResearchData)) {
                    content = formatResearchData(parsedResearchData);
                } else {
                    console.error('Research data is not an array:', parsedResearchData);
                    content = 'Error: Invalid research data format';
                }
            } catch (error) {
                console.error('Error parsing research data:', error);
                content = 'Error: Invalid research data format';
            }
            break;
        case 'review':
        case 'vector_db':
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
            content = `<h3>${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
            
            // First protect LaTeX content
            const { text: protectedContent, placeholders } = protectLatexDelimiters(data);
            
            // Parse markdown
            let parsedContent = marked.parse(protectedContent);
            
            // Process interactive items if needed
            if (answerTabInteractive) {
                // Transform numbered list items into interactive pills
                parsedContent = transformNumberedListToInteractivePills(parsedContent);
                
                // Reset the interactive flag after processing
                answerTabInteractive = false;
            }
            
            // Restore LaTeX content
            const finalContent = restoreLatexDelimiters(parsedContent, placeholders);
            
            // Add the content to the DOM
            content += '<div class="markdown-content">' + finalContent + '</div>';
            
            // Queue LaTeX rendering after content is in DOM
            setTimeout(() => {
                const contentElement = document.querySelector(`#content-${type} .markdown-content`);
                if (contentElement) {
                    renderLatex(contentElement);
                    
                    // Add event listeners to the interactive pills if they exist
                    attachPillEventListeners(contentElement);
                }
            }, 100);
            
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
    if (['query', 'model', 'plan', 'code', 'mermaid'].includes(type)) {
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

function renderPlotTab(data, id, format) {
    const baseContainer = `
        <div class="plot-container" data-plot-id="${id}">
            <div class="plot-header">
                <h3>Plot ${id ? id.split('_')[1] : ''}:</h3>
                <button class="plot-query-btn" aria-label="Query plot">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
                    </svg>
                </button>
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
            const container = document.getElementById(`plotly-container-${id}`);
            if (container) {
                container.innerHTML = data;
                const scripts = container.getElementsByTagName('script');
                Array.from(scripts).forEach(script => {
                    if (!script.src) {
                        eval(script.textContent);
                    }
                });
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
            const container = document.getElementById(`plotly-container-${id}`);
            if (container) {
                try {
                    const plotData = JSON.parse(container.dataset.plotlyJson.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"'));
                    Plotly.newPlot(container, plotData.data, plotData.layout, {
                        responsive: true,
                        useResizeHandler: true,
                        displayModeBar: true
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
                <img src="data:image/png;base64,${data}" alt="Plot ${id ? id.split('_')[1] : ''}" class="plot-image">
            </div>
        </div>`;
    }

    return '';
}

function buildDiagramTab(type, data) {
    // normalise + validate
    const mermaidSrc = typeof data?.visualization === 'string'
                       ? data.visualization.trim()
                       : '';
    const hasDiagram =
          mermaidSrc !== '' && !/\[object Object\]/.test(mermaidSrc);
  
    // YAML is required; fall back to stringified object
    const yamlBlock = data?.yaml ??
                      (typeof data === 'string'
                        ? data
                        : JSON.stringify(data, null, 2));
  
    // header (Plan: / Model:)
    let html = `<h3>${type[0].toUpperCase() + type.slice(1)}:</h3>`;
  
    // diagram or notice
    if (hasDiagram) {
      html += `
        <div class="diagram-container">
          <button class="view-toggle" title="Toggle syntax">
            <svg class="code-icon" width="16" height="16" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
          </button>
  
          <div class="mermaid-view"><div class="mermaid">${mermaidSrc}</div></div>
  
          <div class="syntax-view" hidden>
            <div class="code-header">
              <span class="language-label">MERMAID</span>
              <button class="copy-button" title="Copy code">
                <svg class="copy-icon" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <svg class="check-icon" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" style="display:none">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </button>
            </div>
            <pre><code>${mermaidSrc}</code></pre>
          </div>
        </div>`;
    } else {
      html += `
        <p class="size-error-notice">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path fill="none" stroke="currentColor" stroke-linecap="round"
                  stroke-linejoin="round" stroke-width="2"
                  d="M12 9v2m0 4h.01M5.062 19h13.876c1.54 0 2.502-1.667
                  1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16
                  c-.77 1.333.192 3 1.722 3z"/>
          </svg>
          Diagram visualisation not available – YAML shown below.
        </p>`;
    }
  
    // YAML section
    html += `<div class="markdown-content">${
        marked.parse(`\`\`\`yaml\n${yamlBlock}\n\`\`\``)
    }</div>`;
  
    return { html, hasDiagram, mermaidSrc };
}

//--------------------
//  DATA FORMATTERS
//--------------------

function formatQueryDataAsYAML(data) {
    const yaml = `
original_question: 
"${data.original_question}"

rephrased_question:
  unknown: "${data.unknown}"
  condition: "${data.condition}"

intent_breakdown: "${data.intent_breakdown}"

confidence: ${data.confidence}
requires_dataset: ${data.requires_dataset}
expert: "${data.expert || 'undefined'}"
`;
    return yaml.trim();
}

function formatResearchData(researchData) {
    if (!Array.isArray(researchData)) {
        console.error('Research data is not an array:', researchData);
        return 'Error: Invalid research data format';
    }

    let formattedContent = '<div class="research-container">';
    researchData.forEach(item => {
        formattedContent += `
            <div class="research-item">
                <h2 class="research-query">${escapeHtml(item.query)}</h2>
                <div class="research-result markdown-content">${marked.parse(escapeHtml(item.result))}</div>
                <h3 class="links-header">Sources</h3>
                <ul class="links-list">
                    ${item.links.map(link => `
                        <li class="link-item">
                            <a href="${escapeHtml(link.link)}" target="_blank" rel="noopener noreferrer" class="link-title">
                                ${escapeHtml(link.title)}
                            </a>
                            <span class="link-url">${escapeHtml(link.link)}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    });
    formattedContent += '</div>';
    return formattedContent;
}

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
        pill.addEventListener('click', function() {
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
    const tabContent = document.getElementById('content-code');
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

        try {
            // Clear existing plots before execution
            const plotTab = document.getElementById('content-plot');
            if (plotTab) {
                plotTab.innerHTML = '';
            }

            const response = await fetch('/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: null,
                    chain_id: currentData.chain_id,
                    thread_id: currentData.thread_id,
                    user_code: currentCode
                }),
            });
            
            if (!response.ok) throw new Error('Failed to execute code');
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const {done, value} = await reader.read();
                if (done) break;
                if (typeof processChunk === 'function') {
                    processChunk(decoder.decode(value));
                }
            }

            // Replace the current local storage response at its current index
            responses[currentResponseIndex] = {
                tabContent: document.getElementById('tabContainer').innerHTML,
                contentOutput: document.getElementById('contentOutput').innerHTML,
                streamOutput: document.getElementById('streamOutput').innerHTML,
                chain_id: currentData.chain_id,
                thread_id: currentData.thread_id
            };

            // Update localStorage
            await localforage.setItem('responses', responses);
        } catch (error) {
            console.error('Error executing code:', error);
        }
    });
}

//--------------------
//  PLOT QUERY LISTENERS
//--------------------

function attachPlotQueryListeners(element) {
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
                // Regular PNG plot
                imageData = plotImage.src.split(',')[1];
            } else {
                // Check for Plotly plot
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
            
            const streamOutputDiv = document.getElementById('streamOutput');
            if (!streamOutputDiv) return;
            
            try {
                // Clear previous output
                streamOutputDiv.innerHTML = '';
                clearAllTabs();

                const response = await fetch('/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: queryInput.value,
                        image: imageData,
                        chain_id: currentData.chain_id,
                        thread_id: currentData.thread_id
                    }),
                });

                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                }

                // Handle streaming response
                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                // Process the stream
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) {
                        console.log('Stream complete');
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

                // Hide the query form and reset input after successful submission
                form.style.display = 'none';
                queryInput.value = '';

            } catch (error) {
                console.error('Error in plot query submission:', error);
                streamOutputDiv.innerHTML += `<div class="error">Error: ${error.message}</div>`;
            }
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