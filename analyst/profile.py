"""The rider profile as the analyst meets it (docs/RIDER_PROFILE_DESIGN.md, 2026-10-16): the file the Intervals.icu
loader writes beside the data - the settings the data is read against, one row per setting - read back for the DATA
block. Nothing here names a setting: the line is assembled from the file's own rows (DESIGN_CHECKLIST C5), so an
account whose record holds other keys, or no custom items, reads as it is."""
import io
from typing import Optional

import pandas as pd

PROFILE_COLUMNS = ["section", "sport_types", "key", "value", "unit", "low", "high", "note"]
# the sections, in the file's order: the subject's measurements, the thresholds per sport group, the standard zones, the
# custom zone sets, the custom fields' meanings
SECTIONS = ("subject", "sport", "zone", "custom_zone", "custom_field")


def read_profile(text: str) -> pd.DataFrame:
    """The profile file's text as a frame of text cells (a blank stays blank; a missing column is added empty)."""
    df = pd.read_csv(io.StringIO(text or ""), dtype=str, keep_default_na=False) if (text or "").strip() else pd.DataFrame(columns=PROFILE_COLUMNS)
    for c in PROFILE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df


def _pairs(rows: pd.DataFrame) -> str:
    return ", ".join(f"{r['key']} {r['value']}" + (f" {r['unit']}" if str(r["unit"]) else "") for _, r in rows.iterrows() if str(r["value"]) != "")


def profile_line(df: Optional[pd.DataFrame]) -> str:
    """One line for DATA from the file's rows: the subject's measurements and each sport group's thresholds as `key value
    unit` (the model's estimates, keyed model_*, stay in the file), then what else the file holds, counted. '' for a
    file without rows."""
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
    counts = []
    n_zone = int((df["section"] == "zone").sum())
    if n_zone:
        counts.append(f"{n_zone} zone rows with their bounds")
    cz = df[df["section"] == "custom_zone"]
    if len(cz):
        sets = cz["key"].astype(str).str.split(":").str[0].nunique()
        counts.append(f"{len(cz)} custom zone rows in {sets} set{'s' if sets != 1 else ''}")
    n_cf = int((df["section"] == "custom_field").sum())
    if n_cf:
        counts.append(f"{n_cf} custom field definitions - the codes other files' columns carry, with their options")
    line = "; ".join(p for p in parts if p)
    if counts:
        line += ("; " if line else "") + "also in the file: " + ", ".join(counts)
    return line


def aux_head(path: str, df: Optional[pd.DataFrame]) -> str:
    """The DATA block's entry for the profile file: the path, the columns, the row count with what a row is, and the
    settings line - the rows themselves are the line's source, not a head of five."""
    n = len(df) if df is not None else 0
    cols = ", ".join(list(df.columns) if df is not None and len(df.columns) else PROFILE_COLUMNS)
    head = f"Path: {path}\nColumns: {cols}\nRows: {n} (one row per setting: section, key, value, unit, the bounds for a zone, a note; read the file with pandas)"
    line = profile_line(df)
    return head + (f"\nSettings: {line}" if line else "")
