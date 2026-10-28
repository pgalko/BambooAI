# The reach record — design v1.0 (2026-10-28)

What a cell touched outside the data, recorded by the kernel and reported when the analysis completes. The question
behind it (the product owner, 2026-10-27, after Cohere's note on an open-weight model that reached out unasked): the
platform claims transparency, but nothing in it caught a model that downloads something or sends the data somewhere.
The answer is observation first, prevention later: the kernel records every door a cell leaves through, the person
sees the record where they read the run, and a tally over the store shows the pattern per model. The blacklist stays
as it was; one address is refused on top of it.

The story in one paragraph. A chain ends and its closing card says *1 reach outside the data (1 not asked for) · 1
cell not run*: cell 17 sent 42 KB to an address the question never named, and the attempt after it was refused
because it imported `socket`. The row of cell 17 in the pane carries the same tag in the kernel's sand; the
Investigation tab shows the refused cell with a *Not run* line instead of a red error; the code map's summary lists
the reach beside *Worth checking*, a click away from the step. A month later `tools/reaches_report.py` says which
models reach out, how often, to where, and whether anyone asked them to.

## 1. Rules

1. **Observation, not prevention.** The record changes nothing the cell does. The two exceptions are old and small:
   the blacklist, which refuses a cell before it runs (unchanged in substance), and the cloud instance metadata
   address, refused by the kernel because it answers with the box's own credentials.
2. **Grounded.** A record says what the kernel saw at a door it wraps: a connection, a file opened, a name read, a
   program started. Where the kernel cannot see (section 6), the design says so; nothing is inferred.
3. **Invisible to the model.** Nothing of the record enters any prompt. The analyst's feedback on a refused cell is
   the notice it always had.
4. **The question decides "asked for".** A reach is *asked for* when the question, or an earlier question of the
   thread, names the host (or the domain it sits under), the file, the environment name or the program - a
   substring test, nothing cleverer. "Fetch it from GitHub" does not name `api.github.com`, and the card says so.
5. **A refused cell is its own state.** Not a failure of the code (the code never ran) and not a success: `In [–]`,
   the kernel's sand, *not run*, counted apart from the failed attempts everywhere.
6. **Hosted and self-hosted alike, for now.** The blacklist applies everywhere, as before. A setting that relaxes it
   for self-hosted boxes is a product decision not taken.

## 2. What the kernel records

The worker script (`delve/kernel.py`, the reaches block; the executor image carries the same file) wraps the doors
once per process and records only while a cell runs (`G["_IN_CELL"]`):

| door | what is recorded | the record |
|---|---|---|
| `socket.connect`, `connect_ex`, `sendto` | the host (the name the cell resolved, else the address), the port, the connections, the bytes each way through `send`/`sendall`/`recv`/`recv_into`/`recvfrom`, TLS through `SSLSocket.send`/`read`, a failed connection's error; a unix socket as `unix:<path>` | `{"kind": "net", "host", "ip", "port", "out", "in", "n", "tls", "blocked", "failed", "line"}` |
| `socket.getaddrinfo` | a name resolved and never connected (a resolved-and-connected name folds into its connection) | `{"kind": "dns", "host", "line"}` |
| `socket.listen` | a listening port opened | `{"kind": "listen", "host", "port", "line"}` |
| `open`, `io.open`, `os.open`, `os.listdir`, `os.scandir` | a file opened or a folder listed outside the data, when the cell chose the path (its own frame, or the path written in its code), always when written, always under the box's own places (`/etc`, `/root`, `/home`, `/run`, `/var/run`, `/var/lib`, `/app` outside the datasets, `/srv`, `/opt`, a dotfile) | `{"kind": "file", "path", "op": read/write/list, "via": code/library, "line"}` |
| `os.environ` | a name the cell read; `*` when it walked the whole environment | `{"kind": "env", "name", "line"}` |
| `os.system`, `os.popen`, `subprocess.Popen` | a program the cell started, past the blacklist's spelling (`from os import popen`) | `{"kind": "process", "command", "via", "line"}` |

A library's listing of a folder on the import path (its scan for package metadata, which in the image lists `/app`)
is not a reach; the cell's own listing of such a folder is. "The data" is the dataset the kernel loaded, the person's own datasets folder (the auxiliary files live there), the
generated folder, the plots folder, temp, `/dev`, python's own trees (`/usr`, `sys.prefix`, site-packages), the
matplotlib and user caches. What libraries read on a box as a matter of course (`/etc/localtime`, `/etc/ssl`,
`/etc/fonts`, `/etc/mime.types`, the font scan's `fc-list`, cgroup files under `/proc` and `/sys`) is not a reach.
`line` is the cell line of the top-level statement the call ran from, through any helper, as RESULT records it.
Records merge per cell by host and port, path and operation, name, command; forty are kept per cell and the rest
is one count (`{"kind": "more", "n"}`).

The kernel also reports the box once per process (`kernel.sandbox_facts`): the user and whether it is root, the
effective capabilities with the notable ones named (`sys_admin`, `net_admin`, `net_raw`, `sys_ptrace`,
`dac_override`...), seccomp (off, strict, filter), `no_new_privs`, the container seen (`/.dockerenv`, the cgroup),
the mounts that are not virtual, whether the docker socket is present, and whether the instance metadata address
answers (one connection with a half-second timeout). It rides on `/kernel/start` and `/health`.

## 3. Where it goes

- `kernel.execute` → `last_reaches`, `last_refused` (the restricted word); `kernel_service /kernel/execute` →
  `reaches`, `refused`; `kernel_client.RemoteKernel` → the same attributes; `tools.run_cell` → a fifth value
  `{"reaches", "refused"}`; `tools.sandbox(kernel)`.
- `Turn.reaches` (each record with `asked`), `Turn.refused`, `Run.sandbox` - in the thread store with everything
  else. `analyst/reach.py`: `mark` (the `asked` flag), `line` (one record in words), `chip` (a cell's tag), `summary`
  (the run's report), `summary_of_record` (the same from a chain record), `sandbox_line`.
- The session's events: a cell event carries `reaches` and `refused`; the pane's `pane_cell` carries `refused` and
  the chip, `pane_run_end` the summary and the refused count (`failed` leaves refused cells out).
- The code map's record: each cell's `reaches`, a failed attempt's `refused`, the run's `sandbox`; the view: a step
  row's `reach` chip, a failed row's `refused`, `view["reaches"]`; the meta line's *n cells not run*.

## 4. Where it shows

The stream pane: a tag after the cell's peek (`↓ 1.3 MB from host`, `↑ 42 KB to host:port`, `read /etc/passwd`,
`env HOME`, `ran echo`, `n reaches outside the data`), plain when asked for, the kernel's sand when not, the lines
as its hover; a refused cell as `⊘ In [–] not run: restricted operation (word) · not run`, neither red nor
clickable. The closing card, under the replay line: the heading with the counts, one line per reach with its cell
and tag (*the question named it* / *not asked for* / *refused*), the refused attempts (`attempt after cell n`), the
box in one line; a run that reached nothing says *No reaches outside the data* in one faint line with the sandbox as
its hover; an executor that predates the record shows nothing. The Investigation tab: the same tag in the cell's
header; a refused cell as `In [–]` with a *Not run* line. The code map: the chip among the step's chips, the refused
attempt as its own row, the *Reaches outside the data* section between the data and *Worth checking*.

## 5. The tally

`python3 tools/reaches_report.py [--root DIR] [--days N | --all]` reads every thread under `storage/<user>/threads`
and the run logs under `logs/<user>/` (for the model that ran each chain: the most frequent model among the chain's
calls that were not the rewrite, the reading or the review), and prints: runs, cells, reaches and the share of cells;
per model, runs, cells, fetched and sent (asked / not), files, environment names, programs, refused cells, the hosts
not asked for; the lines not asked for with their cell and question; the refused words; the sandbox line of every
run. Nothing is sent anywhere.

## 6. Not seen, by design or for now

A connection made in C (libpq, pycurl, a compiled extension); a library's own choice of path outside the sensitive
places (a cell that hands a computed path to pandas is seen only under those places); the bytes of a connection
that outlives the cell in a thread; a cell killed by the time limit (its records die with the worker); the replay and
the routines, which re-run the committed cells on the script route - they were observed when the chain ran; and
whether the reach was *right*, which stays with the reader.

## 7. Decisions taken (the product owner, 2026-10-27/28)

1. Observe first; deny egress on the hosted boxes later, once the pattern is known.
2. The blacklist stays everywhere, unchanged in substance. Two faults in it fixed: the `os.exec` and `os.spawn`
   entries had matched nothing (the word boundary after the entry), and the text of an f-string counted as code,
   so `f"http://{host}/x"` was refused as the `http` module.
3. The instance metadata address is refused by the kernel.
4. Red for a failure of the code; the kernel's sand for a cell the executor refused.
5. The report on the closing card, the tags in the pane and the notebook, the section in the code map, the tally
   script - as mocked up and approved.
6. Not built, to ask: a setting relaxing the blacklist for self-hosted boxes; an egress allow-list; the record on
   the script route (replay, routines).
