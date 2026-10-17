//--------------------
//  PDF EXPORT MODULE v5 - SIMPLE & RELIABLE
//  Uses browser's native print-to-PDF (most reliable method)
//--------------------

function initializePDFExport() {
    console.log('Initializing PDF export...');
    // Inject print styles
    injectPrintStyles();
}

//--------------------
//  PRINT STYLES
//--------------------

function injectPrintStyles() {
    if (document.getElementById('pdf-print-styles')) return;
    
    const style = document.createElement('style');
    style.id = 'pdf-print-styles';
    style.textContent = `
        @media print {
            /* Hide everything except print container */
            body * {
                visibility: hidden;
            }
            
            #pdf-print-container,
            #pdf-print-container * {
                visibility: visible;
            }
            
            #pdf-print-container {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
            }
            
            /* Page setup */
            @page {
                size: A4;
                margin: 18mm 15mm 20mm 15mm; /* top, right, bottom, left - extra bottom for footer */
            }
            
            /* Page numbers - works in Chrome/Edge */
            @page {
                @bottom-center {
                    content: counter(page) " of " counter(pages);
                    font-size: 9pt;
                    color: #666;
                }
            }
            
            /* Typography */
            #pdf-print-container {
                font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
                font-size: 10.5pt;
                line-height: 1.6;
                color: #333;
            }
            
            /* Main Title */
            #pdf-print-container h1 {
                font-size: 18pt;
                font-weight: 600;
                color: #1a1a1a;
                margin: 0 0 3mm 0;
                page-break-after: avoid;
                letter-spacing: -0.3px;
            }
            
            /* Section Headers */
            #pdf-print-container h2 {
                font-size: 14pt;
                font-weight: 600;
                color: #2c3e50;
                margin: 8mm 0 4mm 0;
                padding-bottom: 2mm;
                border-bottom: 0.5pt solid #c8e6c9;  /* Light green underline */
                page-break-after: avoid;
            }
            
            #pdf-print-container h3 {
                font-size: 12pt;
                font-weight: 600;
                color: #34495e;
                margin: 6mm 0 3mm 0;
                page-break-after: avoid;
            }
            
            #pdf-print-container h4 {
                font-size: 11pt;
                font-weight: 600;
                color: #445566;
                margin: 4mm 0 2mm 0;
                page-break-after: avoid;
            }
            
            #pdf-print-container p {
                margin: 0 0 3mm 0;
                orphans: 3;
                widows: 3;
                text-align: left;
            }
            
            /* Header Styling */
            #pdf-print-container .pdf-header {
                border-bottom: 2pt solid #4a9d5b;  /* Muted green accent */
                padding-bottom: 4mm;
                margin-bottom: 6mm;
            }
            
            #pdf-print-container .pdf-header h1 {
                color: #2c3e50;
                margin-bottom: 2mm;
            }
            
            #pdf-print-container .pdf-timestamp {
                font-size: 9pt;
                color: #7f8c8d;
                font-style: italic;
            }

            /* The top section (2026-10-17): a kicker, the title that says what was found, the lead, then what the report
               stands on - the question as asked (whole), the data, when and how it was prepared - for a reader who has
               never seen the app */
            #pdf-print-container .pdf-kicker {
                font-size: 8.5pt;
                letter-spacing: 0.6px;
                text-transform: uppercase;
                color: #4a9d5b;
                margin: 0 0 2mm 0;
            }
            #pdf-print-container .pdf-lead {
                font-size: 11.5pt;
                line-height: 1.5;
                color: #2c3e50;
                margin: 0 0 4mm 0;
            }
            #pdf-print-container .pdf-meta {
                font-size: 9pt;
                line-height: 1.5;
                color: #555;
                border-top: 0.5pt solid #c8e6c9;
                padding-top: 2.5mm;
            }
            #pdf-print-container .pdf-meta div { margin: 0 0 1mm 0; }
            #pdf-print-container .pdf-meta b { color: #2c3e50; font-weight: 600; margin-right: 1.5mm; }
            
            /* Tables - Professional Styling */
            #pdf-print-container table {
                width: 100%;
                border-collapse: collapse;
                margin: 5mm 0;
                font-size: 9pt;
                page-break-inside: auto;
                border: 0.5pt solid #bdc3c7;
            }
            
            #pdf-print-container thead {
                display: table-header-group; /* Repeat headers on new pages */
            }
            
            #pdf-print-container tbody {
                display: table-row-group;
            }
            
            #pdf-print-container tr {
                page-break-inside: avoid;
            }
            
            #pdf-print-container th,
            #pdf-print-container td {
                border: 0.5pt solid #bdc3c7;
                padding: 2.5mm 3mm;
                text-align: left;
                word-wrap: break-word;
                vertical-align: top;
            }
            
            #pdf-print-container th {
                background-color: #4a9d5b !important;  /* Muted green */
                color: #ffffff !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                font-weight: 600;
                font-size: 9pt;
                text-transform: none;
            }
            
            /* Zebra striping for table rows */
            #pdf-print-container tbody tr:nth-child(even) {
                background-color: #f8f9fa !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
            
            #pdf-print-container tbody tr:hover {
                background-color: #f1f3f4 !important;
            }
            
            /* Code blocks */
            #pdf-print-container pre {
                background-color: #f8f9fa !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                padding: 3mm;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 9pt;
                white-space: pre-wrap;
                word-wrap: break-word;
                page-break-inside: avoid;
                border: 0.5pt solid #e0e0e0;
                border-left: 3pt solid #4a9d5b;  /* Green accent */
                border-radius: 0 3pt 3pt 0;
                margin: 3mm 0;
            }
            
            /* Inline code - subtle green theme to match app */
            #pdf-print-container code {
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
                font-size: 9pt !important;
                color: #2e7d32 !important;  /* Dark green text */
                background-color: #f1f8e9 !important;  /* Very light green background */
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                padding: 0.5mm 1.5mm !important;
                border-radius: 2pt !important;
                border: 0.5pt solid #c8e6c9 !important;  /* Light green border */
            }
            
            /* Code inside pre blocks - reset the inline code styling */
            #pdf-print-container pre code {
                color: #2c3e50 !important;
                background-color: transparent !important;
                padding: 0 !important;
                border-radius: 0 !important;
                border: none !important;
            }
            
            /* Also catch any spans or other elements that might have code-like classes */
            #pdf-print-container .hljs,
            #pdf-print-container [class*="code"],
            #pdf-print-container [class*="mono"] {
                color: #2e7d32 !important;
            }
            
            /* Lists */
            #pdf-print-container ul,
            #pdf-print-container ol {
                margin: 2mm 0 4mm 0;
                padding-left: 7mm;
            }
            
            #pdf-print-container li {
                margin-bottom: 1.5mm;
                line-height: 1.5;
            }
            
            #pdf-print-container li::marker {
                color: #4a9d5b;  /* Green bullets */
            }
            
            /* Nested lists */
            #pdf-print-container li ul,
            #pdf-print-container li ol {
                margin-top: 1mm;
                margin-bottom: 1mm;
            }
            
            /* Images */
            #pdf-print-container img {
                max-width: 100%;
                height: auto;
                page-break-inside: avoid;
            }
            
            /* Charts container */
            #pdf-print-container .pdf-chart {
                page-break-inside: avoid;
                margin: 5mm 0;
                border: 0.5pt solid #e0e0e0;
                border-radius: 3pt;
                padding: 3mm;
                background-color: #fff;
            }
            
            #pdf-print-container .pdf-chart img {
                width: 100%;
                height: auto;
            }
            
            /* Visualizations section header */
            #pdf-print-container .pdf-charts-section h2 {
                color: #2c3e50;
                border-bottom: 2pt solid #4a9d5b;  /* Green accent */
                padding-bottom: 2mm;
                margin-top: 8mm;
            }
            
            /* Math/KaTeX */
            #pdf-print-container .katex,
            #pdf-print-container .MathJax,
            #pdf-print-container mjx-container {
                page-break-inside: avoid;
            }
            
            /* Blockquotes - professional callout style */
            #pdf-print-container blockquote {
                border-left: 3pt solid #4a9d5b;  /* Green accent */
                padding: 2mm 4mm;
                margin: 3mm 0;
                background-color: #f8f9fa !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                page-break-inside: avoid;
                font-style: italic;
                color: #555;
            }
            
            /* Links */
            #pdf-print-container a {
                color: #2980b9;
                text-decoration: none;
            }
            
            /* Horizontal rules */
            #pdf-print-container hr {
                border: none;
                border-top: 0.5pt solid #e0e0e0;
                margin: 5mm 0;
            }
            
            /* Strong/Bold text */
            #pdf-print-container strong,
            #pdf-print-container b {
                font-weight: 600;
                color: #1a1a1a;
            }
            
            /* Footer branding */
            #pdf-print-container .pdf-footer {
                margin-top: 8mm;
                padding-top: 3mm;
                border-top: 0.5pt solid #e0e0e0;
                font-size: 8pt;
                color: #95a5a6;
                text-align: center;
            }
        }
    `;
    document.head.appendChild(style);
}

//--------------------
//  PDF EXPORT BUTTON
//--------------------

function addPDFExportButton(answerTabContent) {
    if (answerTabContent.querySelector('.pdf-export-btn')) return;
    const header = answerTabContent.querySelector('h3');
    if (!header) return;
    if (!header.parentElement.classList.contains('tab-header-container')) {
        const headerContainer = document.createElement('div');
        headerContainer.className = 'tab-header-container';
        header.parentElement.insertBefore(headerContainer, header);
        headerContainer.appendChild(header);
    }
    const headerContainer = header.parentElement;
    const pdfButton = createPDFButton();
    headerContainer.appendChild(pdfButton);
}

function createPDFButton() {
    const button = document.createElement('button');
    button.className = 'pdf-export-btn';
    button.title = 'Export to PDF';
    button.setAttribute('aria-label', 'Export to PDF');
    button.innerHTML = `
        <svg class="pdf-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14,2 14,8 20,8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10,9 9,9 8,9"></polyline>
        </svg>
        <span class="pdf-text">PDF</span>
    `;
    button.addEventListener('click', handlePDFExport);
    return button;
}

//--------------------
//  CONTENT EXTRACTION
//--------------------

// The top section of the export (2026-10-17). Before, the title was the question cut at 200 characters and the subtitle a
// timestamp - truncated, and nothing for a reader who had never seen the app. The head comes with the answer and is kept
// with the chain: the title and lead the analyst wrote for the finished report, and the question as the analyst understood
// it - its own statement of what it answered, in context, so a follow-up ('Extend to 45 terms') reads whole without the
// thread - then what data the report stands on, the day, the mode and the replay's verdict. Without a head (an older chain,
// a rewrite without the lines) the question as typed is the title.
function pdfHeadModel(data, now) {
    const d = data || {};
    const head = d.reportHead || {};
    const question = String(head.question || (d.queryText && d.queryText !== 'No query' ? d.queryText : '') || '').trim();
    const title = String(head.title || '').trim() || question || 'Analysis report';
    const lead = String(head.lead || '').trim();
    const rows = [];
    if (question && title !== question) rows.push(['Question', question]);
    if (head.data) rows.push(['Data', String(head.data)]);
    const when = now || new Date();
    const day = when.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
    const prepared = [day + ' with BambooAI'];
    if (head.mode) prepared.push(String(head.mode).charAt(0).toUpperCase() + String(head.mode).slice(1) + ' mode');
    if (head.replay === 'reproduced') prepared.push('every number re-computed from the recorded cells and reproduced');
    else if (head.replay === 'differed') prepared.push('the re-computation differed from the report - read the CHECK lines');
    if (d.summaryViewMode === 'simplified') prepared.push('plain-language version');
    rows.push(['Prepared', prepared.join(' · ')]);
    return { kicker: 'Analysis report', title, lead, rows };
}

// the file name the browser offers for the PDF: the title, without the characters a file name cannot carry, at most 120
function pdfFileTitle(title) {
    return String(title || '').replace(/[\\/:*?"<>|\n\r]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120);
}

function renderPdfHead(model) {
    const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    return '<div class="pdf-kicker">' + esc(model.kicker) + '</div>' +
           '<h1>' + esc(model.title) + '</h1>' +
           (model.lead ? '<p class="pdf-lead">' + esc(model.lead) + '</p>' : '') +
           '<div class="pdf-meta">' + model.rows.map(r => '<div><b>' + esc(r[0]) + '</b>' + esc(r[1]) + '</div>').join('') + '</div>';
}
if (typeof module !== 'undefined' && module.exports) { module.exports.pdfHeadModel = pdfHeadModel; module.exports.renderPdfHead = renderPdfHead; module.exports.pdfFileTitle = pdfFileTitle; }

function extractQueryHeader() {
    // kept for callers: the title of the export, as the head model gives it
    try { return pdfHeadModel(typeof currentData !== 'undefined' ? currentData : null).title; } catch (e) { return 'Analysis report'; }
}

function extractAnswerContent() {
    const answerTab = document.getElementById('content-answer');
    if (!answerTab) return null;
    const markdownContent = answerTab.querySelector('.markdown-content');
    return markdownContent;
}

function extractPlotData() {
    const plotTab = document.getElementById('content-plot');
    if (!plotTab) return [];
    
    const plots = [];
    const plotContainers = plotTab.querySelectorAll('.plot-container');
    
    plotContainers.forEach((container, index) => {
        const plotId = container.getAttribute('data-plot-id') || `plot_${index + 1}`;
        const plotlyDiv = container.querySelector('.js-plotly-plot') || 
                          container.querySelector('[class*="plotly"]');
        
        if (plotlyDiv && plotlyDiv._fullData) {
            plots.push({ type: 'plotly', element: plotlyDiv, id: plotId });
            return;
        }
        
        const plotImage = container.querySelector('.plot-image, img');
        if (plotImage && plotImage.src) {
            plots.push({ type: 'image', element: plotImage, id: plotId });
        }
    });
    
    return plots;
}

//--------------------
//  PDF GENERATION
//--------------------

async function handlePDFExport(event) {
    const button = event.target.closest('.pdf-export-btn');
    
    try {
        showPDFLoadingState(button, true);
        
        // Get content
        const headModel = pdfHeadModel(typeof currentData !== 'undefined' ? currentData : null);
        const answerContent = extractAnswerContent();
        const plots = extractPlotData();
        
        if (!answerContent) {
            throw new Error('No content to export');
        }
        
        // Pre-capture Plotly charts as images
        const chartImages = [];
        for (const plot of plots) {
            if (plot.type === 'plotly' && plot.element && plot.element._fullData && typeof Plotly !== 'undefined') {
                try {
                    const imgData = await Plotly.toImage(plot.element, {
                        format: 'png',
                        width: 900,
                        height: 500,
                        scale: 2
                    });
                    chartImages.push({ id: plot.id, data: imgData });
                } catch (e) {
                    console.warn('Failed to capture chart:', e);
                }
            } else if (plot.type === 'image' && plot.element) {
                chartImages.push({ id: plot.id, data: plot.element.src });
            }
        }
        
        // Build print container
        const printContainer = document.createElement('div');
        printContainer.id = 'pdf-print-container';
        
        // the top section (2026-10-17): the head the analyst wrote, the question whole, the data, the day
        const headerDiv = document.createElement('div');
        headerDiv.className = 'pdf-header';
        headerDiv.innerHTML = renderPdfHead(headModel);
        printContainer.appendChild(headerDiv);
        
        // Clone and add content
        const contentClone = answerContent.cloneNode(true);
        
        // Remove buttons and interactive elements
        contentClone.querySelectorAll('button, .copy-btn, .pdf-export-btn, script').forEach(el => el.remove());
        
        // Force style inline code elements for reliable printing
        contentClone.querySelectorAll('code').forEach(codeEl => {
            // Skip code inside pre blocks
            if (codeEl.parentElement && codeEl.parentElement.tagName === 'PRE') {
                return;
            }
            // Apply inline styles - subtle green theme to match app
            codeEl.style.cssText = `
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
                font-size: 9pt !important;
                color: #2e7d32 !important;
                background-color: #f1f8e9 !important;
                padding: 0.5mm 1.5mm !important;
                border-radius: 2pt !important;
                border: 0.5pt solid #c8e6c9 !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            `;
        });
        
        // Force style table headers for better readability (green header)
        contentClone.querySelectorAll('th').forEach(th => {
            th.style.cssText = `
                background-color: #4a9d5b !important;
                color: #ffffff !important;
                font-weight: 600 !important;
                border: 0.5pt solid #bdc3c7 !important;
                padding: 2.5mm 3mm !important;
                text-align: left !important;
                font-size: 9pt !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            `;
        });
        
        // Add zebra striping to table rows
        contentClone.querySelectorAll('tbody tr:nth-child(even)').forEach(tr => {
            tr.style.cssText = `
                background-color: #f8f9fa !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            `;
        });
        
        // Style table cells
        contentClone.querySelectorAll('td').forEach(td => {
            td.style.cssText = `
                border: 0.5pt solid #bdc3c7 !important;
                padding: 2.5mm 3mm !important;
                vertical-align: top !important;
            `;
        });
        
        // Style pre/code blocks
        contentClone.querySelectorAll('pre').forEach(pre => {
            pre.style.cssText = `
                background-color: #f8f9fa !important;
                padding: 3mm !important;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
                font-size: 9pt !important;
                white-space: pre-wrap !important;
                word-wrap: break-word !important;
                border: 0.5pt solid #e0e0e0 !important;
                border-left: 3pt solid #4a9d5b !important;
                border-radius: 0 3pt 3pt 0 !important;
                margin: 3mm 0 !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            `;
        });
        
        printContainer.appendChild(contentClone);
        
        // Add synthesis infographic if present
        if (currentData.synthesisImage) {
            const infraSection = document.createElement('div');
            infraSection.className = 'pdf-chart';
            infraSection.innerHTML = `
                <img src="data:${currentData.synthesisImage.mime_type};base64,${currentData.synthesisImage.data}" 
                     alt="Synthesis infographic"
                     style="width: 100%; height: auto;">
            `;
            printContainer.appendChild(infraSection);
        }
        
        // Add charts
        if (chartImages.length > 0) {
            const chartsSection = document.createElement('div');
            chartsSection.className = 'pdf-charts-section';
            chartsSection.innerHTML = '<h2>Visualizations</h2>';
            
            chartImages.forEach((chart, index) => {
                const chartDiv = document.createElement('div');
                chartDiv.className = 'pdf-chart';
                chartDiv.innerHTML = `
                    <img src="${chart.data}" alt="${chart.id}">
                `;
                chartsSection.appendChild(chartDiv);
            });
            
            printContainer.appendChild(chartsSection);
        }
        
        // Add footer
        const footer = document.createElement('div');
        footer.className = 'pdf-footer';
        footer.innerHTML = 'Generated by BambooAI';
        printContainer.appendChild(footer);
        
        // Add to document
        document.body.appendChild(printContainer);
        
        // Wait a moment for rendering
        await new Promise(r => setTimeout(r, 100));
        
        // Trigger print - the page's title is the file name the browser offers (2026-10-17): the report's title, not the app's
        const pageTitle = document.title;
        document.title = pdfFileTitle(headModel.title) || pageTitle;
        window.print();
        
        // Clean up after print dialog closes
        setTimeout(() => {
            document.title = pageTitle;
            if (document.getElementById('pdf-print-container')) {
                document.body.removeChild(printContainer);
            }
            showPDFLoadingState(button, false);
        }, 1000);
        
    } catch (error) {
        console.error('PDF export error:', error);
        showPDFLoadingState(button, false);
        alert('Error exporting PDF: ' + error.message);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showPDFLoadingState(button, isLoading) {
    if (!button) return;
    if (isLoading) {
        button.disabled = true;
        button.classList.add('loading');
        button.innerHTML = `<div class="pdf-spinner"></div>`;
        button.title = 'Generating PDF...';
    } else {
        button.disabled = false;
        button.classList.remove('loading');
        button.innerHTML = `
            <svg class="pdf-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14,2 14,8 20,8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10,9 9,9 8,9"></polyline>
            </svg>
            <span class="pdf-text">PDF</span>
        `;
        button.title = 'Export to PDF';
    }
}

//--------------------
//  INTEGRATION
//--------------------

function handleAnswerTabUpdate() {
    setTimeout(() => {
        const answerTab = document.getElementById('content-answer');
        if (answerTab) {
            addPDFExportButton(answerTab);
            addSimplifiedSummaryButton(answerTab);
        }
    }, 100);
}

if (typeof document !== 'undefined') {                       // the tests load this file in node for the head model (2026-10-17)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializePDFExport);
    } else {
        initializePDFExport();
    }
}