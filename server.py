"""Data Boss backend.

Long-running process spawned by the Electron app. It reads one JSON request
per line on stdin and writes one JSON response per line on stdout:

    request:  {"id": 1, "cmd": "load", "args": {"path": "/x.csv"}}
    response: {"id": 1, "ok": true, "result": {...}}
              {"id": 1, "ok": false, "error": "message"}

All dataframe state (working copy, undo history, operation log) lives here.
"""

import base64
import json
import math
import os
import queue
import re
import sys
import threading
import traceback
from contextlib import nullcontext

import matplotlib as mpl
import numpy as np
import pandas as pd
from cycler import cycler
from matplotlib.colors import LinearSegmentedColormap

from src import DataCleaner, DataInspector, DataVisualizer
from src.analysis import pivot
from src.files import FileFormatError, excel_sheets, read_table, write_table
from src.inspectors import _label
from src.query import example_queries, quote_ident, run_query, run_query_full, sql_code
from src.segments import compare_segment
from src.stats import compare
from src.trends import trends

MAX_FILE_SIZE_MB = 200
PREVIEW_ROWS = 10
CATEGORICAL_DTYPES = ["object", "category", "bool", "string"]

# Keep stdout reserved for protocol messages; anything a library prints goes
# to stderr instead (Electron forwards stderr to its console).
_protocol_out = sys.stdout
sys.stdout = sys.stderr


def table(df):
    """Serialise a DataFrame to {columns, index, data} with NaN -> null."""
    if df is None:
        return None
    payload = json.loads(
        df.to_json(orient="split", date_format="iso", default_handler=str)
    )
    payload["columns"] = [str(c) for c in payload["columns"]]
    payload["index"] = [str(i) for i in payload.get("index", [])]
    return payload


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def chart_theme(style):
    """Turn UI theme colours into (matplotlib rc params, diverging colormap)."""
    if not style:
        return None, "coolwarm"

    def color(key, default):
        value = str(style.get(key, "")).strip()
        return value if HEX_COLOR.match(value) else default

    surface = color("surface", "#FFFFFF")
    text = color("text", "#18181B")
    muted = color("muted", "#6B6B74")
    border = color("border", "#DEDFE3")
    palette = [str(c).strip() for c in style.get("palette") or [] if HEX_COLOR.match(str(c).strip())]

    rc = {
        "figure.facecolor": surface,
        "axes.facecolor": surface,
        "savefig.facecolor": surface,
        "axes.edgecolor": border,
        "axes.labelcolor": text,
        "axes.titlecolor": text,
        "text.color": text,
        "xtick.color": muted,
        "ytick.color": muted,
        "grid.color": border,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
    if palette:
        rc["axes.prop_cycle"] = cycler(color=palette)

    cmap = LinearSegmentedColormap.from_list(
        "ui_diverging", [color("negative", "#DC2626"), surface, color("positive", "#2563EB")]
    )
    return rc, cmap


def jsonable(value):
    """Make inspection results JSON-safe: DataFrames -> tables, NaN/inf -> null, numpy -> Python."""
    if isinstance(value, pd.DataFrame):
        return table(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def column_kind(series):
    if pd.api.types.is_bool_dtype(series):
        return "categorical"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if str(series.dtype) in CATEGORICAL_DTYPES or pd.api.types.is_object_dtype(series):
        return "categorical"
    return "other"


class Session:
    def __init__(self):
        self.path = None
        self.df = None
        self.read_code = ""
        self.source = {}
        self.secondary = {}  # name -> {"df", "path", "read_code"} for joins
        self.history = []
        self.log = []

    # ---- helpers ---------------------------------------------------------

    def require_df(self):
        if self.df is None:
            raise ValueError("No dataset loaded. Open a CSV file first.")
        return self.df

    def snapshot(self):
        df = self.require_df()
        columns = [
            {
                "name": str(c),
                "dtype": str(df[c].dtype),
                "kind": column_kind(df[c]),
                "missing": int(df[c].isna().sum()),
            }
            for c in df.columns
        ]
        preview = None
        if self.history:
            before = self.history[-1]
            preview = {
                "before": {"shape": list(before.shape), "table": table(before.head(PREVIEW_ROWS))},
                "after": {"shape": list(df.shape), "table": table(df.head(PREVIEW_ROWS))},
            }
        return {
            "path": self.path,
            "fileName": os.path.basename(self.path) if self.path else None,
            "source": self.source,
            "secondary": [
                {"name": k, "shape": list(v["df"].shape),
                 "columns": [{"name": str(c), "dtype": str(v["df"][c].dtype)} for c in v["df"].columns]}
                for k, v in self.secondary.items()
            ],
            "shape": list(df.shape),
            "missingCells": int(df.isna().sum().sum()),
            "duplicateRows": int(df.duplicated().sum()),
            "columns": columns,
            "profile": table(DataInspector(df).show_column_profile()),
            "log": self.log,
            "canUndo": bool(self.history),
            "preview": preview,
        }

    # ---- commands --------------------------------------------------------

    def cmd_load(self, path, sheet=None, options=None):
        """Open a data file. For Excel files with several sheets and no sheet chosen,
        returns {"needsSheet": True, "sheets": [...]} without changing the session."""
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(
                f"File is too large ({size / 1024 / 1024:.1f} MB). "
                f"Maximum allowed size is {MAX_FILE_SIZE_MB} MB."
            )
        try:
            if sheet is None and path.lower().endswith((".xlsx", ".xlsm")):
                sheets = excel_sheets(path)
                if len(sheets) > 1:
                    return {"needsSheet": True, "sheets": sheets, "path": path}
            df, read_code, notes, info = read_table(path, sheet=sheet, options=options)
        except FileFormatError:
            raise
        except Exception as e:  # noqa: BLE001 - surface any parse error to the UI
            raise ValueError(f"Could not read the file: {e}") from e

        self.path = path
        self.df = df
        self.read_code = read_code
        self.source = {**info, "notes": notes, "sheets": excel_sheets(path) if info["format"] == "excel" else None}
        self.secondary = {}
        self.history = []
        self.log = []
        return self.snapshot()

    def cmd_load_secondary(self, path, sheet=None, options=None):
        """Open another file to join with. Same formats and sheet handling as load."""
        self.require_df()
        if sheet is None and path.lower().endswith((".xlsx", ".xlsm")):
            sheets = excel_sheets(path)
            if len(sheets) > 1:
                return {"needsSheet": True, "sheets": sheets, "path": path}
        df, read_code, notes, info = read_table(path, sheet=sheet, options=options)
        stem = os.path.splitext(os.path.basename(path))[0] or "other"
        name, n = stem, 2
        while name in self.secondary and self.secondary[name]["path"] != path:
            name, n = f"{stem}_{n}", n + 1
        self.secondary[name] = {"df": df, "path": path, "read_code": read_code}
        return {"name": name, "shape": list(df.shape), "notes": notes, "state": self.snapshot()}

    def _resolve_join(self, method, params):
        if method != "JOIN":
            return params
        params = dict(params)
        name = params.pop("dataset", None)
        other = self.secondary.get(name)
        if other is None:
            raise ValueError("Choose the other file to join with.")
        return {**params, "right": other["df"], "right_name": name, "right_code": other["read_code"]}

    def cmd_reload(self, sheet=None, options=None):
        """Re-read the current file with different import settings (clears history)."""
        if not self.path:
            raise ValueError("No dataset loaded. Open a file first.")
        return self.cmd_load(self.path, sheet=sheet, options=options)

    def cmd_state(self):
        return self.snapshot()

    def cmd_rows(self, offset=0, limit=100):
        df = self.require_df()
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 1000))
        return {"total": len(df), "offset": offset, "table": table(df.iloc[offset:offset + limit])}

    def cmd_value_counts(self, column):
        df = self.require_df()
        return {"table": table(DataInspector(df).value_counts(column))}

    def cmd_inspect(self, kind, params=None):
        df = self.require_df()
        result = DataInspector(df).render(kind, **(params or {}))
        if result is None:
            raise ValueError(f"Unknown inspection: {kind}")
        return jsonable(result)

    def cmd_clean(self, method, params=None):
        df = self.require_df()
        params = params or {}
        cleaner = DataCleaner(df)
        if method not in cleaner.clean_methods:
            raise ValueError(f"Unknown cleaning method: {method}")

        shape_before = df.shape
        msg = cleaner.apply_clean(method, **self._resolve_join(method, params))  # raises -> state unchanged
        self.history.append(df)
        self.df = cleaner.df.reset_index(drop=True)
        self.log.append({
            "step": len(self.log) + 1,
            "method": method,
            "msg": msg,
            "code": cleaner.code,
            "shape_before": list(shape_before),
            "shape_after": list(self.df.shape),
        })
        return {"message": msg, "state": self.snapshot()}

    def cmd_preview(self, method, params=None, sample=8):
        """Dry run: apply the operation to a copy and describe exactly what would change."""
        before = self.require_df()
        cleaner = DataCleaner(before)
        if method not in cleaner.clean_methods:
            raise ValueError(f"Unknown cleaning method: {method}")
        msg = cleaner.apply_clean(method, **self._resolve_join(method, params or {}))
        after = cleaner.df
        if cleaner.preview_override:  # joins: describe matches instead of a cell diff
            extra = cleaner.preview_override
            result = extra["result"]
            return {
                "message": msg, "rows": [len(before), len(result)], "cols": [before.shape[1], result.shape[1]],
                "removedRows": max(0, len(before) - len(result)), "removedColumns": [],
                "addedColumns": [str(c) for c in result.columns if c not in before.columns],
                "changedCells": 0, "changedByColumn": {}, "dtypeChanges": [], "changes": {"columns": [], "rows": []},
                "removedSample": None, "orderSample": None, "addedSample": None,
                "join": extra["join"], "resultSample": table(result.head(sample)), "code": cleaner.code,
            }

        removed_rows = before.index.difference(after.index)
        removed_cols = [str(c) for c in before.columns if c not in after.columns]
        added_cols = [str(c) for c in after.columns if c not in before.columns]
        rows = after.index.intersection(before.index)
        cols = [c for c in after.columns if c in before.columns]

        changed = pd.DataFrame(False, index=rows, columns=cols)
        dtype_changes = []
        for c in cols:
            b, a = before.loc[rows, c], after.loc[rows, c]
            try:
                same = b.eq(a) | (b.isna() & a.isna())
            except TypeError:
                same = b.astype(str).eq(a.astype(str))
            changed[c] = ~same.astype(bool)
            if str(before[c].dtype) != str(after[c].dtype):
                dtype_changes.append({"column": str(c), "before": str(before[c].dtype), "after": str(after[c].dtype)})

        by_col = {str(c): int(n) for c, n in changed.sum().items() if n}
        hit_rows = changed.index[changed.any(axis=1)][:sample]
        hit_cols = [c for c in cols if by_col.get(str(c))][:5]
        changes = {
            "columns": [str(c) for c in hit_cols],
            "rows": [
                {
                    "row": int(r) if isinstance(r, (int, np.integer)) else str(r),
                    "cells": [
                        {"before": _label(before.at[r, c]), "after": _label(after.at[r, c]), "changed": bool(changed.at[r, c])}
                        for c in hit_cols
                    ],
                }
                for r in hit_rows
            ],
        }
        order_changed = len(removed_rows) == 0 and not after.index.equals(before.index)
        return {
            "message": msg,
            "rows": [len(before), len(after)],
            "cols": [before.shape[1], after.shape[1]],
            "removedRows": int(len(removed_rows)),
            "removedColumns": removed_cols,
            "addedColumns": added_cols,
            "changedCells": int(sum(by_col.values())),
            "changedByColumn": by_col,
            "dtypeChanges": dtype_changes,
            "changes": changes,
            "removedSample": table(before.loc[removed_rows[:sample]]) if len(removed_rows) else None,
            "orderSample": table(after.head(sample)) if order_changed else None,
            "addedSample": table(after[[c for c in after.columns if str(c) in added_cols]].head(sample)) if added_cols else None,
            "code": cleaner.code,
        }

    def cmd_revert(self, keep):
        """Go back to the state after `keep` steps (0 = original data)."""
        self.require_df()
        keep = int(keep)
        if keep < 0 or keep >= len(self.history):
            raise ValueError("Nothing to revert.")
        undone = len(self.history) - keep
        self.df = self.history[keep]
        del self.history[keep:]
        del self.log[keep:]
        msg = "Back to the original data." if keep == 0 else f"Reverted {undone} step(s). Now at step {keep}."
        return {"message": msg, "state": self.snapshot()}

    def cmd_script(self):
        """The cleaning session as a runnable pandas script."""
        self.require_df()
        name = os.path.basename(self.path) if self.path else "data.csv"
        stem = os.path.splitext(name)[0]
        lines = [
            f"# Cleaning steps exported from Data Boss for {name}",
            "import numpy as np",
            "import pandas as pd",
            "",
            *self.read_code.splitlines(),
            "",
        ]
        for entry in self.log:
            lines += [f"# Step {entry['step']}: {entry['msg']}", entry.get("code") or "# (no code recorded)", ""]
        lines += ["df = df.reset_index(drop=True)", f"df.to_csv({stem + '_cleaned.csv'!r}, index=False)", ""]
        return {"code": "\n".join(lines), "fileName": f"{stem}_cleaning.py"}

    def cmd_undo(self):
        self.require_df()
        if not self.history:
            raise ValueError("Nothing to undo.")
        self.df = self.history.pop()
        undone_msg = ""
        if self.log:
            undone_msg = f" (undone: {self.log.pop()['msg']})"
        return {"message": f"Last step undone.{undone_msg}", "state": self.snapshot()}

    def cmd_export(self, path):
        fmt = write_table(self.require_df(), path)
        return {"path": path, "format": fmt}

    def _data_code(self):
        """Code that rebuilds the current data: read the file, then replay the cleaning steps."""
        lines = self.read_code.splitlines()
        if self.log:
            lines.append("")
            for entry in self.log:
                lines += [f"# Step {entry['step']}: {entry['msg']}", *(entry.get("code") or "# (no code recorded)").splitlines()]
            lines.append("df = df.reset_index(drop=True)")
        return lines

    def _render_chart(self, df, kind, params, style, width, fmt, prelude=()):
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        rc, cmap = chart_theme(style)
        with mpl.rc_context(rc) if rc else nullcontext():
            out = DataVisualizer(df, heatmap_cmap=cmap, width=width).render_chart(kind, params, fmt=fmt)

        code = "\n".join([
            "import matplotlib.pyplot as plt",
            "import numpy as np",
            "import pandas as pd",
            "import seaborn as sns",
            "",
            *self._data_code(),
            *prelude,
            "",
            *out["code"],
            *([f"plt.title({params['title']!r})"] if params.get("title") else []),
            "plt.tight_layout()",
            "plt.show()",
            "",
        ])
        result = {"insights": out["insights"], "notes": out["notes"], "code": code}
        if fmt == "svg":
            result["svg"] = out["data"]
        else:
            result["image"] = "data:image/png;base64," + base64.b64encode(out["data"]).decode("ascii")
        return result

    def cmd_plot(self, kind, params=None, style=None, width=None, fmt="png"):
        return self._render_chart(self.require_df(), kind, params, style, width, fmt)

    # ---- pivot -------------------------------------------------------------

    def cmd_pivot(self, params):
        res = pivot(self.require_df(), **params)
        name = os.path.basename(self.path) if self.path else "data.csv"
        code = "\n".join(["import numpy as np", "import pandas as pd", "", *self._data_code(), "", res["code"], "print(table)", ""])
        return {**res, "table": table(res["table"]), "code": code, "source": name}

    def cmd_pivot_apply(self, params):
        return self.cmd_clean("PIVOT", {k: v for k, v in params.items() if k != "totals"})

    def cmd_pivot_chart(self, params, value, kind="BAR", style=None, width=None, fmt="png"):
        rows = params.get("rows") or []
        if len(rows) != 1:
            raise ValueError("Charts work with exactly one row grouping.")
        res = pivot(self.require_df(), **params)
        tbl = res["table"].iloc[:-1] if res["hasTotals"] else res["table"]  # drop the Total row
        if value not in tbl.columns:
            raise ValueError(f"Unknown value column: {value}.")
        x = rows[0]
        chart_params = {"x": x, "y": value, "agg": "sum", "top_n": "25", "sort": "label" if params.get("sort") == "label" else "desc"}
        prelude = ["", "# Pivot table", *res["code"].splitlines(), "df = table"]
        return self._render_chart(tbl, kind, chart_params, style, width, fmt, prelude=prelude)

    # ---- trends ------------------------------------------------------------

    def cmd_trends(self, params):
        res = trends(self.require_df(), **params)
        res["code"] = "\n".join(["import numpy as np", "import pandas as pd", "", *self._data_code(), "", res["code"], ""])
        return {**res, "table": table(res["table"])}

    # ---- segment comparison --------------------------------------------------

    def cmd_segment(self, conditions):
        res = compare_segment(self.require_df(), conditions)
        res["code"] = "\n".join(["import numpy as np", "import pandas as pd", "from scipy import stats", "",
                                 *self._data_code(), "", res["code"], ""])
        return jsonable(res)

    # ---- statistical tests -------------------------------------------------

    def cmd_stats_test(self, outcome, by, groups=None):
        res = compare(self.require_df(), outcome, by, groups=groups or None)
        body = res.pop("code_body")
        res["code"] = "\n".join(["import numpy as np", "import pandas as pd", "from scipy import stats", "",
                                 *self._data_code(), "", f"# {res['test']}", body, ""])
        return jsonable(res)

    def cmd_stats_groups(self, column, limit=200):
        """Distinct values of a column, most common first, for choosing groups to compare."""
        s = self.require_df()[column].dropna().astype(str)
        vc = s.value_counts()
        return {"values": [{"value": k, "count": int(v)} for k, v in vc.head(limit).items()], "total": int(len(vc))}

    # ---- SQL ---------------------------------------------------------------

    def cmd_query_info(self):
        """Schema and starter queries for the Query screen."""
        df = self.require_df()
        return {
            "table": "data",
            "columns": [
                {"name": str(c), "sql": quote_ident(c), "dtype": str(df[c].dtype), "kind": column_kind(df[c])}
                for c in df.columns
            ],
            "examples": example_queries(df),
        }

    def cmd_query(self, sql, limit=500):
        df = self.require_df()
        preview, total, ms = run_query(df, sql, limit=max(1, min(int(limit), 2000)))
        return {
            "table": table(preview),
            "total": total,
            "ms": ms,
            "columns": [
                {"name": str(c), "dtype": str(preview[c].dtype), "kind": column_kind(preview[c])} for c in preview.columns
            ],
        }

    def cmd_query_apply(self, sql):
        """Replace the working data with the query result, as an undoable cleaning step."""
        return self.cmd_clean("SQL_QUERY", {"sql": sql})

    def cmd_query_chart(self, sql, kind, params=None, style=None, width=None, fmt="png"):
        result = run_query_full(self.require_df(), sql)
        if result.empty:
            raise ValueError("The query returned no rows to chart.")
        prelude = ["", "# Query result", *sql_code(sql).splitlines()]
        return self._render_chart(result, kind, params, style, width, fmt, prelude=prelude)


# Commands that can take a while run on a background worker so the app stays
# responsive and they can be cancelled. Everything else is answered inline.
HEAVY_COMMANDS = {"plot", "preview", "inspect", "query", "query_chart", "pivot", "pivot_chart", "stats_test", "trends", "segment"}


class Dispatcher:
    """Routes requests to the session; heavy ones run on a single worker thread.

    Guarantees exactly one response per request id: a cancelled request is
    answered immediately with {"cancelled": true}, and its result (if the work
    was already running) is dropped when it finishes. The worker is a single
    thread on purpose: matplotlib's global state is not thread-safe.
    """

    def __init__(self, session, send, heavy=HEAVY_COMMANDS):
        self.session = session
        self.send = send
        self.heavy = set(heavy)
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.pending = set()    # ids queued or running on the worker
        self.cancelled = set()  # ids already answered as cancelled
        self.worker = threading.Thread(target=self._work, name="heavy-worker", daemon=True)
        self.worker.start()

    @staticmethod
    def _run(handler, args, req_id):
        try:
            return {"id": req_id, "ok": True, "result": handler(**args)}
        except Exception as e:  # noqa: BLE001 - every failure goes back to the UI
            traceback.print_exc(file=sys.stderr)
            return {"id": req_id, "ok": False, "error": str(e)}

    def handle(self, line):
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            cmd = req.get("cmd")
            args = req.get("args") or {}
            if cmd == "cancel":
                self.send({"id": req_id, "ok": True, "result": {"cancelled": self.cancel(args.get("id"))}})
                return
            handler = getattr(self.session, f"cmd_{cmd}", None)
            if handler is None:
                raise ValueError(f"Unknown command: {cmd}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            self.send({"id": req_id, "ok": False, "error": str(e)})
            return
        if cmd in self.heavy:
            with self.lock:
                self.pending.add(req_id)
            self.jobs.put((req_id, handler, args))
        else:
            self.send(self._run(handler, args, req_id))

    def cancel(self, req_id):
        """Cancel a queued or running heavy request. Returns False if it already finished."""
        with self.lock:
            if req_id not in self.pending or req_id in self.cancelled:
                return False
            self.cancelled.add(req_id)
        self.send({"id": req_id, "ok": False, "error": "Cancelled", "cancelled": True})
        return True

    def _work(self):
        while True:
            req_id, handler, args = self.jobs.get()
            response = None
            with self.lock:
                skip = req_id in self.cancelled
            if not skip:
                response = self._run(handler, args, req_id)
            with self.lock:
                self.pending.discard(req_id)
                was_cancelled = req_id in self.cancelled
                self.cancelled.discard(req_id)
            if response is not None and not was_cancelled:
                self.send(response)
            self.jobs.task_done()


def main():
    send_lock = threading.Lock()

    def send(obj):
        try:
            line = json.dumps(obj, default=str, allow_nan=False) + "\n"
        except (TypeError, ValueError) as e:  # never let a bad result kill a thread
            traceback.print_exc(file=sys.stderr)
            line = json.dumps({"id": obj.get("id"), "ok": False, "error": f"Could not encode the result: {e}"}) + "\n"
        with send_lock:
            _protocol_out.write(line)
            _protocol_out.flush()

    dispatcher = Dispatcher(Session(), send)
    send({"id": 0, "ok": True, "result": {"ready": True}})

    for line in sys.stdin:
        line = line.strip()
        if line:
            dispatcher.handle(line)
    dispatcher.jobs.join()  # finish queued work before exiting (e.g. piped input)


if __name__ == "__main__":
    main()
