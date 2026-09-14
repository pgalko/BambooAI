// Plotly stand-in: JSON figures render as an empty box; PNG figures do not need Plotly.
window.Plotly = { newPlot: () => Promise.resolve(), react: () => Promise.resolve(), relayout() {}, purge() {}, toImage: () => Promise.resolve(''), Plots: { resize() {} } };
