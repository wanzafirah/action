"""TalentCorp company database — programme participation CSV loader and lookup.

Usage:
    from utils.company_db import get_company_programmes, search_company_names

The CSV is loaded once per session (lru_cache on _load_df).
Fuzzy name matching is done by normalising both the query and stored names
(strip legal suffixes, punctuation, extra spaces) then checking that all
significant tokens in the query appear in the normalised stored name.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pandas as pd

_CSV_PATH = Path(__file__).parent.parent / "datacompany 1.csv"

# Legal / filler words stripped before matching.
# Generic nouns like "company" are included so a query of
# "Company Ventures Sdn Bhd" reduces to just "ventures" and still
# matches "1337 VENTURES SDN BHD" in the database.
_STRIP_PAT = re.compile(
    r'\b(sdn\.?\s*bhd\.?|sdn|bhd|berhad|formerly|known\s+as|'
    r'previously|ltd\.?|limited|inc\.?|corp\.?|llc|plc|holdings|'
    r'international|industries|enterprise|services|solutions|group|'
    r'company|companies|the|of|and|m\.?\s*bhd\.?)\b',
    re.IGNORECASE,
)
_NONWORD = re.compile(r'[^\w\s]')
_SPACES  = re.compile(r'\s+')


def _normalise(name: str) -> str:
    n = _STRIP_PAT.sub(' ', str(name).lower())
    n = _NONWORD.sub(' ', n)
    return _SPACES.sub(' ', n).strip()


@functools.lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    """Load and cache the CSV.  Called once; result reused for all lookups."""
    df = pd.read_csv(_CSV_PATH, encoding='latin1')
    df.columns = [c.strip() for c in df.columns]
    for col in ('CompanyName', 'CompanyType', 'Programme', 'Sector', 'RefDate'):
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()
        else:
            df[col] = ''
    # Remove clearly invalid rows
    df = df[df['CompanyName'].str.len() > 1].copy()
    df['_norm'] = df['CompanyName'].apply(_normalise)
    return df


def clear_cache() -> None:
    """Force the CSV to reload on next access (call after adding new records)."""
    _load_df.cache_clear()


def get_all_data() -> pd.DataFrame:
    """Return the full DataFrame (for the Companies page table)."""
    return _load_df()


def search_company_names(query: str, limit: int = 25) -> list[str]:
    """Return up to *limit* company names that contain *query* (case-insensitive).

    Used to populate the autocomplete dropdown in the Capture form.
    """
    if not query or len(query.strip()) < 2:
        return []
    df = _load_df()
    q = re.escape(query.strip().lower())
    mask = df['CompanyName'].str.lower().str.contains(q, na=False, regex=True)
    return df[mask]['CompanyName'].drop_duplicates().sort_values().head(limit).tolist()


def get_company_programmes(company_name: str) -> list[dict]:
    """Return TalentCorp programme history for *company_name* using fuzzy matching.

    Strips legal suffixes and generic words (including "company") from both the
    query and stored names, then requires every significant token (length > 2)
    in the query to appear in the stored normalised name.

    Returns list of dicts:
        {company_name, company_type, programme, date, sector, _distinct_count}
    sorted by date descending, deduplicated.

    The special key ``_distinct_count`` (only on the first item) tells callers
    how many distinct company names matched, so the UI can show a
    "too generic / multiple matches" notice when the count is high.
    """
    if not company_name or company_name.strip() in ('', 'Not stated', 'None'):
        return []

    df = _load_df()
    q_norm = _normalise(company_name)
    # Keep alphabetic tokens longer than 2 chars, plus numeric tokens like "1"
    tokens = [t for t in q_norm.split() if len(t) > 2 or t.isdigit()]
    if not tokens:
        return []

    q_set = set(tokens)

    # Step 1 — candidate filter: all query tokens must appear as whole words
    mask = df['_norm'].str.contains(r'\b' + re.escape(tokens[0]) + r'\b', na=False)
    for t in tokens[1:]:
        mask = mask & df['_norm'].str.contains(r'\b' + re.escape(t) + r'\b', na=False)

    candidates = df[mask].copy()
    if candidates.empty:
        return []

    # Step 2 — Jaccard similarity: reject DB entries where the token sets are
    # too different in size (e.g. "malaysia development" should NOT match
    # "Sustainable Energy Development Authority SEDA Malaysia" because those
    # 6 tokens are far from the 2-token query).
    # Threshold scales with query length so single-word queries stay permissive.
    def _jaccard(norm_str: str) -> float:
        db_toks = set(t for t in norm_str.split() if len(t) > 2 or t.isdigit())
        if not db_toks:
            return 0.0
        return len(q_set & db_toks) / len(q_set | db_toks)

    threshold = 0.45 if len(q_set) >= 2 else 0.25
    candidates['_sim'] = candidates['_norm'].apply(_jaccard)
    results = candidates[candidates['_sim'] >= threshold].copy()

    if results.empty:
        return []

    distinct_count = int(results['CompanyName'].nunique())

    seen: set = set()
    out: list[dict] = []
    for _, row in results.iterrows():
        key = (row['CompanyName'], row['Programme'], row['RefDate'])
        if key not in seen:
            seen.add(key)
            out.append({
                'company_name': row['CompanyName'],
                'company_type': row['CompanyType'],
                'programme':    row['Programme'],
                'date':         row['RefDate'],
                'sector':       row['Sector'],
            })

    # Sort by date descending  (MM/DD/YYYY or M/D/YYYY)
    from datetime import datetime as _dt

    def _date_key(r: dict):
        for fmt in ('%m/%d/%Y', '%-m/%-d/%Y', '%Y-%m-%d'):
            try:
                return _dt.strptime(r['date'], fmt)
            except Exception:
                pass
        return _dt.min

    out.sort(key=_date_key, reverse=True)

    # Attach the distinct-company count to the first record so callers can
    # decide how to present results (e.g. show a "too generic" warning).
    if out:
        out[0]['_distinct_count'] = distinct_count
    return out
