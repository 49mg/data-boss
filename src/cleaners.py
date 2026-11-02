import numpy as np
import pandas as pd

from .analysis import pivot
from .base import BaseDataCleaner
from .query import eval_expression, expression_code, run_query_full, sql_code

# Characters stripped before parsing "numbers stored as text": thousands
# separators, spaces, currency and percent signs.
NUMBER_JUNK = r"[,\s$€£¥%]"

FILTER_OPERATORS = {
    "==": "equals",
    "!=": "does not equal",
    ">": "is greater than",
    ">=": "is at least",
    "<": "is less than",
    "<=": "is at most",
    "contains": "contains",
    "not_contains": "does not contain",
    "is_missing": "is missing",
    "not_missing": "is not missing",
}


def filter_mask(df, column, operator, value=""):
    """Boolean mask of rows matching a condition, plus the pandas expression for it."""
    if column not in df.columns:
        raise ValueError(f"Unknown column: {column}.")
    if operator not in FILTER_OPERATORS:
        raise ValueError(f"Unknown operator: {operator}.")
    s = df[column]
    col = repr(column)
    numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)

    if operator == "is_missing":
        mask, expr = s.isna(), f"df[{col}].isna()"
    elif operator == "not_missing":
        mask, expr = s.notna(), f"df[{col}].notna()"
    elif operator in ("contains", "not_contains"):
        if value == "":
            raise ValueError("Enter the text to search for.")
        hit = s.astype("string").str.contains(value, case=False, regex=False, na=False).astype(bool)
        mask = hit if operator == "contains" else ~hit
        expr = f"df[{col}].astype('string').str.contains({value!r}, case=False, regex=False, na=False)"
        if operator == "not_contains":
            expr = f"~{expr}"
    else:
        if value == "":
            raise ValueError("Enter a value to compare with.")
        target = value
        if numeric:
            try:
                target = float(value)
            except ValueError as e:
                raise ValueError(f"“{value}” is not a number, but {column} is numeric.") from e
        elif operator in (">", ">=", "<", "<="):
            raise ValueError("Greater/less than comparisons need a numeric column.")
        mask = {
            "==": s == target, "!=": s != target, ">": s > target,
            ">=": s >= target, "<": s < target, "<=": s <= target,
        }[operator].fillna(False).astype(bool)
        expr = f"df[{col}] {operator} {target!r}"

    return mask, expr


def _changed(before, after):
    """Count cells that differ, treating NaN == NaN as unchanged."""
    same = before.eq(after) | (before.isna() & after.isna())
    return int((~same).sum())


def _plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


class DataCleaner(BaseDataCleaner):
    """Dataframe mutations.

    Every method returns a human-readable message and sets ``self.code`` to the
    equivalent pandas code, so a cleaning session can be exported as a script.
    Methods keep the original row index (the app resets it after committing),
    which lets a dry run tell exactly which rows were dropped or changed.
    """

    def __init__(self, dataframe):
        super().__init__(dataframe)
        self.code = ""
        self.clean_methods = {
            "REMOVE_DUPLICATES": self.remove_duplicates,
            "DROP_NA_ROWS": self.drop_na_rows,
            "DROP_NA_COLUMNS": self.drop_na_columns,
            "FILL_NA": self.fill_na,
            "FILL_NA_MEAN": self.fill_na_mean,
            "FILL_NA_MEDIAN": self.fill_na_median,
            "STRIP_WHITESPACE": self.strip_whitespace,
            "NORMALIZE_TEXT": self.normalize_text,
            "CLIP_IQR": self.clip_outliers_iqr,
            "CLIP_ZSCORE": self.clip_outliers_zscore,
            "ROUND": self.round_numbers,
            "RENAME_COLUMN": self.rename_column,
            "CHANGE_DTYPE": self.change_dtype,
            "TO_NUMERIC": self.to_numeric,
            "TO_DATETIME": self.to_datetime,
            "DROP_COLUMNS": self.drop_columns,
            "REPLACE_VALUES": self.replace_values,
            "FILTER_ROWS": self.filter_rows,
            "SORT_ROWS": self.sort_rows,
            "SQL_QUERY": self.sql_query,
            "PIVOT": self.pivot_table,
            "ADD_COLUMN": self.add_column,
            "DATE_PARTS": self.date_parts,
            "JOIN": self.join,
            "ONE_HOT": self.one_hot,
            "SCALE": self.scale,
            "BIN": self.bin_values,
            "LOG_TRANSFORM": self.log_transform,
            "GROUP_RARE": self.group_rare,
            "ADD_CLUSTERS": self.add_clusters,
        }
        self.preview_override = None  # set by operations that need their own preview (joins)

    # ---- helpers ---------------------------------------------------------

    def _numeric_cols(self, columns=None):
        numeric = [
            c for c in self.df.columns
            if pd.api.types.is_numeric_dtype(self.df[c]) and not pd.api.types.is_bool_dtype(self.df[c])
        ]
        if columns:
            bad = [c for c in columns if c not in numeric]
            if bad:
                raise ValueError(f"Not numeric: {', '.join(map(str, bad))}.")
            return list(columns)
        return numeric

    def _text_cols(self, columns=None):
        text = [
            c for c in self.df.columns
            if pd.api.types.is_object_dtype(self.df[c]) or pd.api.types.is_string_dtype(self.df[c])
        ]
        if columns:
            bad = [c for c in columns if c not in text]
            if bad:
                raise ValueError(f"Not text: {', '.join(map(str, bad))}.")
            return list(columns)
        return text

    def _require(self, columns, what="column"):
        if not columns:
            raise ValueError(f"Select at least one {what}.")
        missing = [c for c in columns if c not in self.df.columns]
        if missing:
            raise ValueError(f"Unknown column(s): {', '.join(map(str, missing))}.")
        return list(columns)

    # ---- rows ------------------------------------------------------------

    def remove_duplicates(self, columns=None, keep="first"):
        if keep not in ("first", "last"):
            raise ValueError("Keep must be 'first' or 'last'.")
        subset = list(columns) if columns else None
        before = len(self.df)
        self.df = self.df.drop_duplicates(subset=subset, keep=keep)
        removed = before - len(self.df)
        args = f"subset={subset!r}, keep={keep!r}" if subset else f"keep={keep!r}"
        self.code = f"df = df.drop_duplicates({args})"
        scope = f" (matching on {', '.join(map(str, subset))})" if subset else ""
        return f"Removed {_plural(removed, 'duplicate row')}{scope}."

    def drop_na_rows(self, columns=None):
        subset = list(columns) if columns else None
        before = len(self.df)
        self.df = self.df.dropna(subset=subset)
        removed = before - len(self.df)
        self.code = f"df = df.dropna(subset={subset!r})" if subset else "df = df.dropna()"
        scope = f" in {', '.join(map(str, subset))}" if subset else ""
        return f"Dropped {_plural(removed, 'row')} with missing values{scope}."

    def filter_rows(self, column, operator, value="", mode="keep"):
        if column not in self.df.columns:
            raise ValueError(f"Unknown column: {column}.")
        if operator not in FILTER_OPERATORS:
            raise ValueError(f"Unknown operator: {operator}.")
        if mode not in ("keep", "remove"):
            raise ValueError("Mode must be 'keep' or 'remove'.")
        mask, expr = filter_mask(self.df, column, operator, value)
        before = len(self.df)
        self.df = self.df[mask] if mode == "keep" else self.df[~mask]
        removed = before - len(self.df)
        self.code = f"df = df[{expr}]" if mode == "keep" else f"df = df[~({expr})]"
        shown = "" if operator in ("is_missing", "not_missing") else f" “{value}”"
        verb = "Kept" if mode == "keep" else "Removed"
        affected = len(self.df) if mode == "keep" else removed
        tail = f" ({_plural(removed, 'row')} dropped)" if mode == "keep" else ""
        return f"{verb} {_plural(affected, 'row')} where {column} {FILTER_OPERATORS[operator]}{shown}{tail}."

    def sort_rows(self, column, ascending=True):
        if column not in self.df.columns:
            raise ValueError(f"Unknown column: {column}.")
        ascending = ascending in (True, "true", "asc", "ascending")
        self.df = self.df.sort_values(column, ascending=ascending, na_position="last", kind="stable")
        self.code = f"df = df.sort_values({column!r}, ascending={ascending}, na_position='last', kind='stable')"
        return f"Sorted rows by {column} ({'ascending' if ascending else 'descending'})."

    # ---- missing values --------------------------------------------------

    def drop_na_columns(self):
        before = list(self.df.columns)
        self.df = self.df.dropna(axis=1, how="all")
        removed = [c for c in before if c not in self.df.columns]
        self.code = "df = df.dropna(axis=1, how='all')"
        names = f": {', '.join(map(str, removed))}" if removed else ""
        return f"Removed {_plural(len(removed), 'empty column')}{names}."

    def fill_na(self, columns, strategy="median", value=""):
        columns = self._require(columns)
        strategies = ("mean", "median", "mode", "constant", "ffill", "bfill")
        if strategy not in strategies:
            raise ValueError(f"Strategy must be one of: {', '.join(strategies)}.")
        if strategy in ("mean", "median"):
            self._numeric_cols(columns)
        filled = int(self.df[columns].isna().sum().sum())
        c = repr(columns)
        if strategy in ("mean", "median"):
            self.df[columns] = self.df[columns].fillna(getattr(self.df[columns], strategy)())
            self.code = f"df[{c}] = df[{c}].fillna(df[{c}].{strategy}())"
        elif strategy == "mode":
            modes = {col: self.df[col].mode(dropna=True) for col in columns}
            fills = {col: m.iloc[0] for col, m in modes.items() if len(m)}
            self.df[columns] = self.df[columns].fillna(fills)
            self.code = (
                f"for col in {c}:\n"
                "    if df[col].notna().any():\n"
                "        df[col] = df[col].fillna(df[col].mode().iloc[0])"
            )
        elif strategy == "constant":
            if value == "":
                raise ValueError("Enter the value to fill with.")
            fills = {}
            for col in columns:
                fill = value
                if pd.api.types.is_numeric_dtype(self.df[col]):
                    try:
                        fill = float(value)
                    except ValueError as e:
                        raise ValueError(f"“{value}” is not a number, but {col} is numeric.") from e
                fills[col] = fill
            self.df[columns] = self.df[columns].fillna(fills)
            self.code = f"df = df.fillna({fills!r})"
        else:
            self.df[columns] = getattr(self.df[columns], strategy)()
            self.code = f"df[{c}] = df[{c}].{strategy}()"
        after = int(self.df[columns].isna().sum().sum())
        label = {"ffill": "previous value", "bfill": "next value", "constant": f"“{value}”"}.get(strategy, strategy)
        left = f" ({_plural(after, 'gap')} left)" if after else ""
        return f"Filled {_plural(filled - after, 'missing cell')} with the {label}{left}." if strategy != "constant" \
            else f"Filled {_plural(filled - after, 'missing cell')} with {label}."

    def fill_na_mean(self):
        cols = self._numeric_cols()
        msg = self.fill_na(cols, "mean") if cols else "No numeric columns."
        return msg

    def fill_na_median(self):
        cols = self._numeric_cols()
        msg = self.fill_na(cols, "median") if cols else "No numeric columns."
        return msg

    # ---- text ------------------------------------------------------------

    def strip_whitespace(self, columns=None):
        cols = self._text_cols(columns)
        changed = 0
        for col in cols:
            s = self.df[col]
            stripped = s.str.strip()
            changed += _changed(s, stripped)
            self.df[col] = stripped
        self.code = (
            f"for col in {cols!r}:\n"
            "    df[col] = df[col].str.strip()"
        )
        return f"Trimmed spaces in {_plural(changed, 'cell')} across {_plural(len(cols), 'text column')}."

    def normalize_text(self, columns, case="none"):
        cols = self._text_cols(self._require(columns))
        if case not in ("none", "lower", "upper", "title"):
            raise ValueError("Case must be none, lower, upper or title.")
        changed = 0
        for col in cols:
            s = self.df[col]
            out = s.str.strip().str.replace(r"\s+", " ", regex=True)
            if case != "none":
                out = getattr(out.str, case)()
            changed += _changed(s, out)
            self.df[col] = out
        case_code = "" if case == "none" else f".str.{case}()"
        self.code = (
            f"for col in {cols!r}:\n"
            f"    df[col] = df[col].str.strip().str.replace(r'\\s+', ' ', regex=True){case_code}"
        )
        how = "" if case == "none" else f", {case} case"
        return f"Normalized {_plural(changed, 'cell')} (trimmed, single spaces{how})."

    def replace_values(self, column, find, replace):
        # An empty replacement means "make it missing", for any column type.
        blank = str(replace).strip() == ""
        if pd.api.types.is_numeric_dtype(self.df[column]):
            try:
                find = float(find)
                replace = float("nan") if blank else float(replace)
            except (ValueError, TypeError):
                pass
        elif blank:
            replace = float("nan")
        count = int((self.df[column] == find).sum())
        self.df[column] = self.df[column].replace(find, replace)
        target_code = "np.nan" if pd.isna(replace) else repr(replace)
        self.code = f"df[{column!r}] = df[{column!r}].replace({find!r}, {target_code})"
        target = "missing (NaN)" if pd.isna(replace) else f"'{replace}'"
        return f"Replaced {count} occurrence(s) of '{find}' with {target} in '{column}'."

    # ---- numbers ---------------------------------------------------------

    def clip_outliers_iqr(self, columns=None):
        cols = self._numeric_cols(columns)
        changed = 0
        for col in cols:
            q1, q3 = self.df[col].quantile(0.25), self.df[col].quantile(0.75)
            iqr = q3 - q1
            clipped = self.df[col].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
            changed += _changed(self.df[col], clipped)
            self.df[col] = clipped
        self.code = (
            f"for col in {cols!r}:\n"
            "    q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)\n"
            "    iqr = q3 - q1\n"
            "    df[col] = df[col].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)"
        )
        return f"Clipped {_plural(changed, 'outlier')} to 1.5×IQR in {_plural(len(cols), 'column')}."

    def clip_outliers_zscore(self, columns=None):
        cols = self._numeric_cols(columns)
        changed = 0
        for col in cols:
            mean, std = self.df[col].mean(), self.df[col].std()
            if std > 0:
                clipped = self.df[col].clip(mean - 3 * std, mean + 3 * std)
                changed += _changed(self.df[col], clipped)
                self.df[col] = clipped
        self.code = (
            f"for col in {cols!r}:\n"
            "    mean, std = df[col].mean(), df[col].std()\n"
            "    if std > 0:\n"
            "        df[col] = df[col].clip(mean - 3 * std, mean + 3 * std)"
        )
        return f"Clipped {_plural(changed, 'outlier')} to ±3σ in {_plural(len(cols), 'column')}."

    def round_numbers(self, columns, decimals=2):
        cols = self._numeric_cols(self._require(columns))
        try:
            decimals = int(decimals)
        except (TypeError, ValueError) as e:
            raise ValueError("Decimals must be a whole number.") from e
        self.df[cols] = self.df[cols].round(decimals)
        self.code = f"df[{cols!r}] = df[{cols!r}].round({decimals})"
        return f"Rounded {_plural(len(cols), 'column')} to {_plural(decimals, 'decimal')}."

    # ---- types & columns -------------------------------------------------

    def rename_column(self, old_name, new_name):
        if new_name in self.df.columns and new_name != old_name:
            raise ValueError(f"Column '{new_name}' already exists.")
        self.df = self.df.rename(columns={old_name: new_name})
        self.code = f"df = df.rename(columns={{{old_name!r}: {new_name!r}}})"
        return f"Renamed '{old_name}' to '{new_name}'."

    def change_dtype(self, column, dtype):
        try:
            self.df[column] = self.df[column].astype(dtype)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot convert '{column}' to {dtype}: {e}") from e
        self.code = f"df[{column!r}] = df[{column!r}].astype({dtype!r})"
        return f"Changed '{column}' type to {dtype}."

    def to_numeric(self, columns):
        cols = self._require(columns)
        failed = 0
        for col in cols:
            s = self.df[col]
            had = s.notna()
            parsed = pd.Series(
                pd.to_numeric(s.astype("string").str.replace(NUMBER_JUNK, "", regex=True), errors="coerce"),
                index=s.index,
            ).astype("float64")
            failed += int((had & parsed.isna()).sum())
            self.df[col] = parsed
        self.code = (
            f"for col in {cols!r}:\n"
            f"    text = df[col].astype('string').str.replace(r'{NUMBER_JUNK}', '', regex=True)\n"
            "    df[col] = pd.to_numeric(text, errors='coerce').astype('float64')"
        )
        lost = f" {_plural(failed, 'value')} could not be read and became missing." if failed else ""
        return f"Converted {_plural(len(cols), 'column')} to numbers.{lost}"

    def to_datetime(self, columns, dayfirst=False):
        cols = self._require(columns)
        dayfirst = dayfirst in (True, "true", "yes")
        failed = 0
        for col in cols:
            s = self.df[col]
            parsed = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst, format="mixed")
            failed += int((s.notna() & parsed.isna()).sum())
            self.df[col] = parsed
        self.code = (
            f"for col in {cols!r}:\n"
            f"    df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst={dayfirst}, format='mixed')"
        )
        lost = f" {_plural(failed, 'value')} could not be read and became missing." if failed else ""
        return f"Converted {_plural(len(cols), 'column')} to dates.{lost}"

    def add_column(self, name, expression):
        """Add (or replace) a column computed from a SQL expression per row."""
        name = str(name or "").strip()
        if not name:
            raise ValueError("Enter a name for the new column.")
        existed = name in self.df.columns
        self.df[name] = eval_expression(self.df, expression)
        self.code = expression_code(name, expression)
        verb = "Replaced" if existed else "Added"
        return f"{verb} column '{name}' = {str(expression).strip()}."

    # part -> (function, pandas code after the column, nullable dtype or None)
    DATE_PARTS = {
        "year": (lambda s: s.dt.year, "dt.year", "Int64"),
        "quarter": (lambda s: s.dt.quarter, "dt.quarter", "Int64"),
        "month": (lambda s: s.dt.month, "dt.month", "Int64"),
        "month_name": (lambda s: s.dt.month_name(), "dt.month_name()", None),
        "week": (lambda s: s.dt.isocalendar().week, "dt.isocalendar().week", "Int64"),
        "day": (lambda s: s.dt.day, "dt.day", "Int64"),
        "weekday": (lambda s: s.dt.day_name(), "dt.day_name()", None),
        "weekday_num": (lambda s: s.dt.dayofweek, "dt.dayofweek", "Int64"),
        "hour": (lambda s: s.dt.hour, "dt.hour", "Int64"),
    }

    def date_parts(self, column, parts):
        """Add columns like <column>_year, <column>_month from a date column."""
        if column not in self.df.columns:
            raise ValueError(f"Unknown column: {column}.")
        if not pd.api.types.is_datetime64_any_dtype(self.df[column]):
            raise ValueError(f"“{column}” is not a date column. Use Convert to date first.")
        parts = [p for p in (parts or []) if p]
        unknown = [p for p in parts if p not in self.DATE_PARTS]
        if not parts or unknown:
            raise ValueError("Choose which date parts to add." if not parts else f"Unknown date part: {', '.join(unknown)}.")
        lines, added = [], []
        for part in parts:
            func, accessor, dtype = self.DATE_PARTS[part]
            new = f"{column}_{part}"
            values = func(self.df[column])
            self.df[new] = values.astype(dtype) if dtype else values
            cast = f".astype({dtype!r})" if dtype else ""
            lines.append(f"df[{new!r}] = df[{column!r}].{accessor}{cast}")
            added.append(new)
        self.code = "\n".join(lines)
        return f"Added {_plural(len(added), 'column')} from {column}: {', '.join(added)}."

    JOIN_HOWS = {"left": "kept all rows of this data", "inner": "kept only matching rows",
                 "outer": "kept all rows of both", "right": "kept all rows of the other file"}

    def join(self, right, right_name, right_code, left_on, right_on, how="left", suffix="_right"):
        """Join another dataset on key columns (pandas merge)."""
        left_on = [left_on] if isinstance(left_on, str) else list(left_on or [])
        right_on = [right_on] if isinstance(right_on, str) else list(right_on or [])
        if not left_on or len(left_on) != len(right_on):
            raise ValueError("Choose a key column on each side.")
        if how not in self.JOIN_HOWS:
            raise ValueError("Join type must be left, inner, outer or right.")
        for c in left_on:
            if c not in self.df.columns:
                raise ValueError(f"Unknown column in this data: {c}.")
        for c in right_on:
            if c not in right.columns:
                raise ValueError(f"Unknown column in {right_name}: {c}.")
        suffix = str(suffix or "_right")
        for lk, rk in zip(left_on, right_on, strict=True):
            lnum, rnum = pd.api.types.is_numeric_dtype(self.df[lk]), pd.api.types.is_numeric_dtype(right[rk])
            if lnum != rnum:
                raise ValueError(f"“{lk}” and “{rk}” hold different kinds of values (numbers vs text). "
                                 "Convert one of them first so the keys can match.")

        left_keys = self.df[left_on].apply(tuple, axis=1)
        right_keys = right[right_on].apply(tuple, axis=1)
        right_set, left_set = set(right_keys), set(left_keys)
        dup_right = int(right_keys.duplicated(keep=False).sum())
        before = len(self.df)
        try:
            result = self.df.merge(right, left_on=left_on, right_on=right_on, how=how, suffixes=("", suffix))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Could not join: {e}") from e
        stats = {
            "otherName": right_name,
            "leftRows": before,
            "rightRows": len(right),
            "matchedLeft": int(left_keys.isin(right_set).sum()),
            "unmatchedLeft": int((~left_keys.isin(right_set)).sum()),
            "unmatchedRight": int((~right_keys.isin(left_set)).sum()),
            "duplicateRightKeys": dup_right,
            "resultRows": len(result),
            "how": how,
        }
        self.preview_override = {"join": stats, "result": result}
        self.df = result

        body = "\n".join("    " + line for line in right_code.splitlines())
        self.code = (
            "def read_other():\n"
            f"{body}\n"
            "    return df\n"
            "right = read_other()\n"
            f"df = df.merge(right, left_on={left_on!r}, right_on={right_on!r}, how={how!r}, suffixes=('', {suffix!r}))"
        )
        grew = f" Rows went from {before:,} to {len(result):,} because some keys repeat in {right_name}." \
            if len(result) > before and dup_right else ""
        return (f"Joined {right_name} on {', '.join(left_on)} ({self.JOIN_HOWS[how]}): "
                f"{stats['matchedLeft']:,} of {before:,} rows matched.{grew}")

    def drop_columns(self, columns):
        if len(columns) == 0:
            raise ValueError("No columns selected to drop.")
        if len(columns) >= len(self.df.columns):
            raise ValueError("Cannot drop all columns. Keep at least one.")
        self.df = self.df.drop(columns=columns)
        self.code = f"df = df.drop(columns={list(columns)!r})"
        return f"Dropped {len(columns)} column(s): {', '.join(map(str, columns))}."

    # ---- feature engineering ------------------------------------------------

    MAX_ONE_HOT = 50

    @staticmethod
    def _number(value, what, integer=False, minimum=None):
        try:
            v = int(str(value).strip()) if integer else float(str(value).strip())
        except (TypeError, ValueError) as e:
            raise ValueError(f"{what} must be a {'whole ' if integer else ''}number.") from e
        if minimum is not None and v < minimum:
            raise ValueError(f"{what} must be at least {minimum}.")
        return v

    def _target_names(self, cols, suffix, keep_original):
        """Where transformed values go: in place, or new <col><suffix> columns."""
        if not keep_original:
            return {c: c for c in cols}
        names = {c: f"{c}{suffix}" for c in cols}
        clash = [n for n in names.values() if n in self.df.columns]
        if clash:
            raise ValueError(f"Column(s) already exist: {', '.join(clash)}. Rename or drop them first.")
        return names

    def one_hot(self, columns, drop_first=False, keep_original=False):
        """Indicator (0/1) columns for each category: <col>_<value>."""
        cols = self._require(columns)
        for c in cols:
            n = self.df[c].nunique()
            if n > self.MAX_ONE_HOT:
                raise ValueError(f"“{c}” has {n} different values; at most {self.MAX_ONE_HOT} can become columns. "
                                 "Use Group rare categories first.")
            if n < 2:
                raise ValueError(f"“{c}” has fewer than two different values, so there is nothing to encode.")
        dummies = pd.get_dummies(self.df[cols], columns=cols, drop_first=bool(drop_first), dtype="int64")
        clash = [n for n in dummies.columns if n in self.df.columns and (keep_original or n not in cols)]
        if clash:
            raise ValueError(f"Column(s) already exist: {', '.join(map(str, clash[:5]))}. Rename them first.")
        gaps = int(self.df[cols].isna().any(axis=1).sum())
        args = f"columns={cols!r}, drop_first={bool(drop_first)}, dtype='int64'"
        if keep_original:
            self.df = self.df.join(dummies)
            self.code = f"df = df.join(pd.get_dummies(df[{cols!r}], {args}))"
        else:
            self.df = pd.get_dummies(self.df, columns=cols, drop_first=bool(drop_first), dtype="int64")
            self.code = f"df = pd.get_dummies(df, {args})"
        extra = f" {_plural(gaps, 'row')} with a missing value get 0 in that column's indicators." if gaps else ""
        return f"Added {_plural(dummies.shape[1], 'indicator column')} for {', '.join(map(str, cols))}.{extra}"

    SCALERS = {
        "standard": ("(df[c] - df[c].mean()) / df[c].std(ddof=0)", "mean 0 and standard deviation 1"),
        "minmax": ("(df[c] - df[c].min()) / (df[c].max() - df[c].min())", "the range 0 to 1"),
    }

    def scale(self, columns, method="standard", keep_original=False):
        """Standardize (z-score, like scikit-learn's StandardScaler) or min-max scale numeric columns."""
        cols = self._numeric_cols(self._require(columns))
        if method not in self.SCALERS:
            raise ValueError("Method must be standard or minmax.")
        expr, what = self.SCALERS[method]
        flat = [c for c in cols if self.df[c].nunique() < 2]
        if flat:
            raise ValueError(f"Can't scale a column with a single value: {', '.join(map(str, flat))}.")
        names = self._target_names(cols, "_scaled", keep_original)
        lines = []
        for c in cols:
            s = self.df[c].astype("float64")
            self.df[names[c]] = (s - s.mean()) / s.std(ddof=0) if method == "standard" else (s - s.min()) / (s.max() - s.min())
            lines.append(f"df[{names[c]!r}] = " + expr.replace("df[c]", f"df[{c!r}].astype('float64')"))
        self.code = "\n".join(lines)
        where = f", saved as {', '.join(names.values())}" if keep_original else ""
        return f"Scaled {_plural(len(cols), 'column')} to {what}{where}."

    @staticmethod
    def _bin_labels(edges):
        def one(a, b, digits):
            if a == -np.inf:
                return f"≤ {b:.{digits}g}"
            if b == np.inf:
                return f"> {a:.{digits}g}"
            return f"{a:.{digits}g}–{b:.{digits}g}"

        for digits in range(3, 12):
            labels = [one(a, b, digits) for a, b in zip(edges[:-1], edges[1:], strict=True)]
            if len(set(labels)) == len(labels):
                return labels
        return [f"bin {i + 1}" for i in range(len(edges) - 1)]

    def bin_values(self, column, method="width", bins=5, edges="", name=""):
        """Turn a number into ordered ranges (equal width, equal count or your own edges)."""
        if column not in self.df.columns:
            raise ValueError(f"Unknown column: {column}.")
        self._numeric_cols([column])
        s = self.df[column].dropna().astype("float64")
        if s.empty:
            raise ValueError(f"“{column}” has no values to bin.")
        if method in ("width", "quantile"):
            n = self._number(bins, "Number of bins", integer=True, minimum=2)
            if n > 100:
                raise ValueError("Use at most 100 bins.")
            if method == "width":
                if s.min() == s.max():
                    raise ValueError(f"Every value of “{column}” is the same; there is nothing to split.")
                cuts = np.linspace(s.min(), s.max(), n + 1).tolist()
                how = f"{n} equal-width ranges"
            else:
                cuts = np.unique(np.quantile(s, np.linspace(0, 1, n + 1))).tolist()
                if len(cuts) < 3:
                    raise ValueError(f"“{column}” has too few different values for {n} equal-count groups.")
                how = f"{len(cuts) - 1} equal-count groups"
                if len(cuts) - 1 < n:
                    how += f" (asked for {n}; repeated values merged some)"
        elif method == "edges":
            parts = [p for p in str(edges or "").replace(";", ",").split(",") if p.strip()]
            try:
                cuts = [float(p) for p in parts]
            except ValueError as e:
                raise ValueError("Edges must be numbers separated by commas, e.g. 0, 18, 30, 65, inf.") from e
            if len(cuts) < 2 or any(b <= a for a, b in zip(cuts[:-1], cuts[1:], strict=True)):
                raise ValueError("Give at least two edges in increasing order, e.g. 0, 18, 30, 65, inf.")
            how = f"{len(cuts) - 1} custom ranges"
        else:
            raise ValueError("Method must be width, quantile or edges.")
        new = (name or "").strip() or f"{column}_bin"
        if new in self.df.columns and new != column:
            raise ValueError(f"Column '{new}' already exists. Choose another name.")
        labels = self._bin_labels(cuts)
        before_missing = int(self.df[column].isna().sum())
        self.df[new] = pd.cut(self.df[column], bins=cuts, labels=labels, include_lowest=True)
        outside = int(self.df[new].isna().sum()) - before_missing
        bins_code = "[" + ", ".join(repr(x) if np.isfinite(x) else f"float('{x}')" for x in cuts) + "]"
        self.code = f"df[{new!r}] = pd.cut(df[{column!r}], bins={bins_code}, labels={labels!r}, include_lowest=True)"
        tail = f" {_plural(outside, 'value')} fell outside the edges and became missing." if outside else ""
        return f"Binned {column} into {how} as {new}.{tail}"

    LOGS = {"log1p": ("np.log1p", -1, "log(1 + x)"), "log": ("np.log", 0, "natural log"), "log10": ("np.log10", 0, "log10")}

    def log_transform(self, columns, method="log1p", keep_original=False):
        """Compress a long right tail (prices, counts, incomes)."""
        cols = self._numeric_cols(self._require(columns))
        if method not in self.LOGS:
            raise ValueError("Method must be log1p, log or log10.")
        func, floor, label = self.LOGS[method]
        for c in cols:
            bad = int((self.df[c] <= floor).sum())
            if bad:
                hint = " Use log(1 + x), which accepts zeros." if method != "log1p" and (self.df[c] > -1).all() else ""
                raise ValueError(f"“{c}” has {_plural(bad, 'value')} at or below {floor}, where {label} is undefined.{hint}")
        names = self._target_names(cols, "_log", keep_original)
        lines = []
        for c in cols:
            self.df[names[c]] = getattr(np, func.split(".")[1])(self.df[c].astype("float64"))
            lines.append(f"df[{names[c]!r}] = {func}(df[{c!r}].astype('float64'))")
        self.code = "\n".join(lines)
        where = f", saved as {', '.join(names.values())}" if keep_original else ""
        return f"Applied {label} to {_plural(len(cols), 'column')}{where}."

    def group_rare(self, columns, mode="top", top_n=10, min_share=1, label="Other"):
        """Merge infrequent categories into one label."""
        cols = self._require(columns)
        label = str(label if label is not None else "Other").strip() or "Other"
        lines, merged = [], []
        for c in cols:
            if pd.api.types.is_numeric_dtype(self.df[c]) and not pd.api.types.is_bool_dtype(self.df[c]):
                raise ValueError(f"“{c}” holds numbers; use Bin values to group them.")
            counts = self.df[c].value_counts()
            if mode == "top":
                n = self._number(top_n, "Categories to keep", integer=True, minimum=1)
                keep = counts.index[:n].tolist()
            elif mode == "share":
                share = self._number(min_share, "Minimum share", minimum=0) / 100
                keep = counts.index[counts / counts.sum() >= share].tolist() if counts.sum() else []
            else:
                raise ValueError("Mode must be top or share.")
            rare = counts.index.difference(keep)
            if len(rare) == 0:
                continue
            is_cat = isinstance(self.df[c].dtype, pd.CategoricalDtype)
            col = self.df[c].astype(object) if is_cat else self.df[c]
            self.df[c] = col.where(col.isin(keep) | col.isna(), label)
            ref = f"df[{c!r}]"
            lines.append(f"keep = {keep!r}")
            if is_cat:
                lines.append(f"{ref} = {ref}.astype(object)")
            lines.append(f"{ref} = {ref}.where({ref}.isin(keep) | {ref}.isna(), {label!r})")
            merged.append(f"{c} ({len(rare)} → {label!r}, {int(counts[rare].sum()):,} rows)")
        if not merged:
            raise ValueError("Nothing to group: every category is common enough with these settings.")
        self.code = "\n".join(lines)
        return f"Grouped rare categories: {'; '.join(merged)}."

    def add_clusters(self, k, features=None, name="cluster"):
        """Add a k-means cluster label (Cluster 1 = largest) as a new column."""
        from .clusters import cluster_code, fit_clusters

        name = str(name or "cluster").strip() or "cluster"
        if name in self.df.columns:
            raise ValueError(f"Column '{name}' already exists. Choose another name.")
        labels, _, used, numeric, categorical = fit_clusters(self.df, features or None, k)
        self.df[name] = [f"Cluster {c}" for c in labels]
        self.code = cluster_code(numeric, categorical, int(k), name)
        sizes = pd.Series(labels).value_counts().sort_index()
        parts = ", ".join(f"{c}: {n:,}" for c, n in sizes.items())
        return f"Added {name} with {int(k)} k-means clusters from {_plural(len(used), 'column')} (rows per cluster {parts})."

    # ---- SQL ---------------------------------------------------------------

    def sql_query(self, sql):
        """Replace the data with the result of a SQL query (table name: data)."""
        before_rows, before_cols = self.df.shape
        self.df = run_query_full(self.df, sql)
        self.code = sql_code(sql)
        rows, cols = self.df.shape
        return (f"Replaced the data with a SQL query result: {_plural(rows, 'row')} × {_plural(cols, 'column')} "
                f"(was {before_rows:,} × {before_cols}).")

    def pivot_table(self, rows, columns=None, values=None, agg="count", percent="none", sort="label"):
        """Replace the data with a pivot table (without the Total row)."""
        res = pivot(self.df, rows, columns=columns, values=values, agg=agg, totals=False, percent=percent, sort=sort)
        self.df = res["table"]
        self.code = res["code"] + "\ndf = table"
        r, c = self.df.shape
        return f"Replaced the data with a pivot table: {_plural(r, 'row')} × {_plural(c, 'column')}."

    # ---- dispatch --------------------------------------------------------

    def apply_clean(self, method_key, **kwargs):
        if method_key and method_key in self.clean_methods:
            return self.clean_methods[method_key](**kwargs)
        return None

    def export_data(self):
        return self.df.to_csv(index=False).encode("utf-8")
