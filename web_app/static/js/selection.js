// selection.js - asking about a selection (2026-11-27, the product owner's pick of three mockups).
//
// Text selected in the content pane gets a small bar beside it: Ask, Copy. The bar takes no focus, so the selection
// stays and copies as on any page. The popup this replaces opened a query box at every mouse-up and put the cursor in
// it, which dropped the selection: nothing could be copied out of a tab.
//
// Ask puts the selection on the query box as a quote and the cursor there - one place to type. The question typed in
// the box is asked about the quoted passage and explained where the passage stands (explain.js): no analysis starts.
// So Ask is on the bar only where a selection can be explained - in the text of a finished analysis' Answer, Code or
// Results tab; elsewhere the bar copies. The quote goes when the box is emptied (core.js emptyComposer), by its ×, and
// with the analysis it was taken from.
//
// window.SelectionUI = { initialize, send, unquote }

(function () {
    'use strict';

    const ICON = {
        ask: '<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    };
    const WORDS = { ask: 'Ask', copy: 'Copy', copied: 'Copied' };
    const GAP = 8;                              // from the bar to the selection, and to the window's edge
    const COPIED_MS = 900;                      // how long Copy says it has copied before the bar goes

    let bar = null;        // the bar, one for the page
    let pressed = false;   // the press under way began in the content pane, with the main button
    let later = 0;         // the timer that takes the bar away after a copy
    let place = null;      // where the passage quoted on the query box stands, with its words (explain.js place())

    const byId = id => document.getElementById(id);
    const selected = () => { const s = window.getSelection(); return s && s.rangeCount ? s.toString().trim() : ''; };

    function hide() {
        clearTimeout(later);
        bar.classList.remove('on');
    }

    // the selection the bar stands beside is no more: the bar goes. And the quote goes with the analysis it was taken
    // from - another chain on screen, or a run begun
    function settle() {
        if (bar.classList.contains('on') && !selected()) hide();
        if (place && !window.ExplainUI.stands(place)) setQuote(null);
    }

    // The bar outside the end of the selection the pointer left it at - over its first line or under its last, not on
    // the selection. Where the window has no room there, at the other end; and where it has none at either - a
    // selection taller than the window - at the window's edge on the pointer's side. With Ask only where the selection
    // can be explained
    function show(range, x, y) {
        const box = range.getBoundingClientRect(), line = [...range.getClientRects()].find(r => r.height) || box;
        clearTimeout(later);
        bar.querySelector('.copy span').textContent = WORDS.copy;
        bar.classList.toggle('copies', !window.ExplainUI.place(range));
        bar.classList.add('on');
        const w = bar.offsetWidth, h = bar.offsetHeight, low = window.innerHeight - h - GAP;
        const over = box.top - h - GAP, under = box.bottom + GAP, [near, far] = y <= line.bottom ? [over, under] : [under, over];
        const fits = top => top >= GAP && top <= low;
        bar.style.left = Math.max(GAP, Math.min(x - w / 2, window.innerWidth - w - GAP)) + 'px';
        bar.style.top = (fits(near) ? near : fits(far) ? far : Math.max(GAP, Math.min(near, low))) + 'px';
    }

    // The end of a press that began in the content pane, once the browser has settled what is selected (a click inside a
    // selection clears it only after the mouse-up): the bar for a selection that lies in the pane, wherever the pointer
    // was let go. None on the Plots tab, whose figures have their own question row, and none for text selected in a
    // field being typed in
    function offer(e) {
        const range = selected() ? window.getSelection().getRangeAt(0) : null, held = range && range.commonAncestorContainer;
        const where = held && (held.nodeType === 1 ? held : held.parentElement);
        const typing = document.activeElement.matches('input, textarea, [contenteditable]');
        if (where && !typing && byId('contentOutput').contains(where) && !where.closest('#content-plot')) show(range, e.clientX, e.clientY);
        else hide();
    }

    // Copy, as the keyboard does it: the selection itself, a table as a table
    function copy() {
        if (!document.execCommand('copy')) return;
        bar.querySelector('.copy span').textContent = WORDS.copied;
        later = setTimeout(hide, COPIED_MS);
    }

    // Ask: the selection onto the query box, the cursor there - the left pane opened first where it is folded away
    function ask() {
        const at = selected() ? window.ExplainUI.place(window.getSelection().getRangeAt(0)) : null, pane = byId('leftPanel');
        hide();
        if (!at) return;
        setQuote(at);
        if (pane.classList.contains('collapsed')) byId('collapseButton').click();
        byId('queryInput').focus();
    }

    // The quote on the query box - of a place, or none: its first words on one line, the passage whole under the pointer
    function setQuote(at) {
        const chip = byId('queryQuote'), words = chip.querySelector('.t'), text = at ? at.quote : '';
        place = at;
        chip.classList.toggle('on', !!at);
        words.textContent = text.replace(/\s+/g, ' ');
        words.title = text;
    }

    function initialize() {
        bar = document.createElement('div');
        bar.className = 'selection-bar';
        bar.innerHTML = '<button type="button" class="ask">' + ICON.ask + WORDS.ask + '</button><span class="sep"></span>' +
            '<button type="button" class="copy">' + ICON.copy + '<span>' + WORDS.copy + '</span></button>';
        document.body.appendChild(bar);
        bar.addEventListener('mousedown', e => e.preventDefault());      // a press on the bar is not a click elsewhere: the selection stays
        bar.querySelector('.ask').addEventListener('click', ask);
        bar.querySelector('.copy').addEventListener('click', copy);
        // a press anywhere but on the bar takes the bar away; one with the main button that begins in the content pane may
        // end as a selection there (the other buttons are the browser's: its own menu, its scrolling)
        document.addEventListener('mousedown', e => { if (!bar.contains(e.target)) { hide(); pressed = e.button === 0 && byId('contentOutput').contains(e.target); } });
        document.addEventListener('mouseup', e => { if (pressed) { pressed = false; setTimeout(() => offer(e), 0); } });
        // the bar goes, too, with what it stood beside: Esc, the window resized, the selection scrolled or gone - also
        // gone from under it when its tab is drawn again, as a running analysis draws it, which the browser does not announce
        document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
        document.addEventListener('scroll', e => { if (e.target.contains(window.getSelection().anchorNode)) hide(); }, true);
        window.addEventListener('resize', hide);
        document.addEventListener('selectionchange', settle);
        new MutationObserver(settle).observe(byId('contentOutput'), { childList: true, subtree: true });
        byId('queryQuote').querySelector('button').addEventListener('click', () => { setQuote(null); byId('queryInput').focus(); });
    }

    window.SelectionUI = {
        initialize,
        // a typed question with a passage quoted on the box: asked about the passage and explained there; says whether it was
        send: question => { if (place) window.ExplainUI.ask(place, question); return !!place; },
        unquote: () => setQuote(null),
    };
})();
