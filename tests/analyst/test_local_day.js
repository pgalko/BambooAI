// The calendar day as the person sees it (2026-10-15): the loaders' dialogs and the routine run dialog had taken "today" from
// toISOString(), the UTC day - before 11:00 in Melbourne the Data tab's load and a run made minutes apart asked for windows
// a day apart, and the cache could never serve one from the other. core.js's localIsoDay and routines.js's isoDay give the
// local day; no toISOString() is left in the three dialogs. Run: node tests/analyst/test_local_day.js
'use strict';
process.env.TZ = 'Australia/Melbourne';
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..', '..', 'web_app', 'static', 'js');
const results = []; const check = (n, c, d) => results.push([n, !!c, d]);
const core = fs.readFileSync(path.join(root, 'core.js'), 'utf8');
const m = core.match(/function localIsoDay\(d\) \{[\s\S]*?\n\}\n/);
const localIsoDay = new Function(m[0] + '; return localIsoDay;')();
const morning = new Date(2026, 9, 15, 10, 29);          // 10:29 in Melbourne: still the 14th in UTC
check('core.js localIsoDay: the local calendar day, where the UTC day is the day before', localIsoDay(morning) === '2026-10-15' && morning.toISOString().slice(0, 10) === '2026-10-14', [localIsoDay(morning), morning.toISOString()]);
check('localIsoDay pads the month and the day', localIsoDay(new Date(2026, 0, 5, 12)) === '2026-01-05');
// routines.js: the run dialog's window ending today, by the same reckoning, the start by calendar days
const { makeDocument } = require(path.join(__dirname, 'minidom.js'));
const doc = makeDocument(); global.document = doc; global.window = { innerWidth: 1400 };
global.responses = []; global.currentResponseIndex = 0; global.currentData = {};
const comp = doc.createElement('div'); comp.innerHTML = '<textarea id="queryInput"></textarea><button id="submitQuery"></button><div class="tab-navigation"></div><div id="datasetStatusPillsContainer"></div>'; doc.body.appendChild(comp);
global.clearAllTabs = () => {}; global.paneRunIds = () => {}; global.paneRunStrip = () => {};
require(path.join(root, 'routines.js'));
const b = window.__routinesBuild;
check('routines.js isoDay agrees with localIsoDay on the morning that differs in UTC', b.isoDay(morning) === '2026-10-15' && b.isoDay(new Date(2026, 9, 15, 23, 30)) === '2026-10-15');
const src = { intervals: fs.readFileSync(path.join(root, 'integrations', 'intervals.js'), 'utf8'), sweatstack: fs.readFileSync(path.join(root, 'integrations', 'sweatstack.js'), 'utf8'), routines: fs.readFileSync(path.join(root, 'routines.js'), 'utf8') };
check('no dialog takes a day from toISOString() any more; the Intervals and SweatStack dialogs go through localIsoDay; the run dialog counts its window back in calendar days',
      !/toISOString\(\)/.test(src.intervals) && !/toISOString\(\)/.test(src.sweatstack) && !/toISOString\(\)/.test(src.routines)
      && (src.intervals.match(/localIsoDay\(/g) || []).length >= 3 && (src.sweatstack.match(/localIsoDay\(/g) || []).length >= 3     // fewer calls since 0165 (the bounds computed once per opening)
      && src.routines.includes("start.setDate(today.getDate() - span)"), [(src.intervals.match(/localIsoDay\(/g) || []).length, (src.sweatstack.match(/localIsoDay\(/g) || []).length]);
const fails = results.filter(r => !r[1]);
results.forEach(r => console.log((r[1] ? '  ok   ' : '  FAIL ') + r[0] + (r[1] ? '' : '  <- ' + String(r[2]).slice(0, 300))));
console.log('\n' + (results.length - fails.length) + ' passed, ' + fails.length + ' failed');
process.exit(fails.length ? 1 : 0);
