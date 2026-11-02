"""Run SQL against the working dataset with DuckDB.

The dataset is registered (zero-copy) as a table named ``data``. File-system
access is disabled, so queries cannot read or write files on disk, and only
statements that return rows are accepted.
"""

import re
import time

import duckdb
import pandas as pd

TABLE = "data"
MAX_ERROR_LINES = 4


class QueryError(ValueError):
    """A user-facing SQL error (syntax, unknown column, not a SELECT...)."""


def _connect(df):
    con = duckdb.connect(config={"enable_external_access": False})
    con.register(TABLE, df)
    return con


def _friendly(exc):
    text = str(exc).strip()
    # DuckDB prefixes messages with their kind, e.g. "Parser Error: ...". Keep it short.
    lines = [ln for ln in text.splitlines() if ln.strip()][:MAX_ERROR_LINES]
    return "\n".join(lines) or exc.__class__.__name__


def _relation(con, sql):
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Write a query first, e.g. SELECT * FROM data LIMIT 10")
    try:
        rel = con.sql(sql)
    except duckdb.Error as e:
        raise QueryError(_friendly(e)) from e
    if rel is None:
        raise QueryError("Only queries that return rows are allowed (SELECT, WITH, ...).")
    return rel


def run_query(df, sql, limit=500):
    """Run ``sql`` and return (preview DataFrame, total row count, elapsed ms)."""
    start = time.perf_counter()
    con = _connect(df)
    try:
        rel = _relation(con, sql)
        try:
            total = rel.shape[0]
            preview = rel.limit(int(limit)).df()
        except duckdb.Error as e:
            raise QueryError(_friendly(e)) from e
    finally:
        con.close()
    return preview, int(total), round((time.perf_counter() - start) * 1000, 1)


def run_query_full(df, sql):
    """Run ``sql`` and return the full result as a DataFrame."""
    con = _connect(df)
    try:
        rel = _relation(con, sql)
        try:
            return rel.df()
        except duckdb.Error as e:
            raise QueryError(_friendly(e)) from e
    finally:
        con.close()


ROW_KEY = "__databoss_row"


def eval_expression(df, expression):
    """Evaluate a SQL expression for every row; returns values aligned with ``df``.

    Rows are matched back by an explicit row number because DuckDB may scan in
    parallel and does not keep input order without ORDER BY.
    """
    expr = (expression or "").strip().rstrip(";")
    if not expr:
        raise QueryError("Write an expression, e.g. price / visits")
    con = duckdb.connect(config={"enable_external_access": False})
    try:
        con.register(TABLE, df.assign(**{ROW_KEY: range(len(df))}))
        try:
            res = con.sql(f"SELECT ({expr}) AS v FROM {TABLE} ORDER BY {ROW_KEY}").df()
        except duckdb.Error as e:
            raise QueryError(_friendly(e)) from e
    finally:
        con.close()
    return res["v"].to_numpy()


def expression_code(name, expression):
    """Code that adds a calculated column the same way the app does."""
    expr = (expression or "").strip().rstrip(";")
    sql = f"SELECT ({expr}) AS v FROM {TABLE} ORDER BY {ROW_KEY}"
    return (
        "import duckdb\n"
        "con = duckdb.connect()\n"
        f"con.register({TABLE!r}, df.assign({ROW_KEY}=range(len(df))))\n"
        f"df[{name!r}] = con.sql({_triple_quote(sql)}).df()['v'].to_numpy()"
    )


_SIMPLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name):
    """Quote a column name for SQL when needed (spaces, slashes, keywords...)."""
    name = str(name)
    if _SIMPLE_NAME.match(name) and name.lower() not in {"select", "from", "where", "group", "order", "by", "limit", "table"}:
        return name
    return '"' + name.replace('"', '""') + '"'


def example_queries(df, limit=6):
    """A few useful starter queries built from the dataset's columns."""
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    text = [c for c in df.columns if c not in numeric and 1 < df[c].nunique() <= 50]
    dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    q = quote_ident
    out = [{"title": "First 100 rows", "sql": f"SELECT *\nFROM {TABLE}\nLIMIT 100"}]
    if text:
        out.append({"title": f"Most common {text[0]}",
                    "sql": f"SELECT {q(text[0])}, COUNT(*) AS n\nFROM {TABLE}\nGROUP BY {q(text[0])}\nORDER BY n DESC"})
    if text and numeric:
        group, value, alias = q(text[0]), q(numeric[0]), f"avg_{_slug(numeric[0])}"
        out.append({"title": f"Average {numeric[0]} by {text[0]}",
                    "sql": (f"SELECT {group},\n       COUNT(*) AS n,\n       ROUND(AVG({value}), 2) AS {alias}\n"
                            f"FROM {TABLE}\nGROUP BY {group}\nORDER BY {alias} DESC")})
    if numeric:
        c = numeric[0]
        out.append({"title": f"Top 10 by {c}", "sql": f"SELECT *\nFROM {TABLE}\nWHERE {q(c)} IS NOT NULL\nORDER BY {q(c)} DESC\nLIMIT 10"})
    if dates and numeric:
        out.append({"title": f"{numeric[0]} per month",
                    "sql": (f"SELECT date_trunc('month', {q(dates[0])}) AS month,\n       SUM({q(numeric[0])}) AS total\n"
                            f"FROM {TABLE}\nGROUP BY month\nORDER BY month")})
    gappy = [c for c in df.columns if df[c].isna().any()]
    if gappy:
        c = gappy[0]
        out.append({"title": f"Rows missing {c}", "sql": f"SELECT *\nFROM {TABLE}\nWHERE {q(c)} IS NULL"})
    return out[:limit]


def _slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_").lower() or "value"


def sql_code(sql):
    """pandas + DuckDB code that reproduces a query step in an exported script."""
    body = (sql or "").strip().rstrip(";")
    return (
        "import duckdb\n"
        "con = duckdb.connect()\n"
        f"con.register({TABLE!r}, df)\n"
        f"df = con.sql({_triple_quote(body)}).df()"
    )


def _triple_quote(text):
    if '"""' not in text and "\\" not in text and not text.endswith('"'):
        return '"""' + text + '"""'
    return repr(text)
