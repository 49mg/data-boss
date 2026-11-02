"""Target analysis: how strongly each column is related to one chosen column.

Every relationship is put on a 0..1 scale so columns of different kinds can be
ranked together:

* numeric target + numeric column      -> |Pearson r|
* numeric target + category column     -> correlation ratio eta (sqrt of eta squared)
* category target + numeric column     -> correlation ratio eta
* category target + category column    -> Cramer's V

Each result also carries a p-value (how surprising the pattern would be if
there were no relationship), a small chart of group values and one plain
sentence. These are associations only; nothing here shows cause and effect.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

MAX_TARGET_CLASSES = 20
MAX_LEVELS = 50
CHART_ITEMS = 8
NUMERIC_BINS = 5


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _short(v):
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.3g}"
    text = str(v)
    return text if len(text) <= 40 else text[:37] + "…"


def strength_word(score):
    return ("very strong" if score >= 0.8 else "strong" if score >= 0.6 else "moderate" if score >= 0.4
            else "weak" if score >= 0.2 else "negligible")


def _is_numeric(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _kind(s):
    """'numeric', 'category', 'date' or None (constant / empty)."""
    if pd.api.types.is_datetime64_any_dtype(s) or isinstance(s.dtype, pd.PeriodDtype):
        return "date"
    if _is_numeric(s):
        return "numeric" if s.nunique() > 2 else "category"
    return "category"


# ---- the three measures --------------------------------------------------------

def pearson(x, y):
    """Pearson r and p-value on paired numeric values (NaN pairs removed)."""
    r, p = stats.pearsonr(x.astype(float), y.astype(float))
    return float(r), float(p)


def correlation_ratio(categories, values):
    """eta and the one-way ANOVA p-value for numeric values split by category."""
    values = values.astype(float)
    grand = values.mean()
    groups = values.groupby(categories, observed=True)
    ss_between = float((groups.count() * (groups.mean() - grand) ** 2).sum())
    ss_total = float(((values - grand) ** 2).sum())
    k, n = groups.ngroups, len(values)
    eta = math.sqrt(ss_between / ss_total) if ss_total > 0 else 0.0
    p = None
    if k > 1 and n > k:
        ss_within = ss_total - ss_between
        if ss_within > 0:
            f = (ss_between / (k - 1)) / (ss_within / (n - k))
            p = float(stats.f.sf(f, k - 1, n - k))
        else:
            p = 0.0
    return min(eta, 1.0), p


def cramers_v(a, b):
    """Cramer's V (no bias correction) and the chi-square test p-value."""
    table = pd.crosstab(a, b)
    r, c = table.shape
    if r < 2 or c < 2:
        return 0.0, None
    chi2, p, _, _ = stats.chi2_contingency(table.to_numpy(), correction=False)
    n = table.to_numpy().sum()
    return math.sqrt(chi2 / (n * (min(r, c) - 1))), float(p)


# ---- per-column analysis -------------------------------------------------------

def _focus_class(target):
    """The class whose share is charted for a category target."""
    counts = target.value_counts()
    if len(counts) == 2:
        return counts.index[-1]  # the rarer of two, e.g. "churned"
    return counts.index[0]


def _bins(x):
    """Quantile bins of a numeric column, labelled by their value range."""
    try:
        binned = pd.qcut(x, NUMERIC_BINS, duplicates="drop")
    except ValueError:
        return None
    if binned.cat.categories.size < 2:
        return None
    labels = [f"{_short(iv.left)}–{_short(iv.right)}" for iv in binned.cat.categories]
    return binned.cat.rename_categories(labels)


def _chart(groups, value_of, top_by_count=True):
    items = []
    keys = groups.size().sort_values(ascending=False).index[:CHART_ITEMS] if top_by_count else list(groups.groups)
    for key, g in groups:
        if key in keys:
            items.append({"label": _short(key), "value": _f(value_of(g)), "n": int(len(g))})
    if top_by_count:
        items.sort(key=lambda i: -(i["value"] if i["value"] is not None else -math.inf))
    return items


def _analyse(df, target, tkind, col, focus):
    x_raw = df[col]
    kind = _kind(x_raw)
    base = {"column": str(col), "kind": kind}
    if kind == "date":
        return {**base, "skipped": "Date column. Add date parts in Clean to compare it."}
    pair = pd.DataFrame({"x": x_raw, "y": df[target]}).dropna()
    n = len(pair)
    if n < 3:
        return {**base, "skipped": "Fewer than 3 rows have both values."}
    if pair["x"].nunique() < 2:
        return {**base, "skipped": "Only one value where the target is filled."}
    if kind == "category":
        levels = pair["x"].nunique()
        if levels > MAX_LEVELS:
            why = "a different value in every row (like an ID)" if levels == n else f"{levels} distinct values"
            return {**base, "skipped": f"Has {why}; too many groups to compare."}
        pair["x"] = pair["x"].astype(str)
    x, y = pair["x"], pair["y"]

    if tkind == "numeric" and kind == "numeric":
        r, p = pearson(x, y)
        score, measure = abs(r), "Pearson r"
        bins = _bins(x)
        chart = _chart(y.groupby(bins, observed=True), lambda g: g.mean(), top_by_count=False) if bins is not None else []
        direction = "higher" if r > 0 else "lower"
        sentence = (f"Higher {col} goes with {direction} {target} (r = {r:+.2f}, {strength_word(score)})."
                    if score >= 0.1 else f"{col} and {target} barely move together (r = {r:+.2f}).")
        out = {"value": r, "chartMetric": f"average {target}", "chartBy": f"{col} range"}
    elif tkind == "numeric":  # category column, numeric target
        score, p = correlation_ratio(x, y)
        measure = "Correlation ratio η"
        means = y.groupby(x, observed=True).mean()
        hi, lo = means.idxmax(), means.idxmin()
        chart = _chart(y.groupby(x, observed=True), lambda g: g.mean())
        sentence = (f"Average {target} ranges from {_short(means[lo])} ({_short(lo)}) to {_short(means[hi])} ({_short(hi)}); "
                    f"{col} accounts for {score ** 2:.0%} of the variation in {target} (η = {score:.2f}, {strength_word(score)}).")
        out = {"value": score, "chartMetric": f"average {target}", "chartBy": str(col)}
    elif kind == "numeric":  # numeric column, category target
        score, p = correlation_ratio(y.astype(str), x)
        measure = "Correlation ratio η"
        means = x.groupby(y.astype(str), observed=True).mean()
        hi, lo = means.idxmax(), means.idxmin()
        chart = _chart(x.groupby(y.astype(str), observed=True), lambda g: g.mean())
        sentence = (f"Average {col} is {_short(means[hi])} for {_short(hi)} and {_short(means[lo])} for {_short(lo)} "
                    f"(η = {score:.2f}, {strength_word(score)}).")
        out = {"value": score, "chartMetric": f"average {col}", "chartBy": str(target)}
    else:  # both categories
        score, p = cramers_v(x, y.astype(str))
        measure = "Cramér's V"
        is_focus = y.astype(str) == str(focus)
        shares = is_focus.groupby(x, observed=True).mean()
        hi, lo = shares.idxmax(), shares.idxmin()
        chart = _chart(is_focus.groupby(x, observed=True), lambda g: g.mean() * 100)
        sentence = (f"The share of {target} = {_short(focus)} ranges from {shares[lo]:.0%} ({_short(lo)}) to "
                    f"{shares[hi]:.0%} ({_short(hi)}) (V = {score:.2f}, {strength_word(score)}).")
        out = {"value": score, "chartMetric": f"% {target} = {_short(focus)}", "chartBy": str(col)}

    if p is not None and p >= 0.05:
        sentence += f" With p = {p:.2g} this could easily be chance."
    return {**base, **out, "score": _f(score), "measure": measure, "p": _f(p), "n": int(n),
            "strength": strength_word(score), "sentence": sentence, "chart": chart}


def target_analysis(df, target):
    if target not in df.columns:
        raise ValueError(f"Unknown column: {target}.")
    t = df[target]
    tkind = _kind(t)
    if tkind == "date":
        raise ValueError("Pick a numeric or category column as the target, not a date.")
    filled = t.dropna()
    if filled.nunique() < 2:
        raise ValueError(f"“{target}” has fewer than two different values, so nothing can be related to it.")
    focus = None
    if tkind == "category":
        classes = filled.astype(str).nunique()
        if classes > MAX_TARGET_CLASSES:
            raise ValueError(f"“{target}” has {classes} different values. Pick a numeric column or a category "
                             f"with at most {MAX_TARGET_CLASSES} values (group rare ones in Clean first).")
        focus = str(_focus_class(filled.astype(str)))

    results = [_analyse(df, target, tkind, c, focus) for c in df.columns if c != target]
    ranked = sorted((r for r in results if "skipped" not in r), key=lambda r: -(r["score"] or 0))
    skipped = [r for r in results if "skipped" in r]
    summary = {
        "target": str(target), "kind": tkind, "rows": int(len(filled)),
        "missingTarget": int(t.isna().sum()), "focus": focus,
    }
    if tkind == "numeric":
        summary.update(mean=_f(filled.mean()), median=_f(filled.median()), min=_f(filled.min()), max=_f(filled.max()))
    else:
        vc = filled.astype(str).value_counts()
        summary["classes"] = [{"label": _short(k), "count": int(v)} for k, v in vc.head(CHART_ITEMS).items()]
        summary["classCount"] = int(len(vc))
    return {"summary": summary, "columns": ranked, "skipped": skipped}
