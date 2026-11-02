"""Statistical tests chosen automatically and explained in plain language.

``compare(df, outcome, by)`` looks at the two column types (and, for groups,
their count, size, shape and spread) and runs the fitting test:

* number split by 2 groups   -> Student's t / Welch's t, or Mann-Whitney U
* number split by 3+ groups  -> one-way ANOVA, or Kruskal-Wallis (+ pairwise, Holm)
* category vs category       -> chi-square test of independence, or Fisher's exact
* number vs number           -> Pearson or Spearman correlation

Each result lists the checks that led to the choice, the p-value, an effect
size with a rough size label, a confidence interval where one is standard,
one interpretation sentence and caveats. Wording never claims proof or cause.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
MAX_GROUPS = 20
MAX_PAIRWISE_GROUPS = 10
SMALL_N = 20
BOOTSTRAP_REPS = 2000
BOOTSTRAP_MAX_N = 50_000


class StatsError(ValueError):
    """A user-facing problem with the chosen columns."""


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _s(v):
    """Short label for a number or category in sentences."""
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return f"{v:.3g}" if abs(v) < 1e5 else f"{v:,.0f}"
    text = str(v)
    return text if len(text) <= 40 else text[:37] + "…"


def p_text(p):
    if p is None:
        return "p = —"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}" if p < 0.01 else f"p = {p:.2f}"


def _size(value, cuts):
    a = abs(value)
    return "large" if a >= cuts[2] else "medium" if a >= cuts[1] else "small" if a >= cuts[0] else "negligible"


def _kind(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return "date"
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and s.nunique() > 2:
        return "numeric"
    return "category"


def looks_normal(x):
    """(ok, reason): is a t-test / ANOVA / Pearson reasonable for this sample?

    Small samples (< 30) must pass Shapiro-Wilk at 5%. Larger samples are
    fine unless strongly skewed, because averages of many values behave
    normally even when single values do not.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return False, f"only {n} value(s)"
    if np.ptp(x) == 0:
        return False, "all values are the same"
    if n < 30:
        p = stats.shapiro(x).pvalue
        return (True, f"looks normal (Shapiro-Wilk {p_text(p)})") if p >= ALPHA else (False, f"not normal (Shapiro-Wilk {p_text(p)})")
    skew = float(stats.skew(x))
    if abs(skew) >= 2:
        return False, f"strongly skewed (skew {skew:.1f})"
    return True, f"{n} values, skew {skew:.1f}: large enough"


def _holm(pvalues):
    order = np.argsort(pvalues)
    m = len(pvalues)
    adjusted = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def _mean_ci(x, level=0.95):
    n = len(x)
    if n < 2:
        return None, None
    half = stats.t.ppf((1 + level) / 2, n - 1) * np.std(x, ddof=1) / math.sqrt(n)
    return float(np.mean(x) - half), float(np.mean(x) + half)


def _wilson(k, n, level=0.95):
    if n == 0:
        return None, None
    z = stats.norm.ppf((1 + level) / 2)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def _bootstrap_median_diff(a, b, seed=0):
    rng = np.random.default_rng(seed)
    a = a if len(a) <= BOOTSTRAP_MAX_N else rng.choice(a, BOOTSTRAP_MAX_N, replace=False)
    b = b if len(b) <= BOOTSTRAP_MAX_N else rng.choice(b, BOOTSTRAP_MAX_N, replace=False)
    chunk = max(1, int(4e6 // max(len(a), len(b))))
    diffs = []
    for start in range(0, BOOTSTRAP_REPS, chunk):
        reps = min(chunk, BOOTSTRAP_REPS - start)
        ma = np.median(rng.choice(a, (reps, len(a))), axis=1)
        mb = np.median(rng.choice(b, (reps, len(b))), axis=1)
        diffs.append(ma - mb)
    low, high = np.percentile(np.concatenate(diffs), [2.5, 97.5])
    return float(low), float(high)


# ---- the four cases ----------------------------------------------------------------

def _groups(df, outcome, by, groups):
    data = df[[outcome, by]].dropna()
    data = data.assign(**{by: data[by].astype(str)})
    if groups:
        wanted = [str(g) for g in groups]
        data = data[data[by].isin(wanted)]
    counts = data[by].value_counts()
    if len(counts) > MAX_GROUPS:
        raise StatsError(f"“{by}” has {len(counts)} groups; compare at most {MAX_GROUPS}. Pick the groups to compare.")
    tiny = counts[counts < 2]
    data = data[~data[by].isin(tiny.index)]
    order = sorted(counts.index.difference(tiny.index), key=lambda g: (-counts[g], g))
    if len(order) < 2:
        raise StatsError(f"Need at least two groups of “{by}” with two or more values each.")
    return data, order, [str(g) for g in tiny.index]


def _compare_groups(df, outcome, by, groups, swapped):
    data, order, tiny = _groups(df, outcome, by, groups)
    samples = [data.loc[data[by] == g, outcome].astype(float).to_numpy() for g in order]
    k, n = len(samples), sum(len(s) for s in samples)
    checks, why, caveats = [], [], []

    normal = [looks_normal(s) for s in samples]
    all_normal = all(ok for ok, _ in normal)
    checks.append({"name": "Normal shape", "ok": all_normal,
                   "detail": "; ".join(f"{g}: {reason}" for g, (_, reason) in zip(order, normal, strict=True))})
    lev_p = None
    if all(np.ptp(s) > 0 for s in samples):
        with np.errstate(all="ignore"):
            lev_p = _f(stats.levene(*samples, center="median").pvalue)
    equal_var = lev_p is not None and lev_p >= ALPHA
    checks.append({"name": "Equal spread", "ok": equal_var,
                   "detail": "could not be checked (too few or identical values)" if lev_p is None else
                   f"Levene (Brown-Forsythe) {p_text(lev_p)}: " + ("similar spread" if equal_var else "spreads differ")})
    smallest = min(len(s) for s in samples)
    checks.append({"name": "Sample size", "ok": smallest >= SMALL_N, "detail": f"smallest group has {smallest} values"})

    table = []
    for g, s in zip(order, samples, strict=True):
        lo, hi = _mean_ci(s)
        table.append({"group": _s(g), "n": int(len(s)), "mean": _f(np.mean(s)), "median": _f(np.median(s)),
                      "std": _f(np.std(s, ddof=1)) if len(s) > 1 else None, "ciLow": _f(lo), "ciHigh": _f(hi)})

    what = f"Does {outcome} differ between groups of {by}?"
    res = {"question": what, "kind": "groups", "groups": table, "outcome": str(outcome), "by": str(by)}
    if k == 2:
        a, b = samples
        ga, gb = order
        if all_normal:
            test = stats.ttest_ind(a, b, equal_var=equal_var)
            name = "Student's t-test" if equal_var else "Welch's t-test"
            spread = " and similar spread" if equal_var else "; spreads differ, so Welch's version"
            why.append("two groups with a roughly normal shape" + spread)
            sp = math.sqrt(((len(a) - 1) * np.var(a, ddof=1) + (len(b) - 1) * np.var(b, ddof=1)) / (len(a) + len(b) - 2))
            d = (np.mean(a) - np.mean(b)) / sp if sp > 0 else 0.0
            ci = test.confidence_interval(0.95)
            diff = float(np.mean(a) - np.mean(b))
            res.update(statistic={"name": "t", "value": _f(test.statistic)}, df=_f(test.df), p=_f(test.pvalue),
                       effect={"name": "Cohen's d", "value": _f(d), "size": _size(d, (0.2, 0.5, 0.8)),
                               "explain": "difference in means measured in standard deviations"},
                       ci={"label": f"Difference in mean {outcome} ({_s(ga)} − {_s(gb)})", "estimate": diff,
                           "low": _f(ci.low), "high": _f(ci.high)})
            higher, lower = (ga, gb) if diff > 0 else (gb, ga)
            lo_gap, hi_gap = (ci.low, ci.high) if diff > 0 else (-ci.high, -ci.low)
            gap = f"{_s(higher)} averages {_s(abs(diff))} more than {_s(lower)} (95% CI {_s(lo_gap)} to {_s(hi_gap)})"
            code = f"res = stats.ttest_ind(a, b, equal_var={equal_var})\nprint(res.statistic, res.pvalue, res.confidence_interval())"
        else:
            test = stats.mannwhitneyu(a, b, alternative="two-sided")
            name = "Mann-Whitney U test"
            why.append("two groups, and at least one is not normal-shaped, so a rank-based test that does not assume a shape")
            rbc = 2 * test.statistic / (len(a) * len(b)) - 1
            diff = float(np.median(a) - np.median(b))
            lo, hi = _bootstrap_median_diff(a, b)
            res.update(statistic={"name": "U", "value": _f(test.statistic)}, df=None, p=_f(test.pvalue),
                       effect={"name": "Rank-biserial r", "value": _f(rbc), "size": _size(rbc, (0.1, 0.3, 0.5)),
                               "explain": f"+1 = every {_s(ga)} value is above every {_s(gb)} value, 0 = no tendency"},
                       ci={"label": f"Difference in median {outcome} ({_s(ga)} − {_s(gb)}, bootstrap)", "estimate": diff,
                           "low": _f(lo), "high": _f(hi)})
            higher, lower = (ga, gb) if rbc > 0 else (gb, ga)
            med = {g: np.median(x) for g, x in zip(order, samples, strict=True)}
            gap = f"values in {_s(higher)} tend to be higher than in {_s(lower)} (medians {_s(med[higher])} vs {_s(med[lower])})"
            code = "res = stats.mannwhitneyu(a, b, alternative='two-sided')\nprint(res.statistic, res.pvalue)"
        groups_code = f"a = data.loc[data[{by!r}] == {ga!r}, {outcome!r}]\nb = data.loc[data[{by!r}] == {gb!r}, {outcome!r}]\n"
        res["code_body"] = groups_code + code
        if res["p"] < ALPHA:
            sentence = (f"{outcome} differs between {_s(ga)} and {_s(gb)} ({p_text(res['p'])}): {gap}. "
                        f"The difference is {res['effect']['size']}.")
        else:
            sentence = (f"No clear difference in {outcome} between {_s(ga)} and {_s(gb)} ({p_text(res['p'])}). "
                        "That does not mean they are the same, only that this data cannot tell them apart.")
    else:
        if all_normal and equal_var:
            test = stats.f_oneway(*samples)
            name = "One-way ANOVA"
            why.append(f"{k} groups with a roughly normal shape and similar spread")
            grand = np.concatenate(samples).mean()
            ss_b = sum(len(s) * (s.mean() - grand) ** 2 for s in samples)
            ss_t = ((np.concatenate(samples) - grand) ** 2).sum()
            eff = ss_b / ss_t if ss_t > 0 else 0.0
            res.update(statistic={"name": "F", "value": _f(test.statistic)}, df=[k - 1, n - k], p=_f(test.pvalue),
                       effect={"name": "η² (eta squared)", "value": _f(eff), "size": _size(eff, (0.01, 0.06, 0.14)),
                               "explain": f"share of the variation in {outcome} explained by {by}"})
            code = "res = stats.f_oneway(*samples)\nprint(res.statistic, res.pvalue)"
            pair_test = "Welch's t-test"
        else:
            test = stats.kruskal(*samples)
            name = "Kruskal-Wallis test"
            reason = "not all are normal-shaped" if not all_normal else "their spreads differ"
            why.append(f"{k} groups, but {reason}, so a rank-based test")
            eff = test.statistic / (n - 1)
            res.update(statistic={"name": "H", "value": _f(test.statistic)}, df=k - 1, p=_f(test.pvalue),
                       effect={"name": "ε² (epsilon squared)", "value": _f(min(eff, 1.0)), "size": _size(eff, (0.01, 0.06, 0.14)),
                               "explain": f"share of the rank variation in {outcome} explained by {by}"})
            code = "res = stats.kruskal(*samples)\nprint(res.statistic, res.pvalue)"
            pair_test = "Mann-Whitney U"
        res["ci"] = None
        res["code_body"] = (f"order = {order!r}\nsamples = [data.loc[data[{by!r}] == g, {outcome!r}] for g in order]\n" + code)
        key, word = ("mean", "average") if all_normal else ("median", "median")
        best = max(table, key=lambda r: r[key])
        worst = min(table, key=lambda r: r[key])
        if res["p"] < ALPHA:
            sentence = (f"{outcome} is not the same across all {k} groups of {by} ({p_text(res['p'])}); the {word} ranges from "
                        f"{_s(worst[key])} ({worst['group']}) to {_s(best[key])} ({best['group']}). The effect is {res['effect']['size']}.")
        else:
            sentence = (f"No clear difference in {outcome} across the {k} groups of {by} ({p_text(res['p'])}). "
                        "That does not mean they are equal, only that this data cannot tell them apart.")
        if res["p"] < ALPHA and k <= MAX_PAIRWISE_GROUPS:
            pairs = []
            for i in range(k):
                for j in range(i + 1, k):
                    if pair_test == "Welch's t-test":
                        p = stats.ttest_ind(samples[i], samples[j], equal_var=False).pvalue
                    else:
                        p = stats.mannwhitneyu(samples[i], samples[j], alternative="two-sided").pvalue
                    pairs.append((order[i], order[j], float(p)))
            adjusted = _holm(np.array([p for *_, p in pairs]))
            res["pairwise"] = {"test": pair_test, "correction": "Holm", "rows": [
                {"a": _s(a), "b": _s(b), "p": _f(p), "pAdjusted": _f(q), "significant": bool(q < ALPHA)}
                for (a, b, p), q in zip(pairs, adjusted, strict=True)]}
            caveats.append("The overall test only says some groups differ; the pairwise table shows which (p-values adjusted for "
                           "making several comparisons).")
        elif res["p"] < ALPHA:
            caveats.append(f"Too many groups for pairwise comparisons; pick up to {MAX_PAIRWISE_GROUPS} groups to see which differ.")

    res.update(test=name, why=why, checks=checks, n=int(n))
    if swapped:
        why.insert(0, f"{by} has few distinct values, so it is used to split {outcome} into groups")
    if smallest < SMALL_N:
        caveats.append(f"Small groups (smallest has {smallest} values): results can change a lot with a few more rows.")
    sizes = [len(s) for s in samples]
    if max(sizes) > 4 * min(sizes):
        caveats.append("Group sizes are very unequal; the smaller groups have much wider uncertainty.")
    if tiny:
        caveats.append(f"Left out groups with fewer than 2 values: {', '.join(_s(t) for t in tiny[:5])}{'…' if len(tiny) > 5 else ''}.")
    return res, sentence, caveats


def _compare_categories(df, a, b, groups):
    data = df[[a, b]].dropna().astype(str)
    if groups:
        data = data[data[b].isin([str(g) for g in groups])]
    table = pd.crosstab(data[b], data[a])
    for col, size in ((a, table.shape[1]), (b, table.shape[0])):
        if size > MAX_GROUPS:
            raise StatsError(f"“{col}” has {size} different values; at most {MAX_GROUPS} can be compared. Group rare values first.")
        if size < 2:
            raise StatsError(f"“{col}” needs at least two different values here.")
    obs = table.to_numpy()
    n = int(obs.sum())
    chi2_raw, _, dof, expected = stats.chi2_contingency(obs, correction=False)
    low_cells = float((expected < 5).mean())
    min_expected = float(expected.min())
    expected_ok = low_cells <= 0.2 and min_expected >= 1
    checks = [{"name": "Expected counts", "ok": expected_ok,
               "detail": f"{low_cells:.0%} of cells expect fewer than 5 rows (smallest {min_expected:.1f}); "
                         "the chi-square test wants at most 20%"},
              {"name": "Sample size", "ok": n >= 40, "detail": f"{n} rows with both values"}]
    caveats, why = [], []
    counts = data[a].value_counts()
    focus = counts.index[-1] if len(counts) == 2 else counts.index[0]
    v = math.sqrt(chi2_raw / (n * (min(obs.shape) - 1)))
    df_star = min(obs.shape) - 1
    cuts = tuple(c / math.sqrt(df_star) for c in (0.1, 0.3, 0.5))
    effect = {"name": "Cramér's V", "value": _f(v), "size": _size(v, cuts), "explain": "0 = unrelated, 1 = one fully determines the other"}
    res = {"question": f"Are {a} and {b} related?", "kind": "categories", "outcome": str(a), "by": str(b), "focus": _s(focus),
           "crosstab": {"rows": [_s(r) for r in table.index], "columns": [_s(c) for c in table.columns], "counts": obs.tolist()}}

    if obs.shape == (2, 2) and not expected_ok:
        test = stats.fisher_exact(obs)
        res.update(test="Fisher's exact test", statistic={"name": "odds ratio", "value": _f(test.statistic)}, df=None, p=_f(test.pvalue))
        why.append("a 2 × 2 table with small expected counts, where Fisher's exact test is more reliable than chi-square")
        code = "res = stats.fisher_exact(table)\nprint(res.statistic, res.pvalue)"
    else:
        test = stats.chi2_contingency(obs)
        res.update(test="Chi-square test of independence", statistic={"name": "χ²", "value": _f(test.statistic)},
                   df=int(dof), p=_f(test.pvalue))
        why.append("two category columns" + (" (2 × 2, so with Yates' continuity correction)" if obs.shape == (2, 2) else ""))
        if not expected_ok:
            caveats.append("Many cells have small expected counts, so the chi-square p-value is approximate. Group rare categories first.")
        code = "res = stats.chi2_contingency(table)\nprint(res.statistic, res.pvalue)"
    res["effect"] = effect
    res["code_body"] = f"table = pd.crosstab(data[{b!r}].astype(str), data[{a!r}].astype(str))\n" + code

    shares = []
    col = list(table.columns).index(focus)
    for i, g in enumerate(table.index):
        k_, n_ = int(obs[i, col]), int(obs[i].sum())
        lo, hi = _wilson(k_, n_)
        shares.append({"group": _s(g), "n": n_, "share": _f(k_ / n_), "ciLow": _f(lo), "ciHigh": _f(hi)})
    res["shares"] = shares
    hi_g = max(shares, key=lambda s: s["share"])
    lo_g = min(shares, key=lambda s: s["share"])
    if obs.shape == (2, 2):
        (k1, n1), (k2, n2) = [(obs[i, col], obs[i].sum()) for i in range(2)]
        p1, p2 = k1 / n1, k2 / n2
        se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        res["ci"] = {"label": f"Difference in share of {a} = {_s(focus)} ({shares[0]['group']} − {shares[1]['group']}, percentage points)",
                     "estimate": _f((p1 - p2) * 100), "low": _f((p1 - p2 - 1.96 * se) * 100), "high": _f((p1 - p2 + 1.96 * se) * 100)}
    else:
        res["ci"] = None
    if res["p"] < ALPHA:
        sentence = (f"{a} and {b} are related ({p_text(res['p'])}): the share of {a} = {_s(focus)} ranges from "
                    f"{lo_g['share']:.0%} ({lo_g['group']}) to {hi_g['share']:.0%} ({hi_g['group']}). The association is {effect['size']}.")
    else:
        sentence = (f"No clear relationship between {a} and {b} ({p_text(res['p'])}). "
                    "That does not mean they are independent, only that this data does not show a link.")
    res.update(why=why, checks=checks, n=n)
    return res, sentence, caveats


def _correlate(df, a, b):
    data = df[[a, b]].dropna()
    x, y = data[a].astype(float).to_numpy(), data[b].astype(float).to_numpy()
    n = len(x)
    if n < 3:
        raise StatsError("Need at least 3 rows where both columns are filled.")
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise StatsError("One of the columns has the same value in every row.")
    nx, ny = looks_normal(x), looks_normal(y)
    checks = [{"name": "Normal shape", "ok": nx[0] and ny[0], "detail": f"{a}: {nx[1]}; {b}: {ny[1]}"},
              {"name": "Sample size", "ok": n >= 30, "detail": f"{n} rows with both values"}]
    caveats = []
    if nx[0] and ny[0]:
        test = stats.pearsonr(x, y)
        ci = test.confidence_interval(0.95)
        name, letter, low, high = "Pearson correlation", "r", ci.low, ci.high
        why = ["two number columns with a roughly normal shape: Pearson measures a straight-line relationship"]
        code = "res = stats.pearsonr(data[a], data[b])\nprint(res.statistic, res.pvalue, res.confidence_interval())"
    else:
        test = stats.spearmanr(x, y)
        name, letter = "Spearman rank correlation", "ρ"
        z, se = math.atanh(max(min(test.statistic, 0.999999), -0.999999)), 1 / math.sqrt(n - 3) if n > 3 else math.inf
        low, high = math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)
        why = ["two number columns, at least one not normal-shaped: Spearman uses ranks and catches any steady up/down trend"]
        caveats.append("The confidence interval for Spearman's ρ uses the Fisher z approximation.")
        code = "res = stats.spearmanr(data[a], data[b])\nprint(res.statistic, res.pvalue)"
    r = float(test.statistic)
    res = {"question": f"Do {a} and {b} move together?", "kind": "correlation", "outcome": str(a), "by": str(b),
           "test": name, "why": why, "checks": checks, "n": n, "df": n - 2,
           "statistic": {"name": letter, "value": _f(r)}, "p": _f(test.pvalue),
           "effect": {"name": f"Correlation {letter}", "value": _f(r), "size": _size(r, (0.1, 0.3, 0.5)),
                      "explain": "−1 = perfect opposite trend, +1 = perfect same trend, 0 = none"},
           "ci": {"label": f"Correlation {letter}", "estimate": _f(r), "low": _f(low), "high": _f(high)},
           "code_body": f"a, b = {a!r}, {b!r}\n" + code}
    if res["p"] < ALPHA:
        direction = "higher" if r > 0 else "lower"
        sentence = (f"Rows with higher {a} tend to have {direction} {b} ({letter} = {r:+.2f}, {p_text(res['p'])}, "
                    f"95% CI {low:+.2f} to {high:+.2f}). "
                    f"The relationship is {res['effect']['size']}.")
    else:
        sentence = (f"No clear relationship between {a} and {b} ({letter} = {r:+.2f}, {p_text(res['p'])}). "
                    "There may still be a curved or group-specific pattern; check a scatter plot.")
    return res, sentence, caveats


def compare(df, outcome, by, groups=None):
    for c in (outcome, by):
        if not c:
            raise StatsError("Choose two columns to compare.")
        if c not in df.columns:
            raise StatsError(f"Unknown column: {c}.")
    if outcome == by:
        raise StatsError("Choose two different columns.")
    ko, kb = _kind(df[outcome]), _kind(df[by])
    if "date" in (ko, kb):
        raise StatsError("Date columns can't be tested directly. Add date parts in Clean (e.g. month), then compare those.")

    if ko == "numeric" and kb == "category":
        res, sentence, caveats = _compare_groups(df, outcome, by, groups, swapped=False)
    elif ko == "category" and kb == "numeric":
        res, sentence, caveats = _compare_groups(df, by, outcome, groups, swapped=True)
    elif ko == "category":
        res, sentence, caveats = _compare_categories(df, outcome, by, groups)
    else:
        res, sentence, caveats = _correlate(df, outcome, by)

    o, b = res["outcome"], res["by"]
    prep = [f"data = df[[{o!r}, {b!r}]].dropna()"]
    if res["kind"] != "correlation":
        prep.append(f"data[{b!r}] = data[{b!r}].astype(str)")
        if groups:
            prep.append(f"data = data[data[{b!r}].isin({[str(g) for g in groups]!r})]")
    res["code_body"] = "\n".join(prep) + "\n" + res["code_body"]

    used = res["n"]
    dropped = len(df) - len(df[[outcome, by]].dropna())
    if dropped:
        caveats.append(f"{dropped:,} row(s) with an empty value in either column were left out.")
    if used > 5000 and res["p"] is not None and res["p"] < ALPHA and res["effect"]["size"] in ("negligible", "small"):
        caveats.append("With this many rows even tiny differences are statistically significant; judge by the effect size.")
    caveats.append("This data was observed, not from an experiment: a difference or relationship does not show what causes it.")
    res.update(alpha=ALPHA, significant=bool(res["p"] is not None and res["p"] < ALPHA),
               interpretation=sentence, caveats=caveats, dropped=int(dropped))
    return res
