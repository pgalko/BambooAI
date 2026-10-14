"""The coding pass at load (docs/CONTEXT_DESIGN.md §4 F1, §6): the context file read back from where the load wrote
it, every passage coded once in batches on the Coder seat, the renderings written into the file and the codes
file written beside it, the coder's proposals stored in the user's codebook. Runs on the app, where the model
layer and the codebook are; the executor only keeps the files. Nothing here is fatal to a load: a batch that
fails twice leaves its passages uncoded and the report counts them."""
from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Callable, Optional

import pandas as pd

from analyst import codebook as cb
from analyst import coder
from analyst import context as context_mod

logger = logging.getLogger(__name__)


def codes_path_for(notes_path: str) -> str:
    """The codes file beside the context file: context_notes_<window>.csv -> context_codes_<window>.csv."""
    return notes_path.replace("context_notes_", "context_codes_")


def code_context(instance, notes_path: str, progress: Optional[Callable[[int, int], None]] = None,
                 chain_id: Optional[str] = None) -> dict:
    """The pass over one loaded context file. Returns the report: passages, coded, uncoded, rendered, proposed,
    batches, failed_batches, unanswered, dropped (what the checks refused, by reason), codes_path,
    codebook_version, coder, seconds - and `error` when the file could not be read at all."""
    t0 = time.time()
    report = {"passages": 0, "coded": 0, "uncoded": 0, "rendered": 0, "proposed": 0, "batches": 0, "failed_batches": 0,
              "unanswered": 0, "dropped": {}, "codes_path": "", "codebook_version": 0, "coder": "", "seconds": 0.0}
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
    rows, renderings, proposals, dropped, seen = [], {}, [], Counter(), set()
    groups = coder.batches(passages)
    report["batches"] = len(groups)
    for k, batch in enumerate(groups, 1):
        if progress:
            try:
                progress(k, len(groups))
            except Exception:                                   # noqa: BLE001
                pass
        system, user = coder.coder_messages(vocabulary, batch)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        items, cut = [], False
        for attempt in (1, 2):
            try:
                reply = instance.models.llm_call(instance.log_and_call_manager, messages, agent=seat, chain_id=chain_id) or ""
            except Exception as exc:                            # noqa: BLE001
                logger.warning("the coder's call failed (batch %d, attempt %d): %s", k, attempt, exc)
                reply = ""
            items, cut = coder.parse_reply(reply)
            if items and not cut:
                break
        if not items:
            report["failed_batches"] += 1
            continue
        if cut:
            dropped["cut_reply"] += 1                           # what parsed is kept; the rest of the batch stays unanswered
        proposed_now = proposed_before | {p["code"] for p in proposals}
        v = coder.validate(items, batch, book_codes, proposed_now)
        rows.extend(v["rows"])
        renderings.update(v["renderings"])
        proposals.extend(v["proposals"])
        dropped.update(v["dropped"])
        seen |= v["seen"]

    # the renderings into the context file; the codes file beside it
    for uid, r in renderings.items():
        mask = notes["id"].astype(str) == uid
        notes.loc[mask, "lang"] = r["lang"]
        notes.loc[mask, "text_en"] = r["text_en"]
    codes_df = pd.DataFrame([dict(r, coder=report["coder"], codebook_version=report["codebook_version"]) for r in rows],
                            columns=context_mod.CODES_COLUMNS)
    codes_path = codes_path_for(notes_path)
    if not instance._put_aux_file(notes_path, notes.to_csv(index=False)):
        report["error"] = "the context file with its renderings could not be written back"
    if instance._put_aux_file(codes_path, codes_df.to_csv(index=False)):
        report["codes_path"] = codes_path
    else:
        report["error"] = "the codes file could not be written"

    # the codebook: proposals stored for the coach, the load's counts recorded
    book, added = cb.add_proposals(book, proposals, coder=report["coder"])
    cb.record_uses(book, Counter(r["code"] for r in rows))
    try:
        cb.save(storage, book)
    except OSError as exc:
        logger.warning("the codebook could not be saved: %s", exc)

    coded_ids = {r["id"] for r in rows}
    report.update({"coded": len(coded_ids), "uncoded": int(len(notes)) - len(coded_ids),
                   "rendered": sum(1 for r in renderings.values() if r["text_en"]), "proposed": len(added),
                   "proposals": added, "unanswered": int(len(notes)) - len(seen), "dropped": dict(dropped),
                   "seconds": round(time.time() - t0, 1)})
    return report
