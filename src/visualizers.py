import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from .base import BaseDataVisualizer  # noqa: E402

AGGREGATIONS = ("mean", "sum", "median", "count", "min", "max")
# UI frequency -> pandas resample alias
FREQUENCIES = {"D": "D", "W": "W", "M": "ME", "Q": "QE", "Y": "YE"}
FREQUENCY_NAMES = {"D": "day", "W": "week", "M": "month", "Q": "quarter", "Y": "year"}


def _f(v):
    """Compact number for chart insights."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    v = float(v)
    if v != 0 and (abs(v) >= 1e7 or abs(v) < 1e-3):
        return f"{v:.2e}"
    if abs(v) >= 100 or float(v).is_integer():
        return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 or abs(v) >= 100 else f"{v:,.2f}"
    return f"{v:,.3g}"


def _x(v, freq=""):
    """Readable label for an x-axis value (dates without midnight times)."""
    if isinstance(v, pd.Timestamp):
        if freq == "Q":
            return f"{v.year} Q{v.quarter}"
        return v.strftime({"M": "%b %Y", "Y": "%Y"}.get(freq, "%Y-%m-%d"))
    return _f(v) if isinstance(v, (int, float, np.number)) else str(v)


def _strength(r):
    a = abs(r)
    word = "very strong" if a >= 0.8 else "strong" if a >= 0.6 else "moderate" if a >= 0.4 else "weak" if a >= 0.2 else "no clear"
    if word == "no clear":
        return "no clear linear relationship"
    return f"{word} {'positive' if r > 0 else 'negative'} relationship"


def _is_numeric(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


class DataVisualizer(BaseDataVisualizer):
    """Charts with insights.

    Each ``draw_*`` method returns ``(figure, insights, notes, code)``:
    plain-language findings, caveats (rows skipped, categories hidden), and
    the seaborn/matplotlib code that reproduces the chart.
    """

    def __init__(self, dataframe, heatmap_cmap="coolwarm", width=None):
        super().__init__(dataframe)
        self.heatmap_cmap = heatmap_cmap
        # Figure width follows the on-screen panel; height keeps a 16:9-ish ratio.
        w = min(14.0, max(6.0, (width or 900) / 100))
        self.figsize = (round(w, 1), round(w * 0.56, 1))
        self.methods = {
            "HIST": self.draw_histogram,
            "BOX": self.draw_boxplot,
            "SCAT": self.scatter_plot,
            "HEAT": self.draw_heatmap,
            "LINE": self.draw_line_chart,
            "BAR": self.draw_bar_chart,
            "COUNT": self.draw_count_chart,
            "PAIR": self.draw_pairplot,
        }

    # ---- helpers ---------------------------------------------------------

    def _fig(self, size=None):
        fig, ax = plt.subplots(figsize=size or self.figsize)
        return fig, ax

    def _code_fig(self, size=None):
        w, h = size or self.figsize
        return f"fig, ax = plt.subplots(figsize=({w}, {h}))"

    def _require(self, *cols):
        for c in cols:
            if c is not None and c not in self.df.columns:
                raise ValueError(f"Unknown column: {c}.")

    def _clean(self, cols, notes):
        data = self.df[[c for c in dict.fromkeys(cols) if c]].dropna()
        skipped = len(self.df) - len(data)
        if skipped:
            notes.append(f"{skipped:,} row(s) with missing values were skipped for this chart.")
        if data.empty:
            raise ValueError("No rows left to plot after skipping missing values.")
        return data

    def _top_categories(self, data, col, top_n, notes, label="categories"):
        counts = data[col].value_counts()
        if top_n and len(counts) > top_n:
            notes.append(f"Showing the {top_n} most common {label} of {len(counts):,}.")
            keep = counts.head(top_n).index
            return data[data[col].isin(keep)], list(keep)
        return data, list(counts.index)

    @staticmethod
    def _rotate_labels(ax, labels, axis="x"):
        longest = max((len(str(lbl)) for lbl in labels), default=0)
        if axis == "x" and (len(labels) > 6 or longest > 10):
            ax.tick_params(axis="x", rotation=35)
            for t in ax.get_xticklabels():
                t.set_horizontalalignment("right")

    @staticmethod
    def _title(ax, title):
        if title:
            ax.set_title(title, fontsize=13, fontweight="semibold", loc="left", pad=12)

    # ---- histogram -------------------------------------------------------

    def draw_histogram(self, column, bins="auto", kde=True, hue=None, title=""):
        self._require(column, hue)
        if not _is_numeric(self.df[column]):
            raise ValueError(f"{column} is not numeric.")
        notes, insights = [], []
        data = self._clean([column, hue], notes)
        if hue:
            data, _ = self._top_categories(data, hue, 6, notes, "groups")
        bins_v = "auto" if bins in (None, "", "auto") else int(bins)
        kde = bool(kde) and len(data) > 2 and data[column].nunique() > 1
        fig, ax = self._fig()
        sns.histplot(data=data, x=column, hue=hue, bins=bins_v, kde=kde, ax=ax,
                     element="step" if hue else "bars", alpha=0.35 if hue else 0.75, linewidth=0.6)
        s = data[column]
        median = s.median()
        ax.axvline(median, color=plt.rcParams["text.color"], linestyle="--", linewidth=1, alpha=0.7)
        ax.annotate(f"median {_f(median)}", xy=(median, 1), xycoords=("data", "axes fraction"),
                    xytext=(4, -12), textcoords="offset points", fontsize=9, alpha=0.8)
        ax.set_ylabel("Count")
        self._title(ax, title)

        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        skew = s.skew() if len(s) > 2 else 0
        shape = (
            "right-skewed: most values are low with a long tail of high values" if skew > 1 else
            "left-skewed: most values are high with a tail of low values" if skew < -1 else
            "slightly skewed" if abs(skew) > 0.5 else "roughly symmetric"
        )
        insights += [
            f"{len(s):,} values. Mean {_f(s.mean())}, median {_f(median)}, standard deviation {_f(s.std())}.",
            f"The middle 50% of values lie between {_f(q1)} and {_f(q3)}.",
            f"The distribution is {shape} (skewness {skew:.2f}).",
        ]
        if abs(skew) > 1:
            insights.append("With this much skew, the median is a better “typical value” than the mean.")

        hue_arg = f", hue={hue!r}" if hue else ""
        code = [
            self._code_fig(),
            f"sns.histplot(data=df, x={column!r}{hue_arg}, bins={bins_v!r}, kde={kde}, ax=ax)",
            f"ax.axvline(df[{column!r}].median(), linestyle='--', linewidth=1)",
        ]
        return fig, insights, notes, code

    # ---- box plot --------------------------------------------------------

    def draw_boxplot(self, y, x=None, top_n=12, log=False, title=""):
        self._require(x, y)
        if not _is_numeric(self.df[y]):
            raise ValueError(f"{y} is not numeric.")
        notes, insights = [], []
        data = self._clean([x, y], notes)
        order: list = []
        medians = pd.Series(dtype=float)
        if x:
            data, _ = self._top_categories(data, x, int(top_n or 12), notes, "groups")
            medians = data.groupby(x)[y].median().sort_values(ascending=False)
            order = list(medians.index)
        fig, ax = self._fig()
        sns.boxplot(data=data, x=x, y=y, order=order or None, ax=ax, fliersize=2.5, linewidth=1,
                    color=None if x else plt.rcParams["axes.prop_cycle"].by_key()["color"][0])
        if log:
            ax.set_yscale("log" if data[y].min() > 0 else "symlog")
        if order:
            self._rotate_labels(ax, order)
        self._title(ax, title)

        s = data[y]
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        outliers = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        if x and order:
            insights.append(f"Highest median: {order[0]} ({_f(medians.iloc[0])}). Lowest: {order[-1]} ({_f(medians.iloc[-1])}).")
            sizes = data[x].value_counts()
            small = [str(g) for g in order if sizes[g] < 5]
            if small:
                insights.append(f"Few values in {', '.join(small[:4])}; their boxes are unreliable.")
        insights.append(f"Overall median {_f(s.median())}; middle 50% between {_f(q1)} and {_f(q3)}.")
        insights.append(f"{outliers:,} point(s) fall outside the whiskers (1.5 × IQR)." if outliers else "No points outside the whiskers.")

        code = [self._code_fig()]
        if x:
            code.append(f"order = df.groupby({x!r})[{y!r}].median().sort_values(ascending=False).index[:{int(top_n or 12)}]")
            code.append(f"sns.boxplot(data=df[df[{x!r}].isin(order)], x={x!r}, y={y!r}, order=order, ax=ax)")
        else:
            code.append(f"sns.boxplot(data=df, y={y!r}, ax=ax)")
        if log:
            code.append("ax.set_yscale('log')")
        return fig, insights, notes, code

    # ---- scatter ---------------------------------------------------------

    def scatter_plot(self, x, y, hue=None, trend=True, log_x=False, log_y=False, title=""):
        self._require(x, y, hue)
        for c in (x, y):
            if not _is_numeric(self.df[c]):
                raise ValueError(f"{c} is not numeric.")
        notes, insights = [], []
        data = self._clean([x, y, hue], notes)
        if hue:
            data, _ = self._top_categories(data, hue, 6, notes, "groups")
        n = len(data)
        alpha = 0.85 if n < 500 else 0.55 if n < 5000 else 0.3
        size = 40 if n < 500 else 20 if n < 5000 else 8
        fig, ax = self._fig()
        sns.scatterplot(data=data, x=x, y=y, hue=hue, ax=ax, alpha=alpha, s=size, edgecolor="none")
        xv, yv = data[x].astype(float), data[y].astype(float)
        r = xv.corr(yv) if n > 2 else float("nan")
        if trend and n > 2 and xv.nunique() > 1:
            m, b = np.polyfit(xv, yv, 1)
            xs = np.linspace(xv.min(), xv.max(), 100)
            ax.plot(xs, m * xs + b, color=plt.rcParams["text.color"], linewidth=1.4, alpha=0.75,
                    linestyle="--", label=f"trend (r = {r:.2f})")
            ax.legend(frameon=False)
            insights.append(f"Trend line: each +1 in {x} goes with about {'+' if m >= 0 else ''}{_f(m)} in {y}.")
        if log_x:
            ax.set_xscale("log" if xv.min() > 0 else "symlog")
        if log_y:
            ax.set_yscale("log" if yv.min() > 0 else "symlog")
        self._title(ax, title)

        if np.isfinite(r):
            rho = xv.rank().corr(yv.rank())  # Spearman without needing scipy
            insights.insert(0, f"Pearson r = {r:.2f}: {_strength(r)} ({n:,} points).")
            if abs(rho - r) > 0.15:
                insights.append(f"Rank correlation (Spearman) is {rho:.2f}, so the relationship is not a straight line"
                                " or is driven by a few extreme points.")
        hue_arg = f", hue={hue!r}" if hue else ""
        code = [self._code_fig(), f"sns.scatterplot(data=df, x={x!r}, y={y!r}{hue_arg}, alpha={alpha}, s={size}, ax=ax)"]
        if trend:
            code += [
                f"d = df[[{x!r}, {y!r}]].dropna()",
                f"m, b = np.polyfit(d[{x!r}], d[{y!r}], 1)",
                f"xs = np.linspace(d[{x!r}].min(), d[{x!r}].max(), 100)",
                "ax.plot(xs, m * xs + b, linestyle='--')",
            ]
        if log_x:
            code.append("ax.set_xscale('log')")
        if log_y:
            code.append("ax.set_yscale('log')")
        return fig, insights, notes, code

    # ---- correlation heatmap -------------------------------------------

    def draw_heatmap(self, columns=None, method="pearson", title=""):
        cols = list(columns or [c for c in self.df.columns if _is_numeric(self.df[c])])
        if len(cols) < 2:
            raise ValueError("Select at least 2 numeric columns.")
        self._require(*cols)
        if method not in ("pearson", "spearman"):
            raise ValueError("Method must be pearson or spearman.")
        notes, insights = [], []
        corr = self.df[cols].corr(method=method)
        k = len(cols)
        side = min(12.0, max(5.5, 0.75 * k + 3))
        fig, ax = self._fig((side + 1.5, side))
        mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
        sns.heatmap(corr, mask=mask, annot=k <= 12, fmt=".2f", cmap=self.heatmap_cmap, vmin=-1, vmax=1,
                    square=True, linewidths=0.5, linecolor=plt.rcParams["axes.facecolor"],
                    cbar_kws={"shrink": 0.75}, ax=ax, annot_kws={"fontsize": 9})
        self._rotate_labels(ax, cols)
        self._title(ax, title)
        if k > 12:
            notes.append("Too many columns to label every cell; hover-free values are in Inspect → Correlations.")

        pairs = corr.where(mask.T & ~np.eye(k, dtype=bool)).stack()
        if len(pairs):
            top = pairs.reindex(pairs.abs().sort_values(ascending=False).index)
            a, b = top.index[0]
            insights.append(f"Strongest pair: {a} and {b} (r = {top.iloc[0]:.2f}, {_strength(top.iloc[0])}).")
            neg = pairs[pairs < 0]
            if len(neg) and neg.min() <= -0.3:
                a, b = neg.idxmin()
                insights.append(f"Most negative: {a} and {b} (r = {neg.min():.2f}).")
            weak = int((pairs.abs() < 0.2).sum())
            insights.append(f"{weak} of {len(pairs)} pairs show little or no linear relationship (|r| < 0.2).")
        code = [
            f"cols = {cols!r}",
            f"corr = df[cols].corr(method={method!r})",
            "mask = np.triu(np.ones_like(corr, dtype=bool), k=1)",
            self._code_fig((side + 1.5, side)),
            f"sns.heatmap(corr, mask=mask, annot={k <= 12}, fmt='.2f', cmap='coolwarm', vmin=-1, vmax=1, square=True, ax=ax)",
        ]
        return fig, insights, notes, code

    # ---- line ------------------------------------------------------------

    def draw_line_chart(self, x, y, agg="mean", freq="", title=""):
        self._require(x, y)
        if not _is_numeric(self.df[y]):
            raise ValueError(f"{y} is not numeric.")
        if agg not in AGGREGATIONS + ("none",):
            raise ValueError("Unknown aggregation.")
        notes, insights = [], []
        data = self._clean([x, y], notes)
        is_dt = pd.api.types.is_datetime64_any_dtype(data[x])
        if is_dt and freq:
            if freq not in FREQUENCIES:
                raise ValueError("Unknown time grouping.")
            series = data.set_index(x)[y].resample(FREQUENCIES[freq]).agg("mean" if agg == "none" else agg)
            # Label each period by its start (e.g. 2024-02-01 for February) so points sit on their own tick.
            series.index = series.index.to_period(freq).to_timestamp()
            how = f"{'mean' if agg == 'none' else agg} per {FREQUENCY_NAMES[freq]}"
            code_series = (f"s = df.set_index({x!r})[{y!r}].resample({FREQUENCIES[freq]!r}).{'mean' if agg == 'none' else agg}()\n"
                           f"s.index = s.index.to_period({freq!r}).to_timestamp()")
        elif agg != "none":
            series = data.groupby(x)[y].agg(agg).sort_index()
            how = f"{agg} of {y} for each {x}"
            code_series = f"s = df.groupby({x!r})[{y!r}].{agg}().sort_index()"
        else:
            series = data.sort_values(x).set_index(x)[y]
            how = "raw values, sorted by x"
            code_series = f"s = df.sort_values({x!r}).set_index({x!r})[{y!r}]"
        series = series.dropna()
        if series.empty:
            raise ValueError("Nothing to plot after grouping.")
        fig, ax = self._fig()
        ax.plot(series.index, series.values, linewidth=1.8, marker="o" if len(series) <= 40 else None, markersize=4)
        ax.set_xlabel(x)
        ax.set_ylabel(y if agg == "none" else f"{y} ({how.split(' ')[0]})")
        ax.grid(axis="y", alpha=0.35)
        if is_dt:
            fig.autofmt_xdate()
        elif not _is_numeric(data[x]):
            self._rotate_labels(ax, list(series.index))
        self._title(ax, title)

        first, last = series.iloc[0], series.iloc[-1]
        insights.append(f"{len(series):,} point{'' if len(series) == 1 else 's'} ({how}).")
        if first != 0 and np.isfinite(first):
            change = (last - first) / abs(first) * 100
            insights.append(f"From first to last point: {_f(first)} → {_f(last)} ({change:+.1f}%).")
        fq = freq if is_dt else ""
        insights.append(f"Highest at {_x(series.idxmax(), fq)} ({_f(series.max())}); "
                        f"lowest at {_x(series.idxmin(), fq)} ({_f(series.min())}).")
        if not is_dt and agg == "none" and data[x].duplicated().any():
            notes.append(f"{x} has repeated values; choose an aggregation to get one point per {x}.")
        code = [code_series, self._code_fig(), "ax.plot(s.index, s.values, marker='o')", f"ax.set_xlabel({x!r})", f"ax.set_ylabel({y!r})"]
        return fig, insights, notes, code

    # ---- bar & count -----------------------------------------------------

    def _bars(self, series, title, value_label, horizontal, labels_on_bars, fmt_pct=False, pct_total=None):
        n = len(series)
        labels = [str(i) for i in series.index]
        if horizontal == "auto":
            horizontal = n > 8 or max((len(lb) for lb in labels), default=0) > 12
        size = (self.figsize[0], max(self.figsize[1], 0.32 * n + 1.2)) if horizontal else self.figsize
        fig, ax = self._fig(size)
        color = plt.rcParams["axes.prop_cycle"].by_key()["color"][0]
        if horizontal:
            bars = ax.barh(labels[::-1], series.values[::-1], color=color)
            ax.set_xlabel(value_label)
            ax.grid(axis="x", alpha=0.35)
        else:
            bars = ax.bar(labels, series.values, color=color)
            ax.set_ylabel(value_label)
            ax.grid(axis="y", alpha=0.35)
            self._rotate_labels(ax, labels)
        ax.set_axisbelow(True)
        if labels_on_bars and n <= 30:
            total = pct_total or series.sum()
            fmt = (lambda v: f"{v / total:.0%}") if fmt_pct and total else _f
            ax.bar_label(bars, labels=[fmt(v) for v in (series.values[::-1] if horizontal else series.values)],
                         padding=3, fontsize=9)
            ax.margins(x=0.08) if horizontal else ax.margins(y=0.1)
        self._title(ax, title)
        return fig, horizontal, size

    def draw_bar_chart(self, x, y=None, agg="mean", top_n=15, sort="desc", horizontal="auto", labels=True, title=""):
        self._require(x, y)
        if agg not in AGGREGATIONS:
            raise ValueError("Unknown aggregation.")
        if y and agg != "count" and not _is_numeric(self.df[y]):
            raise ValueError(f"{y} is not numeric.")
        notes, insights = [], []
        if not y or agg == "count":
            data = self._clean([x], notes)
            series = data[x].value_counts()
            value_label, how = "Count", "count"
        else:
            data = self._clean([x, y], notes)
            series = data.groupby(x)[y].agg(agg)
            value_label, how = f"{agg} of {y}", agg
        series = self._sort_limit(series, sort, int(top_n or 15), notes)
        fig, horiz, size = self._bars(series, title, value_label, horizontal, labels)

        top_label, top_val = series.idxmax(), series.max()
        low_label, low_val = series.idxmin(), series.min()
        insights.append(f"Highest: {top_label} ({_f(top_val)}). Lowest: {low_label} ({_f(low_val)}).")
        if how in ("sum", "count") and series.sum():
            share = top_val / (data[x].value_counts().sum() if how == "count" else data[y].sum()) * 100
            insights.append(f"{top_label} alone accounts for {share:.0f}% of the total.")
        if how in ("mean", "median") and top_val and low_val:
            insights.append(f"The highest group is {top_val / low_val:.1f}× the lowest." if low_val > 0 else
                            f"Values range from {_f(low_val)} to {_f(top_val)}.")
        if how in ("mean", "median"):
            sizes = data[x].value_counts()
            small = [str(g) for g in series.index if sizes.get(g, 0) < 5]
            if small:
                notes.append(f"{len(small)} bar(s) are based on fewer than 5 rows, so treat them with care.")

        expr = f"df[{x!r}].value_counts()" if (not y or agg == "count") else f"df.groupby({x!r})[{y!r}].{agg}()"
        code = [f"s = {expr}.sort_values(ascending=False).head({int(top_n or 15)})", self._code_fig(size),
                "ax.barh(s.index.astype(str)[::-1], s.values[::-1])" if horiz else "ax.bar(s.index.astype(str), s.values)"]
        return fig, insights, notes, code

    def draw_count_chart(self, column, top_n=15, sort="desc", horizontal="auto", percent=False, title=""):
        self._require(column)
        notes, insights = [], []
        s = self.df[column]
        missing = int(s.isna().sum())
        counts = s.value_counts()
        if counts.empty:
            raise ValueError("This column has no values.")
        series = self._sort_limit(counts, sort, int(top_n or 15), notes)
        fig, horiz, size = self._bars(series, title, "Count", horizontal, True, fmt_pct=percent, pct_total=counts.sum())
        total = counts.sum()
        insights.append(f"{len(counts):,} distinct values across {total:,} rows.")
        insights.append(f"Most common: {counts.index[0]} ({counts.iloc[0]:,}, {counts.iloc[0] / total:.0%}).")
        top3 = counts.head(3).sum() / total
        if len(counts) > 3:
            insights.append(f"The top 3 values cover {top3:.0%} of rows.")
        singles = int((counts == 1).sum())
        if singles and len(counts) > 10:
            insights.append(f"{singles:,} values appear only once.")
        if missing:
            notes.append(f"{missing:,} missing value(s) are not shown.")
        code = [f"s = df[{column!r}].value_counts().head({int(top_n or 15)})", self._code_fig(size),
                "ax.barh(s.index.astype(str)[::-1], s.values[::-1])" if horiz else "ax.bar(s.index.astype(str), s.values)"]
        return fig, insights, notes, code

    @staticmethod
    def _sort_limit(series, sort, top_n, notes):
        full = len(series)
        series = series.sort_values(ascending=False)
        if top_n and full > top_n:
            series = series.head(top_n)
            notes.append(f"Showing the top {top_n} of {full:,} categories.")
        if sort == "asc":
            series = series.sort_values(ascending=True)
        elif sort == "label":
            series = series.sort_index(key=lambda i: i.astype(str))
        return series

    # ---- pair plot -------------------------------------------------------

    def draw_pairplot(self, columns=None, hue=None, title=""):
        cols = list(columns or [])
        if len(cols) < 2:
            raise ValueError("Select at least 2 columns for a pair plot.")
        self._require(*cols, hue)
        notes, insights = [], []
        data = self._clean(cols + ([hue] if hue and hue not in cols else []), notes)
        if hue:
            data, _ = self._top_categories(data, hue, 6, notes, "groups")
        if len(data) > 2000:
            data = data.sample(2000, random_state=0)
            notes.append("Sampled 2,000 rows to keep the pair plot fast.")
        g = sns.pairplot(data, vars=cols, hue=hue, corner=True, height=min(2.6, 11 / len(cols)),
                         plot_kws={"s": 14, "alpha": 0.6, "edgecolor": "none"}, diag_kws={"linewidth": 0.6})
        if title:
            g.figure.suptitle(title, x=0.02, ha="left", fontsize=13, fontweight="semibold")
        corr = data[cols].corr()
        pairs = corr.where(np.tril(np.ones_like(corr, dtype=bool), k=-1)).stack()
        if len(pairs):
            a, b = pairs.abs().idxmax()
            insights.append(f"Strongest relationship: {a} and {b} (r = {corr.loc[a, b]:.2f}).")
        insights.append("Diagonal: each column's distribution. Below it: every pair of columns against each other.")
        hue_arg = f", hue={hue!r}" if hue else ""
        code = [f"g = sns.pairplot(df, vars={cols!r}{hue_arg}, corner=True)"]
        return g.figure, insights, notes, code

    # ---- rendering -------------------------------------------------------

    def render_chart(self, kind, params=None, fmt="png"):
        """Draw a chart. Returns {"data": bytes|str, "insights", "notes", "code"}."""
        if kind not in self.methods:
            raise ValueError(f"Unknown chart type: {kind}")
        fig, insights, notes, code = self.methods[kind](**(params or {}))
        try:
            fig.tight_layout()
            buffer = io.BytesIO()
            if fmt == "svg":
                fig.savefig(buffer, format="svg", bbox_inches="tight")
                data = buffer.getvalue().decode("utf-8")
            else:
                fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
                data = buffer.getvalue()
        finally:
            plt.close(fig)
        return {"data": data, "insights": insights, "notes": notes, "code": code}

    def render(self, method_key, **params):
        """PNG bytes for a chart (kept for programmatic use)."""
        if method_key not in self.methods:
            return None
        return self.render_chart(method_key, params)["data"]
