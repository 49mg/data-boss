import io
import math

import numpy as np
import pandas as pd

from .base import BaseDataInspector
from .target import target_analysis

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _num(v):
    """Plain float for JSON (NaN/inf -> None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _label(v):
    """Short string for showing a value in the UI."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.6g}"
    text = str(v)
    return text if len(text) <= 80 else text[:77] + "…"


class DataInspector(BaseDataInspector):
    """Read-only summaries of a dataframe.

    Every method returns plain data (strings / DataFrames / dicts) so the
    caller decides how to present it.
    """

    def __init__(self, dataframe):
        super().__init__(dataframe)
        self.methods = {
            "INFO": self.show_info,
            "DESC": self.show_desc,
            "DUPLICATED": self.show_duplicated_value,
            "NON_VALUE": self.show_non_value,
            "QUALITY": self.quality_report,
            "STRUCTURE": self.structure,
            "STATS": self.statistics,
            "MISSING": self.missing_report,
            "DUPES": self.duplicates,
            "OUTLIERS": self.outliers,
            "CORR": self.correlations,
            "TARGET": self.target,
        }

    # ---- column helpers ------------------------------------------------

    def _numeric_cols(self):
        return [
            c for c in self.df.columns
            if pd.api.types.is_numeric_dtype(self.df[c]) and not pd.api.types.is_bool_dtype(self.df[c])
        ]

    def _text_cols(self):
        return [
            c for c in self.df.columns
            if pd.api.types.is_object_dtype(self.df[c])
            or pd.api.types.is_string_dtype(self.df[c])
            or isinstance(self.df[c].dtype, pd.CategoricalDtype)
        ]

    @staticmethod
    def _iqr_bounds(s):
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        return q1 - 1.5 * iqr, q3 + 1.5 * iqr

    def show_info(self):
        buffer = io.StringIO()
        self.df.info(buf=buffer)
        return {"text": buffer.getvalue()}

    def show_desc(self):
        numeric = self.df.select_dtypes(include=["number"])
        if numeric.shape[1] == 0:
            return {"message": "No numeric columns to describe.", "table": None}
        return {"table": self.df.describe()}

    def show_duplicated_value(self):
        duplicated_sum = int(self.df.duplicated().sum())
        table = self.df[self.df.duplicated(keep=False)] if duplicated_sum > 0 else None
        return {"message": f"Duplicate rows: {duplicated_sum}", "table": table}

    def show_non_value(self):
        missing = self.df.isna().sum()
        missing_cols = missing[missing > 0]
        table = missing_cols.rename("missing_count").to_frame() if len(missing_cols) > 0 else None
        message = f"Total missing: {int(missing.sum())}"
        if table is None:
            message = "No missing values found. " + message
        return {"message": message, "table": table}

    def show_column_profile(self):
        rows = []
        for col in self.df.columns:
            series = self.df[col]
            non_null = int(series.notna().sum())
            missing = int(series.isna().sum())
            missing_pct = float(series.isna().mean() * 100) if len(series) else 0.0
            unique = int(series.nunique())

            if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
                s = series.dropna()
                if len(s) > 0:
                    range_str = f"min={s.min():.4g}  ·  med={s.median():.4g}  ·  max={s.max():.4g}"
                else:
                    range_str = "—"
            else:
                top = series.value_counts().head(3)
                range_str = "  ·  ".join([f"{v} ({c})" for v, c in top.items()]) if len(top) > 0 else "—"

            rows.append({
                "Column": str(col),
                "Type": str(series.dtype),
                "Non-null": non_null,
                "Missing": f"{missing} ({missing_pct:.1f}%)",
                "Unique": unique,
                "Top values / Range": range_str,
            })

        return pd.DataFrame(rows)

    def value_counts(self, column, limit=20):
        vc = self.df[column].value_counts(dropna=False).head(limit).reset_index()
        vc.columns = ["Value", "Count"]
        return vc

    # ---- quality report --------------------------------------------------

    def quality_report(self):
        """Automatic checks for common data problems, each with a suggested fix."""
        df = self.df
        n = len(df)
        issues = []

        def add(severity, title, detail, columns=None, action=None):
            issues.append({
                "severity": severity,
                "title": title,
                "detail": detail,
                "columns": [str(c) for c in (columns or [])],
                "action": action,
            })

        dup = int(df.duplicated().sum())
        if dup:
            add("warning", f"{dup:,} duplicate row(s)",
                f"{dup / n:.1%} of rows are exact copies of an earlier row.",
                action={"method": "REMOVE_DUPLICATES", "label": "Remove duplicates"})

        numeric = set(self._numeric_cols())
        text = set(self._text_cols())
        gappy_numeric, whitespace_cols, outlier_cols = [], [], []

        for col in df.columns:
            s = df[col]
            miss = float(s.isna().mean()) if n else 0.0
            nonnull = s.dropna()
            nunique = int(nonnull.nunique())

            if n and miss == 1:
                add("critical", f"“{col}” is empty", "Every value in this column is missing.", [col],
                    {"method": "DROP_COLUMNS", "params": {"columns": [str(col)]}, "label": "Drop column"})
                continue
            if miss >= 0.5:
                add("warning", f"“{col}” is {miss:.0%} missing",
                    "Mostly-empty columns rarely help analysis. Consider dropping it.", [col],
                    {"method": "DROP_COLUMNS", "params": {"columns": [str(col)]}, "label": "Drop column"})
            elif miss > 0 and col in numeric:
                gappy_numeric.append(col)

            if n > 1 and nunique == 1:
                add("warning", f"“{col}” has a single value",
                    f"Every non-missing value is “{_label(nonnull.iloc[0])}”, so it carries no information.", [col],
                    {"method": "DROP_COLUMNS", "params": {"columns": [str(col)]}, "label": "Drop column"})

            if col in text and len(nonnull):
                as_str = nonnull.astype(str)
                stripped = as_str.str.strip()

                if (as_str != stripped).any():
                    whitespace_cols.append(col)

                parsed = pd.to_numeric(stripped.str.replace(r"[,\s$€£¥%]", "", regex=True), errors="coerce")
                ratio = float(parsed.notna().mean())
                if len(nonnull) >= 5 and ratio >= 0.8:
                    bad = stripped[parsed.isna()]
                    extra = (
                        f" {len(bad):,} value(s) are not numbers (e.g. “{_label(bad.iloc[0])}”) and will become missing."
                        if len(bad) else ""
                    )
                    add("warning", f"“{col}” holds numbers stored as text",
                        f"{ratio:.0%} of its values are numeric. Converting enables statistics and charts.{extra}",
                        [col],
                        {"method": "TO_NUMERIC", "params": {"columns": [str(col)]}, "label": "Convert to number"})

                normalized = stripped.str.lower().str.replace(r"\s+", " ", regex=True)
                variants = int(as_str.nunique() - normalized.nunique())
                if variants > 0 and nunique < 0.9 * len(nonnull):
                    groups = (
                        pd.DataFrame({"raw": as_str, "key": normalized})
                        .drop_duplicates()
                        .groupby("key")["raw"].agg(list)
                    )
                    example = next((v for v in groups if len(v) > 1), [])
                    shown = " / ".join(f"“{_label(v)}”" for v in example[:3])
                    add("info", f"“{col}” has {variants} near-duplicate label(s)",
                        f"Values differ only by case or spacing, e.g. {shown}. They are counted as separate categories.",
                        [col],
                        {"method": "NORMALIZE_TEXT", "params": {"columns": [str(col)], "case": "title"},
                         "label": "Normalize text"})

                if n > 20 and nunique == len(nonnull) and miss < 0.05:
                    add("info", f"“{col}” looks like an identifier",
                        "Every value is unique. Useful as a key, but not for grouping or charts.", [col])

            if col in numeric and len(nonnull) >= 8:
                skew = _num(nonnull.skew())
                if skew is not None and abs(skew) >= 2:
                    add("info", f"“{col}” is heavily skewed",
                        f"Skewness is {skew:.1f}. The median describes it better than the mean; "
                        "consider a log scale in charts.", [col])
                lo, hi = self._iqr_bounds(nonnull)
                if ((nonnull < lo) | (nonnull > hi)).any():
                    outlier_cols.append(col)

        if gappy_numeric:
            add("info", f"Missing values in {len(gappy_numeric)} numeric column(s)",
                "Filling gaps with the median keeps every row in calculations.", gappy_numeric,
                {"method": "FILL_NA", "params": {"columns": [str(c) for c in gappy_numeric], "strategy": "median"},
                 "label": "Fill with median"})
        if whitespace_cols:
            add("warning", f"Stray spaces in {len(whitespace_cols)} text column(s)",
                "Leading or trailing spaces make equal values look different.", whitespace_cols,
                {"method": "STRIP_WHITESPACE", "params": {"columns": [str(c) for c in whitespace_cols]},
                 "label": "Strip whitespace"})
        if outlier_cols:
            add("info", f"Outliers in {len(outlier_cols)} numeric column(s)",
                "Values beyond 1.5 × IQR. Review them in the Outliers tab before clipping.", outlier_cols,
                {"method": "CLIP_IQR", "params": {"columns": [str(c) for c in outlier_cols]}, "label": "Clip with IQR"})

        issues.sort(key=lambda i: SEVERITY_ORDER[i["severity"]])
        cells = n * df.shape[1]
        return {
            "summary": {
                "completeness": _num(1 - df.isna().sum().sum() / cells) if cells else None,
                "uniqueness": _num(1 - dup / n) if n else None,
                "critical": sum(i["severity"] == "critical" for i in issues),
                "warning": sum(i["severity"] == "warning" for i in issues),
                "info": sum(i["severity"] == "info" for i in issues),
            },
            "issues": issues,
        }

    # ---- structure -------------------------------------------------------

    def structure(self):
        df = self.df
        memory = df.memory_usage(deep=True)
        numeric = set(self._numeric_cols())
        columns = []
        for i, col in enumerate(df.columns):
            s = df[col]
            samples = [_label(v) for v in s.dropna().unique()[:3]]
            columns.append({
                "position": i,
                "name": str(col),
                "dtype": str(s.dtype),
                "kind": "numeric" if col in numeric else "categorical",
                "nonNull": int(s.notna().sum()),
                "missing": int(s.isna().sum()),
                "unique": int(s.nunique()),
                "memory": int(memory[col]),
                "samples": samples,
            })
        dtypes = df.dtypes.astype(str).value_counts()
        return {
            "rows": len(df),
            "memory": int(memory.sum()),
            "dtypes": [{"dtype": k, "count": int(v)} for k, v in dtypes.items()],
            "columns": columns,
            "raw": self.show_info()["text"],
        }

    # ---- statistics ------------------------------------------------------

    def statistics(self, bins=16):
        df = self.df
        numeric, categorical = [], []
        for col in self._numeric_cols():
            s = df[col].dropna()
            item = {"name": str(col), "dtype": str(df[col].dtype), "count": int(len(s)),
                    "missing": int(df[col].isna().sum())}
            if len(s):
                counts, edges = np.histogram(s.astype(float), bins=bins)
                item.update({
                    "mean": _num(s.mean()), "std": _num(s.std()), "min": _num(s.min()),
                    "q1": _num(s.quantile(0.25)), "median": _num(s.median()),
                    "q3": _num(s.quantile(0.75)), "max": _num(s.max()),
                    "skew": _num(s.skew()) if len(s) > 2 else None,
                    "zeros": int((s == 0).sum()),
                    "hist": {"counts": [int(c) for c in counts], "min": _num(edges[0]), "max": _num(edges[-1])},
                })
            numeric.append(item)
        numeric_cols = set(self._numeric_cols())
        for col in self.df.columns:
            if col in numeric_cols:
                continue
            s = df[col].dropna()
            vc = s.astype(str).value_counts()
            lengths = s.astype(str).str.len()
            categorical.append({
                "name": str(col), "dtype": str(df[col].dtype), "count": int(len(s)),
                "missing": int(df[col].isna().sum()), "unique": int(s.nunique()),
                "top": [{"value": _label(v), "count": int(c)} for v, c in vc.head(5).items()],
                "avgLength": _num(lengths.mean()) if len(s) else None,
            })
        return {"numeric": numeric, "categorical": categorical}

    # ---- missing values --------------------------------------------------

    def missing_report(self, patterns=6):
        df = self.df
        n = len(df)
        mask = df.isna()
        per_col = mask.sum().sort_values(ascending=False)
        any_missing = mask.any(axis=1)
        combos = []
        if any_missing.any():
            gappy = mask[any_missing]
            keys = gappy.apply(lambda r: tuple(str(c) for c in r.index[r]), axis=1)
            for cols, count in keys.value_counts().head(patterns).items():
                combos.append({"columns": list(cols), "rows": int(count)})
        return {
            "rows": n,
            "cells": int(mask.sum().sum()),
            "completeRows": int(n - any_missing.sum()),
            "columns": [
                {"name": str(c), "missing": int(v), "pct": _num(v / n) if n else 0.0}
                for c, v in per_col.items()
            ],
            "patterns": combos,
        }

    # ---- duplicates ------------------------------------------------------

    def duplicates(self, columns=None, limit=200):
        df = self.df
        subset = [c for c in (columns or []) if c in df.columns] or None
        extra = df.duplicated(subset=subset)
        involved = df.duplicated(subset=subset, keep=False)
        rows = df[involved]
        key_cols = subset or list(df.columns)
        groups = int(rows.drop_duplicates(subset=subset).shape[0]) if len(rows) else 0
        if len(rows):
            rows = rows.sort_values(by=key_cols, kind="stable", na_position="last")
        return {
            "subset": [str(c) for c in subset] if subset else None,
            "extraRows": int(extra.sum()),
            "involvedRows": int(involved.sum()),
            "groups": groups,
            "table": rows.head(limit),
            "truncated": bool(len(rows) > limit),
        }

    # ---- outliers --------------------------------------------------------

    def outliers(self):
        result = []
        for col in self._numeric_cols():
            s = self.df[col].dropna()
            if len(s) < 4:
                continue
            lo, hi = self._iqr_bounds(s)
            below, above = int((s < lo).sum()), int((s > hi).sum())
            std = s.std()
            z = int(((s - s.mean()).abs() > 3 * std).sum()) if std and std > 0 else 0
            extremes = s[(s < lo) | (s > hi)]
            extremes = extremes.reindex((extremes - s.median()).abs().sort_values(ascending=False).index)
            result.append({
                "name": str(col),
                "count": int(len(s)),
                "lower": _num(lo), "upper": _num(hi),
                "min": _num(s.min()), "max": _num(s.max()),
                "below": below, "above": above,
                "pct": _num((below + above) / len(s)),
                "zscore": z,
                "examples": [_num(v) for v in extremes.head(4)],
            })
        result.sort(key=lambda r: -(r["below"] + r["above"]))
        return {"columns": result}

    # ---- correlations ----------------------------------------------------

    def correlations(self, method="pearson", limit=40):
        if method not in ("pearson", "spearman"):
            raise ValueError("Method must be pearson or spearman.")
        cols = self._numeric_cols()
        if len(cols) < 2:
            return {"method": method, "pairs": [], "columns": len(cols)}
        data = self.df[cols]
        corr = data.corr(method=method)
        notna = data.notna().astype(int)
        overlap = notna.T @ notna
        pairs = []
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                r = _num(corr.loc[a, b])
                if r is None:
                    continue
                pairs.append({"a": str(a), "b": str(b), "r": r, "n": int(overlap.loc[a, b])})
        pairs.sort(key=lambda p: -abs(p["r"]))
        return {"method": method, "pairs": pairs[:limit], "columns": len(cols), "total": len(pairs)}

    def target(self, column=None):
        if not column:
            return {"summary": None, "columns": [], "skipped": []}
        return target_analysis(self.df, column)

    def render(self, method_key, **params):
        if method_key and method_key in self.methods:
            return self.methods[method_key](**params)
        return None
