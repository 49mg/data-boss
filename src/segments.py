"""Compare a segment (rows matching conditions) with the rest, column by column.

For each column the segment and the rest are summarised side by side and
tested:

* numbers    -> Welch's t-test when both sides look normal, otherwise
                Mann-Whitney U; effect size = rank-biserial r (used for ranking)
* categories -> chi-square test of independence (Fisher's exact for a small
                2 x 2 table); effect size = Cramer's V

Because many columns are tested at once, p-values are adjusted with Holm's
method before calling a difference significant.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

from .cleaners import FILTER_OPERATORS, filter_mask
from .stats import ALPHA, _holm, looks_normal, p_text

MAX_LEVELS = 20
TOP_SHARES = 6


class SegmentError(ValueError):
    """A user-facing problem with the segment definition."""


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _s(v):
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.3g}"
    text = str(v)
    return text if len(text) <= 40 else text[:37] + "…"


def describe(conditions):
    parts = []
    for c in conditions:
        shown = "" if c["operator"] in ("is_missing", "not_missing") else f" “{c.get('value', '')}”"
        parts.append(f"{c['column']} {FILTER_OPERATORS[c['operator']]}{shown}")
    return " and ".join(parts)


def segment_mask(df, conditions):
    conditions = [c for c in (conditions or []) if c and c.get("column")]
    if not conditions:
        raise SegmentError("Define the segment with at least one condition.")
    mask = pd.Series(True, index=df.index)
    exprs = []
    for c in conditions:
        m, expr = filter_mask(df, c["column"], c.get("operator", "=="), c.get("value", ""))
        mask &= m
        exprs.append(f"({expr})")
    return mask, " & ".join(exprs), conditions


def _numeric(name, a, b):
    a, b = a.astype(float).to_numpy(), b.astype(float).to_numpy()
    if len(a) < 2 or len(b) < 2:
        return None
    u = stats.mannwhitneyu(a, b, alternative="two-sided")
    rbc = 2 * u.statistic / (len(a) * len(b)) - 1
    if looks_normal(a)[0] and looks_normal(b)[0]:
        test, p = "Welch's t-test", stats.ttest_ind(a, b, equal_var=False).pvalue
    else:
        test, p = "Mann-Whitney U", u.pvalue
    ma, mb = a.mean(), b.mean()
    rel = (ma - mb) / abs(mb) * 100 if mb != 0 else None
    rel_text = f" ({rel:+.0f}%)" if rel is not None else ""
    sentence = f"Average {name} is {_s(ma)} in the segment vs {_s(mb)} in the rest{rel_text}."
    return {"kind": "numeric", "test": test, "p": _f(p), "effect": _f(rbc), "effectName": "rank-biserial r",
            "strength": _f(abs(rbc)), "segment": {"mean": _f(ma), "median": _f(np.median(a)), "n": int(len(a))},
            "rest": {"mean": _f(mb), "median": _f(np.median(b)), "n": int(len(b))}, "relDiff": _f(rel),
            "sentence": sentence}


def _categorical(name, a, b):
    a, b = a.astype(str), b.astype(str)
    both = pd.concat([a, b])
    counts = both.value_counts()
    if len(counts) < 2:
        return None
    if len(counts) > MAX_LEVELS:
        keep = set(counts.index[:MAX_LEVELS - 1])
        a = a.where(a.isin(keep), "Other")
        b = b.where(b.isin(keep), "Other")
    table = pd.crosstab(pd.concat([a, b]), np.r_[np.ones(len(a), bool), np.zeros(len(b), bool)])
    obs = table.to_numpy()
    if obs.shape[1] < 2 or obs.shape[0] < 2:
        return None
    chi2, p, _, expected = stats.chi2_contingency(obs, correction=False)
    test = "Chi-square"
    if obs.shape == (2, 2) and expected.min() < 5:
        test, p = "Fisher's exact", stats.fisher_exact(obs).pvalue
    v = math.sqrt(chi2 / (obs.sum() * (min(obs.shape) - 1)))
    share_a = a.value_counts(normalize=True)
    share_b = b.value_counts(normalize=True)
    levels = share_a.index.union(share_b.index)
    diff = (share_a.reindex(levels, fill_value=0) - share_b.reindex(levels, fill_value=0))
    order = diff.abs().sort_values(ascending=False).index[:TOP_SHARES]
    top = order[0]
    sentence = (f"{name} = {_s(top)} is {share_a.get(top, 0):.0%} of the segment vs {share_b.get(top, 0):.0%} of the rest.")
    return {"kind": "category", "test": test, "p": _f(p), "effect": _f(v), "effectName": "Cramér's V", "strength": _f(v),
            "shares": [{"value": _s(k), "segment": _f(share_a.get(k, 0)), "rest": _f(share_b.get(k, 0))} for k in order],
            "segment": {"n": int(len(a))}, "rest": {"n": int(len(b))}, "sentence": sentence}


def compare_segment(df, conditions):
    mask, expr, conditions = segment_mask(df, conditions)
    n_seg, n_rest = int(mask.sum()), int((~mask).sum())
    label = describe(conditions)
    if n_seg < 2:
        raise SegmentError(f"Only {n_seg} row(s) match “{label}”; the segment needs at least 2.")
    if n_rest < 2:
        raise SegmentError(f"Almost every row matches “{label}”; there is no “rest” to compare with.")
    used = {c["column"] for c in conditions}
    results, skipped = [], []
    for col in df.columns:
        s = df[col]
        if col in used:
            skipped.append({"column": str(col), "reason": "Used to define the segment."})
            continue
        if pd.api.types.is_datetime64_any_dtype(s):
            skipped.append({"column": str(col), "reason": "Date column."})
            continue
        a, b = s[mask].dropna(), s[~mask].dropna()
        numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and s.nunique() > 2
        if not numeric and s.nunique() > 0.9 * len(s.dropna()) and s.nunique() > MAX_LEVELS:
            skipped.append({"column": str(col), "reason": "Almost every value is different (like an ID or free text)."})
            continue
        try:
            res = _numeric(col, a, b) if numeric else _categorical(col, a, b)
        except ValueError:
            res = None
        if res is None:
            skipped.append({"column": str(col), "reason": "Not enough values on both sides."})
            continue
        res["column"] = str(col)
        res["missing"] = {"segment": int(s[mask].isna().sum()), "rest": int(s[~mask].isna().sum())}
        results.append(res)

    if results:
        adjusted = _holm(np.array([r["p"] if r["p"] is not None else 1.0 for r in results]))
        for r, q in zip(results, adjusted, strict=True):
            r["pAdjusted"] = _f(q)
            r["significant"] = bool(q < ALPHA)
            if not r["significant"]:
                r["sentence"] += f" This could be chance (adjusted {p_text(q)})."
    results.sort(key=lambda r: (not r["significant"], -(r["strength"] or 0)))
    n_sig = sum(r["significant"] for r in results)
    summary = (f"{n_sig} of {len(results)} columns differ clearly between the segment and the rest."
               if n_sig else "No column differs clearly between the segment and the rest.")
    code = "\n".join([
        f"segment = {expr}",
        "seg, rest = df[segment], df[~segment]",
        "# e.g. a number column:",
        "# stats.mannwhitneyu(seg[col].dropna(), rest[col].dropna())",
        "# e.g. a category column:",
        "# stats.chi2_contingency(pd.crosstab(df[col].astype(str), segment))",
        "print(seg.describe(include='all').T.join(rest.describe(include='all').T, lsuffix='_segment', rsuffix='_rest'))",
    ])
    return {"label": label, "segmentRows": n_seg, "restRows": n_rest, "summary": summary, "columns": results,
            "skipped": skipped, "correction": "Holm", "code": code,
            "caveats": ["p-values are adjusted for testing many columns at once (Holm).",
                        "A difference shows the segment is unusual on that column, not why."]}
