"""
Dataset I/O and schema for the inverted-core entry point (step 5).

Lean by design: the premium Investigator orients itself from a compact schema
(columns, dtypes, null %, sample values, numeric ranges) on step 1. There is no
heavy two-phase orientation agent and no pre-baked KEY_CONSTRAINTS block — the
old data_profile's steering is exactly what mis-framed the EEDR run.
"""

import os
import sys


def load_dataset(path):
    """Load a dataset, inferring format from extension."""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".tsv":
            return pd.read_csv(path, sep="\t", low_memory=False)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        if ext in (".parquet", ".pq"):
            return pd.read_parquet(path)
        if ext == ".json":
            return pd.read_json(path)
        if ext == ".jsonl":
            return pd.read_json(path, lines=True)
        return pd.read_csv(path, low_memory=False)
    except Exception as exc:
        print(f"Error loading {ext or 'file'}: {exc}", file=sys.stderr)
        sys.exit(1)


def build_schema(df, data_dictionary=None, max_samples=6):
    """Compact, factual schema for the Investigator. Columns, dtypes, null %,
    distinct counts, sample values for low-cardinality columns, numeric ranges.
    No interpretation, no suggested framings — the Investigator decides those."""
    if df is None:
        return "(no dataset — computation-only mode)"
    n = len(df)
    parts = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns", "Columns:"]
    for col in df.columns:
        dtype = df[col].dtype
        nunique = df[col].nunique(dropna=True)
        nulls = int(df[col].isna().sum())
        null_pct = f", {nulls} null ({100*nulls/n:.0f}%)" if nulls else ""
        is_str = dtype == "object" or str(dtype) == "category"
        line = f"  - {col} ({dtype}, {nunique} unique{null_pct})"
        if is_str or nunique <= 20:
            samples = df[col].dropna().unique()[:max_samples].tolist()
            line += f" values: {samples}"
        else:
            try:
                lo, hi = df[col].min(), df[col].max()
                line += f" range: [{lo}, {hi}]"
            except (TypeError, ValueError):
                pass
        parts.append(line)
    schema = "\n".join(parts)
    if data_dictionary:
        schema += ("\n\nDATA DICTIONARY (author-provided context for column meaning "
                   "and caveats; verify its claims against the data):\n" + data_dictionary)
    return schema
