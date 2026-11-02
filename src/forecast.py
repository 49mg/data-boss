"""Simple, honest forecasting with exponential smoothing (statsmodels).

The value is aggregated per calendar period (as in Trends). An incomplete last
period is left out, because a half-finished month would look like a collapse.
Holt-Winters variants (with / without a damped trend, with / without
seasonality when there are at least two full seasons) are compared by AICc and
the best one forecasts ahead. Uncertainty bands come from simulating the fitted
model (fixed seed). A backtest refits on all but the last periods and compares
the forecast with what really happened, next to a naive "same as last time"
forecast, so the error is shown honestly.
"""

import math
import warnings

import numpy as np
import pandas as pd
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .trends import ADDITIVE, AGGS, FREQS, _periods, period_name

SEED = 42
SEASON = {"D": 7, "W": 52, "M": 12, "Q": 4, "Y": None}
SIMULATIONS = 1000
MAX_HORIZON = 60
MIN_PERIODS = 8


class ForecastError(ValueError):
    """A user-facing problem with the forecast settings."""


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _s(v):
    v = float(v)
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.3g}"


def season_name(p, freq):
    """The position of a period within its season: a month, quarter, weekday or week number."""
    return {"M": lambda: p.strftime("%B"), "Q": lambda: f"Q{p.quarter}", "D": lambda: p.start_time.strftime("%A"),
            "W": lambda: f"week {p.week}"}.get(freq, lambda: period_name(p, freq))()


def build_series(df, date, value, agg, freq):
    """Values per period as a float array, the matching periods, and notes."""
    if date not in df.columns:
        raise ForecastError(f"Unknown column: {date}.")
    if not pd.api.types.is_datetime64_any_dtype(df[date]):
        raise ForecastError(f"“{date}” is not a date column. Use Convert to date in Clean first.")
    if freq not in FREQS:
        raise ForecastError("Period must be day, week, month, quarter or year.")
    if value:
        if value not in df.columns:
            raise ForecastError(f"Unknown column: {value}.")
        if agg not in AGGS:
            raise ForecastError(f"Combine with one of: {', '.join(AGGS)}.")
        if agg in ("sum", "mean", "median") and not (pd.api.types.is_numeric_dtype(df[value])
                                                     and not pd.api.types.is_bool_dtype(df[value])):
            raise ForecastError(f"“{value}” is not numeric; use count.")
    else:
        agg = "count"
    data = df[[date] + ([value] if value else [])].dropna(subset=[date])
    if data.empty:
        raise ForecastError(f"“{date}” has no dates.")
    periods = _periods(data[date], freq)
    full = pd.period_range(periods.min(), periods.max(), freq=periods.dt.freq)
    grouped = data.groupby(periods)[value].agg(agg) if value else data.groupby(periods).size()
    series = grouped.reindex(full)
    notes = []
    if agg in ADDITIVE:
        series = series.fillna(0)
    elif series.isna().any():
        notes.append(f"{int(series.isna().sum())} empty period(s) were filled by straight lines between neighbours.")
        series = series.interpolate(limit_direction="both")
    last = data[date].max()
    if getattr(last, "tzinfo", None) is not None:
        last = last.tz_localize(None)
    if last.normalize() < full[-1].end_time.normalize() and len(full) > MIN_PERIODS:
        notes.append(f"The last {FREQS[freq][0]} ({period_name(full[-1], freq)}) is incomplete (data ends {last:%d %b %Y}), "
                     "so it is left out of the model.")
        series, full = series.iloc[:-1], full[:-1]
    label = "number of rows" if not value else {"count": f"count of {value}", "nunique": f"distinct {value}"}.get(agg, f"{agg} of {value}")
    return series.to_numpy(dtype=float), full, label, agg, notes


CONFIGS = [
    {"trend": None, "damped": False, "seasonal": False},
    {"trend": "add", "damped": True, "seasonal": False},
    {"trend": None, "damped": False, "seasonal": True},
    {"trend": "add", "damped": True, "seasonal": True},
]


def _fit(y, cfg, m):
    model = ExponentialSmoothing(y, trend=cfg["trend"], damped_trend=cfg["damped"],
                                 seasonal="add" if cfg["seasonal"] else None,
                                 seasonal_periods=m if cfg["seasonal"] else None,
                                 initialization_method="estimated")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        return model.fit(optimized=True)


def _describe(cfg):
    parts = ["level"]
    if cfg["trend"]:
        parts.append("damped trend")
    if cfg["seasonal"]:
        parts.append("seasonality")
    return "Exponential smoothing with " + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def _choose(y, m):
    seasonal_ok = m is not None and len(y) >= 2 * m + 2
    best = None
    for cfg in CONFIGS:
        if cfg["seasonal"] and not seasonal_ok:
            continue
        if cfg["trend"] and len(y) < 10:
            continue
        try:
            res = _fit(y, cfg, m)
        except (ValueError, np.linalg.LinAlgError):
            continue
        score = res.aicc if np.isfinite(res.aicc) else res.aic
        if best is None or score < best[0]:
            best = (score, cfg, res)
    if best is None:
        raise ForecastError("Could not fit a forecasting model to this series.")
    return best[1], best[2], seasonal_ok


def _bands(res, h):
    sims = res.simulate(h, repetitions=SIMULATIONS, error="add", anchor="end", rng=np.random.default_rng(SEED))
    sims = np.asarray(sims).reshape(h, -1)
    return {q: np.percentile(sims, q, axis=1) for q in (2.5, 10, 90, 97.5)}


def forecast(df, date, value=None, agg="sum", freq="M", horizon=None, backtest=None):
    y, periods, label, agg, notes = build_series(df, date, value, agg, freq)
    unit = FREQS[freq][0]
    if len(y) < MIN_PERIODS:
        raise ForecastError(f"Only {len(y)} complete {unit}s; at least {MIN_PERIODS} are needed to forecast. "
                            "Pick a shorter period or more data.")
    m = SEASON[freq]
    cfg, res, seasonal_ok = _choose(y, m)
    h = int(horizon) if horizon else (m if cfg["seasonal"] else max(3, min(12, len(y) // 4)))
    if h < 1 or h > MAX_HORIZON:
        raise ForecastError(f"Forecast between 1 and {MAX_HORIZON} {unit}s ahead.")
    if m and not seasonal_ok:
        notes.append(f"Seasonality needs at least two full years of {unit}s ({2 * m + 2}); this series has {len(y)}, "
                     "so seasonal patterns are not modelled.")
    pred = res.forecast(h)
    band = _bands(res, h)
    nonnegative = bool((y >= 0).all())
    if nonnegative:
        # Counts and amounts can't go below zero, even though the simulated noise is symmetric.
        pred = np.maximum(pred, 0)
        band = {q: np.maximum(v, 0) for q, v in band.items()}
        if (band[2.5] == 0).any():
            notes.append("The lower end of the range is cut off at 0, because the values can't be negative.")
    future = pd.period_range(periods[-1] + 1, periods=h, freq=periods.freq)

    # Backtest: hide the last periods, forecast them, compare with reality and a naive forecast.
    bt_h = int(backtest) if backtest else max(1, min(h, len(y) // 4))
    bt = None
    if len(y) - bt_h >= MIN_PERIODS:
        train, actual = y[:-bt_h], y[-bt_h:]
        try:
            bt_res = _fit(train, cfg, m) if not (cfg["seasonal"] and len(train) < 2 * m + 2) else _fit(train, {**cfg, "seasonal": False}, m)
            bt_pred = bt_res.forecast(bt_h)
            if cfg["seasonal"] and len(train) >= m:
                naive = np.array([train[len(train) - m + (i % m)] for i in range(bt_h)])
                naive_name = "same period last season"
            else:
                naive = np.repeat(train[-1], bt_h)
                naive_name = f"last {unit} repeated"
            mae = float(np.mean(np.abs(actual - bt_pred)))
            naive_mae = float(np.mean(np.abs(actual - naive)))
            mape = float(np.mean(np.abs((actual - bt_pred) / actual)) * 100) if np.all(actual != 0) else None
            bt = {"periods": [period_name(p, freq) for p in periods[-bt_h:]], "actual": [_f(v) for v in actual],
                  "predicted": [_f(v) for v in bt_pred], "mae": _f(mae), "mape": _f(mape), "naiveMae": _f(naive_mae),
                  "naive": naive_name, "beatsNaive": bool(mae < naive_mae)}
        except (ValueError, np.linalg.LinAlgError):
            bt = None
    if bt is None:
        notes.append("Too few periods to hold some back for a backtest; treat the forecast as a rough guide.")

    seasonal_pattern = None
    if cfg["seasonal"]:
        season = np.asarray(res.season)[-m:]
        # order the seasonal effects by position in the calendar cycle of the last m periods
        labels = [season_name(p, freq) for p in periods[-m:]]
        seasonal_pattern = [{"period": lab, "effect": _f(e)} for lab, e in zip(labels, season, strict=True)]

    out = {
        "label": label, "unit": unit, "freq": freq, "method": _describe(cfg), "config": cfg, "seasonLength": m,
        "history": {"periods": [period_name(p, freq) for p in periods], "values": [_f(v) for v in y],
                    "fitted": [_f(v) for v in np.asarray(res.fittedvalues)]},
        "forecast": {"periods": [period_name(p, freq) for p in future], "values": [_f(v) for v in pred],
                     "low80": [_f(v) for v in band[10]], "high80": [_f(v) for v in band[90]],
                     "low95": [_f(v) for v in band[2.5]], "high95": [_f(v) for v in band[97.5]]},
        "backtest": bt, "seasonal": seasonal_pattern, "notes": notes,
    }
    out["insights"] = _insights(out, y, unit)
    out["code"] = _code(date, value, agg, freq, cfg, m, h, bt_h if bt else None, out["notes"], nonnegative)
    return out


def _insights(out, y, unit):
    f = out["forecast"]
    lines = [f"Next {unit} ({f['periods'][0]}): about {_s(f['values'][0])}, likely between {_s(f['low80'][0])} and "
             f"{_s(f['high80'][0])} (80% range)."]
    if len(f["values"]) > 1:
        total_change = (f["values"][-1] - y[-1]) / abs(y[-1]) * 100 if y[-1] else None
        if total_change is not None:
            where = (f"about the same as the last complete {unit}" if abs(total_change) < 1 else
                     f"{abs(total_change):.0f}% {'above' if total_change >= 0 else 'below'} the last complete {unit}")
            lines.append(f"By {f['periods'][-1]} the forecast is {_s(f['values'][-1])}, {where}.")
    if out["seasonal"]:
        eff = sorted(out["seasonal"], key=lambda e: e["effect"])
        lines.append(f"Seasonal pattern: {eff[-1]['period']} is typically the high point (+{_s(eff[-1]['effect'])}) "
                     f"and {eff[0]['period']} the low point ({_s(eff[0]['effect'])}).")
    bt = out["backtest"]
    if bt:
        acc = f"off by {_s(bt['mae'])} on average" + (f" ({bt['mape']:.0f}%)" if bt["mape"] is not None else "")
        verdict = ("better than" if bt["beatsNaive"] else "no better than")
        lines.append(f"Backtest on the last {len(bt['periods'])} {unit}s: the model was {acc}, {verdict} simply using the "
                     f"{bt['naive']} (off by {_s(bt['naiveMae'])}).")
    return lines


def _code(date, value, agg, freq, cfg, m, h, bt_h, notes, nonnegative=False):
    incomplete = any("incomplete" in n for n in notes)
    lines = [
        "from statsmodels.tsa.holtwinters import ExponentialSmoothing",
        "",
        f"periods = df[{date!r}].dt.to_period({freq!r})",
        (f"series = df.groupby(periods)[{value!r}].agg({agg!r})" if value else "series = df.groupby(periods).size()"),
        "series = series.reindex(pd.period_range(series.index.min(), series.index.max(), freq=series.index.freq))",
        "series = series.fillna(0)" if agg in ADDITIVE else "series = series.interpolate(limit_direction='both')",
    ]
    if incomplete:
        lines.append("series = series.iloc[:-1]  # the last period is incomplete")
    seasonal = "'add'" if cfg["seasonal"] else "None"
    lines += [
        "y = series.to_numpy(dtype=float)",
        "",
        "def fit(values):",
        f"    model = ExponentialSmoothing(values, trend={cfg['trend']!r}, damped_trend={cfg['damped']}, seasonal={seasonal},",
        f"                                 seasonal_periods={m if cfg['seasonal'] else None}, initialization_method='estimated')",
        "    return model.fit(optimized=True)",
        "",
        "model = fit(y)",
        f"forecast = model.forecast({h})",
        f"sims = model.simulate({h}, repetitions={SIMULATIONS}, error='add', anchor='end', rng=np.random.default_rng({SEED}))",
        *(["forecast, sims = np.maximum(forecast, 0), np.maximum(sims, 0)  # values can't be negative"] if nonnegative else []),
        f"future = pd.period_range(series.index[-1] + 1, periods={h}, freq=series.index.freq)",
        "print(pd.DataFrame({'forecast': forecast, 'low80': np.percentile(sims, 10, axis=1),",
        "                    'high80': np.percentile(sims, 90, axis=1)}, index=future))",
    ]
    if bt_h:
        lines += [
            "",
            f"# Backtest: forecast the last {bt_h} periods from the ones before",
            f"bt = fit(y[:-{bt_h}]).forecast({bt_h})",
            f"print('backtest MAE:', np.mean(np.abs(y[-{bt_h}:] - bt)))",
        ]
    return "\n".join(lines)
