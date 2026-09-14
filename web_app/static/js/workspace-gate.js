// workspace-gate.js - the workspace gate (2026-09-09).
//
// One pill, centred, from the first paint of the page until the executor chip reports Ready:
//   Signing you in · 3 s  ->  Preparing your workspace · 5 s  ->  Starting your executor · pro · 12 s
//   ->  Executor ready · pro · 14 s (tick, then it fades)     |  Executor did not start (red, stays)
// While it is up the page is inert: nothing can be clicked or focused behind it.
//
// It changes nothing about how the workspace is built. It only OBSERVES what the page already
// does: the shell becoming visible (sign-in complete), the login and mandatory screens (it
// steps aside for them), and the executor chip's own status updates (#containerStatus, written
// by container-status.js on every poll). The tier comes from the subscription data the page
// loads anyway; the clock is its own, carried across the reload New workflow performs.
//
// Callers: ui-controls.js showLoadingOverlay()/hideLoadingOverlay() (the old page while
// /new_conversation runs), auth.js showProcessingMessage() (the sign-in stage).
(function () {
    'use strict';

    const LONG_WAIT_S = 8;          // after this, the "up to two minutes" caption
    const NOT_FOUND_POLLS = 4;      // chip polls saying "no container" before the pill calls it a failure (~28 s)
    const CEILING_S = 180;          // no Ready by then: the failed state, whatever the chip says
    const CLOCK_KEY = 'wsGateStart';

    const STAGE_TEXT = { signin: 'Signing you in', workspace: 'Preparing your workspace', executor: 'Starting your executor',
                         ready: 'Executor ready', failed: 'Executor did not start' };
    const ORDER = ['signin', 'workspace', 'executor', 'ready'];
    const WAITING = { spawning: 1, starting: 1, restarting: 1, execution: 1 };
    const ABSENT = { not_found: 1, offline: 1 };
    const FAILED = { failed: 1, error: 1 };

    let stage = 'signin', failed = false, released = false, hiddenFor = null, open = true;
    let pending = false;          // no sign of a session at first paint: the pill waits for a sign-in to start or finish
    let notFound = 0, ticker = null, observers = [];
    let start = (function () {
        // the clock carries over the reload New workflow performs (sessionStorage is per tab)
        try {
            const v = parseInt(sessionStorage.getItem(CLOCK_KEY) || '', 10);
            sessionStorage.removeItem(CLOCK_KEY);
            if (v && Date.now() - v < 10 * 60 * 1000) return v;
        } catch (e) { /* storage unavailable: a fresh clock */ }
        return Date.now();
    })();

    // ---------------------------------------------------------------- render
    const $ = (sel) => document.querySelector(sel);
    const gate = () => document.getElementById('workspaceGate');

    function elapsed() {
        const s = Math.max(0, Math.round((Date.now() - start) / 1000));
        return s < 60 ? s + ' s' : Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    }

    function tier() {
        try {
            const cs = window.containerStatus && window.containerStatus.getCurrentStatus && window.containerStatus.getCurrentStatus();
            if (cs && cs.tier && cs.tier !== 'unknown') return cs.tier;
        } catch (e) { /* no chip yet */ }
        try {
            if (typeof subscriptionState !== 'undefined' && subscriptionState && subscriptionState.computeTier) return subscriptionState.computeTier;
        } catch (e) { /* not loaded */ }
        return '';
    }

    function render() {
        const g = gate();
        if (!g) return;
        const text = g.querySelector('.ws-text'), dots = g.querySelectorAll('.ws-dots i'), cap = g.querySelector('.ws-caption'),
              act = g.querySelector('.ws-actions'), pill = g.querySelector('.ws-pill');
        const segs = [STAGE_TEXT[failed ? 'failed' : stage]];
        const t = tier();
        if (t && (stage === 'executor' || stage === 'ready' || failed)) segs.push('<span class="dim">' + t + '</span>');
        segs.push('<span class="dim">' + elapsed() + '</span>');
        if (text) text.innerHTML = segs.join('<span class="sep">·</span>');
        const idx = failed ? ORDER.indexOf('executor') : ORDER.indexOf(stage);
        dots.forEach((d, i) => { d.className = failed && i === idx ? 'fail' : (i < idx || stage === 'ready' ? 'done' : (i === idx ? 'busy' : '')); });
        if (pill) { pill.classList.toggle('ready', stage === 'ready' && !failed); pill.classList.toggle('failed', failed); }
        const secs = (Date.now() - start) / 1000;
        if (cap) {
            if (failed) { cap.textContent = 'Use Refresh below, or Restart on the executor chip.'; cap.hidden = false; }
            else if (stage === 'executor' && secs >= LONG_WAIT_S) { cap.textContent = 'A fresh executor takes up to two minutes the first time; after that it is reused.'; cap.hidden = false; }
            else cap.hidden = true;
        }
        if (act) act.hidden = !failed;
        g.classList.toggle('failed', failed);
        g.setAttribute('aria-busy', failed || released ? 'false' : 'true');
    }

    // ------------------------------------------------------------- the page
    function setInert(on) {
        const c = $('.container');
        if (!c) return;
        try { c.inert = on; } catch (e) { /* older engine: the backdrop still blocks the pointer */ }
        document.body.classList.toggle('ws-gated', on);
    }

    // The Auth0 SDK keeps `auth0.<client>.is.authenticated=true` while a session exists and clears it on
    // logout (2026-09-10). Without it the load is heading for the sign-in screen - the page that comes back
    // from Auth0's logout, a first visit - and the pill has nothing to wait for yet. With cookies blocked
    // the hint is absent too; the pill then appears when the shell does, one stage later.
    function sessionHint() {
        try { return /(^|;\s*)auth0\.[^=;]*\.is\.authenticated=true/.test(document.cookie); } catch (e) { return true; }
    }

    function show() {
        const g = gate();
        if (!g || released) return;
        pending = false;
        open = true;
        g.hidden = false;
        g.classList.remove('hidden', 'leaving');
        setInert(true);
        if (!ticker) ticker = setInterval(tick, 1000);
        render();
    }

    function hide() {
        const g = gate();
        if (g) g.classList.add('hidden');
        setInert(false);
        if (!hiddenFor) open = false;                 // gone for good (not merely stepping aside for a sign-in or account screen)
    }

    function glog() { console.log.apply(console, ['[gate]'].concat(Array.prototype.slice.call(arguments))); }

    function setStage(s) {
        if (released || failed) return;
        if (ORDER.indexOf(s) > ORDER.indexOf(stage)) { stage = s; glog('stage', s, 'at', elapsed()); }
        render();
    }

    function fail() {
        if (released) return;
        glog('failed at', elapsed(), '- chip status:', chipStatus() || '(none yet)');
        failed = true;
        setInert(false);                              // the chip's Restart must be reachable
        render();
    }

    function release() {
        if (released) return;
        glog('ready at', elapsed(), '- released');
        released = true; failed = false; stage = 'ready';
        render();
        const g = gate();
        setTimeout(() => {
            if (g) g.classList.add('leaving');
            setTimeout(() => { hide(); }, 400);
        }, 700);
        clearInterval(ticker); ticker = null;
        observers.forEach(o => { try { o.disconnect(); } catch (e) { /* gone */ } });
        observers = [];
    }

    // the old page, while /new_conversation builds the next workspace (showLoadingOverlay):
    // the pill again, inert page, a fresh clock that the reloaded page continues
    function begin(s) {
        glog('begin', s || 'executor', released ? '(a new wait)' : '(continuing)');
        if (released) start = Date.now();             // a usable page: the wait begins now; otherwise the clock keeps counting from first paint
        released = false; failed = false; notFound = 0; stage = s || 'executor';
        try { sessionStorage.setItem(CLOCK_KEY, String(start)); } catch (e) { /* no storage */ }
        const g = gate();
        if (g) g.classList.add('over-shell');
        show();
    }

    function end() {                                  // the build did not happen (hideLoadingOverlay): the failed state, page usable
        try { sessionStorage.removeItem(CLOCK_KEY); } catch (e) { /* no storage */ }
        released = false;
        fail();
    }

    function tick() {
        if (released) return;
        render();
        if (!failed && (Date.now() - start) / 1000 >= CEILING_S) fail();
    }

    // ----------------------------------------------------------- the signals
    function shellVisible() {
        // sign-in complete: auth.js sets isAuthenticationComplete and gives the shell an explicit display:flex in
        // completeAuthentication (2026-09-10). The shell is also visible for an instant at first paint, before
        // initializeAuth hides it, which is why the computed style alone is not the signal.
        try { if (typeof isAuthenticationComplete !== 'undefined' && isAuthenticationComplete) return true; } catch (e) { /* not defined */ }
        const c = $('.container');
        return !!(c && c.style && c.style.display === 'flex');
    }

    function chipStatus() {
        const el = document.getElementById('containerStatus');
        if (!el) return '';
        const m = /status-([a-z_]+)/.exec(el.className || '');
        return m ? m[1] : '';
    }

    function onChip() {
        if (released) return;
        const st = chipStatus();
        if (!st) return;
        glog('chip', st, 'at', elapsed());
        if (stage === 'workspace') setStage('executor');       // the first poll: the app's modules are up
        const g = gate();
        if (g) g.classList.add('over-shell');
        if (st === 'ready') { release(); return; }
        if (WAITING[st]) { notFound = 0; render(); return; }
        if (FAILED[st]) { fail(); return; }
        if (ABSENT[st] && ++notFound >= NOT_FOUND_POLLS) fail();
    }

    function blockers() {
        // screens the person must be able to use: the sign-in/error card, a mandatory account dialog
        if (document.getElementById('authScreen')) return 'auth';
        const m = document.getElementById('subscriptionModal');
        if (m && m.classList.contains('mandatory') && getComputedStyle(m).display !== 'none') return 'subscription';
        return null;
    }

    function reconcile() {
        if (released) return;
        const b = blockers();
        if (b) { if (hiddenFor !== b) { hiddenFor = b; hide(); } return; }
        if (hiddenFor) { hiddenFor = null; if (!pending) show(); }
        if (shellVisible()) {
            if (pending || gate().classList.contains('hidden')) show();      // signed in after all: from here on as usual
            setStage('workspace');
            const g = gate();
            if (g) g.classList.add('over-shell');
        }
    }

    function init() {
        const g = gate();
        if (!g) return;
        const refresh = g.querySelector('#wsGateRefresh');
        if (refresh) refresh.addEventListener('click', () => { window.location.reload(); });
        if (sessionHint()) {
            show();
        } else {
            pending = true; open = false;                 // hidden and not blocking: the sign-in screen may be next
            g.classList.add('hidden');
            glog('no session hint at first paint: the pill waits for a sign-in');
        }
        const body = new MutationObserver(reconcile);
        body.observe(document.body, { childList: true });
        observers.push(body);
        const c = $('.container');
        if (c) {
            const o = new MutationObserver(reconcile);
            o.observe(c, { attributes: true, attributeFilter: ['style', 'class'] });
            observers.push(o);
        }
        const sub = document.getElementById('subscriptionModal');
        if (sub) {
            const o = new MutationObserver(reconcile);
            o.observe(sub, { attributes: true, attributeFilter: ['style', 'class'] });
            observers.push(o);
        }
        const chip = document.getElementById('containerStatus');
        if (chip) {
            const o = new MutationObserver(onChip);                  // container-status.js rewrites the class on every poll
            o.observe(chip, { attributes: true, attributeFilter: ['class'] });
            observers.push(o);
        }
        reconcile();
    }

    // ----------------------------------------------------------- the surface
    window.WorkspaceGate = {
        show: show, hide: hide, stage: setStage, fail: fail, release: release, begin: begin, end: end,
        // open: the pill is up and the page inert (released turns true at the tick, ~1 s before the pill is gone)
        state: function () { return { stage: stage, failed: failed, released: released, open: open, hiddenFor: hiddenFor, seconds: Math.round((Date.now() - start) / 1000) }; }
    };

    // the script sits after the shell in the document, so everything it observes is parsed: start now
    if (gate()) init();
    else document.addEventListener('DOMContentLoaded', init);
})();
