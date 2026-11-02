"""Read and write data files: CSV/TSV, Excel, Parquet, JSON and JSON Lines.

Every read returns the DataFrame plus the Python code that reproduces it, so
exported scripts open the file exactly like the app did.
"""

import csv
import json
import os

import duckdb
import pandas as pd

FORMATS = {
    ".csv": "csv", ".tsv": "csv", ".tab": "csv", ".txt": "csv",
    ".xlsx": "excel", ".xlsm": "excel",
    ".parquet": "parquet", ".pq": "parquet",
    ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
}
READABLE = sorted(FORMATS)
WRITABLE = {".csv": "csv", ".xlsx": "excel", ".parquet": "parquet"}

SEPARATORS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
# Tried in order when the encoding is not given. Windows-1256 covers Arabic
# files saved by Excel on Windows; Latin-1 accepts any byte as a last resort.
ENCODINGS = ["utf-8-sig", "cp1256", "latin-1"]
ENCODING_NAMES = {"utf-8-sig": "UTF-8", "utf-8": "UTF-8", "cp1256": "Arabic (Windows-1256)", "latin-1": "Western (Latin-1)"}
EXCEL_MAX_ROWS = 1_048_575  # plus the header row


class FileFormatError(ValueError):
    """A user-facing problem reading or writing a file."""


def detect_format(path):
    ext = os.path.splitext(str(path))[1].lower()
    if ext == ".xls":
        raise FileFormatError("Old Excel .xls files are not supported. Save the file as .xlsx in Excel and open that.")
    fmt = FORMATS.get(ext)
    if not fmt:
        raise FileFormatError(f"Unsupported file type “{ext or 'no extension'}”. Open CSV, Excel (.xlsx), Parquet or JSON.")
    return fmt


def excel_sheets(path):
    from openpyxl import load_workbook

    try:
        wb = load_workbook(path, read_only=True)
    except Exception as e:  # noqa: BLE001 - corrupt or password-protected workbooks
        raise FileFormatError(f"Could not open the Excel file: {e}") from e
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _args(**kwargs):
    """Render keyword arguments for generated code, skipping defaults (None)."""
    return "".join(f", {k}={v!r}" for k, v in kwargs.items() if v is not None)


def _sniff(path, encoding):
    with open(path, encoding=encoding, newline="") as f:
        sample = f.read(64 * 1024)
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(SEPARATORS)).delimiter
    except csv.Error:
        return ","


def _detect_encoding(path):
    with open(path, "rb") as f:
        raw = f.read(1024 * 1024)
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def read_csv(path, sep=None, encoding=None, header=True):
    name = os.path.basename(path)
    notes = []
    enc = encoding or _detect_encoding(path)
    if enc not in ("utf-8-sig", "utf-8") and not encoding:
        notes.append(f"Read with {ENCODING_NAMES.get(enc, enc)} text encoding.")
    ext = os.path.splitext(path)[1].lower()
    if sep is None:
        sep = "\t" if ext in (".tsv", ".tab") else _sniff(path, enc)
        if sep != "," and ext not in (".tsv", ".tab"):
            notes.append(f"Detected {SEPARATORS.get(sep, repr(sep))} as the column separator.")
    try:
        df = pd.read_csv(path, sep=sep, encoding=enc, header=0 if header else None)
    except Exception as e:  # noqa: BLE001 - surface any parse error
        raise FileFormatError(f"Could not read the CSV file: {e}") from e
    if not header:
        df.columns = [f"column_{i + 1}" for i in range(df.shape[1])]
    if df.shape[1] == 1 and any(s in str(df.columns[0]) for s in ";\t|"):
        notes.append("Everything landed in one column. Try a different separator in Import settings.")
    args = _args(sep=None if sep == "," else sep, encoding=None if enc in ("utf-8-sig", "utf-8") else enc)
    if header:
        code = f"df = pd.read_csv({name!r}{args})"
    else:
        code = (f"df = pd.read_csv({name!r}{args}, header=None)\n"
                "df.columns = [f'column_{i + 1}' for i in range(df.shape[1])]")
    options = {"sep": sep, "encoding": enc, "header": bool(header)}
    return df, code, notes, options


def read_excel(path, sheet=None):
    name = os.path.basename(path)
    try:
        df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, engine="openpyxl")
    except Exception as e:  # noqa: BLE001
        raise FileFormatError(f"Could not read the Excel file: {e}") from e
    df.columns = [str(c) for c in df.columns]
    return df, f"df = pd.read_excel({name!r}{_args(sheet_name=sheet)})", [], {"sheet": sheet}


def read_parquet(path):
    name = os.path.basename(path)
    con = duckdb.connect()
    try:
        df = con.read_parquet(str(path)).df()
    except duckdb.Error as e:
        raise FileFormatError(f"Could not read the Parquet file: {str(e).splitlines()[0]}") from e
    finally:
        con.close()
    return df, f"import duckdb\ndf = duckdb.read_parquet({name!r}).df()", [], {}


def read_json(path, lines=False):
    name = os.path.basename(path)
    notes = []
    try:
        if lines:
            records = []
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            df = pd.json_normalize(records)
            code = (f"import json\nwith open({name!r}, encoding='utf-8-sig') as f:\n"
                    "    df = pd.json_normalize([json.loads(line) for line in f if line.strip()])")
        else:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # {"col": [values...]} tables, or a wrapper like {"items": [...]}
                lists = {k: v for k, v in data.items() if isinstance(v, list)}
                if len(lists) == 1 and all(isinstance(x, dict) for x in next(iter(lists.values()))):
                    key = next(iter(lists))
                    data = lists[key]
                    notes.append(f"Read the records under “{key}”.")
                    code = (f"import json\nwith open({name!r}, encoding='utf-8-sig') as f:\n"
                            f"    df = pd.json_normalize(json.load(f)[{key!r}])")
                elif lists and len({len(v) for v in lists.values()}) == 1 and len(lists) == len(data):
                    df = pd.DataFrame(data)
                    code = (f"import json\nwith open({name!r}, encoding='utf-8-sig') as f:\n"
                            "    df = pd.DataFrame(json.load(f))")
                    return df, code, notes, {}
                else:
                    data = [data]
                    code = (f"import json\nwith open({name!r}, encoding='utf-8-sig') as f:\n"
                            "    df = pd.json_normalize([json.load(f)])")
            else:
                code = (f"import json\nwith open({name!r}, encoding='utf-8-sig') as f:\n"
                        "    df = pd.json_normalize(json.load(f))")
            if not isinstance(data, list):
                raise FileFormatError("The JSON file does not contain a table (a list of records).")
            df = pd.json_normalize(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        hint = " If it has one record per line, rename it to .jsonl." if not lines else ""
        raise FileFormatError(f"Could not read the JSON file: {e}.{hint}") from e
    if any("." in str(c) for c in df.columns):
        notes.append("Nested fields were flattened into columns like “parent.child”.")
    return df, code, notes, {}


def read_table(path, sheet=None, options=None):
    """Read any supported file. Returns (df, read_code, notes, info)."""
    options = options or {}
    fmt = detect_format(path)
    if fmt == "csv":
        df, code, notes, opts = read_csv(path, options.get("sep"), options.get("encoding"), options.get("header", True))
    elif fmt == "excel":
        df, code, notes, opts = read_excel(path, sheet)
    elif fmt == "parquet":
        df, code, notes, opts = read_parquet(path)
    else:
        df, code, notes, opts = read_json(path, lines=fmt == "jsonl")
    if df.shape[1] == 0:
        raise FileFormatError("The file has no columns.")
    return df, code, notes, {"format": fmt, **opts}


def write_table(df, path):
    """Write the data in the format given by the file extension."""
    ext = os.path.splitext(str(path))[1].lower()
    fmt = WRITABLE.get(ext)
    if fmt is None:
        raise FileFormatError(f"Can't export as “{ext or 'no extension'}”. Use .csv, .xlsx or .parquet.")
    if fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "excel":
        if len(df) > EXCEL_MAX_ROWS:
            raise FileFormatError(f"Excel holds at most {EXCEL_MAX_ROWS:,} rows; this data has {len(df):,}. Export as CSV or Parquet.")
        out = df.copy()
        for c in out.columns:  # Excel can't store time-zone-aware datetimes
            if isinstance(out[c].dtype, pd.DatetimeTZDtype):
                out[c] = out[c].dt.tz_localize(None)
        out.to_excel(path, index=False, engine="openpyxl")
    else:
        con = duckdb.connect()
        try:
            con.register("data", df)
            target = str(path).replace("'", "''")
            con.execute(f"COPY data TO '{target}' (FORMAT parquet)")
        except duckdb.Error as e:
            raise FileFormatError(f"Could not write Parquet: {str(e).splitlines()[0]}") from e
        finally:
            con.close()
    return fmt
