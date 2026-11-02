"""Group-by / pivot tables.

``pivot`` returns the table plus the pandas code that rebuilds it. Totals are
computed explicitly: for additive aggregations (count, sum) by adding cells,
for the others (mean, median, ...) from the raw rows, so a "Total" mean is the
true overall mean rather than an average of averages.
"""

import pandas as pd

AGGS = ("count", "sum", "mean", "median", "min", "max", "nunique")
ADDITIVE = ("count", "sum")
PERCENTS = ("none", "row", "column", "total")
SORTS = ("label", "value_desc", "value_asc")
MAX_ROW_GROUPS = 1000
MAX_COLUMN_GROUPS = 50
TOTAL = "Total"


class PivotError(ValueError):
    """A user-facing problem with the pivot settings."""


def _value_label(values, agg):
    if values is None:
        return "rows"
    return {"nunique": f"distinct {values}", "count": f"count of {values}"}.get(agg, f"{agg} of {values}")


def pivot(df, rows, columns=None, values=None, agg="count", totals=True, percent="none", sort="label"):
    """Build a pivot table.

    rows:    list of columns to group rows by (at least one)
    columns: optional column whose values become table columns
    values:  column to aggregate; None counts rows
    """
    rows = [r for r in (rows or []) if r]
    if not rows:
        raise PivotError("Choose at least one column for the rows.")
    for c in [*rows, columns, values]:
        if c and c not in df.columns:
            raise PivotError(f"Unknown column: {c}.")
    if columns in rows:
        raise PivotError("Use different columns for rows and columns.")
    if agg not in AGGS:
        raise PivotError(f"Aggregation must be one of: {', '.join(AGGS)}.")
    if percent not in PERCENTS or sort not in SORTS:
        raise PivotError("Unknown display option.")
    if values is None:
        agg = "count"
    elif agg in ("sum", "mean", "median") and not pd.api.types.is_numeric_dtype(df[values]):
        raise PivotError(f"“{values}” is not numeric; use count or distinct count.")
    if percent != "none" and agg not in ADDITIVE:
        raise PivotError("Percentages only make sense for count or sum.")
    if percent in ("row", "column") and not columns:
        raise PivotError("Pick a column grouping to show % of row or % of column.")

    keys = rows + ([columns] if columns else [])
    needed = list(dict.fromkeys(keys + ([values] if values else [])))
    data = df[needed].dropna(subset=keys)
    dropped = len(df) - len(data)
    notes = [f"{dropped:,} row(s) with an empty grouping value were left out."] if dropped else []

    def aggregate(by):
        g = data.groupby(by, observed=True, sort=True)
        return g.size() if values is None else g[values].agg(agg)

    def overall():
        return len(data) if values is None else data[values].agg(agg)

    cells = aggregate(keys)
    label = _value_label(values, agg)
    if columns:
        n_cols = cells.index.get_level_values(columns).nunique()
        if n_cols > MAX_COLUMN_GROUPS:
            raise PivotError(f"“{columns}” has {n_cols} distinct values; at most {MAX_COLUMN_GROUPS} fit as columns. "
                             "Put it in the rows instead, or filter first.")
        table = cells.unstack(columns)
        table.columns = [str(c) for c in table.columns]
    else:
        table = cells.to_frame(label)
    if len(table) > MAX_ROW_GROUPS:
        raise PivotError(f"That makes {len(table):,} row groups; at most {MAX_ROW_GROUPS:,} can be shown. Use fewer row columns.")
    if agg == "count":
        table = table.fillna(0).astype("int64")

    # Totals, before percentages so they can be used as denominators.
    if agg in ADDITIVE:
        row_tot = table.sum(axis=1)
        col_tot = table.sum(axis=0)
        grand = row_tot.sum()
    else:
        row_tot = aggregate(rows).reindex(table.index) if columns else table.iloc[:, 0]
        col_tot = (aggregate(columns) if columns else pd.Series({label: overall()}))
        col_tot.index = [str(c) for c in col_tot.index]
        grand = overall()

    if percent == "row":
        table = table.div(row_tot, axis=0) * 100
        row_tot = row_tot / row_tot * 100
        col_tot = col_tot / grand * 100
        grand = 100.0
    elif percent == "column":
        table = table.div(col_tot, axis=1) * 100
        row_tot = row_tot / grand * 100
        col_tot = col_tot / col_tot * 100
        grand = 100.0
    elif percent == "total":
        table = table / grand * 100
        row_tot = row_tot / grand * 100
        col_tot = col_tot / grand * 100
        grand = 100.0

    if columns and totals:
        # For count/sum the Total column is the sum of the cells shown (also after
        # percentages), exactly as the exported code computes it, so sorting by it
        # gives the same order in the app and in the script.
        table[TOTAL] = table.sum(axis=1) if agg in ADDITIVE else row_tot

    sort_col = TOTAL if (columns and totals) else table.columns[0]
    if sort == "value_desc":
        table = table.sort_values(sort_col, ascending=False, kind="stable")
    elif sort == "value_asc":
        table = table.sort_values(sort_col, ascending=True, kind="stable")

    out = table.reset_index()
    out.columns = [str(c) for c in out.columns]
    if totals:
        total_row: dict[str, object] = {r: "" for r in rows}
        total_row[rows[0]] = TOTAL
        for c in table.columns:
            total_row[str(c)] = grand if c == TOTAL else col_tot.get(str(c), grand if not columns else None)
        out = pd.concat([out, pd.DataFrame([total_row])], ignore_index=True)

    value_cols = [str(c) for c in table.columns]
    code = _code(rows, columns, values, agg, totals, percent, sort, label)
    return {"table": out, "rows": rows, "valueColumns": value_cols, "label": label,
            "percent": percent != "none", "hasTotals": bool(totals), "notes": notes, "code": code}


def _code(rows, columns, values, agg, totals, percent, sort, label):
    """Readable pandas code that builds the same table."""
    keys = rows + ([columns] if columns else [])
    lines = [f"data = df.dropna(subset={keys!r})"]
    if values is None:
        lines.append(f"cells = data.groupby({keys!r}, observed=True).size()")
    else:
        lines.append(f"cells = data.groupby({keys!r}, observed=True)[{values!r}].agg({agg!r})")
    if columns:
        lines.append(f"table = cells.unstack({columns!r})")
    else:
        lines.append(f"table = cells.to_frame({label!r})")
    if agg == "count":
        lines.append("table = table.fillna(0).astype('int64')")
    if percent == "row":
        lines.append("table = table.div(table.sum(axis=1), axis=0) * 100")
    elif percent == "column":
        lines.append("table = table.div(table.sum(axis=0), axis=1) * 100")
    elif percent == "total":
        lines.append("table = table / table.values.sum() * 100")
    if columns and totals:
        if agg in ADDITIVE:
            lines.append(f"table[{TOTAL!r}] = table.sum(axis=1)")
        else:
            lines.append(f"table[{TOTAL!r}] = data.groupby({rows!r}, observed=True)[{values!r}].agg({agg!r})")
    if sort != "label":
        col = TOTAL if (columns and totals) else None
        target = repr(col) if col else "table.columns[0]"
        lines.append(f"table = table.sort_values({target}, ascending={sort == 'value_asc'}, kind='stable')")
    lines.append("table = table.reset_index()")
    return "\n".join(lines)
