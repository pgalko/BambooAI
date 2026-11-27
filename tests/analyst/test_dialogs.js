// Dialog markup contract (2026-09-08): every id and class the dialog's JS relies on exists in the
// re-marked HTML, and the shell's structure is in place. Parsed with the mini DOM, like the pane tests.
'use strict';
const fs = require('fs'), path = require('path');
const { makeDocument, fragment: pageFragment } = require(path.join(__dirname, 'minidom.js'));
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'templates', 'index.html'), 'utf8');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const fragment = id => pageFragment(html, id);
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
// ---- the usage dialog (usage.js builds it, 2026-10-31; the old #usageTrackingModal markup and usage-tracking.js are retired) ----
check('usage dialog: no markup in the page (the script builds it); usage.js linked, usage-tracking.js gone; the settings entry is .usage-option', !html.includes('usageTrackingModal') && html.includes("filename='js/usage.js'") && !html.includes('usage-tracking.js') && html.includes('settings-option usage-option') && !html.includes("filename='css/usage-tracking.css'"));
const us = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'usage.js'), 'utf8');
check('usage dialog: the script builds the hooks it later queries - the period select, the compare toggle, the export button, the tabs, the body, the foot, the close - inside the shell, and addresses no id of the old dialog',
  ['data-period', 'data-compare', 'data-act="export"', 'data-tab="overview"', 'data-body', 'data-foot', 'class="close x"', "modal.className = 'modal ui-modal'", "modal.id = 'usageModal'"].every(t => us.includes(t)) && !us.includes('usageTrackingModal') && !us.includes('Plotly'));
check('usage charts: the series colours are classes over the --viz tokens (no hex in the script), so the SVG follows the theme', !/#[0-9a-fA-F]{6}\b/.test(us) && us.includes("'us-s' + (i + 1)") && fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'css', 'tokens.css'), 'utf8').includes('--viz-other'));
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
check('workflows dialog: dialogs.css styles the generated cards, labels and thread nav', ['.workflow-card', '.workflow-label-item', '.workflow-thread-nav', '.workflow-card-saved-badge'].every(c => dcss.includes(c)));
// the v1 replay view is retired with step 4 of the routines (docs/ROUTINES_DESIGN.md S10): its script is not linked, its
// dataset picker is not styled, the modal keeps no replay state, and the card's Replay button is gone with it
check('workflows dialog: workflow-replay.js is retired (not linked; no replay view or state snapshot in workflow-modal.js; no replay rules in dialogs.css)', !html.includes("filename='js/workflow-replay.js'") && !fs.existsSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-replay.js')) && !fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'workflow-modal.js'), 'utf8').match(/enterReplayView|isReplayView|modalStateSnapshot/) && !dcss.match(/replay-dataset|workflow-replay-theme|workflow-card-replay/));
// ---- the JS-built dialogs: the scripts build the ids they later query, inside the shell ----
const dm = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'dataset-manager.js'), 'utf8');
const dmroot = doc.createElement('div'); dmroot.innerHTML = dm.slice(dm.indexOf('<div class="modal-content'), dm.indexOf('`;', dm.indexOf('<div class="modal-content')));
check('dataset dialog: the script builds every id it queries, inside the shell (header/close/body panels): the filter, the tree, the generated list and the details (2026-10-29: the tree replaces the Primary, Auxiliary and Store lists)',
  ['datasetFilter', 'datasetTree', 'generatedDatasetList', 'datasetDetails'].every(id => dmroot.querySelector('#' + id)) && !dmroot.querySelector('#primaryDatasetList') && !dmroot.querySelector('#storeList') && dmroot.querySelector('.ui-dlg-h .x.close') && dmroot.querySelector('.dataset-list-panel') && dmroot.querySelector('.dataset-details-panel') && dm.includes("modal.className = 'modal ui-modal'"));
check('dataset dialog (redesigned 2026-10-29; the Load row 2026-11-08): the tree\'s lines open their details, where the actions are - the Load row (from → to within the plan\'s reach and window, the quick picks 3 m · 6 m · 1 y, Load all datasets / Load <dataset>; a window over the plan\'s is moved and said at Load; days the store does not hold go through Intervals.icu, the rest from the store) and Clear <dataset> / Clear the cache (after asking) - a dot and the words on every line for what is on the Data tab now (an indicator: no click on the dot, no legend), the caret folds, the filter narrows; a dataset alone is loaded without the frame (with_frame off, the dialog\'s own poller), pills come off through their own removers; no earlier loads, no quiet delete link, no Forget, no "to today"; the columns of a second file under a small label; and dialogs.css styles the dots, the words, the facts, the Load row, the labels and one size for the dialog',
  ['data-act="load"', 'data-act="pick"', 'data-act="forget"', 'ds-window', 'ds-picks', 'ds-subj-head', 'ds-feed', 'ds-caret', 'ds-filter', 'ds-dot', 'ds-feed-state', 'ds-kv', 'ds-actions', 'ds-file', "fetch('/cache/forget'", "fetch('/intervals/load_data'", 'pollIntervalsJob(data.job_id', 'function pollDatasetJob', 'dsLoadStatus', 'from_store: !online', 'with_frame: withFrame', 'function onTab', 'function unloadFromTab', 'function forgetDataset', 'removeDatasetPill(p, null, true)', "on ? 'on the Data tab' : 'in the store only'",
    'Load ${esc(what)}', 'Clear ${esc(what)}', 'window.DateWindow.check(dw, win.from, win.to', "const online = key && (win.from < span.from || win.to > span.to);", 'Up to ${esc(dw.windowLabel)} at a time. Days not in the cache are downloaded.', "Removes this athlete's data from the cache and the Data tab.", "[[92, '3 m'], [184, '6 m'], [365, '1 y']].filter(([d]) => d <= dw.window)"].every(t => dm.includes(t))
  && !/data-act="use"|data-act="extend"|data-act="delete"|data-act="today"|ds-link|ds-legend|click a dot|Delete from the store|in memory|ds-mem|openIntervalsLoad|legacy|earlier loads|loadKinds|subject\.kinds|Forget \$|to today|Load everything|function actionRows/.test(dm) && dm.includes("showIntervalsModal(d.athlete)") && dm.includes('function keyedWithoutData') && dm.includes('data-act="dialog"') && !dm.includes("closest('.ds-feed .ds-dot')")
  && ['.ds-subj-head', '.ds-feed', '.ds-caret', '.ds-filter', '.ds-load-status', '.ds-dot.on', '.ds-feed-state.on', '.ds-kv', '.ds-actions', '.ds-row .hint', '.ds-window .ui-input', '.ds-window .ds-picks > span', '.ds-window-hint', '.ds-file', '.ds-on', '.ds-off', '.dataset-action-btn.wide', '.ds-feed.active'].every(c => dcss.includes(c)) && /#datasetManagerModal \.ui-dlg \{[^}]*height: min\(86vh, 800px\)/.test(dcss) && !dcss.includes('.ds-link') && !dcss.includes('.ds-legend') && !dcss.includes('.ds-dot:hover') && !dm.includes('storeList') && !/\.ds-acts|\.ds-act\b/.test(dcss),
  ['data-act="pick"', 'ds-window', 'Clear ${esc(what)}', 'function unloadFromTab', 'function forgetDataset'].filter(c => !dm.includes(c)).concat(['.ds-window .ui-input', '.ds-window-hint'].filter(c => !dcss.includes(c))));
const FEEDN = dm.match(/const FEED_NAMES = \{[^}]*\}/)[0];
check('dataset dialog: the lines are exactly the datasets the Intervals.icu dialog offers plus the frame - Activities, Activity summary, Activity intervals, Wellness, Context (the calendar inside it), Rider profile - and a load of each asks for the dialog\'s kinds (the planned workouts with the context)',
  ["activities: 'Activities'", "summary: 'Activity summary'", "laps: 'Activity intervals'", "wellness: 'Wellness'", "context: 'Context'", "profile: 'Rider profile'"].every(t => FEEDN.includes(t)) && !/Calendar|chats:/.test(FEEDN)
  && dm.includes("context: ['context', 'plan']") && dm.includes("laps: ['intervals']") && dm.includes("profile: ['rider']"), FEEDN);
const ijs = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'intervals.js'), 'utf8');
const cip = ijs.slice(ijs.indexOf('function createIntervalsPill('), ijs.indexOf('function intervalsAuxDisplayName(')), cap = ijs.slice(ijs.indexOf('function createIntervalsAuxiliaryPills('), ijs.indexOf('function contextPillAdd('));
check('intervals.js puts the athlete\'s folder on the window\'s record when a load completes (the dialog\'s dots read it), and keeps one athlete on the Data tab where the pills are made (2026-10-29: whatever path brings them - the Intervals.icu dialog, the cache dialog, a routine): a frame pill takes the earlier frame\'s pill and the other athletes\' file pills off, a file pill the other athletes\' too; another athlete\'s file is any the loader writes (by its name) that is not under this athlete\'s views/, whatever path an earlier load gave it; the cache dialog asks first',
  ijs.includes("folder: (job.result && job.result.subject && job.result.subject.folder) || ''") && ijs.includes('function intervalsOtherAthletePills') && ijs.includes('function intervalsOneAthlete')
  && ijs.includes("const INTERVALS_LOADER_FILE = /^(activity_summary|wellness_data|activity_intervals|context_notes|context_codes|planned_workouts|rider_profile|custom_zone_times)_\\d{8}_to_\\d{8}\\.csv$/;")
  && ijs.includes("if (INTERVALS_LOADER_FILE.test(id.split('/').pop()) && !id.includes('/' + folder + '/views/')) out.push(p);") && !ijs.includes('match(/\\/(intervals\\/[^/]+)\\/views\\//)')
  && cip.includes('if (currentIntervalsState.pillId) { const old = document.getElementById(currentIntervalsState.pillId); if (old) old.remove(); }') && cip.indexOf('currentIntervalsState.dataInfo = dataInfo;') < cip.indexOf('intervalsOneAthlete(dataInfo.folder);')
  && cap.indexOf('intervalsOneAthlete(dataInfo && dataInfo.folder);') < cap.indexOf('createOrUpdateDatasetPill(') && (ijs.match(/intervalsOneAthlete\(/g) || []).length === 3
  && dm.includes('intervalsOtherAthletePills(folder)') && dm.includes("The Data tab holds another athlete's data"), [cip.length, cap.length, (ijs.match(/intervalsOneAthlete\(/g) || []).length]);
check('dataset-manager.css and memory.css are retired (not linked)', !html.includes("filename='css/dataset-manager.css'") && !html.includes("filename='css/memory.css'"));
check('dialogs.css keeps the top-panel pill the dataset sheet provided', dcss.includes('.dataset-manager-pill'));
// ---- 2.8: the old memory is retired - the Memory dialog and the rating step are gone, Save as favourite is one click ----
const staticDir = path.join(__dirname, '..', '..', 'web_app', 'static');
const allCss = ['styles.css', 'dialogs.css', 'shell.css', 'components.css', 'tabs.css'].map(f => fs.readFileSync(path.join(staticDir, 'css', f), 'utf8')).join('\n');
const pageJs = fs.readdirSync(path.join(staticDir, 'js')).filter(f => f.endsWith('.js') && !f.includes('.min.')).map(f => fs.readFileSync(path.join(staticDir, 'js', f), 'utf8')).join('\n');
check('the Memory dialog is gone (2.8): no script, no rail button, no rule, no call for it',
  !fs.existsSync(path.join(staticDir, 'js', 'memory-review.js')) && !/memory-review|memoryReview/.test(html + allCss + pageJs) && !pageJs.includes('/memory/review'));
check('the rating step is gone (2.8): no dialog in the page, no rule for it, and the scripts neither open it nor send a rating',
  !/rankModal|rating-segment|submit-rank/.test(html + allCss + pageJs) && !/currentRankData|showRankModal|submit_rank|isTrajectoryRank/.test(pageJs)
  && !/\brank:/.test(fs.readFileSync(path.join(staticDir, 'js', 'query-processing.js'), 'utf8')));
check('a saved chain\'s badge in Saved workflows says how it was saved, in plain words', pageJs.includes("? 'You saved this chain' : 'Saved with its thread'") && !/agent memory/i.test(pageJs));
// ---- the prompt viewer ----
const ai = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'agent-instructions.js'), 'utf8');
check('prompt viewer: the script builds the shell with the ids it fills and the sections it toggles', ai.includes('id="agentInstructionsModal" class="agent-instructions-modal-container ui-modal-plain"') && ai.includes('id="systemInstructions"') && ai.includes('id="userInstructions"') && ai.includes('class="agent-instructions-close x"'));
check('agent-instructions.css is retired; the card button rules are kept', !html.includes("filename='css/agent-instructions.css'") && dcss.includes('.agent-instructions-btn'));
// ---- the integration dialogs: seven elements, one form ----
const intIds = {sweatstackModal: ['cycling-checkbox', 'running-checkbox', 'users-selection', 'startDate', 'endDate', 'modal-message', 'connectSweatstack'], sweatstackAuthenticatedModal: ['logoutSweatstack'],
  intervalsModal: ['intervalsStartDate', 'intervalsEndDate', 'wellness-checkbox', 'summary-checkbox', 'intervals-checkbox', 'context-checkbox', 'intervals-refresh', 'intervals-modal-message', 'connectIntervals'], intervalsConfigModal: ['intervalsApiKeyStatus', 'intervalsAthletes', 'intervalsApiKeyInput', 'intervals-config-message', 'saveIntervalsApiKey'],
  enduraModal: ['enduraRaceSelect', 'endura-modal-message', 'loadEnduraData'], enduraConfigModal: ['enduraApiKeyStatus', 'enduraApiKeyInput', 'endura-config-message', 'removeEnduraApiKey', 'saveEnduraApiKey']};
const intMissing = [];
for (const [mid, ids] of Object.entries(intIds)) { const r = doc.createElement('div'); r.innerHTML = fragment(mid); ids.forEach(id => { if (!r.querySelector('#' + id)) intMissing.push(mid + '#' + id); }); if (!r.querySelector('.ui-dlg-h .x.close')) intMissing.push(mid + ' close'); if (!r.querySelector('#' + mid).className.includes('integration-dialog')) intMissing.push(mid + ' class'); }
check('integration dialogs: every id the three scripts address exists, each in the shell with the shared integration-dialog class', intMissing.length === 0, intMissing.join(','));
const hookClasses = ['sport-option', 'metric-option', 'intervals-aux-option', 'endura-aux-option', 'circular-button', 'check-icon', 'api-key-status', 'date-input'];
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
const secs = iroot.querySelectorAll('.modal-section h4').map(h => h.textContent.trim());
const icards = iroot.querySelectorAll('.int-cards .int-card');
check('Intervals dialog: the sections in order - Athlete (2026-10-30: the roster with its find box and the line to Settings), Window, Also load, Download - and the five cards in the data\'s order (summary, intervals, wellness, rider profile, context), each a label with its checkbox, a tick, a name and a line; the Rider profile on (2026-10-16); Context on and spanning the row beneath the 2 x 2, with an empty slot for its codebook line',
  secs.join('|') === 'Athlete|Window|Also load|Download' && iroot.querySelector('.int-athlete-section .int-athlete-wrap #intervalsRoster') && iroot.querySelector('.int-athlete-section .int-athlete-find #intervalsAthleteFind') && iroot.querySelector('.int-athlete-section #intervalsAthleteNone').textContent.includes('Settings') && iroot.querySelector('.int-athlete-section h4 #intervalsAthleteNote') && icards.map(c => c.querySelector('input').id).join(',') === 'summary-checkbox,intervals-checkbox,wellness-checkbox,rider-checkbox,context-checkbox'
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
check('a load\'s close shuts only the Intervals.icu dialog it was scheduled for (2026-11-06; since 2026-11-27 one counter for the three load dialogs, core.js): every opening is counted, and the close schedules itself for the opening it found',
  ij.includes("modal.style.display = 'flex';\n        loadDialogOpened(modal);") && ij.includes("if (!note) closeLoadDialogSoon(document.getElementById('intervalsModal'), hideIntervalsModal);") && !ij.includes('intervalsModalOpens'));
check('intervals.js sends the flag with the load, says the counts when it is in and puts the choice back on Only what\'s new after', ij.includes('refresh: refresh') && ij.includes("say.end(true, intervalsLoadedLine(job.result && job.result.store), note);") && ij.includes('setIntervalsRefresh(false);'));
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
// the plan's reach and window (2026-11-08, docs/DATASETS_DESIGN.md §18): one rule for the three pickers, checked at Load, never while typing
global.localIsoDay = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const DW = ijm.DateWindow, T = new Date(2026, 10, 8), pro = DW.of({ window_days: 365, reach_days: 1461, window_label: '1 year', reach_label: '4 years' }), old = DW.of({ max_days: 35 }), none = DW.of(null);
check('DateWindow.of: the route\'s reach and window with their words; an older answer with max_days alone is a window that is also the reach; no answer is three months, a year back',
  pro.reach === 1461 && pro.window === 365 && pro.windowLabel === '1 year' && old.reach === 35 && old.window === 35 && old.windowLabel === '35 days' && none.window === 92 && none.reach === 92);
check('DateWindow.bounds and line: from the reach to today; "up to 1 year at a time · back to 8 Nov 2022"', JSON.stringify(DW.bounds(pro, T)) === JSON.stringify({ min: '2022-11-08', max: '2026-11-08' }) && DW.line(pro, T) === 'up to 1 year at a time · back to 8 Nov 2022');
check('DateWindow.check: a calendar year passes with no note; two years with the end set last move the start up a year and say so; with the start set last the end moves down; a start before the reach moves to it; an end after today moves to today; a window with a date missing is left alone',
  JSON.stringify(DW.check(pro, '2023-01-01', '2023-12-31', 'end', new Date(T))) === JSON.stringify({ start: '2023-01-01', end: '2023-12-31', note: '' })
  && JSON.stringify(DW.check(pro, '2022-01-01', '2023-12-31', 'end', new Date(T))) === JSON.stringify({ start: '2022-12-31', end: '2023-12-31', note: 'Up to 1 year at a time: the start moved to 31 Dec 2022.' })
  && JSON.stringify(DW.check(pro, '2023-01-01', '2024-12-31', 'start', new Date(T))) === JSON.stringify({ start: '2023-01-01', end: '2024-01-01', note: 'Up to 1 year at a time: the end moved to 1 Jan 2024.' })
  && JSON.stringify(DW.check(pro, '2022-01-01', '2022-12-01', 'end', new Date(T))) === JSON.stringify({ start: '2022-11-08', end: '2022-12-01', note: 'Data goes back 4 years: the start moved to 8 Nov 2022.' })
  && JSON.stringify(DW.check(pro, '2026-10-01', '2027-01-01', 'end', new Date(T))) === JSON.stringify({ start: '2026-10-01', end: '2026-11-08', note: 'The end moved to today.' })
  && JSON.stringify(DW.check(pro, '', '2026-11-08', 'end', new Date(T))) === JSON.stringify({ start: '', end: '2026-11-08', note: '' }), [DW.check(pro, '2022-01-01', '2023-12-31', 'end', new Date(T)), DW.check(pro, '2023-01-01', '2024-12-31', 'start', new Date(T))]);
check('the Intervals.icu dialog: the bounds are the reach, the default start the window back, the heading\'s note the line, and Load runs the check - the moved dates written in and said, Load pressed again; nothing rewrites a date while it is typed',
  ij.includes("const { min: lo, max: hi } = DateWindow.bounds(dw);") && ij.includes("if (!startDateInput.value) startDateInput.value = localIsoDay(DateWindow.plus(new Date(), -dw.window));") && ij.includes("if (note) note.textContent = DateWindow.line(dw);")
  && ij.includes("const fit = DateWindow.check(dw, dateRange.start, dateRange.end, intervalsLastChanged);") && ij.includes("showIntervalsMessage(fit.note, 'error');") && !ij.includes("'Date range cannot exceed 1 year.'") && !/addEventListener\('change'/.test(ij.slice(ij.indexOf('const DateWindow'), ij.indexOf('async function applyIntervalsDateLimits')))
  && html.includes('<h4>Window <span class="h-note" id="intervalsWindowNote"></span></h4>'));
// the roster (2026-10-30): the athletes with a key and what the store holds for each, the last loaded first; the foot's store line is the picked athlete's
const tree = { sources: [{ source: 'intervals', subjects: [{ id: 'i1', name: 'Second Athlete', folder: 'intervals/i1', last_load: 1800000000, feeds: [{ feed: 'activities', count: 640, from: '2025-10-31', to: '2026-10-29' }] },
                                                          { id: 'i0', name: 'First Athlete', folder: 'intervals/i0', last_load: 1799900000, feeds: [{ feed: 'activities', count: 512, from: '2025-11-01', to: '2026-10-28' }] }] }] };
const roster = ijm.intervalsRosterOf([{ id: 'i0', name: 'First Athlete', added: '2026-10-01T00:00:00' }, { id: 'i1', name: 'Second Athlete', added: '2026-10-02T00:00:00' }, { id: 'i9', name: 'Ninth Athlete', added: '2026-10-29T00:00:00' }, { id: '', name: '' }], tree);
ijm.renderIntervalsAthletePicker(roster);
const rows = dmx.querySelectorAll('#intervalsRoster .row').map(r => [r.dataset.athlete, r.className, r.querySelector('.ini').textContent, r.querySelector('.who b').textContent, r.querySelector('.facts').textContent]);
const line1 = dmx.getElementById('intervals-modal-message').textContent;
check('the roster: the last loaded first, then the one with a key and nothing held, then the key not named yet; the initials, the name, the facts (the activities, the span, when loaded; "nothing held yet"; "named by the next load"); the first row lit and its id the one picked; the foot line that athlete\'s store',
  roster.map(a => a.id).join() === 'i1,i0,i9,' && rows[0][1] === 'row on' && rows[0][2] === 'SA' && rows[0][3] === 'Second Athlete' && rows[0][4] === '640 activities · 2025-10-31 → 2026-10-29 · loaded ' + ijm.intervalsFactsOf(roster[0]).split('loaded ')[1]
  && rows[1][1] === 'row' && rows[2][4].endsWith('nothing held yet') && rows[2][4].startsWith('key added') && rows[3][3] === 'a key stored earlier' && rows[3][4] === 'its athlete is named by the next load'
  && ijm.intervalsAthleteId() === 'i1' && line1 === 'Store · Second Athlete · 640 activities · 2025-10-31 → 2026-10-29 · only what the window lacks is fetched', [rows, line1]);
ijm.intervalsPickAthlete('i9');
const line2 = dmx.getElementById('intervals-modal-message').textContent;
const find = dmx.getElementById('intervalsAthleteFind'); find.value = 'nin'; ijm.intervalsFilterRoster();
const narrowed = { shown: dmx.querySelectorAll('#intervalsRoster .row').filter(r => !r.className.includes('hidden')).map(r => r.dataset.athlete), count: dmx.getElementById('intervalsAthleteCount').textContent };
check('a click on a row picks it (the foot line follows: nothing in the store for them yet); the find box narrows the rows by name and says how many of how many', ijm.intervalsAthleteId() === 'i9' && line2 === 'Nothing in the store for Ninth Athlete yet · the first load fills it; later loads fetch only what they lack'
  && narrowed.shown.join() === 'i9' && narrowed.count === '1 of 4 · Enter picks the first', [line2, narrowed]);
check('the initials: two words give two letters, one word one, none the id\'s first two', ijm.intervalsInitials('First Athlete', 'i0') === 'FA' && ijm.intervalsInitials('Solo', 'i0') === 'S' && ijm.intervalsInitials('', 'i77') === 'I7');
// ---- the end of a load (2026-11-27, docs/DATASETS_DESIGN.md §19, the product owner's pick of three mockups): one look of the Load
// button for each moment of a load, the counts and what was not loaded in the foot, the dialog closing itself
const coreJs = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'core.js'), 'utf8');
Object.assign(global, new Function(coreJs.match(/const LOAD_DONE_MS = [\s\S]*?\nfunction closeLoadDialogSoon\(modal, hide\) \{[\s\S]*?\n\}\n/)[0] + '; return { LOAD_DONE_MS, setLoadButton, loadDialogOpened, closeLoadDialogSoon };')());
const lb = dmx.getElementById('connectIntervals');
const drawnHtml = lb.innerHTML, drawnTitle = lb.getAttribute('title'), drawnLabel = lb.getAttribute('aria-label');
const look = () => ({ state: lb.dataset.state, cls: lb.className, disabled: !!lb.disabled, text: lb.textContent.trim(), tick: lb.innerHTML.includes('<polyline points="20 6 9 17 4 12"'), drawn: lb.innerHTML === drawnHtml, title: lb.getAttribute('title'), label: lb.getAttribute('aria-label') });
setLoadButton(lb, 'busy'); const busyL = look();
setLoadButton(lb, 'done'); const doneL = look();
setLoadButton(lb, 'close'); const closeL = look();
setLoadButton(lb, 'idle'); const idleL = look();
check('the Load button\'s four looks (core.js): busy - its loading class, pressed no more, its own markup (the plane and Load) and title; done - "Loaded" with a tick, no loading class, nothing to press, said so to a reader too; close - "Close", pressable; idle - the page\'s markup, title and label back',
  LOAD_DONE_MS === 1500 && busyL.state === 'busy' && /\bloading\b/.test(busyL.cls) && busyL.disabled && busyL.drawn && busyL.text === 'Load' && busyL.title === drawnTitle && busyL.label === drawnLabel
  && doneL.state === 'done' && /\bdone\b/.test(doneL.cls) && !/\bloading\b/.test(doneL.cls) && doneL.disabled && doneL.text === 'Loaded' && doneL.tick && doneL.title === 'Loaded' && doneL.label === 'Loaded'
  && closeL.state === 'close' && !closeL.disabled && closeL.text === 'Close' && !/\b(done|loading)\b/.test(closeL.cls) && closeL.label === 'Close' && closeL.title === 'Close'
  && idleL.state === 'idle' && !idleL.disabled && idleL.drawn && idleL.title === drawnTitle && idleL.label === drawnLabel && !/\b(done|loading)\b/.test(idleL.cls), [busyL, doneL, closeL, idleL]);
const ld = ijm.intervalsLoadedLine;
check('the counts once a load is in (the product owner: the essentials): how many activities and how many of them were new - nothing new, all new, all downloaded again, one activity, thousands; the cache dialog\'s load from the store alone; nothing without a window',
  ld({ window: 14, held: 12, fetched: 2 }) === '14 activities · 2 new' && ld({ window: 14, held: 14, fetched: 0 }) === '14 activities · nothing new' && ld({ window: 14, held: 0, fetched: 14 }) === '14 activities · all new'
  && ld({ window: 14, held: 9, fetched: 14, refresh: true }) === '14 activities · all downloaded again' && ld({ window: 1, held: 0 }) === '1 activity · all new' && ld({ window: 1200, held: 1000 }) === '1,200 activities · 200 new'
  && ld({ window: 101, held: 101, offline: true }) === '101 activities · from the store' && ld({ window: 101, held: 90, offline: true }) === '90 of 101 activities · from the store' && ld({ window: 0 }) === '' && ld(null) === '',
  [ld({ window: 14, held: 12 }), ld({ window: 1200, held: 1000 }), ld({ window: 101, held: 90, offline: true })]);
const nl = ijm.intervalsNotLoaded;
check('what a load did not bring, and why: a file not written said as its dataset not loaded, any other warning as a sentence of its own, the Context\'s failed calls counted; nothing when everything came',
  nl({ warnings: ['no wellness file: the window has no wellness days'] }) === 'Wellness not loaded: the window has no wellness days.'
  && nl({ warnings: ['no activity intervals file: no laps came back for the window', "the subject's record could not be fetched, so there is no rider profile in this load"] }) === "Activity intervals not loaded: no laps came back for the window. The subject's record could not be fetched, so there is no rider profile in this load."
  && nl({ warnings: ['no activity summary file: the window has no activities'], context: { passages: 212, failed: ['the messages of activity 7 could not be fetched (HTTPError)', 'the calendar entries could not be fetched (HTTPError)'] } }) === 'Activity summary not loaded: the window has no activities. Context: 2 calls failed.'
  && nl({ context: { failed: ['x'] } }) === 'Context: 1 call failed.' && nl({ warnings: [], context: { passages: 3, failed: [] } }) === '' && nl(null) === '' && nl({}) === '',
  [nl({ warnings: ['no wellness file: the window has no wellness days'] }), nl({ warnings: ['no activity summary file: the window has no activities'], context: { failed: ['a', 'b'] } })]);
const pl = ijm.intervalsProgressLine;
check('a step of the load as the foot says it: a count as "5 of 14", the three dots one character, no percent; nothing said yet is "Loading…"',
  pl('Downloading activities... (5/14)') === 'Downloading activities · 5 of 14' && pl('Parsing activity data... (3/14)') === 'Parsing activity data · 3 of 14' && pl('Connecting to Intervals.icu...') === 'Connecting to Intervals.icu…'
  && pl('The store holds all 14 activities of this window; nothing to download') === 'The store holds all 14 activities of this window; nothing to download' && pl('') === 'Loading…' && pl(undefined) === 'Loading…', [pl('Downloading activities... (5/14)'), pl('Connecting to Intervals.icu...')]);
const ivModal = dmx.getElementById('intervalsModal'), ivMsg = dmx.getElementById('intervals-modal-message');
const timers = [], realTimeout = global.setTimeout;
global.setTimeout = (fn, ms) => { timers.push([fn, ms]); return timers.length; };
ivModal.style.display = 'flex'; loadDialogOpened(ivModal); setLoadButton(lb, 'busy');
ijm.intervalsLoadEnded(true, '14 activities · 2 new', '');
const ended = { text: ivMsg.textContent, cls: ivMsg.className, button: look(), timers: timers.map(t => t[1]) };
timers.splice(0).forEach(([fn]) => fn());
const closedAfter = ivModal.style.display;
ivModal.style.display = 'flex'; loadDialogOpened(ivModal); setLoadButton(lb, 'busy');
ijm.intervalsLoadEnded(true, '14 activities · 2 new', 'Wellness not loaded: the window has no wellness days.');
const noted = { text: ivMsg.textContent, button: look(), timers: timers.length };
ijm.intervalsLoadEnded(false, 'Failed: the executor did not answer');
const failedL = { text: ivMsg.textContent, cls: ivMsg.className, button: look() };
setLoadButton(lb, 'busy'); ijm.intervalsLoadEnded(true, '14 activities · 2 new', '');
ivModal.style.display = 'none'; ivModal.style.display = 'flex'; loadDialogOpened(ivModal);         // closed and opened again within the moment
timers.splice(0).forEach(([fn]) => fn());
const reopened = ivModal.style.display;
global.setTimeout = realTimeout;
check('a load from the dialog ends: the counts in the foot as the done line (no colour of success), "Loaded" where the button was, the dialog closing itself LOAD_DONE_MS later; with a note the note beside the counts and the button closing the dialog, nothing scheduled; a failure in the error line with Load back; a close scheduled for one opening leaves the dialog opened again since',
  ended.text === '14 activities · 2 new' && /\bdone-message\b/.test(ended.cls) && !/\b(success|error|loading)-message\b/.test(ended.cls) && ended.button.state === 'done' && ended.button.text === 'Loaded' && JSON.stringify(ended.timers) === '[1500]' && closedAfter === 'none'
  && noted.text === '14 activities · 2 new. Wellness not loaded: the window has no wellness days.' && noted.button.state === 'close' && !noted.button.disabled && noted.timers === 0
  && failedL.text === '✗ Failed: the executor did not answer' && /\berror-message\b/.test(failedL.cls) && failedL.button.state === 'idle' && !failedL.button.disabled && failedL.button.drawn
  && reopened === 'flex', [ended, closedAfter, noted, failedL, reopened]);
setLoadButton(lb, 'busy'); ijm.renderIntervalsAthletePicker(roster); const keptBusy = lb.disabled;
setLoadButton(lb, 'idle'); lb.disabled = true; ijm.renderIntervalsAthletePicker(roster); const freed = lb.disabled;
check('the roster drawn again while a load runs keeps the button pressed no more; on an idle dialog it sets the button by the athletes', keptBusy === true && freed === false, [keptBusy, freed]);
const en = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'endura.js'), 'utf8');
const body = (src, name) => { const a = src.indexOf('function ' + name + '('), b = src.slice(a + 1).search(/\n\s*(async )?function /); return src.slice(a, b < 0 ? undefined : a + 1 + b); };      // one function's text
const ss = fs.readFileSync(path.join(__dirname, '..', '..', 'web_app', 'static', 'js', 'integrations', 'sweatstack.js'), 'utf8');
check('the three dialogs end a load the same way: the button busy while it runs, done once the data is in and the dialog closing itself, back to idle on a failure and at every opening unless a load still runs; no script keeps a button helper of its own, the old success line or a caption to fill',
  [ij, en, ss].every(s => s.includes(", 'busy');") && s.includes(", 'done')") && s.includes(", 'idle');") && s.includes('closeLoadDialogSoon(') && s.includes('loadDialogOpened(modal);') && s.includes(".dataset.state !== 'busy'") && !s.includes('Data loaded successfully') && !s.includes('button-label'))
  && !ij.includes('function setIntervalsButtonLoading') && !ss.includes('function setButtonLoading') && ij.includes("if (connectButton.dataset.state === 'close') { hideIntervalsModal(); return; }")
  && !body(ij, 'showIntervalsMessage').includes("case 'success':") && !body(ss, 'showModalMessage').includes("case 'success':") && !ij.includes('function contextReportLine'));
check('Endura\'s line keeps the dialog\'s classes as its state changes (2026-11-27: the whole class was replaced and the line lost its look), and a failed load stays in the foot; SweatStack\'s foot says the page\'s own note at every opening (the old one came back after a load as a longer sentence)',
  en.includes("messageElement.classList.remove('error-message', 'loading-message');") && !body(en, 'showMainMessage').includes('className = ') && en.includes('try { await loadRaceData(raceId, auxDatasets); } catch (e) {')
  && ss.includes("sweatstackIdleNote = document.getElementById('modal-message')?.innerHTML || '';") && ss.includes('showModalMessage(sweatstackIdleNote);') && !ss.includes('Note: More metrics'));
check('the foot\'s second caption is gone - from the three load dialogs and the two config dialogs - with its rules; grey and still while a load runs, "Loaded" without a frame once it is in, the counts\' line in its own size and grey',
  !html.includes('button-label') && !dcss.includes('.integration-dialog .button-label') && dcss.includes('.integration-dialog .circular-button.loading { opacity: 1; border-color: var(--border-tertiary); color: var(--text-quaternary); pointer-events: none; }')
  && dcss.includes('.integration-dialog .circular-button.loading svg { animation: none; }') && dcss.includes('.integration-dialog .circular-button.done { opacity: 1; border-color: transparent;') && dcss.includes('.integration-dialog .int-message.done-message { font-size: var(--fs-meta); color: var(--text-secondary); }'));
check('the Dataset cache dialog\'s Load hears how an Intervals.icu load goes through callbacks - the step, the end with its counts and note - and no longer reads the Intervals.icu dialog\'s line; a note keeps the cache dialog open, and its one-dataset loads say what was not loaded in the same words',
  dm.includes('pollIntervalsJob(data.job_id, { start: from, end: to }, kinds, {') && dm.includes("end: (ok, line, note) => done(ok, ok ? ['Loaded' + (line ? ' \\u00b7 ' + line : ''), note].filter(Boolean).join('. ') : line, !!note)")
  && !dm.includes("getElementById('intervals-modal-message')") && dm.includes('if (ok && !stays) setTimeout(hideModal, 1500);') && dm.includes("const note = typeof intervalsNotLoaded === 'function' ? intervalsNotLoaded(job.result) : '';") && !dm.includes('Not written'));
// a load started from the cache dialog: pollIntervalsJob with a report - the step and the end go there; the Intervals.icu dialog's foot is left as it stood
(async () => {
  const said = [], ticks = [], realInterval = global.setInterval, realClear = global.clearInterval, realLater = global.setTimeout, realLog = console.log, realWarn = console.warn;
  global.setInterval = fn => { ticks.push(fn); return ticks.length; }; global.clearInterval = () => {}; global.setTimeout = () => 0; console.log = console.warn = () => {};
  const steps = [{ status: 'processing', message: 'Downloading activities... (5/14)', percent: 35 },
                 { status: 'completed', result: { store: { window: 14, held: 12, fetched: 2 }, warnings: ['no wellness file: the window has no wellness days'], shape: [10, 3], columns: [], aux_datasets: [], subject: { folder: 'intervals/i0' } } }];
  global.window.authService = { fetch: async () => ({ ok: true, json: async () => steps.shift() }) };
  setLoadButton(lb, 'idle'); ivMsg.textContent = 'the foot as it stood';
  global.window.Intervals.pollJob('j9', { start: '2026-08-01', end: '2026-10-30' }, [], { progress: line => said.push(['progress', line]), end: (ok, line, note) => said.push(['end', ok, line, note]) });
  try { await ticks[0](); await ticks[0](); } finally { global.setInterval = realInterval; global.clearInterval = realClear; global.setTimeout = realLater; console.log = realLog; console.warn = realWarn; }
  check('a load started elsewhere hears how it goes through its report - the step as the foot would say it, then the end with the counts and the note - and the Intervals.icu dialog\'s foot is left as it stood',
    JSON.stringify(said) === JSON.stringify([['progress', 'Downloading activities · 5 of 14'], ['end', true, '14 activities · 2 new', 'Wellness not loaded: the window has no wellness days.']]) && lb.dataset.state === 'idle' && ivMsg.textContent === 'the foot as it stood', [said, lb.dataset.state, ivMsg.textContent]);
  global.document = doc; finish();
})();
function finish() {
  let fails = 0; for (const [n, ok, d] of results) { console.log((ok ? '  ok   ' : '  FAIL ') + n + (ok ? '' : '  <- ' + (d || ''))); if (!ok) fails++; }
  console.log(`\n${results.length - fails} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
}
