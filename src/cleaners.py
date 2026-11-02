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
        }

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
        s = self.df[column]
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

    def drop_columns(self, columns):
        if len(columns) == 0:
            raise ValueError("No columns selected to drop.")
        if len(columns) >= len(self.df.columns):
            raise ValueError("Cannot drop all columns. Keep at least one.")
        self.df = self.df.drop(columns=columns)
        self.code = f"df = df.drop(columns={list(columns)!r})"
        return f"Dropped {len(columns)} column(s): {', '.join(map(str, columns))}."

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
