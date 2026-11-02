"""Period-over-period trends for a date column.

``trends`` groups rows into calendar periods (day, week, month, quarter,
year), aggregates a value per period and adds the change against the previous
period or the same period a year earlier, an optional moving average and a
running total. It also writes a few insight sentences and the pandas code that
rebuilds the table.
"""

import math

import numpy as np
import pandas as pd

FREQS = {
    "D": ("day", 365, "%d %b %Y"),
    "W": ("week", 52, "week of %d %b %Y"),
    "M": ("month", 12, "%B %Y"),
    "Q": ("quarter", 4, None),
    "Y": ("year", 1, "%Y"),
}
AGGS = ("sum", "mean", "median", "count", "min", "max", "nunique")
ADDITIVE = ("sum", "count")
MAX_PERIODS = 2000


class TrendError(ValueError):
    """A user-facing problem with the trend settings."""


def _f(v):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _num(v):
    v = float(v)
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.3g}" if abs(v) >= 1 or v == 0 else f"{v:.3g}"


def period_name(p, freq):
    if freq == "Q":
        return f"{p.year} Q{p.quarter}"
    fmt = FREQS[freq][2]
    return p.start_time.strftime(fmt)


def _periods(dates, freq):
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    return dates.dt.to_period(freq)


def trends(df, date, value=None, agg="sum", freq="M", compare="previous", window=0):
    if date not in df.columns:
        raise TrendError(f"Unknown column: {date}.")
    if not pd.api.types.is_datetime64_any_dtype(df[date]):
        raise TrendError(f"“{date}” is not a date column. Use Convert to date in Clean first.")
    if freq not in FREQS:
        raise TrendError("Period must be day, week, month, quarter or year.")
    if compare not in ("previous", "year"):
        raise TrendError("Compare with the previous period or the same period last year.")
    if value:
        if value not in df.columns:
            raise TrendError(f"Unknown column: {value}.")
        if agg not in AGGS:
            raise TrendError(f"Combine with one of: {', '.join(AGGS)}.")
        if agg in ("sum", "mean", "median") and not (
                pd.api.types.is_numeric_dtype(df[value]) and not pd.api.types.is_bool_dtype(df[value])):
            raise TrendError(f"“{value}” is not numeric; use count or distinct count.")
    else:
        agg = "count"
    try:
        window = int(window or 0)
    except (TypeError, ValueError) as e:
        raise TrendError("The moving average window must be a whole number.") from e
    if window < 0 or window == 1:
        raise TrendError("Use a moving average window of 2 or more, or 0 for none.")

    unit, per_year, _ = FREQS[freq]
    data = df[[date] + ([value] if value and value != date else [])].dropna(subset=[date])
    dropped = len(df) - len(data)
    if data.empty:
        raise TrendError(f"“{date}” has no dates.")
    periods = _periods(data[date], freq)
    full = pd.period_range(periods.min(), periods.max(), freq=periods.dt.freq)
    if len(full) > MAX_PERIODS:
        raise TrendError(f"That makes {len(full):,} {unit}s; at most {MAX_PERIODS:,} can be shown. Pick a longer period.")
    if len(full) < 2:
        raise TrendError(f"All dates fall in one {unit}; pick a shorter period to see a trend.")

    grouped = (data.groupby(periods)[value].agg(agg) if value else data.groupby(periods).size())
    series = grouped.reindex(full)
    if agg in ADDITIVE:
        series = series.fillna(0)
    label = "number of rows" if not value else {"nunique": f"distinct {value}", "count": f"count of {value}"}.get(agg, f"{agg} of {value}")

    lag = 1 if compare == "previous" else per_year
    if compare == "year" and freq == "Y":
        lag = 1
    prev = series.shift(lag)
    change = series - prev
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (change / prev.abs()) * 100
    pct = pct.where(prev != 0)
    table = pd.DataFrame({"period": [period_name(p, freq) for p in full], "value": series.to_numpy(dtype=float),
                          "change": change.to_numpy(dtype=float), "changePct": pct.to_numpy(dtype=float)})
    if window:
        table["movingAvg"] = series.rolling(window, min_periods=window).mean().to_numpy(dtype=float)
    if agg in ADDITIVE:
        table["runningTotal"] = series.cumsum().to_numpy(dtype=float)

    notes = []
    if dropped:
        notes.append(f"{dropped:,} row(s) without a date were left out.")
    last_date, first_date = data[date].max(), data[date].min()
    if getattr(last_date, "tzinfo", None) is not None:
        last_date, first_date = last_date.tz_localize(None), first_date.tz_localize(None)
    partial_last = last_date.normalize() < full[-1].end_time.normalize()
    partial_first = first_date.normalize() > full[0].start_time.normalize()
    if partial_last:
        notes.append(f"The data ends on {last_date:%d %b %Y}, so the last {unit} ({table['period'].iloc[-1]}) may be incomplete.")
    if partial_first:
        notes.append(f"The data starts on {first_date:%d %b %Y}, so the first {unit} may be incomplete.")
    if compare == "year" and len(full) <= lag:
        notes.append(f"Less than a year of {unit}s, so there is nothing to compare with yet.")

    complete = np.ones(len(table), dtype=bool)
    if partial_last:
        complete[-1] = False
    if partial_first:
        complete[0] = False
    table["complete"] = complete
    insights = _insights(table, lag, unit, label, compare)
    return {
        "table": table, "label": label, "unit": unit, "freq": freq, "compare": compare, "window": window,
        "insights": insights, "notes": notes, "partialLast": bool(partial_last),
        "code": _code(date, value, agg, freq, compare, lag, window),
    }


def _insights(table, lag, unit, label, compare):
    """Sentences about complete periods only, so a half-filled first or last period can't fake a jump."""
    out = []
    complete = table["complete"].to_numpy()
    prev_complete = np.r_[np.zeros(lag, dtype=bool), complete[:-lag]] if lag < len(complete) else np.zeros(len(complete), bool)
    fair = table[complete & prev_complete]
    full = table[complete]
    against = "the previous " + unit if compare == "previous" else "the same " + unit + " a year earlier"
    pct = fair["changePct"].dropna()
    if len(pct):
        up, down = pct.idxmax(), pct.idxmin()
        if pct[up] > 0:
            out.append(f"{table['period'][up]} was {pct[up]:.0f}% above {against} ({_num(table['value'][up])}), "
                       "the biggest rise.")
        if pct[down] < 0:
            out.append(f"{table['period'][down]} was {abs(pct[down]):.0f}% below {against} "
                       f"({_num(table['value'][down])}), the biggest drop.")
    vals = full["value"].dropna()
    if len(vals):
        hi, lo = vals.idxmax(), vals.idxmin()
        if vals[hi] == vals[lo]:
            out.append(f"Every complete {unit} has the same value: {_num(vals[hi])}.")
        else:
            out.append(f"Highest: {_num(vals[hi])} in {table['period'][hi]}. Lowest: {_num(vals[lo])} in {table['period'][lo]}.")
    if len(full) and full.index[-1] in pct.index:
        i = full.index[-1]
        word = "above" if pct[i] >= 0 else "below"
        out.append(f"The latest complete {unit}, {table['period'][i]}, is {abs(pct[i]):.0f}% {word} {against}.")
    if len(vals) >= 3 and vals.mean() != 0:
        slope = np.polyfit(vals.index.to_numpy(dtype=float), vals.to_numpy(dtype=float), 1)[0]
        rel = slope / abs(vals.mean()) * 100
        if abs(rel) < 1:
            out.append(f"Overall the {label} stays roughly flat over time.")
        else:
            out.append(f"Overall the trend is {'rising' if rel > 0 else 'falling'}: about {_num(abs(slope))} "
                       f"{'more' if rel > 0 else 'less'} per {unit} ({abs(rel):.1f}% of the average).")
    return out


def _code(date, value, agg, freq, compare, lag, window):
    lines = [f"periods = df[{date!r}].dt.to_period({freq!r})"]
    if value:
        lines.append(f"series = df.groupby(periods)[{value!r}].agg({agg!r})")
    else:
        lines.append("series = df.groupby(periods).size()")
    lines.append("series = series.reindex(pd.period_range(series.index.min(), series.index.max(), freq=series.index.freq))")
    if agg in ADDITIVE:
        lines.append("series = series.fillna(0)")
    lines += [
        "table = series.rename('value').to_frame()",
        f"table['change'] = table['value'] - table['value'].shift({lag})",
        f"table['change_pct'] = (table['change'] / table['value'].shift({lag}).abs() * 100).replace([np.inf, -np.inf], np.nan)",
    ]
    if window:
        lines.append(f"table['moving_avg'] = table['value'].rolling({window}).mean()")
    if agg in ADDITIVE:
        lines.append("table['running_total'] = table['value'].cumsum()")
    lines.append("print(table)")
    return "\n".join(lines)
