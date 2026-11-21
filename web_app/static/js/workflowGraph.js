//--------------------
//  WORKFLOW GRAPH — Dagre + HTML/SVG Renderer
//  Replaces Mermaid-based workflow map rendering
//  Dependency: dagre.js (https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js)
//
//  The Workflow map draws a thread's chains. The same drawing serves the two maps under it - the Pathfinding map, the
//  steps that made a brief (architect.js; docs/ARCHITECT_DESIGN.md §2.25), and the Analysis map, the turns of an
//  analysis (branch.js; docs/BRANCH_DESIGN.md §5) - each of which gives its boxes as chains are given ({chain_id,
//  parentChainId, queryText}) and says, in render()'s last argument, what is its own:
//      sub(item, i)    a box's second line
//      show(item, i)   what the drawer's foot says of the box under the pointer
//      pick(item, i)   a box clicked
//      tag(item, i)    a mark on a box's corner, where the map has one
//  and has the way to the box in use lit while no box is under the pointer. The thread's own boxes are analyses: where
//  one has branches its box says how many (`branches`), and a click brings the chain of it the box stands for on
//  screen (BranchUI.open) - the drawer stays open, and follows.
//
//  The three are the levels of one drawer, whose head is the switch between them (maps.js): render() puts zoom and
//  full screen into the head, before its close, and rest() writes what the drawer's foot says until a box is under
//  the pointer.
//--------------------

window.WorkflowGraph = (function () {

    var currentZoom = 1;
    var fitZoom = 1;               // the scale at which the whole graph fits the frame
    var fitObserver = null;
    function fitToFrame(wrapper, frame, W, H) {
        var cw = frame.clientWidth - 28, ch = frame.clientHeight - 28;
        if (cw <= 0 || ch <= 0) return;
        fitZoom = Math.max(MIN_ZOOM, Math.min(1, cw / W, ch / H));
        applyZoom(wrapper, fitZoom);
        wrapper.style.marginLeft = Math.max(0, (frame.clientWidth - W * currentZoom) / 2 - 14) + 'px';
    }
    var MIN_ZOOM = 0.3;
    var MAX_ZOOM = 2.0;
    var ZOOM_STEP = 0.15;

    // ── Helpers ──────────────────────────────────────────────

    function sanitizeText(text) {
        if (!text) return 'No query';
        return text.replace(/[<>&"']/g, '').replace(/\n/g, ' ').trim();
    }

    function getNodeType(queryText) {
        var qt = (queryText || '').toLowerCase();
        if (qt.includes('user requested variations')) return 'fork';
        if (qt.includes('synthesis of exploration')) return 'synthesis';
        return 'normal';
    }

    function buildChainIndex(responses) {
        var map = {};
        responses.forEach(function (r, i) { if (r.chain_id) map[r.chain_id] = i; });
        return map;
    }

    function getAncestorPath(nodeIndex, responses, chainIndex) {
        var path = [nodeIndex];
        var current = responses[nodeIndex];
        while (current && current.parentChainId) {
            var parentIdx = chainIndex[current.parentChainId];
            if (parentIdx !== undefined && path.indexOf(parentIdx) === -1) {
                path.push(parentIdx);
                current = responses[parentIdx];
            } else { break; }
        }
        return path;
    }

    // ── Zoom ────────────────────────────────────────────────

    function applyZoom(wrapper, zoom) {
        currentZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
        wrapper.style.transform = 'scale(' + currentZoom + ')';

        var tools = document.getElementById('mapDrawerTools');
        var label = tools.querySelector('.wf-zoom-level');
        if (label) label.textContent = Math.round(currentZoom * 100) + '%';

        var controls = tools.querySelector('.wf-zoom-controls');
        if (controls) {
            var btns = controls.querySelectorAll('.wf-zoom-btn');
            btns[0].disabled = (currentZoom <= MIN_ZOOM);
            btns[1].disabled = (currentZoom >= MAX_ZOOM);       // the way further in; the third button is fit, which is never shut
        }
    }

    function createZoomControls(container, wrapper) {
        var controls = document.createElement('div');
        controls.className = 'wf-zoom-controls';

        var btnOut = document.createElement('button');
        btnOut.className = 'wf-zoom-btn';
        btnOut.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>';
        btnOut.title = 'Zoom out';
        btnOut.addEventListener('click', function () { applyZoom(wrapper, currentZoom - ZOOM_STEP); });

        var level = document.createElement('span');
        level.className = 'wf-zoom-level';
        level.textContent = '100%';

        var btnIn = document.createElement('button');
        btnIn.className = 'wf-zoom-btn';
        btnIn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
        btnIn.title = 'Zoom in';
        btnIn.addEventListener('click', function () { applyZoom(wrapper, currentZoom + ZOOM_STEP); });

        var btnReset = document.createElement('button');
        btnReset.className = 'wf-zoom-btn wf-zoom-reset';
        btnReset.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 5 5 0 0 0-4 2"/><polyline points="3 3 3 7 7 7"/></svg>';
        btnReset.title = 'Fit to the frame';
        btnReset.addEventListener('click', function () { applyZoom(wrapper, fitZoom || 1); });

        controls.appendChild(btnOut);
        controls.appendChild(level);
        controls.appendChild(btnIn);
        controls.appendChild(btnReset);
        [btnOut, btnIn, btnReset].forEach(function (b) { b.setAttribute('aria-label', b.title); });       // a button of a mark alone: its name, for a reader

        container.appendChild(controls);
    }

    // ── Full screen ─────────────────────────────────────────

    var FULLSCREEN_ICON = {
        off: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>',
        on: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>'
    };

    // the button says what a click does: the drawer over the whole page, or back at its side
    function fullscreenLooks(btn, isFs) {
        btn.innerHTML = isFs ? FULLSCREEN_ICON.on : FULLSCREEN_ICON.off;
        btn.title = isFs ? 'Leave full screen' : 'Full screen';
        btn.setAttribute('aria-label', btn.title);
    }

    function createFullscreenButton(container) {
        var btn = document.createElement('button');
        btn.className = 'wf-fullscreen-btn';
        fullscreenLooks(btn, !!document.querySelector('.workflow-modal-content.wf-fullscreen'));       // a map drawn again while the drawer is over the whole page
        btn.addEventListener('click', toggleFullscreen);
        container.appendChild(btn);
    }

    function toggleFullscreen() {
        var modal = document.querySelector('.workflow-modal-content');
        if (!modal) return;

        var isFs = modal.classList.toggle('wf-fullscreen');
        var btn = document.querySelector('.wf-fullscreen-btn');
        if (btn) fullscreenLooks(btn, isFs);
    }

    // ── Layout ──────────────────────────────────────────────

    function computeLayout(responses, of) {
        var g = new dagre.graphlib.Graph();
        g.setGraph({
            rankdir: 'TB',
            nodesep: 30,
            ranksep: 55,
            marginx: 30,
            marginy: 30
        });
        g.setDefaultEdgeLabel(function () { return {}; });

        // Nodes
        responses.forEach(function (response, index) {
            var label = sanitizeText(response.queryText);
            if (label.length > 30) label = label.substring(0, 27) + '...';

            g.setNode(String(index), {
                label: label,
                chainId: response.chain_id || 'N/A',
                width: 190,
                height: 52,
                type: of ? 'normal' : getNodeType(response.queryText),      // another map's boxes are no chains: what one says makes it no fork
                index: index
            });
        });

        // Edges
        responses.forEach(function (response, index) {
            if (response.parentChainId) {
                var parentIndex = responses.findIndex(function (r) { return r.chain_id === response.parentChainId; });
                if (parentIndex >= 0) {
                    g.setEdge(String(parentIndex), String(index), {
                        isFork: !of && getNodeType(response.queryText) === 'fork'
                    });
                }
            }
        });

        dagre.layout(g);
        return g;
    }

    // ── SVG edge path ───────────────────────────────────────

    function edgePath(x1, y1, x2, y2) {
        var midY = (y1 + y2) / 2;
        return 'M ' + x1 + ' ' + y1 + ' C ' + x1 + ' ' + midY + ', ' + x2 + ' ' + midY + ', ' + x2 + ' ' + y2;
    }

    // ── Render ──────────────────────────────────────────────

    function render(container, responses, activeIndex, of) {
        var tools = document.getElementById('mapDrawerTools');       // zoom and full screen stand in the drawer's head (2.9); a map with nothing on it has neither
        container.innerHTML = '';
        tools.innerHTML = '';
        currentZoom = 1;

        if (!responses || responses.length === 0) {
            container.innerHTML = '<div class="wf-empty">No workflow data to display.</div>';
            return;
        }

        var graph = computeLayout(responses, of);
        var info = graph.graph();
        var W = (info.width || 400) + 60;
        var H = (info.height || 300) + 60;

        // ── Wrapper ──
        var wrapper = document.createElement('div');
        wrapper.className = 'wf-graph';
        wrapper.style.width = W + 'px';
        wrapper.style.height = H + 'px';
        wrapper.style.transformOrigin = 'top left';

        // ── SVG layer (edges + arrowheads) ──
        var ns = 'http://www.w3.org/2000/svg';
        var svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('width', W);
        svg.setAttribute('height', H);
        svg.classList.add('wf-edges');

        // Arrowhead markers
        var defs = document.createElementNS(ns, 'defs');

        function createMarker(id, cls) {
            var m = document.createElementNS(ns, 'marker');
            m.setAttribute('id', id);
            m.setAttribute('markerWidth', '8');
            m.setAttribute('markerHeight', '6');
            m.setAttribute('refX', '8');
            m.setAttribute('refY', '3');
            m.setAttribute('orient', 'auto');
            var poly = document.createElementNS(ns, 'polygon');
            poly.setAttribute('points', '0 0, 8 3, 0 6');
            poly.classList.add(cls);
            m.appendChild(poly);
            return m;
        }
        defs.appendChild(createMarker('wf-arrow', 'wf-arrowhead'));
        defs.appendChild(createMarker('wf-arrow-hl', 'wf-arrowhead-hl'));
        svg.appendChild(defs);

        // Draw edges
        var edgeLabelsData = [];
        graph.edges().forEach(function (e) {
            var data = graph.edge(e);
            var from = graph.node(e.v);
            var to = graph.node(e.w);

            var x1 = from.x, y1 = from.y + from.height / 2;
            var x2 = to.x,   y2 = to.y - to.height / 2;

            var p = document.createElementNS(ns, 'path');
            p.setAttribute('d', edgePath(x1, y1, x2, y2));
            p.setAttribute('data-from', e.v);
            p.setAttribute('data-to', e.w);
            p.setAttribute('marker-end', 'url(#wf-arrow)');
            p.classList.add('wf-edge');
            svg.appendChild(p);

            if (data.isFork) {
                edgeLabelsData.push({ x: (x1 + x2) / 2, y: (y1 + y2) / 2 });
            }
        });

        wrapper.appendChild(svg);

        // Edge labels (fork badges)
        edgeLabelsData.forEach(function (lb) {
            var el = document.createElement('div');
            el.className = 'wf-edge-label';
            el.textContent = 'Fork';
            el.style.left = lb.x + 'px';
            el.style.top = lb.y + 'px';
            wrapper.appendChild(el);
        });

        // ── Precompute data for interactions ──
        var chainIndex = buildChainIndex(responses);
        var nodeContents = of ? [] : responses.map(function (r) { return extractTaskFromResponse(r); });
        var nodePlots    = of ? [] : responses.map(function (r) { return extractPlotDataFromResponse(r); });
        // another map's way to the box in use, lit while no box is under the pointer
        var atRest = function () { if (of && responses[activeIndex]) highlightPath(wrapper, getAncestorPath(activeIndex, responses, chainIndex)); };

        // ── HTML nodes ──
        graph.nodes().forEach(function (nodeId) {
            var nd = graph.node(nodeId);
            var idx = nd.index;
            var resp = responses[idx];

            var div = document.createElement('div');
            div.className = 'wf-node wf-node--' + nd.type;
            if (idx === activeIndex) div.classList.add('wf-node--active');
            div.setAttribute('data-index', idx);

            div.style.left   = (nd.x - nd.width / 2) + 'px';
            div.style.top    = (nd.y - nd.height / 2) + 'px';
            div.style.width  = nd.width + 'px';
            div.style.height = nd.height + 'px';

            var span = document.createElement('span');
            span.className = 'wf-node-label';
            span.textContent = nd.label;
            div.appendChild(span);

            var chainSpan = document.createElement('span');
            chainSpan.className = 'wf-node-chain';
            chainSpan.textContent = of ? of.sub(resp, idx) : 'Chain: ' + nd.chainId;
            div.appendChild(chainSpan);

            // how the question was made (docs/ARCHITECT_DESIGN.md §2.9): framed with the Architect, or a brief not yet run;
            // on another map, that map's own mark
            var made = of ? (of.tag ? of.tag(resp, idx) : '') : (window.ArchitectUI ? window.ArchitectUI.mark(resp) : '');
            if (made) {
                var madeSpan = document.createElement('span');
                madeSpan.className = 'wf-node-made';
                madeSpan.textContent = made;
                div.appendChild(madeSpan);
                if (made === 'not run') div.classList.add('wf-node--notrun');
            }
            // an analysis that went on more than one way: how many branches it has (their turns: the Analysis map)
            if (!of && resp && resp.branches) {
                var branchSpan = document.createElement('span');
                branchSpan.className = 'wf-node-branches';
                branchSpan.textContent = resp.branches + (resp.branches === 1 ? ' branch' : ' branches');
                div.appendChild(branchSpan);
            }

            // the code map's way in (2026-10-20): an eye on the hovered box and on the open chain's; the app moves to
            // the chain, the drawer shuts, the map opens
            if (!of && resp && resp.chain_id && made !== 'not run') {
                var eye = document.createElement('button');
                eye.className = 'wf-node-map';
                eye.type = 'button';
                eye.title = 'Code map: how this chain got its numbers';
                eye.setAttribute('aria-label', 'Code map of chain ' + (idx + 1));
                eye.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path></svg>';
                eye.addEventListener('click', function (e) {
                    e.stopPropagation();
                    if (typeof navigateToChainId === 'function' && String(resp.chain_id) !== String(currentData.chain_id)) navigateToChainId(resp.chain_id);
                    window.MapsUI.shut();
                    if (window.CodeMapUI && typeof window.CodeMapUI.open === 'function') window.CodeMapUI.open(resp.chain_id);
                });
                div.appendChild(eye);
            }

            // ── Hover ──
            div.addEventListener('mouseenter', function () {
                var ancestors = getAncestorPath(idx, responses, chainIndex);
                clearHighlight(wrapper);
                highlightPath(wrapper, ancestors);
                if (of) of.show(resp, idx); else updateDetailPane(idx, resp, nodeContents, nodePlots, responses);
            });

            div.addEventListener('mouseleave', function () {
                clearHighlight(wrapper);
                atRest();
            });

            // ── Click → navigate ──
            // a chain's box: the chain comes on screen and the drawer stays open, so its other maps are a click away (2.9)
            div.addEventListener('click', function () {
                if (of) { of.pick(resp, idx); return; }
                if (window.BranchUI) window.BranchUI.open(resp);       // the box stands for a chain of its analysis: that chain opens
                else {
                    currentResponseIndex = idx;
                    lastActiveChainId = responses[idx].chain_id || null;
                    loadResponseContent(responses[idx]);
                    if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
                }
            });

            wrapper.appendChild(div);
        });

        container.appendChild(wrapper);
        atRest();

        // ── Zoom and full screen, in the drawer's head ──
        var mapContainer = container.closest('.workflow-map-container') || container;
        createZoomControls(tools, wrapper);
        createFullscreenButton(tools);
        // the graph is scaled to fit the frame, now and whenever the frame changes size (fullscreen, resize)
        fitToFrame(wrapper, mapContainer, W, H);
        if (fitObserver) fitObserver.disconnect();
        if (typeof ResizeObserver === 'function') {
            fitObserver = new ResizeObserver(function () { fitToFrame(wrapper, mapContainer, W, H); });
            fitObserver.observe(mapContainer);
        }

        // ── Scroll-wheel zoom ── the frame's one handler, for the drawing it now holds: the frame outlives its drawings
        mapContainer.onwheel = function (e) {
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                var delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
                applyZoom(wrapper, currentZoom + delta);
            }
        };
    }

    // ── Path highlighting ───────────────────────────────────

    function highlightPath(wrapper, ancestors) {
        wrapper.classList.add('wf-path-active');

        ancestors.forEach(function (idx) {
            var node = wrapper.querySelector('.wf-node[data-index="' + idx + '"]');
            if (node) node.classList.add('wf-node--ancestor');
        });

        for (var i = 0; i < ancestors.length - 1; i++) {
            var child  = ancestors[i];
            var parent = ancestors[i + 1];
            var edge = wrapper.querySelector('.wf-edge[data-from="' + parent + '"][data-to="' + child + '"]');
            if (edge) {
                edge.classList.add('wf-edge--highlighted');
                edge.setAttribute('marker-end', 'url(#wf-arrow-hl)');
            }
        }
    }

    function clearHighlight(wrapper) {
        wrapper.classList.remove('wf-path-active');
        wrapper.querySelectorAll('.wf-node--ancestor').forEach(function (n) { n.classList.remove('wf-node--ancestor'); });
        wrapper.querySelectorAll('.wf-edge--highlighted').forEach(function (e) {
            e.classList.remove('wf-edge--highlighted');
            e.setAttribute('marker-end', 'url(#wf-arrow)');
        });
    }

    // ── Detail pane update ──────────────────────────────────

    function updateDetailPane(index, response, nodeContents, nodePlots, responses) {
        var taskEl = document.getElementById('nodeTaskContent');
        var plotEl = document.getElementById('nodePlotPreview');
        if (!taskEl) return;

        var queryText = response.queryText || 'No query';

        if (getNodeType(queryText) === 'fork') {
            var variations = extractVariationsFromStreamOutput(response.streamOutput);
            var withStatus = getExploredVariations(response.chain_id, variations);
            if (withStatus.length > 0) {
                renderVariationPills(withStatus, taskEl);
            } else {
                taskEl.innerHTML = 'Generated variation questions for exploration.';
            }
        } else {
            var content = nodeContents[index];
            var html = '';
            if (content.task && content.task !== 'null' && content.task.trim()) {
                html = content.task;
            } else if (content.originalQuestion && content.originalQuestion.trim()) {
                html = content.originalQuestion.length > 200
                    ? content.originalQuestion.substring(0, 200) + '...'
                    : content.originalQuestion;
            } else {
                html = 'No content available for this node';
            }
            taskEl.innerHTML = html;
        }

        if (plotEl) {
            // the chain's basics (2026-09-08): where it sits in the thread, what it followed, what followed it, what it concluded
            var esc = function (t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
            var parentIdx = response.parentChainId ? responses.findIndex(function (r) { return r.chain_id === response.parentChainId; }) : -1;
            var children = responses.filter(function (r) { return r.parentChainId && r.parentChainId === response.chain_id; }).length;
            var plain = String(response.technicalAnswer || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
            plain = plain.replace(/^(Answer|Explore|Synthesis|Results)\s*:\s*/i, '');
            var m = plain.match(/^(.{20,240}?[.!?])(\s|$)/);
            var conclusion = m ? m[1] : (plain.length > 240 ? plain.slice(0, 237) + '...' : plain);
            var rows = '<div class="wf-info-row"><span>Chain</span><b>' + (index + 1) + ' of ' + responses.length + ' <span class="wf-info-id">' + esc(response.chain_id || '') + '</span></b></div>';
            rows += '<div class="wf-info-row"><span>Follows</span><b>' + (parentIdx >= 0 ? 'chain ' + (parentIdx + 1) : 'the thread\'s start') + '</b></div>';
            rows += '<div class="wf-info-row"><span>Follow-ups</span><b>' + (children ? children : 'none') + '</b></div>';
            if (response.branches) rows += '<div class="wf-info-row"><span>Branches</span><b>' + response.branches + '</b></div>';
            if (conclusion) rows += '<div class="wf-info-row wf-info-conclusion"><span>Concluded</span><b>' + esc(conclusion) + '</b></div>';
            plotEl.innerHTML = '<div class="wf-info">' + rows + '</div>';
        }
    }

    // ── The drawer's foot ───────────────────────────────────

    // What the drawer's foot says of the map it holds until a box is under the pointer: what a click and the pointer
    // do - nothing, for a map with nothing on it
    function rest(words) {
        document.getElementById('nodeTaskContent').innerHTML = words ? '<span class="map-rest">' + words + '</span>' : '';
        document.getElementById('nodePlotPreview').innerHTML = '';
    }

    // ── Public API ──────────────────────────────────────────

    return { render: render, rest: rest, toggleFullscreen: toggleFullscreen };

})();