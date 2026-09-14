// Memory Review — the promotion review's UI (step 27).
//
// Self-contained: injects its own trigger button and modal, house-styled
// via CSS variables. Appears only when the server reports promotable
// cards (page load, and the memory_review stream event after a rank).
// Each promotable card offers: hook polish (editable fields), merge of
// similar cards (checkboxes), retire, and promote. Only established
// cards govern; this is where advising becomes binding — or is refused.

(function () {
    'use strict';

    let promotableCache = [];
    let establishedCache = [];

    // ── The pill lives in the template, beside Dataset Cache, styled
    //    as its sibling; this module only reveals it, wires the click,
    //    and keeps the badge honest. ──
    function ensurePill() {
        const pill = document.getElementById('memoryReviewPill');
        if (pill && !pill.dataset.mrBound) {
            pill.dataset.mrBound = '1';
            pill.style.cursor = 'pointer';
            pill.addEventListener('click', openMemoryReview);
        }
        return pill;
    }

    // ── Modal (injected once; all styling in memory.css) ──
    function ensureModal() {
        let modal = document.getElementById('memoryReviewModal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'memoryReviewModal';
        modal.className = 'memory-modal-container ui-modal-plain';
        modal.innerHTML =
            '<div class="memory-modal ui-dlg">' +
            '<div class="memory-modal-header ui-dlg-h">' +
            '<div><div class="memory-modal-title title">Memory</div>' +
            '<div class="sub">methods this workspace has learned from the answers you kept</div></div>' +
            '<span class="sp"></span>' +
            '<button id="memoryReviewClose" class="memory-modal-close x" title="Close">×</button>' +
            '</div>' +
            '<div id="memoryReviewBody" class="memory-modal-body ui-dlg-b"></div>' +
            '</div>';
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeMemoryReview();
        });
        document.body.appendChild(modal);
        document.getElementById('memoryReviewClose')
            .addEventListener('click', closeMemoryReview);
        return modal;
    }

    function esc(t) {
        return String(t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function cardHtml(card) {
        const sims = (card.similar || []).map(s => {
            const nm = (s && s.name) || s;
            const st = (s && s.status) || 'candidate';
            const blocked = st !== 'candidate';
            const chip = blocked
                ? '<span class="memory-status-chip memory-chip-rule">' +
                  'standing rule</span>'
                : '<span class="memory-status-chip">candidate</span>';
            return '<label class="memory-similar-row' +
                (blocked ? ' memory-similar-blocked' : '') + '"' +
                (blocked ? ' title="Already a standing rule - remove it ' +
                    'below first if you really mean to replace it."' : '') +
                '><input type="checkbox" class="mr-absorb" value="' +
                esc(nm) + '"' + (blocked ? ' disabled' : '') +
                '> <code>' + esc(nm) + '</code> ' + chip + '</label>';
        }).join('');
        const flagged = card.note &&
            /review|echo|overlap|genericity/i.test(card.note);
        const flag = flagged
            ? '<span class="memory-flag" title="' + esc(card.note) + '">' +
              'Wording may need a tidy-up</span>'
            : '';
        return '<div class="mr-card memory-card" data-name="' +
            esc(card.name) + '">' +
            '<div class="memory-card-header">' +
            '<span class="memory-card-name">' + esc(card.name) + '</span>' +
            '<span class="memory-card-meta">proved in ' + card.distinct +
            ' saved answers</span></div>' +
            flag +
            '<div class="memory-field-label">Answers the question</div>' +
            '<textarea class="mr-aq memory-textarea" rows="2">' +
            esc(card.hooks.answers_question) + '</textarea>' +
            '<div class="memory-field-label">Use it when</div>' +
            '<textarea class="mr-uw memory-textarea" rows="2">' +
            esc(card.hooks.use_when) + '</textarea>' +
            (sims ? '<div class="memory-similar">' +
                '<div class="memory-field-label">Similar cards - merge ' +
                'them into this one?</div>' + sims + '</div>' : '') +
            '<div class="memory-actions">' +
            '<button class="mr-promote memory-btn memory-btn-primary">' +
            'Promote</button>' +
            '<button class="mr-merge memory-btn"' +
            (sims ? '' : ' disabled') + '>Merge selected</button>' +
            '<button class="mr-retire memory-btn memory-btn-danger ' +
            'memory-btn-right">Remove</button></div>' +
            '<div class="mr-status memory-action-status"></div>' +
            '</div>';
    }

    function establishedHtml() {
        if (!establishedCache.length) return '';
        const rows = establishedCache.map(c => {
            const b = c.body || {}, h = c.hooks || {};
            const field = (label, v) => v
                ? '<div class="memory-field-label">' + label + '</div>' +
                  '<div class="memory-detail-text">' + esc(v) + '</div>'
                : '';
            const detail =
                '<div class="memory-gov-detail" style="display:none;">' +
                field('Answers the question', h.answers_question) +
                field('Use it when', h.use_when) +
                field('Method', b.function_definition) +
                field('Assumes', b.assumes) +
                field('Limitations', b.limitations) +
                field('Rationale', b.rationale) +
                field('History', c.note) +
                '<div class="memory-card-meta" style="margin-top:6px;">' +
                'used ' + (c.use_count || 0) + ' times' +
                (c.last_used ? ' \u00b7 last ' + esc(c.last_used) : '') +
                '</div></div>';
            return '<div class="mr-gov memory-gov-row-wrap" data-name="' +
                esc(c.name) + '">' +
                '<div class="memory-gov-row">' +
                '<code>' + esc(c.name) + '</code>' +
                '<span class="memory-gov-meta">in ' + c.distinct +
                ' saved answers</span>' +
                '<button class="mr-gov-view memory-btn">View</button>' +
                '<button class="mr-gov-retire memory-btn ' +
                'memory-btn-danger">Remove</button>' +
                '<span class="mr-gov-status memory-action-status"></span>' +
                '</div>' + detail + '</div>';
        }).join('');
        return '<h4 class="memory-section-title" style="margin-top:18px;">' +
            'Standing rules</h4>' +
            '<p class="memory-section-sub">Your analyses follow these ' +
            'automatically. Remove one if it no longer matches how you ' +
            'work.</p>' + rows;
    }

    function render() {
        const body = document.getElementById('memoryReviewBody');
        const promoHead = promotableCache.length
            ? '<h4 class="memory-section-title">Ready to promote</h4>' +
              '<p class="memory-section-sub">These cards have proved ' +
              'themselves in three or more answers you saved. Promote ' +
              'one to make it a standing rule - tidy the wording first ' +
              'if it still reads like your original question.</p>'
            : '<p class="memory-empty">Nothing to review yet. A card ' +
              'appears here once it has helped in three answers you ' +
              'saved.</p>';
        body.innerHTML = promoHead + promotableCache.map(cardHtml).join('')
            + establishedHtml();
        body.querySelectorAll('.mr-gov').forEach(el => {
            const name = el.dataset.name;
            const status = el.querySelector('.mr-gov-status');
            el.querySelector('.mr-gov-view').addEventListener('click',
                () => {
                    const d = el.querySelector('.memory-gov-detail');
                    const open = d.style.display !== 'none';
                    d.style.display = open ? 'none' : 'block';
                    el.querySelector('.mr-gov-view').textContent =
                        open ? 'View' : 'Hide';
                });
            el.querySelector('.mr-gov-retire').addEventListener('click',
                () => {
                    if (!window.confirm('Remove "' + name + '"? Your ' +
                        'analyses will stop following this rule.')) return;
                    act(el, status, { action: 'retire', name: name },
                        'Removed.');
                });
        });
        body.querySelectorAll('.mr-card').forEach(el => {
            const name = el.dataset.name;
            const status = el.querySelector('.mr-status');
            el.querySelector('.mr-promote').addEventListener('click', () =>
                act(el, status, {
                    action: 'promote', name: name,
                    hooks: {
                        answers_question: el.querySelector('.mr-aq').value,
                        use_when: el.querySelector('.mr-uw').value
                    }
                }, 'Promoted - this card is now a standing rule.'));
            el.querySelector('.mr-retire').addEventListener('click', () =>
                act(el, status, { action: 'retire', name: name },
                    'Removed.'));
            el.querySelector('.mr-merge').addEventListener('click', () => {
                const absorb = Array.from(
                    el.querySelectorAll('.mr-absorb:checked'))
                    .map(c => c.value);
                if (!absorb.length) {
                    status.textContent = 'Tick at least one card to merge in.';
                    return;
                }
                act(el, status, { action: 'merge', name: name,
                                  absorb: absorb },
                    'Merged. You can promote it whenever you are ready.');
            });
        });
    }

    async function act(el, status, payload, doneMsg) {
        status.textContent = 'Working…';
        try {
            const r = await window.authService.fetch('/memory/review/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await r.json();
            if (data.ok) {
                status.textContent = doneMsg;
                await refresh();
            } else {
                status.textContent = 'Refused: ' + (data.reason || 'unknown');
            }
        } catch (e) {
            status.textContent = 'Error: ' + e.message;
        }
    }

    async function refresh() {
        try {
            const r = await window.authService.fetch('/memory/review');
            const data = await r.json();
            promotableCache = data.promotable || [];
            establishedCache = data.established || [];
        } catch (e) {
            promotableCache = [];
            establishedCache = [];
        }
        const pill = ensurePill();
        if (pill) {
            pill.style.removeProperty('display');
            const badge = document.getElementById('memoryReviewBadge');
            if (badge) {
                badge.style.display = promotableCache.length
                    ? 'inline-block' : 'none';
                badge.textContent = promotableCache.length;
            }
        }
        if (document.getElementById('memoryReviewModal') &&
            document.getElementById('memoryReviewModal').style.display ===
            'flex') {
            render();
        }
    }

    function openMemoryReview() {
        const modal = ensureModal();
        modal.style.display = 'flex';
        modal.style.pointerEvents = 'auto';
        render();
    }

    function closeMemoryReview() {
        const modal = document.getElementById('memoryReviewModal');
        if (modal) modal.style.display = 'none';
    }

    // The stream handler calls this when a rank crosses the threshold.
    window.memoryReviewReady = function (names) {
        promotableCache = [];  // stale until refreshed
        refresh();
    };

    // House-pattern init: core.js calls this from
    // continueAppInitialization, after auth has settled.
    let initialized = false;
    window.initializeMemoryReview = function () {
        if (initialized) return;
        initialized = true;
        refresh();
    };

    // Fallback only - if a stale core.js never calls the initializer,
    // check once, late, rather than never.
    window.addEventListener('load', () =>
        setTimeout(() => { if (!initialized) window.initializeMemoryReview(); },
                   8000));
})();
