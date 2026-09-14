// Dialog markup contract (2026-09-08): every id and class the dialog's JS relies on exists in the
// re-marked HTML, and the shell's structure is in place. Parsed with the mini DOM, like the pane tests.
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
function fragment(id) { const s = html.indexOf(`id="${id}"`); const start = html.lastIndexOf('<div', s); let depth = 0, i = start; const re = /<\/?div\b[^>]*>/g; re.lastIndex = start; let m;
  while ((m = re.exec(html))) { if (m[0].startsWith('</')) { depth--; if (depth === 0) return html.slice(start, m.index + m[0].length); } else if (!m[0].endsWith('/>')) depth++; } return html.slice(start); }
function hooks(jsFile, prefix) { const js = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', jsFile), 'utf8');
  const ids = new Set([...js.matchAll(/getElementById\('([^']+)'\)/g)].map(m => m[1]).concat([...js.matchAll(new RegExp(`#${prefix}[^']*?#([\\w-]+)`, 'g'))].map(m => m[1])));
  const classes = new Set([...js.matchAll(/querySelector(?:All)?\('([^']+)'\)/g)].flatMap(m => [...m[1].matchAll(/\.([\w-]+)/g)].map(x => x[1])).concat([...js.matchAll(/closest\('\.([\w-]+)'\)/g)].map(m => m[1])));
  return { ids, classes }; }
// ---- the account dialog ----
const doc = makeDocument(); const root = doc.createElement('div'); root.innerHTML = fragment('subscriptionModal');
const { ids, classes } = hooks('subscription.js', 'subscriptionModal');
const inDialog = new Set(['subscriptionModal', 'saveSubscription', 'addFundsBtn', 'proceedToPayment', 'customAmount', 'totalAmount', 'queryUsageCount', 'queryUsageBadge', 'queryPriceDisplay', 'limitIndicator', 'integrationGrid', 'integrationCost', 'configDescription', 'accountBalance', 'modelConfigSection', 'balanceInfo']);
const missingIds = [...inDialog].filter(id => !root.querySelector('#' + id));
check('account dialog: every id subscription.js addresses exists in the new markup', missingIds.length === 0, missingIds.join(','));
const needClasses = ['close', 'subscription-tab', 'tab-content', 'tier-option', 'toggle-option', 'amount-btn', 'optional'].filter(c => classes.has(c) || c === 'optional');
const missingClasses = needClasses.filter(c => c !== 'optional' && !root.querySelector('.' + c));
check('account dialog: every hook class the JS queries exists (close, tabs, tab panes, tier options, toggles, amount buttons)', missingClasses.length === 0, missingClasses.join(','));
check('account dialog: the radios keep their names and values', root.querySelectorAll('input[name="model-tier"]').length === 2 && root.querySelectorAll('input[name="compute-tier"]').length === 3 && root.querySelector('input[value="managed"]'));
check('account dialog: four tabs with data-tab and four matching panes', root.querySelectorAll('.subscription-tab').length === 4 && ['models', 'compute', 'data', 'funds'].every(t => root.querySelector('#' + t + '-tab')));
check('account dialog: the shell is in place (header/body/footer, the close button in the header, dialog classes on the legacy element)',
  root.querySelector('.ui-dlg-h .x.close') && root.querySelector('.ui-dlg-b') && root.querySelector('.ui-dlg-f') && root.querySelector('#subscriptionModal').className.includes('ui-modal') && root.querySelector('.modal-content').className.includes('ui-dlg'));
check('account dialog: the mandatory state still has a rule that hides the close button', fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8').includes('#subscriptionModal.mandatory .ui-dlg-h .x.close { display: none; }'));
check('account dialog: subscription.css is retired (not linked); dialogs.css is', !html.includes("filename='css/subscription.css'") && html.includes("filename='css/dialogs.css'"));
// ---- the usage dialog ----
const uroot = doc.createElement('div'); uroot.innerHTML = fragment('usageTrackingModal');
const uids = ['usageTrackingModal', 'usagePeriodSelector', 'usageViewSelector', 'usageLoadingContainer', 'usageErrorContainer', 'usageErrorMessage', 'usageDataContainer', 'usagePeriodDescription', 'totalQueries', 'totalCost', 'totalInputTokens', 'totalOutputTokens', 'costChartData', 'tokenChartData'];
const umissing = uids.filter(id => !uroot.querySelector('#' + id));
check('usage dialog: every id usage-tracking.js addresses exists', umissing.length === 0, umissing.join(','));
check('usage dialog: the close button, the shell, and the charts section the height rule measures', uroot.querySelector('.ui-dlg-h .x.close') && uroot.querySelector('.ui-dlg-b') && uroot.querySelector('#usageTrackingModal .charts-section') && uroot.querySelector('#usageTrackingModal').className.includes('ui-modal'));
check('usage dialog: the period and view selects keep their option values', ['1_day', '7_days', '30_days', '90_days'].every(v => uroot.querySelector(`#usagePeriodSelector option[value="${v}"]`)) && ['agents', 'models', 'queries'].every(v => uroot.querySelector(`#usageViewSelector option[value="${v}"]`)));
check('usage dialog: usage-tracking.css is retired (not linked)', !html.includes("filename='css/usage-tracking.css'"));
const uj = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'usage-tracking.js'), 'utf8');
check('usage charts: colours come from the theme tokens, not a hard-coded palette', uj.includes("v('--accent-color'") && uj.includes("--c-kernel") && !uj.includes("'#1E2730'"));
// ---- the saved-workflows dialog (workflow-modal.js, workflow-replay.js, labels.js all reach into it) ----
const wroot = doc.createElement('div'); wroot.innerHTML = fragment('workflowManagerModal');
const wids = ['workflowManagerModal', 'workflowNewLabelInput', 'workflowAddLabelBtn', 'workflowLabelsList', 'workflowSearchInput', 'workflowSearchClear', 'workflowSearchSubmit', 'workflowChainsGrid'];
const wmissing = wids.filter(id => !wroot.querySelector('#' + id));
check('workflows dialog: every id its scripts address exists', wmissing.length === 0, wmissing.join(','));
const wclasses = ['workflow-modal-left', 'workflow-modal-right', 'workflow-section-header', 'workflow-search-container', 'workflow-modal-close', 'workflow-search-spinner', 'workflow-loading'];
const wmiss = wclasses.filter(c => !wroot.querySelector('.' + c));
check('workflows dialog: every structural class the scripts swap, replace or toggle exists (left/right panels, header, search container, close, spinner)', wmiss.length === 0, wmiss.join(','));
check('workflows dialog: the search container precedes the grid inside the right panel (the thread nav is inserted before the grid)', (() => { const r = wroot.querySelector('.workflow-modal-right'); const kids = r.elements.map(e => e.className); return kids.findIndex(c => c.includes('workflow-modal-header-row')) < kids.findIndex(c => c.includes('workflow-chains-grid')); })());
check('workflows dialog: workflow-modal.css and workflow-replay.css are retired (not linked)', !html.includes("filename='css/workflow-modal.css'") && !html.includes("filename='css/workflow-replay.css'"));
const dcss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'dialogs.css'), 'utf8');
check('workflows dialog: dialogs.css styles the generated cards, labels, thread nav and replay parts', ['.workflow-card', '.workflow-label-item', '.workflow-thread-nav', '.replay-dataset-card', '.replay-execute-btn', '.workflow-card-memory-badge'].every(c => dcss.includes(c)));
// ---- the JS-built dialogs: the scripts build the ids they later query, inside the shell ----
const dm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'dataset-manager.js'), 'utf8');
const dmroot = doc.createElement('div'); dmroot.innerHTML = dm.slice(dm.indexOf('<div class="modal-content'), dm.indexOf('`;', dm.indexOf('<div class="modal-content')));
check('dataset dialog: the script builds every id it queries, inside the shell (header/close/body panels)',
  ['primaryDatasetList', 'auxiliaryDatasetList', 'generatedDatasetList', 'datasetDetails'].every(id => dmroot.querySelector('#' + id)) && dmroot.querySelector('.ui-dlg-h .x.close') && dmroot.querySelector('.dataset-list-panel') && dmroot.querySelector('.dataset-details-panel') && dm.includes("modal.className = 'modal ui-modal'"));
const mr = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'memory-review.js'), 'utf8');
check('memory dialog: the script builds the shell and the body it renders into', mr.includes("'<div class=\"memory-modal ui-dlg\">'") && mr.includes('id="memoryReviewBody" class="memory-modal-body ui-dlg-b"') && mr.includes('memoryReviewClose'));
check('dataset-manager.css and memory.css are retired (not linked)', !html.includes("filename='css/dataset-manager.css'") && !html.includes("filename='css/memory.css'"));
check('dialogs.css keeps the two top-panel pills those sheets provided', dcss.includes('.dataset-manager-pill') && dcss.includes('.memory-review-pill'));
// ---- the save-this-chain dialog ----
const rroot = doc.createElement('div'); rroot.innerHTML = fragment('rankModal');
check('rank dialog: every id query-processing.js addresses exists (fill, value, hint, status, submit) and the ten segments with the threshold at 5',
  ['ratingFill', 'ratingValue', 'thresholdHint', 'rankStatusMessage', 'submit-rank'].every(id => rroot.querySelector('#' + id)) && rroot.querySelectorAll('.rating-segment').length === 10 && rroot.querySelector('.rating-segment.threshold-indicator[data-value="5"]') && rroot.querySelector('.ui-dlg-h .x.close'));
check('rank dialog: its rules left styles.css for dialogs.css', !fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'styles.css'), 'utf8').includes('.progress-rating-track') && dcss.includes('#rankModal .progress-rating-track'));
// ---- the prompt viewer ----
const ai = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'agent-instructions.js'), 'utf8');
check('prompt viewer: the script builds the shell with the ids it fills and the sections it toggles', ai.includes('id="agentInstructionsModal" class="agent-instructions-modal-container ui-modal-plain"') && ai.includes('id="systemInstructions"') && ai.includes('id="userInstructions"') && ai.includes('class="agent-instructions-close x"'));
check('agent-instructions.css is retired; the card button rules are kept', !html.includes("filename='css/agent-instructions.css'") && dcss.includes('.agent-instructions-btn'));
// ---- the integration dialogs: seven elements, one form ----
const intIds = {sweatstackModal: ['cycling-checkbox', 'running-checkbox', 'users-selection', 'startDate', 'endDate', 'modal-message', 'connectSweatstack'], sweatstackAuthenticatedModal: ['logoutSweatstack'],
  intervalsModal: ['intervalsStartDate', 'intervalsEndDate', 'wellness-checkbox', 'summary-checkbox', 'intervals-checkbox', 'intervals-modal-message', 'connectIntervals'], intervalsConfigModal: ['intervalsApiKeyStatus', 'intervalsApiKeyInput', 'intervals-config-message', 'removeIntervalsApiKey', 'saveIntervalsApiKey'],
  enduraModal: ['enduraRaceSelect', 'endura-modal-message', 'loadEnduraData'], enduraConfigModal: ['enduraApiKeyStatus', 'enduraApiKeyInput', 'endura-config-message', 'removeEnduraApiKey', 'saveEnduraApiKey']};
const intMissing = [];
for (const [mid, ids] of Object.entries(intIds)) { const r = doc.createElement('div'); r.innerHTML = fragment(mid); ids.forEach(id => { if (!r.querySelector('#' + id)) intMissing.push(mid + '#' + id); }); if (!r.querySelector('.ui-dlg-h .x.close')) intMissing.push(mid + ' close'); if (!r.querySelector('#' + mid).className.includes('integration-dialog')) intMissing.push(mid + ' class'); }
check('integration dialogs: every id the three scripts address exists, each in the shell with the shared integration-dialog class', intMissing.length === 0, intMissing.join(','));
const hookClasses = ['sport-option', 'metric-option', 'intervals-aux-option', 'endura-aux-option', 'circular-button', 'button-label', 'check-icon', 'api-key-status', 'date-input'];
check('integration dialogs: the hook classes the scripts query survive', hookClasses.every(c => html.includes('class="' + c) || html.includes(' ' + c + '"') || html.includes(' ' + c + ' ')));
check('integration dialogs: the SweatStack metrics are still rendered by the template loop', html.includes('{% for metric in sweatstack_metrics %}') && html.includes('{{ metric.value }}-checkbox'));
check('integration stylesheets are retired (not linked); one ruleset in dialogs.css', !html.includes("css/integrations/sweatstack.css") && !html.includes("css/integrations/intervals.css") && !html.includes("css/integrations/endura.css") && dcss.includes('.integration-dialog .int-options label'));
let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
