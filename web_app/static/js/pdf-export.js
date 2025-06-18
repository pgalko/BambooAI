//--------------------
//  PDF EXPORT MODULE
//--------------------

function initializePDFExport() {
    console.log('Initializing PDF export...');
    loadPDFDependencies()
        .then(() => console.log('PDF export dependencies loaded'))
        .catch(error => console.error('Failed to load PDF export dependencies:', error));
}

//--------------------
//  LIBRARY LOADING
//--------------------

async function loadPDFDependencies() {
    if (typeof window.jsPDF !== 'undefined' && typeof html2canvas !== 'undefined' && typeof Plotly !== 'undefined') {
        return;
    }
    
    const loadScript = (src) => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) {
            resolve();
            return;
        }
        
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
    
    try {
        if (typeof html2canvas === 'undefined') {
            await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
        }
        if (typeof window.jsPDF === 'undefined') {
            await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
        }
        if (typeof window.Plotly === 'undefined') {
            await loadScript('https://cdn.plot.ly/plotly-latest.min.js');
        }
    } catch (error) {
        console.error('Error loading PDF libraries:', error);
        throw error;
    }
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

function extractReportContent() {
    try {
        return {
            header: extractQueryHeader(),
            answer: extractAnswerContent(),
            plots: extractPlotData()
        };
    } catch (error) {
        console.error('Error extracting report content:', error);
        throw new Error('Failed to extract content for PDF report');
    }
}

function extractQueryHeader() {
    const queryTab = document.getElementById('content-query');
    if (!queryTab) return 'BambooAI Analysis Report';
    const yamlWrapper = queryTab.querySelector('.yaml-wrapper');
    const yamlText = yamlWrapper ? yamlWrapper.textContent : queryTab.textContent;
    if (!yamlText) return 'BambooAI Analysis Report';
    const lines = yamlText.split('\n');
    const fields = {};
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const colonIndex = trimmed.indexOf(':');
        if (colonIndex === -1) continue;
        const key = trimmed.substring(0, colonIndex).trim();
        let value = trimmed.substring(colonIndex + 1).trim();
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        }
        fields[key] = value;
    }
    const preferredFields = ['unknown', 'intent_breakdown', 'original_question', 'condition'];
    for (const field of preferredFields) {
        if (fields[field] && fields[field].toLowerCase() !== 'null' && fields[field].trim() !== '') {
            return fields[field].trim();
        }
    }
    return 'BambooAI Analysis Report';
}

function extractAnswerContent() {
    const answerTab = document.getElementById('content-answer');
    if (!answerTab) throw new Error('No answer content found');
    const markdownContent = answerTab.querySelector('.markdown-content');
    if (!markdownContent) throw new Error('No markdown content found in answer tab');
    return markdownContent;
}

function extractPlotData() {
    const plotTab = document.getElementById('content-plot');
    if (!plotTab) return [];
    const plots = [];
    const plotContainers = plotTab.querySelectorAll('.plot-container');
    plotContainers.forEach((container, index) => {
        const plotId = container.getAttribute('data-plot-id') || `plot_${index + 1}`;
        const plotlyDiv = container.querySelector('.plotly-plot div[id^="plotly-container"]');
        if (plotlyDiv) {
            plots.push({ type: 'plotly', element: plotlyDiv, id: plotId });
            return;
        }
        const plotImage = container.querySelector('.plot-image');
        if (plotImage) {
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
        await loadPDFDependencies();
        const content = extractReportContent();
        // This function is a wrapper that sets up the async process.
        // We add a reference to the button to turn off the loading state in the callback.
        setupPDFGeneration(content, button);
    } catch (error) {
        console.error('Error generating PDF:', error);
        const message = `Error generating PDF: ${error.message}`;
        if (typeof showGenericToast === 'function') {
            showGenericToast(message, 5000, 'error');
        } else {
            alert(message);
        }
        showPDFLoadingState(button, false);
    }
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

function setupPDFGeneration(content, button) {
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF('p', 'mm', 'a4');

    const reportContainer = document.createElement('div');

    const headerHtml = `<h1>${content.header}</h1><div class="timestamp">Generated: ${new Date().toLocaleString()}</div>`;
    const answerClone = content.answer ? content.answer.cloneNode(true) : document.createElement('div');
    
    reportContainer.innerHTML = `<div class="pdf-render-wrapper">${headerHtml}</div>`;
    reportContainer.querySelector('.pdf-render-wrapper').appendChild(answerClone);

    const A4_WIDTH_MM = 210;
    const MARGIN_MM = 15;
    const contentWidth = A4_WIDTH_MM - (MARGIN_MM * 2);

    const options = {
        callback: function (doc) {
            const addPlotsPromise = (content.plots && content.plots.length > 0)
                ? addPlotsToPDF(doc, content.plots, { contentWidth, margin: MARGIN_MM, pageHeight: doc.internal.pageSize.getHeight(), bottomMargin: MARGIN_MM })
                : Promise.resolve(doc);

            addPlotsPromise.then((finalDoc) => {
                const timestamp = new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-');
                const filename = `BambooAI-Report-${timestamp}.pdf`;
                finalDoc.save(filename);
                showPDFLoadingState(button, false);
            });
        },
        margin: MARGIN_MM,
        autoPaging: 'text', // Changed to 'text' with enhanced CSS
        width: contentWidth,
        windowWidth: 800,
    };

    pdf.html(reportContainer, options);
}

async function addPlotsToPDF(pdf, plots, config) {
    if (plots.length === 0) return pdf;
    
    // Don't automatically add a new page - try to use current page first
    // Get current Y position (estimate based on page content)
    let currentY = getCurrentYPosition(pdf, config);
    
    // Add small margin after text content
    const textToPlotMargin = 15;
    currentY += textToPlotMargin;
    
    const plotWidth = config.contentWidth;
    const spaceBetweenPlots = 10;
    const headerHeight = 12;
    const headerMargin = 8;
    let headerAdded = false;

    for (let i = 0; i < plots.length; i++) {
        const plot = plots[i];
        
        // Determine plot height based on plot characteristics
        const plotHeight = calculatePlotHeight(plot, plotWidth);
        
        // Calculate space needed for this plot (including header if not added yet)
        let spaceNeeded = plotHeight;
        if (!headerAdded) {
            spaceNeeded += headerHeight + headerMargin;
        }
        if (i > 0 || headerAdded) {
            spaceNeeded += spaceBetweenPlots;
        }
        
        // Check if we need a new page for this plot
        if (currentY + spaceNeeded > config.pageHeight - config.bottomMargin) {
            pdf.addPage();
            currentY = config.margin;
            headerAdded = false; // Reset header for new page
        }
        
        // Add "Visualisations:" header if not added yet
        if (!headerAdded) {
            pdf.setFontSize(11);
            pdf.setFont('helvetica', 'bold');
            pdf.setTextColor(0, 0, 0);
            pdf.text('Visualisations:', config.margin, currentY);
            currentY += headerHeight + headerMargin;
            headerAdded = true;
        } else if (i > 0) {
            // Add space between plots (but not before the first plot after header)
            currentY += spaceBetweenPlots;
        }
        
        await addSinglePlot(pdf, plot, config.margin, currentY, plotWidth, plotHeight);
        currentY += plotHeight;
    }
    
    return pdf;
}

// Helper function to estimate current Y position after text content
function getCurrentYPosition(pdf, config) {
    // Get the current page number
    const currentPage = pdf.internal.getNumberOfPages();
    const pageHeight = config.pageHeight;
    const margin = config.margin;
    
    // For the first page, estimate based on typical content
    // For subsequent pages, assume they're mostly full
    if (currentPage === 1) {
        // Conservative estimate for first page - assume content takes up 60-70% of page
        // but leave enough room for at least one small plot
        const estimatedY = Math.min(pageHeight * 0.65, pageHeight - 80);
        return Math.max(estimatedY, margin + 50); // At least 50mm from top
    } else {
        // For subsequent pages, assume they're mostly full
        return Math.min(pageHeight * 0.85, pageHeight - 60);
    }
}

function calculatePlotHeight(plot, plotWidth) {
    // Default aspect ratio for single plots - smaller to fit 2 per page
    let aspectRatio = 0.5; // More rectangular, allows 2 single plots per page
    
    if (plot.type === 'plotly' && plot.element) {
        // Method 1: Get actual dimensions from the Plotly element
        const actualAspectRatio = getPlotlyElementAspectRatio(plot.element);
        
        if (actualAspectRatio !== null) {
            // Use the actual aspect ratio from the rendered plot
            // If it's more square (> 0.6), treat as combined; otherwise as single
            if (actualAspectRatio > 0.6) {
                aspectRatio = Math.min(actualAspectRatio, 0.8); // Cap at 0.8 for combined plots
                console.log(`Plot ${plot.id || 'unknown'} using actual aspect ratio ${actualAspectRatio.toFixed(2)} (combined)`);
            } else {
                aspectRatio = Math.min(actualAspectRatio, 0.55); // Cap at 0.55 for single plots
                console.log(`Plot ${plot.id || 'unknown'} using actual aspect ratio ${actualAspectRatio.toFixed(2)} (single)`);
            }
        } else {
            // Fallback: Use content-based detection
            const plotlyData = plot.element._fullData || [];
            const plotlyLayout = plot.element._fullLayout || {};
            const isCombinedPlot = detectCombinedPlot(plotlyData, plotlyLayout);
            
            if (isCombinedPlot) {
                aspectRatio = 0.75;
                console.log(`Plot ${plot.id || 'unknown'} fallback detection - combined plot`);
            } else {
                console.log(`Plot ${plot.id || 'unknown'} fallback detection - single plot`);
            }
        }
    } else if (plot.type === 'image' && plot.element) {
        // For image plots, check the actual aspect ratio from the HTML element
        const img = plot.element;
        if (img.naturalWidth && img.naturalHeight) {
            const imageAspectRatio = img.naturalHeight / img.naturalWidth;
            
            // Use actual image aspect ratio with reasonable limits
            if (imageAspectRatio > 0.6) {
                aspectRatio = Math.min(imageAspectRatio, 0.8); // Combined plot
                console.log(`Image plot ${plot.id || 'unknown'} using actual aspect ratio ${imageAspectRatio.toFixed(2)} (combined)`);
            } else {
                aspectRatio = Math.min(imageAspectRatio, 0.55); // Single plot
                console.log(`Image plot ${plot.id || 'unknown'} using actual aspect ratio ${imageAspectRatio.toFixed(2)} (single)`);
            }
        }
    }
    
    return plotWidth * aspectRatio;
}

function getPlotlyElementAspectRatio(plotlyElement) {
    try {
        // Method 1: Check the plotly element's computed style dimensions
        if (plotlyElement.style.width && plotlyElement.style.height) {
            const width = parseFloat(plotlyElement.style.width);
            const height = parseFloat(plotlyElement.style.height);
            if (width > 0 && height > 0) {
                return height / width;
            }
        }
        
        // Method 2: Check the getBoundingClientRect dimensions
        const rect = plotlyElement.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            return rect.height / rect.width;
        }
        
        // Method 3: Check the layout dimensions if available
        const layout = plotlyElement._fullLayout;
        if (layout && layout.width && layout.height) {
            return layout.height / layout.width;
        }
        
        // Method 4: Check the parent container dimensions
        const container = plotlyElement.closest('.plot-container') || plotlyElement.parentElement;
        if (container) {
            const containerRect = container.getBoundingClientRect();
            if (containerRect.width > 0 && containerRect.height > 0) {
                return containerRect.height / containerRect.width;
            }
        }
        
        return null; // Could not determine aspect ratio
    } catch (error) {
        console.warn('Error getting Plotly element aspect ratio:', error);
        return null;
    }
}

function detectCombinedPlot(plotlyData, plotlyLayout) {
    // Method 1: Check for multiple subplots
    if (plotlyLayout.xaxis2 || plotlyLayout.yaxis2 || 
        plotlyLayout.grid || plotlyLayout.subplot) {
        return true;
    }
    
    // Method 2: Check for multiple different trace types
    const traceTypes = new Set();
    plotlyData.forEach(trace => {
        if (trace.type) {
            traceTypes.add(trace.type);
        }
    });
    
    // If we have more than one trace type, it's likely a combined plot
    if (traceTypes.size > 1) {
        return true;
    }
    
    // Method 3: Check for specific combinations that indicate combined plots
    const hasBar = plotlyData.some(trace => trace.type === 'bar');
    const hasScatter = plotlyData.some(trace => trace.type === 'scatter' || trace.mode === 'lines');
    
    if (hasBar && hasScatter) {
        return true;
    }
    
    // Method 4: Check layout properties that suggest combined plots
    if (plotlyLayout.yaxis && plotlyLayout.yaxis2) {
        return true;
    }
    
    // Method 5: Check for multiple y-axes (secondary axis)
    const hasSecondaryAxis = plotlyData.some(trace => trace.yaxis === 'y2');
    if (hasSecondaryAxis) {
        return true;
    }
    
    return false;
}

async function addSinglePlot(pdf, plot, x, y, width, height) {
    try {
        let plotImageData;
        if (plot.type === 'plotly') {
            // Calculate appropriate image dimensions for export
            const isCombined = plot.element && detectCombinedPlot(
                plot.element._fullData || [], 
                plot.element._fullLayout || {}
            );
            
            // Use consistent high resolution, adjust dimensions based on type
            const exportWidth = 1000;
            const exportHeight = isCombined ? 750 : 500; // Combined plots taller
            
            plotImageData = await Plotly.toImage(plot.element, { 
                format: 'png', 
                width: exportWidth, 
                height: exportHeight, 
                scale: 2 
            });
        } else if (plot.type === 'image') {
            plotImageData = plot.element.src;
        }
        
        if (plotImageData) {
            pdf.addImage(plotImageData, 'PNG', x, y, width, height);
        }
    } catch (error) {
        console.error('Error adding plot to PDF:', error);
        pdf.setFontSize(10);
        pdf.setTextColor(255, 0, 0);
        pdf.text('Error: Could not render plot', x, y + 10);
        pdf.setTextColor(0, 0, 0);
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
        }
    }, 100);
}