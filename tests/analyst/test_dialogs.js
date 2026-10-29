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
// ---- the saved-workflows dialog (workflow-modal.js and labels.js reach into it; workflow-replay.js is retired, 2026-10-11) ----
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
check('workflows dialog: dialogs.css styles the generated cards, labels and thread nav', ['.workflow-card', '.workflow-label-item', '.workflow-thread-nav', '.workflow-card-memory-badge'].every(c => dcss.includes(c)));
// the v1 replay view is retired with step 4 of the routines (docs/ROUTINES_DESIGN.md S10): its script is not linked, its
// dataset picker is not styled, the modal keeps no replay state, and the card's Replay button is gone with it
check('workflows dialog: workflow-replay.js is retired (not linked; no replay view or state snapshot in workflow-modal.js; no replay rules in dialogs.css)', !html.includes("filename='js/workflow-replay.js'") && !fs.existsSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-replay.js')) && !fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-modal.js'), 'utf8').match(/enterReplayView|isReplayView|modalStateSnapshot/) && !dcss.match(/replay-dataset|workflow-replay-theme|workflow-card-replay/));
// ---- the JS-built dialogs: the scripts build the ids they later query, inside the shell ----
const dm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'dataset-manager.js'), 'utf8');
const dmroot = doc.createElement('div'); dmroot.innerHTML = dm.slice(dm.indexOf('<div class="modal-content'), dm.indexOf('`;', dm.indexOf('<div class="modal-content')));
check('dataset dialog: the script builds every id it queries, inside the shell (header/close/body panels): the filter, the tree, the generated list and the details (2026-10-29: the tree replaces the Primary, Auxiliary and Store lists)',
  ['datasetFilter', 'datasetTree', 'generatedDatasetList', 'datasetDetails'].every(id => dmroot.querySelector('#' + id)) && !dmroot.querySelector('#primaryDatasetList') && !dmroot.querySelector('#storeList') && dmroot.querySelector('.ui-dlg-h .x.close') && dmroot.querySelector('.dataset-list-panel') && dmroot.querySelector('.dataset-details-panel') && dm.includes("modal.className = 'modal ui-modal'"));
check('dataset dialog (redesigned 2026-10-29): the tree\'s lines open their details, where the actions are - Load <dataset> / Load <dataset> to today / Forget <dataset> (off the Data tab and out of the cache, after asking), Load everything for the athlete - a dot and the words on every line for what is on the Data tab now (an indicator: no click on the dot, no legend), the caret folds, the filter narrows; a dataset alone is loaded without the frame (with_frame off, the dialog\'s own poller), pills come off through their own removers; no earlier loads, no quiet delete link; the columns of a second file under a small label; and dialogs.css styles the dots, the words, the facts, the action rows, the labels and one size for the dialog',
  ['data-act="load"', 'data-act="today"', 'data-act="forget"', 'ds-subj-head', 'ds-feed', 'ds-caret', 'ds-filter', 'ds-dot', 'ds-feed-state', 'ds-kv', 'ds-actions', 'ds-file', "fetch('/cache/forget'", "fetch('/intervals/load_data'", 'pollIntervalsJob(data.job_id', 'function pollDatasetJob', 'dsLoadStatus', 'from_store: !online', 'with_frame: withFrame', 'function onTab', 'function unloadFromTab', 'function forgetDataset', 'removeDatasetPill(p, null, true)', "on ? 'on the Data tab' : 'in the store only'", 'Load ${esc(what)} to today', 'Forget ${esc(what)}'].every(t => dm.includes(t))
  && !/data-act="use"|data-act="extend"|data-act="delete"|ds-link|ds-legend|click a dot|Delete from the store|in memory|ds-mem|openIntervalsLoad|showIntervalsModal\(|legacy|earlier loads|loadKinds|subject\.kinds/.test(dm) && !dm.includes("closest('.ds-feed .ds-dot')")
  && ['.ds-subj-head', '.ds-feed', '.ds-caret', '.ds-filter', '.ds-load-status', '.ds-dot.on', '.ds-feed-state.on', '.ds-kv', '.ds-actions', '.ds-row .hint', '.ds-file', '.ds-on', '.ds-off', '.dataset-action-btn.wide', '.ds-feed.active'].every(c => dcss.includes(c)) && /#datasetManagerModal \.ui-dlg \{[^}]*height: min\(86vh, 800px\)/.test(dcss) && !dcss.includes('.ds-link') && !dcss.includes('.ds-legend') && !dcss.includes('.ds-dot:hover') && !dm.includes('storeList') && !/\.ds-acts|\.ds-act\b/.test(dcss),
  ['ds-feed-state', 'function unloadFromTab', 'function forgetDataset'].filter(c => !dm.includes(c)).concat(['.ds-dot.on', '.ds-feed-state.on', '.ds-file'].filter(c => !dcss.includes(c))));
const FEEDN = dm.match(/const FEED_NAMES = \{[^}]*\}/)[0];
check('dataset dialog: the lines are exactly the datasets the Intervals.icu dialog offers plus the frame - Activities, Activity summary, Activity intervals, Wellness, Context (the calendar inside it), Rider profile - and a load of each asks for the dialog\'s kinds (the planned workouts with the context)',
  ["activities: 'Activities'", "summary: 'Activity summary'", "laps: 'Activity intervals'", "wellness: 'Wellness'", "context: 'Context'", "profile: 'Rider profile'"].every(t => FEEDN.includes(t)) && !/Calendar|chats:/.test(FEEDN)
  && dm.includes("context: ['context', 'plan']") && dm.includes("laps: ['intervals']") && dm.includes("profile: ['rider']"), FEEDN);
const ijs = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js'), 'utf8');
check('intervals.js puts the athlete\'s folder on the window\'s record when a load completes (the dialog\'s dots read it), and keeps one athlete on the Data tab: the other athletes\' pills listed by their folder, taken off at the dialog\'s completion and before a load from the cache dialog (after asking)',
  ijs.includes("folder: (job.result && job.result.subject && job.result.subject.folder) || ''") && ijs.includes('function intervalsOtherAthletePills') && ijs.includes('function intervalsOneAthlete') && ijs.includes('intervalsOneAthlete(dataInfo.folder)')
  && dm.includes('intervalsOtherAthletePills(folder)') && dm.includes("The Data tab holds another athlete's data"));
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
  intervalsModal: ['intervalsStartDate', 'intervalsEndDate', 'wellness-checkbox', 'summary-checkbox', 'intervals-checkbox', 'context-checkbox', 'intervals-refresh', 'intervals-modal-message', 'connectIntervals'], intervalsConfigModal: ['intervalsApiKeyStatus', 'intervalsApiKeyInput', 'intervals-config-message', 'removeIntervalsApiKey', 'saveIntervalsApiKey'],
  enduraModal: ['enduraRaceSelect', 'endura-modal-message', 'loadEnduraData'], enduraConfigModal: ['enduraApiKeyStatus', 'enduraApiKeyInput', 'endura-config-message', 'removeEnduraApiKey', 'saveEnduraApiKey']};
const intMissing = [];
for (const [mid, ids] of Object.entries(intIds)) { const r = doc.createElement('div'); r.innerHTML = fragment(mid); ids.forEach(id => { if (!r.querySelector('#' + id)) intMissing.push(mid + '#' + id); }); if (!r.querySelector('.ui-dlg-h .x.close')) intMissing.push(mid + ' close'); if (!r.querySelector('#' + mid).className.includes('integration-dialog')) intMissing.push(mid + ' class'); }
check('integration dialogs: every id the three scripts address exists, each in the shell with the shared integration-dialog class', intMissing.length === 0, intMissing.join(','));
const hookClasses = ['sport-option', 'metric-option', 'intervals-aux-option', 'endura-aux-option', 'circular-button', 'button-label', 'check-icon', 'api-key-status', 'date-input'];
check('integration dialogs: the hook classes the scripts query survive', hookClasses.every(c => html.includes('class="' + c) || html.includes(' ' + c + '"') || html.includes(' ' + c + ' ')));
check('integration dialogs: the SweatStack metrics are still rendered by the template loop', html.includes('{% for metric in sweatstack_metrics %}') && html.includes('{{ metric.value }}-checkbox'));
check('integration stylesheets are retired (not linked); one ruleset in dialogs.css', !html.includes("css/integrations/sweatstack.css") && !html.includes("css/integrations/intervals.css") && !html.includes("css/integrations/endura.css") && dcss.includes('.integration-dialog .int-options label'));
// ---- the store below the cache (docs/INCREMENTAL_LOADS_DESIGN.md, 2026-10-15): the download choice in the Intervals dialog, off; the load's line from core.js
// (2026-10-16: Refresh everything became a two-sided choice, Only what's new / Everything again; the hidden box keeps the state the script reads)
const iroot = doc.createElement('div'); iroot.innerHTML = fragment('intervalsModal');
check('Intervals dialog: Download is a two-sided choice - Only what\'s new on, Everything again - over a hidden box that is off by default, with one line on what each side does',
  iroot.querySelectorAll('#intervalsDownload [data-refresh]').map(b => b.textContent + ':' + b.className).join('|') === 'Only what’s new:on|Everything again:' && iroot.querySelector('#intervals-refresh').hasAttribute('hidden') && !iroot.querySelector('#intervals-refresh').hasAttribute('checked')
  && iroot.querySelector('.int-dl .help').textContent === 'what the store already holds is reused · or the whole window fetched afresh' && dcss.includes('.integration-dialog .int-dl'), iroot.querySelectorAll('#intervalsDownload [data-refresh]').map(b => b.textContent + ':' + b.className).join('|'));
// ---- the load dialogs' shared grammar (2026-10-16): the window first; Also load as cards of one size in the data's order; the status in the foot ----
const secs = iroot.querySelectorAll('.modal-section h4').map(h => h.textContent);
const icards = iroot.querySelectorAll('.int-cards .int-card');
check('Intervals dialog: the sections in order - Window, Also load, Download - and the five cards in the data\'s order (summary, intervals, wellness, rider profile, context), each a label with its checkbox, a tick, a name and a line; the Rider profile on (2026-10-16); Context on and spanning the row beneath the 2 x 2, with an empty slot for its codebook line',
  secs.join('|') === 'Window|Also load|Download' && icards.map(c => c.querySelector('input').id).join(',') === 'summary-checkbox,intervals-checkbox,wellness-checkbox,rider-checkbox,context-checkbox'
  && icards.every(c => c.className.includes('intervals-aux-option') && c.querySelector('.tick .check-icon') && c.querySelector('b').textContent && c.querySelector('.d').textContent)
  && icards[3].querySelector('input').hasAttribute('checked') && icards[3].querySelector('input').getAttribute('value') === 'rider' && icards[3].querySelector('b').textContent === 'Rider profile' && icards[3].querySelector('.d').textContent.includes('the settings the data is read against') && !icards[3].className.includes('span')
  && icards[4].querySelector('input').hasAttribute('checked') && !icards[0].querySelector('input').hasAttribute('checked') && icards[4].querySelector('b').textContent === 'Context' && icards[4].className.includes('span') && icards[4].querySelector('.d').textContent.includes('the planned workouts ride along'), secs.join('|') + ' ' + icards.map(c => c.querySelector('input').id).join(','));
check('Intervals dialog: the status line sits in the foot before the Load button; the title names Intervals.icu', iroot.querySelector('.ui-dlg-f #intervals-modal-message.status') && iroot.querySelector('.ui-dlg-f .sp') && iroot.querySelector('.ui-dlg-f #connectIntervals') && iroot.querySelector('.ui-dlg-h .title').textContent === 'Load data from Intervals.icu');
const sroot = doc.createElement('div'); sroot.innerHTML = fragment('sweatstackModal');
const eroot = doc.createElement('div'); eroot.innerHTML = fragment('enduraModal');
check('SweatStack dialog: the same grammar - Window first, then Athletes, Sports and Metrics as grids of equal columns; the message in the foot',
  sroot.querySelectorAll('.modal-section h4').map(h => h.textContent).join('|') === 'Window|Athletes|Sports|Metrics' && sroot.querySelectorAll('.int-options.int-chips').length === 3 && sroot.querySelector('.ui-dlg-f #modal-message.status') && dcss.includes('.integration-dialog .int-options.int-chips { display: grid; grid-template-columns: repeat(3, 1fr); }'));
check('Endura dialog: the race, then Also load as cards (the profile always on and disabled; up to three); the message in the foot; the logo in the header',
  eroot.querySelectorAll('.modal-section h4').map(h => h.textContent.trim().startsWith('Race') || h.textContent.trim().startsWith('Also load')).every(Boolean) && eroot.querySelectorAll('.int-cards .int-card.endura-aux-option').length === 4
  && eroot.querySelector('.int-card.always-selected input').hasAttribute('disabled') && eroot.querySelector('.h-note').textContent === '· up to three' && eroot.querySelector('.ui-dlg-f #endura-modal-message.status') && eroot.querySelector('.ui-dlg-h .int-logo'));
check('the cards\' rules: one size in a two-column grid, a span class for an odd card, the tick drawn from the hidden input (checked or the scripts\' selected class), the disabled state',
  dcss.includes('.integration-dialog .int-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }') && dcss.includes('.integration-dialog .int-cards .span { grid-column: 1 / -1; }') && dcss.includes('.integration-dialog .int-card:has(input:checked), .integration-dialog .int-card.selected {') && dcss.includes('.integration-dialog .int-card.disabled:not(.selected) { opacity: .5; }'));
const core = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'core.js'), 'utf8');
const storeLine = new Function(core.match(/function storeLine\(st\) \{[\s\S]*?\n\}\n/)[0] + '; return storeLine;')();
check('storeLine: the load\'s completion phrase - held and downloaded, all held, none held, a refresh, nothing without a window',
  storeLine({ window: 101, held: 91, fetched: 10 }) === '91 of 101 activities from the store, 10 downloaded' && storeLine({ window: 101, held: 101, fetched: 0 }) === 'all 101 activities from the store, nothing downloaded'
  && storeLine({ window: 91, held: 0, fetched: 91 }) === '91 activities downloaded' && storeLine({ window: 1, held: 0, fetched: 1 }) === '1 activity downloaded' && storeLine({ window: 101, held: 0, fetched: 101, refresh: true }) === '101 activities fetched again' && storeLine(null) === '' && storeLine({}) === '',
  [storeLine({ window: 101, held: 91, fetched: 10 }), storeLine({ window: 1, held: 0, fetched: 1 })]);
check('storeLine: a load from the store alone (2026-10-29) says nothing was fetched', storeLine({ window: 101, held: 101, fetched: 0, offline: true }) === 'all 101 activities from the store, nothing fetched' && storeLine({ window: 101, held: 90, fetched: 0, offline: true }) === '90 of 101 activities from the store, nothing fetched');
check('storeLine: the laps\' account when the laps file was asked (2026-10-29) - every lap from the store, some, none said nothing; not on a refresh',
  storeLine({ window: 101, held: 101, fetched: 0, laps: { window: 101, held: 101, fetched: 0 } }) === 'all 101 activities from the store, nothing downloaded; every lap from the store'
  && storeLine({ window: 101, held: 91, fetched: 10, laps: { window: 101, held: 91, fetched: 10 } }) === '91 of 101 activities from the store, 10 downloaded; laps: 91 of 101 from the store'
  && storeLine({ window: 91, held: 0, fetched: 91, laps: { window: 91, held: 0, fetched: 91 } }) === '91 activities downloaded' && storeLine({ window: 101, held: 0, fetched: 101, refresh: true, laps: { window: 101, held: 0, fetched: 101 } }) === '101 activities fetched again'
  && storeLine({ window: 5, held: 5, fetched: 0, laps: null }) === 'all 5 activities from the store, nothing downloaded',
  [storeLine({ window: 101, held: 91, fetched: 10, laps: { window: 101, held: 91, fetched: 10 } })]);
const ij = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js'), 'utf8');
check('intervals.js sends the flag with the load, says the store\'s line with the success message and puts the choice back on Only what\'s new after', ij.includes('refresh: refresh') && ij.includes("storeLine(job.result && job.result.store)") && ij.includes('setIntervalsRefresh(false);'));
// the Download choice driven on the mini DOM: a click on a side sets the hidden box and lights the side; the foot's store line
const dmx = makeDocument(); global.document = dmx; const dlHost = dmx.createElement('div'); dlHost.innerHTML = fragment("intervalsModal"); dmx.body.appendChild(dlHost);
const fetched = []; global.window = { authService: { fetch: async u => { fetched.push(u); return { ok: true, json: async () => ({ stores: [{ key_mark: 'abcd', activities: 101, chats: 40, from: '2025-10-18', to: '2026-10-08', size_mb: 12.3 }, { key_mark: 'efgh', activities: 60, from: '2026-07-01', to: '2026-08-30' }] }) }; } } };
const ijm = require(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js'));
ijm.initializeDownloadChoice(); const seg = dmx.getElementById('intervalsDownload');
seg.dispatch('click', seg.querySelector('[data-refresh="1"]'));
const after1 = { box: dmx.getElementById('intervals-refresh').checked, on: seg.querySelectorAll('.on').map(b => b.textContent).join() };
seg.dispatch('click', seg.querySelector('[data-refresh="0"]'));
const after0 = { box: dmx.getElementById('intervals-refresh').checked, on: seg.querySelectorAll('.on').map(b => b.textContent).join() };
ijm.setIntervalsRefresh(true); const afterSet = seg.querySelectorAll('.on').map(b => b.textContent).join();
check('the Download choice: Everything again sets the hidden box and lights its side alone; Only what\'s new clears it; setIntervalsRefresh drives both', after1.box === true && after1.on === 'Everything again' && after0.box === false && after0.on === 'Only what’s new' && afterSet === 'Everything again', [after1, after0, afterSet]);
(async () => { await ijm.showIntervalsStoreLine(); await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  const line = dmx.getElementById('intervals-modal-message').textContent;
  check('the foot\'s store line on opening: the activities held across the account\'s stores, the span from the earliest to the latest, and that only what the window lacks is fetched', fetched[0] === '/cache/inspect' && line === 'Store · 161 activities · 2025-10-18 → 2026-10-08 · only what the window lacks is fetched', line);
  global.document = doc; finish(); })();
function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
