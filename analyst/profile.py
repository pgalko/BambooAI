"""The rider profile as the analyst meets it (docs/RIDER_PROFILE_DESIGN.md, 2026-10-16): the file the Intervals.icu
loader writes beside the data - the settings the data is read against, one row per setting - read back for the DATA
block. Nothing here names a setting: the line is assembled from the file's own rows (DESIGN_CHECKLIST C5), so an
account whose record holds other keys, or no custom items, reads as it is."""
import io
import re
from typing import Optional

import pandas as pd

PROFILE_COLUMNS = ["section", "sport_types", "key", "value", "unit", "low", "high", "note"]
# the sections, in the file's order: the subject's measurements, the thresholds per sport group, the standard zones, the
# custom zone sets, the custom fields' meanings, the subjective scales the account tracks with the end that is good
SECTIONS = ("subject", "sport", "zone", "custom_zone", "custom_field", "scale")
# what a custom zone set is, for the line - said only when the file has custom_zone rows: the sets are the account's own
# (set by hand, from testing), not the platform's defaults, and they are the ones meant when intensity is read
CUSTOM_SETS_RULE = ("the custom zone sets are the account's own, set by hand rather than the platform's defaults, and take precedence "
                    "over the standard zones when reading intensity - time in them is in the custom zone times file, the standard "
                    "zones' times in the summary file")


def read_profile(text: str) -> pd.DataFrame:
    """The profile file's text as a frame of text cells (a blank stays blank; a missing column is added empty)."""
    df = pd.read_csv(io.StringIO(text or ""), dtype=str, keep_default_na=False) if (text or "").strip() else pd.DataFrame(columns=PROFILE_COLUMNS)
    for c in PROFILE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df


def _sets(cz: pd.DataFrame) -> list:
    """The custom zone sets as the line names them, in the file's order: the set's code (the zone times file's set_code),
    its name when it says more than the code, and the stream it is cut on - `TymeWearVE on tidal_volume_min` (2026-10-18:
    with the sets only counted, two runs had to guess which one was the ventilatory set, and one guessed the breathing
    rate's)."""
    codes = cz["key"].astype(str).str.split(":").str[0].tolist()
    out, seen = [], set()
    for code, unit, note in zip(codes, cz["unit"].astype(str), cz["note"].astype(str)):
        if code in seen:
            continue
        seen.add(code)
        m = re.search(r"set '([^']*)'", note)
        name = m.group(1) if m else ""
        same = re.sub(r"\W", "", name).lower() == re.sub(r"\W", "", code).lower()
        out.append(code + (f" '{name}'" if name and not same else "") + (f" on {unit}" if unit else ""))
    return out


def _pairs(rows: pd.DataFrame) -> str:
    return ", ".join(f"{r['key']} {r['value']}" + (f" {r['unit']}" if str(r["unit"]) else "") for _, r in rows.iterrows() if str(r["value"]) != "")


def _scales(sc: pd.DataFrame) -> str:
    """The scale rows as one part of the line: the keys, then the range and the note they share - `soreness, sleepQuality
    1-4 (the wellness file's subjective scales: a bigger number is worse, 1 the good end ...)`; each row whole when they
    differ (2026-10-18: nothing had said which end of a scale was good, and a run read one the wrong way round)."""
    values, notes = set(sc["value"].astype(str)), set(sc["note"].astype(str))
    if len(values) == 1 and len(notes) == 1:
        note = notes.pop()
        return f"{', '.join(sc['key'].astype(str))} {values.pop()}" + (f" ({note})" if note else "")
    return ", ".join(f"{r['key']} {r['value']}" + (f" ({r['note']})" if str(r["note"]) else "") for _, r in sc.iterrows())


def profile_line(df: Optional[pd.DataFrame]) -> str:
    """One line for DATA from the file's rows: the subject's measurements and each sport group's thresholds as `key value
    unit` (the model's estimates, keyed model_*, stay in the file), the scales the account tracks with the end that is
    good, then what else the file holds, counted. '' for a file without rows."""
    if df is None or not len(df):
        return ""
    parts = []
    subject = df[df["section"] == "subject"]
    if len(subject):
        parts.append(_pairs(subject))
    for types, rows in df[df["section"] == "sport"].groupby("sport_types", sort=False):
        shown = rows[~rows["key"].astype(str).str.startswith("model_")]
        if len(shown):
            parts.append(f"{types or 'every sport'}: {_pairs(shown)}")
    sc = df[df["section"] == "scale"]
    if len(sc):
        parts.append(_scales(sc))
    counts = []
    n_zone = int((df["section"] == "zone").sum())
    if n_zone:
        counts.append(f"{n_zone} zone rows with their bounds")
    cz = df[df["section"] == "custom_zone"]
    if len(cz):
        sets = _sets(cz)
        counts.append(f"{len(cz)} custom zone rows in {len(sets)} set{'s' if len(sets) != 1 else ''} ({'; '.join(sets)})")
    n_cf = int((df["section"] == "custom_field").sum())
    if n_cf:
        counts.append(f"{n_cf} custom field definitions - the codes other files' columns carry, with their options")
    line = "; ".join(p for p in parts if p)
    if counts:
        line += ("; " if line else "") + "also in the file: " + ", ".join(counts)
    if len(cz):
        # the rule about what a custom set is (2026-10-16, Palo: a coach's own zones come from testing and are the ones meant),
        # said only when the account has any - an account without them reads nothing of it
        line += "; " + CUSTOM_SETS_RULE
    return line


def aux_head(path: str, df: Optional[pd.DataFrame]) -> str:
    """The DATA block's entry for the profile file: the path, the columns, the row count with what a row is, and the
    settings line - the rows themselves are the line's source, not a head of five."""
    n = len(df) if df is not None else 0
    cols = ", ".join(list(df.columns) if df is not None and len(df.columns) else PROFILE_COLUMNS)
    head = f"Path: {path}\nColumns: {cols}\nRows: {n} (one row per setting: section, key, value, unit, the bounds for a zone, a note; read the file with pandas)"
    line = profile_line(df)
    return head + (f"\nSettings: {line}" if line else "")
