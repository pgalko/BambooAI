//--------------------
//  COMPRESSION MODULE
//--------------------

async function compressContent(content) {
    // Check content size first (30MB limit for compression)
    if (content.length > 30 * 1024 * 1024) {
        console.warn(`Content too large for compression: ${(content.length / 1024 / 1024).toFixed(1)}MB`);
        return content; // Return uncompressed if too large
    }
    
    try {
        const stream = new CompressionStream('gzip');
        const writer = stream.writable.getWriter();
        const reader = stream.readable.getReader();
        
        writer.write(new TextEncoder().encode(content));
        writer.close();
        
        const chunks = [];
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
        }
        
        // Combine chunks efficiently without creating massive arrays
        let totalLength = 0;
        for (const chunk of chunks) {
            totalLength += chunk.length;
        }
        
        const compressed = new Uint8Array(totalLength);
        let offset = 0;
        for (const chunk of chunks) {
            compressed.set(chunk, offset);
            offset += chunk.length;
        }
        
        // Convert to base64 safely for large arrays using smaller chunks
        let binary = '';
        const chunkSize = 32768; // 32KB chunks for better performance
        for (let i = 0; i < compressed.length; i += chunkSize) {
            const end = Math.min(i + chunkSize, compressed.length);
            const slice = compressed.subarray(i, end);
            binary += String.fromCharCode.apply(null, Array.from(slice));
        }
        
        return btoa(binary);
    } catch (error) {
        console.error('Compression failed:', error);
        console.warn('Returning uncompressed content due to compression failure');
        return content; // Fallback to uncompressed
    }
}

async function decompressContent(compressedData) {
    // Check if data is actually compressed (base64 encoded gzip data vs plain text)
    // Compressed data will be base64, uncompressed will be regular text/HTML
    try {
        // If it looks like HTML/text content, it's probably uncompressed
        if (compressedData.includes('<') || compressedData.includes('{') || compressedData.length < 100) {
            return compressedData; // Return as-is if uncompressed
        }
        
        // Try to decode as base64 - if it fails, it's probably uncompressed
        const compressed = new Uint8Array(atob(compressedData).split('').map(c => c.charCodeAt(0)));
        
        const stream = new DecompressionStream('gzip');
        const writer = stream.writable.getWriter();
        const reader = stream.readable.getReader();
        
        writer.write(compressed);
        writer.close();
        
        const chunks = [];
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
        }
        
        let totalLength = 0;
        for (const chunk of chunks) {
            totalLength += chunk.length;
        }
        
        const decompressed = new Uint8Array(totalLength);
        let offset = 0;
        for (const chunk of chunks) {
            decompressed.set(chunk, offset);
            offset += chunk.length;
        }
        
        return new TextDecoder().decode(decompressed);
    } catch (error) {
        // If decompression fails, assume it was stored uncompressed
        console.warn('Decompression failed, assuming uncompressed content');
        return compressedData;
    }
}

async function generatePlotPreview(contentOutput) {
    if (typeof Plotly === 'undefined') return null;
    
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = contentOutput;
    
    const plotTab = tempDiv.querySelector('#content-plot');
    if (!plotTab) return null;
    
    // Check for static image first (PNG/SVG)
    const imgElement = plotTab.querySelector('img[src^="data:image"]');
    if (imgElement && imgElement.src) {
        // Already a base64 image, return as is
        return imgElement.src;
    }
    
    // Check for interactive Plotly plot
    const plotlyDiv = plotTab.querySelector('.plotly-plot div[data-plotly-json]');
    if (!plotlyDiv || !plotlyDiv.dataset.plotlyJson) return null;
    
    try {
        const plotData = JSON.parse(plotlyDiv.dataset.plotlyJson);
        
        // Check if it's already a static image in the JSON
        if (plotData.format === 'png' && plotData.data) {
            // Return the base64 PNG data with proper prefix
            return `data:image/png;base64,${plotData.data}`;
        }
        if (plotData.format === 'svg' && plotData.data) {
            // Return the base64 SVG data with proper prefix
            return `data:image/svg+xml;base64,${plotData.data}`;
        }
        
        // Generate preview from interactive plot
        const tempPlot = document.createElement('div');
        tempPlot.style.cssText = 'width:800px;height:500px;position:absolute;left:-9999px;visibility:hidden;';
        document.body.appendChild(tempPlot);
        
        await Plotly.newPlot(tempPlot, plotData.data || [], 
            Object.assign({}, plotData.layout || {}, { width: 800, height: 500, margin: { t: 30, r: 30, b: 50, l: 60 }}),
            { displayModeBar: false }
        );
        
        const imageUrl = await Plotly.toImage(tempPlot, { format: 'png', width: 800, height: 500 });
        
        Plotly.purge(tempPlot);
        document.body.removeChild(tempPlot);
        
        return imageUrl;
    } catch (error) {
        console.error('Plot preview generation failed:', error);
        return null;
    }
}

// Make functions globally available immediately
window.compressContent = compressContent;
window.decompressContent = decompressContent;
window.generatePlotPreview = generatePlotPreview;

function initializeCompression() {
    console.log('Compression utilities initialized');
}