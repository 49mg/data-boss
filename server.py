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
import re
import sys
import traceback
from contextlib import nullcontext

import matplotlib as mpl
import numpy as np
import pandas as pd
from cycler import cycler
from matplotlib.colors import LinearSegmentedColormap

from src import DataCleaner, DataInspector, DataVisualizer
from src.inspectors import _label

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

    def cmd_load(self, path):
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(
                f"File is too large ({size / 1024 / 1024:.1f} MB). "
                f"Maximum allowed size is {MAX_FILE_SIZE_MB} MB."
            )
        try:
            df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001 - surface any parse error to the UI
            raise ValueError(f"Could not read the CSV file: {e}") from e

        self.path = path
        self.df = df
        self.history = []
        self.log = []
        return self.snapshot()

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
        msg = cleaner.apply_clean(method, **params)  # raises -> state unchanged
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
        msg = cleaner.apply_clean(method, **(params or {}))
        after = cleaner.df

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
            f"df = pd.read_csv({name!r})",
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
        df = self.require_df()
        with open(path, "wb") as f:
            f.write(DataCleaner(df).export_data())
        return {"path": path}

    def cmd_plot(self, kind, params=None, style=None, width=None, fmt="png"):
        df = self.require_df()
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        rc, cmap = chart_theme(style)
        with mpl.rc_context(rc) if rc else nullcontext():
            out = DataVisualizer(df, heatmap_cmap=cmap, width=width).render_chart(kind, params, fmt=fmt)

        name = os.path.basename(self.path) if self.path else "data.csv"
        code = "\n".join([
            "import matplotlib.pyplot as plt",
            "import numpy as np",
            "import pandas as pd",
            "import seaborn as sns",
            "",
            f"df = pd.read_csv({name!r})",
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


def main():
    session = Session()

    def send(obj):
        _protocol_out.write(json.dumps(obj, default=str, allow_nan=False) + "\n")
        _protocol_out.flush()

    send({"id": 0, "ok": True, "result": {"ready": True}})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            handler = getattr(session, f"cmd_{req.get('cmd')}", None)
            if handler is None:
                raise ValueError(f"Unknown command: {req.get('cmd')}")
            send({"id": req_id, "ok": True, "result": handler(**(req.get("args") or {}))})
        except Exception as e:  # noqa: BLE001 - every failure goes back to the UI
            traceback.print_exc(file=sys.stderr)
            send({"id": req_id, "ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
