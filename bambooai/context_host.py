"""The coding pass at load (docs/CONTEXT_DESIGN.md §4 F1, §6; §12 D1's fallback): the context file read back from
where the load wrote it, the passages the user's store has already coded reused, the rest coded in parallel
batches on the Coder seat, a second round for what the first left unanswered, the renderings written into the
file and the codes file written beside it, the coder's proposals stored in the codebook, the coded passages
remembered per subject. Runs on the app, in a thread of its own behind the load; the executor only keeps the
files. Nothing here is fatal to a load: a passage no call answered stays uncoded and the report counts it."""
from __future__ import annotations

import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import pandas as pd

from analyst import codebook as cb
from analyst import coder
from analyst import context as context_mod
from analyst.coded import CodedStore

logger = logging.getLogger(__name__)

PARALLEL = 6                 # calls in flight at once: six batches of twenty is a 120-passage window in one round


def codes_path_for(notes_path: str) -> str:
    """The codes file beside the context file: context_notes_<window>.csv -> context_codes_<window>.csv."""
    return notes_path.replace("context_notes_", "context_codes_")


def _call(instance, seat, chain_id, vocabulary, batch, earlier=None):
    """One batch through the Coder seat, with the passages before it for reference: (items, cut). A failed call is an
    empty reply."""
    system, user = coder.coder_messages(vocabulary, batch, earlier)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        reply = instance.models.llm_call(instance.log_and_call_manager, messages, agent=seat, chain_id=chain_id) or ""
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("the coder's call failed on a batch of %d: %s", len(batch), exc)
        reply = ""
    return coder.parse_reply(reply)


def code_context(instance, notes_path: str, progress: Optional[Callable[[int, int], None]] = None,
                 chain_id: Optional[str] = None, key_mark: Optional[str] = None) -> dict:
    """The pass over one loaded context file. Returns the report: passages, coded, reused, uncoded, rendered,
    proposed, batches, failed_batches, unanswered, dropped (what the checks refused, by reason), codes_path,
    codebook_version, coder, seconds - and `error` when the file could not be read at all."""
    t0 = time.time()
    report = {"passages": 0, "coded": 0, "reused": 0, "uncoded": 0, "rendered": 0, "proposed": 0, "batches": 0, "failed_batches": 0,
              "unanswered": 0, "labels": 0, "copies": 0, "dropped": {}, "codes_path": "", "codebook_version": 0, "coder": "", "seconds": 0.0}
    notes = instance._context_file(notes_path)
    if notes is None:
        report["error"] = "the context file could not be read"
        return report
    report["passages"] = int(len(notes))
    if not len(notes):
        return report
    storage = instance._user_storage()
    book = cb.load(storage)
    vocabulary = cb.vocabulary_text(book)
    book_codes, proposed_before = cb.active_codes(book), cb.proposed_codes(book)
    report["codebook_version"] = int(book.get("version", 1))
    seat = instance._coder_seat()
    try:
        model = instance.models.get_model_name(seat)
        model = model[0] if isinstance(model, (tuple, list)) else model
    except Exception:                                           # noqa: BLE001
        model = ""
    report["coder"] = str(model or seat)

    passages = [{k: ("" if pd.isna(v) else v) for k, v in r.items()} for r in notes.to_dict("records")]
    # a tag is a label, not a sentence: tallied on the map, never rendered or coded; a copy repeats an earlier passage's
    # words (copy_of, the executor's mark) and takes that passage's rendering, not codes of its own (2026-10-18)
    labels = [p for p in passages if str(p.get("kind") or "") == "tag"]
    copies = [p for p in passages if str(p.get("copy_of") or "").strip() and str(p.get("kind") or "") != "tag"]
    report["labels"], report["copies"] = len(labels), len(copies)
    aside = {str(p.get("id")) for p in labels + copies}
    to_read = [p for p in passages if str(p.get("id")) not in aside]
    # what an earlier load of this subject's data already established (D1's fallback)
    store = CodedStore(storage, key_mark).load() if key_mark else None
    known, todo = store.lookup(to_read, reading=coder.READING_VERSION) if store else ({}, list(to_read))
    rows, renderings = [], {}
    for uid, e in known.items():
        renderings[uid] = {"lang": e.get("lang", ""), "text_en": e.get("text_en", "")}
        for c in e.get("codes") or []:
            rows.append({"id": uid, "code": c["code"], "tone": c.get("tone", "neutral"), "quote": c.get("quote", ""), "status": c.get("status", "codebook"),
                         "coder": e.get("coder", ""), "codebook_version": e.get("codebook_version", report["codebook_version"]),
                         "direction": c.get("direction", ""), "basis": c.get("basis", ""), "about": c.get("about", "")})
    report["reused"] = len(known)

    proposals, dropped, seen = [], Counter(), set(known)
    new_rows, new_renderings = [], {}
    done_batches = [0]

    def run_round(group_list):
        """The batches called in parallel, validated in order (a proposal made in one batch is usable in the next)."""
        if not group_list:
            return
        with ThreadPoolExecutor(max_workers=min(PARALLEL, len(group_list))) as pool:
            replies = list(pool.map(lambda b: _call(instance, seat, chain_id, vocabulary, b, coder.earlier_for(to_read, b)), group_list))
        for batch, (items, cut) in zip(group_list, replies):
            done_batches[0] += 1
            if progress:
                try:
                    progress(done_batches[0], report["batches"])
                except Exception:                               # noqa: BLE001
                    pass
            if not items:
                report["failed_batches"] += 1
                continue
            if cut:
                dropped["cut_reply"] += 1                       # what parsed is kept; the rest of the batch goes to the second round
            proposed_now = proposed_before | {p["code"] for p in proposals}
            v = coder.validate(items, batch, book_codes, proposed_now)
            new_rows.extend(v["rows"])
            new_renderings.update(v["renderings"])
            proposals.extend(v["proposals"])
            dropped.update(v["dropped"])
            seen.update(v["seen"])

    groups = coder.batches(todo)
    report["batches"] = len(groups)
    run_round(groups)
    # the second round: only the passages no reply answered - a failed batch, or the tail of a cut reply
    left = [p for p in todo if str(p.get("id")) not in seen]
    if left:
        retry = coder.batches(left)
        report["batches"] += len(retry)
        run_round(retry)

    # the renderings into the context file; the codes file beside it
    rows.extend(dict(r, coder=report["coder"], codebook_version=report["codebook_version"]) for r in new_rows)
    renderings.update(new_renderings)
    for p in copies:                                            # a copy reads as the passage it repeats
        first = renderings.get(str(p.get("copy_of") or "").strip())
        if first:
            renderings[str(p.get("id"))] = dict(first)
    for uid, r in renderings.items():
        mask = notes["id"].astype(str) == uid
        notes.loc[mask, "lang"] = r["lang"]
        notes.loc[mask, "text_en"] = r["text_en"]
    order = {str(p.get("id")): i for i, p in enumerate(passages)}
    rows.sort(key=lambda r: order.get(str(r["id"]), 0))
    codes_df = pd.DataFrame(rows, columns=context_mod.CODES_COLUMNS)
    codes_df["day"] = context_mod.reading_days(codes_df, notes)          # the day each reading describes (patch 0206)
    codes_path = codes_path_for(notes_path)
    if not instance._put_aux_file(notes_path, notes.to_csv(index=False)):
        report["error"] = "the context file with its renderings could not be written back"
    if instance._put_aux_file(codes_path, codes_df.to_csv(index=False)):
        report["codes_path"] = codes_path
    else:
        report["error"] = "the codes file could not be written"

    # the codebook: proposals stored for the coach, the load's counts recorded; the store: what this pass established
    book, added = cb.add_proposals(book, proposals, coder=report["coder"])
    cb.record_uses(book, Counter(r["code"] for r in rows))
    try:
        cb.save(storage, book)
    except OSError as exc:
        logger.warning("the codebook could not be saved: %s", exc)
    if store is not None:
        try:
            store.remember(todo, new_rows, new_renderings, report["coder"], report["codebook_version"], reading=coder.READING_VERSION)
            store.save()
        except OSError as exc:
            logger.warning("the coded passages could not be saved: %s", exc)

    coded_ids = {r["id"] for r in rows}
    report.update({"coded": len(coded_ids), "uncoded": int(len(notes)) - len(coded_ids),
                   "rendered": sum(1 for r in renderings.values() if r["text_en"]), "proposed": len(added),
                   "proposals": added, "unanswered": len(to_read) - len(seen), "dropped": dict(dropped),
                   "seconds": round(time.time() - t0, 1)})
    return report
