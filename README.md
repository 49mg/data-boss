# Data Boss

[![CI](https://github.com/49mg/data-boss/actions/workflows/ci.yml/badge.svg?branch=desktop-application)](https://github.com/49mg/data-boss/actions/workflows/ci.yml)

**Data Boss** is a free desktop app for analysing data without writing code, and without hiding the code either. Open a CSV, Excel, Parquet or JSON file, find the problems, clean them with full undo, ask questions with SQL, pivot tables and statistical tests, train simple models, chart everything interactively and share the result as a report, a notebook or a Python script that reproduces it exactly.

![Data Boss in action](docs/demo.gif)

**Highlights**

- **Clean with confidence:** about 30 operations, each with a live preview of exactly what changes, full undo, and exported pandas code that reproduces the same file byte for byte.
- **Analysis that explains itself:** pivot tables, trends, segment comparison and statistical tests that pick the right test and say what the result means in plain words, never "proof".
- **Honest models:** regression, classification, clustering and forecasting with a baseline, held-out test rows, backtests and warnings for leakage and overfitting.
- **Share it:** interactive charts, a dashboard that redraws after every change, HTML/PDF reports, Jupyter notebooks.
- **English and Arabic:** a full right-to-left Arabic interface, and Arabic data (including Windows-1256 files) handled correctly.
- **Private:** your data never leaves your computer (see [Privacy](#privacy)).

| | |
|---|---|
| ![Inspect](docs/screenshots/inspect.png) | ![Clean](docs/screenshots/clean.png) |
| ![Statistical tests](docs/screenshots/tests.png) | ![Model](docs/screenshots/model.png) |
| ![Dashboard](docs/screenshots/dashboard.png) | ![Arabic interface](docs/screenshots/arabic.png) |

**Case studies** made with Data Boss: [what makes a top-rated gym in Baghdad](case-studies/01-baghdad-gyms), [two years of Washington bike sharing](case-studies/02-bike-sharing) and [an honest model of a bank's phone campaign](case-studies/03-bank-marketing).

Under the hood: an Electron window talks to a bundled Python engine (pandas, DuckDB, scipy, scikit-learn, statsmodels, Matplotlib). See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

## Install

Download the file for your computer from the [latest release](https://github.com/49mg/data-boss/releases/latest). Nothing else is needed — Python and all libraries are bundled inside the app.

| Your computer | Download | How to install |
|---|---|---|
| **Windows 10/11** | `Data-Boss-x.y.z-win-x64.exe` | Run it and follow the installer. Launch from the Start menu or desktop shortcut. |
| **Mac with Apple silicon** (M1–M4) | `Data-Boss-x.y.z-mac-arm64.dmg` | Open it and drag **Data Boss** into **Applications**. |
| **Mac with Intel chip** | `Data-Boss-x.y.z-mac-x64.dmg` | Same as above. |
| **Ubuntu / Debian** | `Data-Boss-x.y.z-linux-amd64.deb` | `sudo apt install ./Data-Boss-x.y.z-linux-amd64.deb`, then find it in your app menu. |
| **Any other Linux** | `Data-Boss-x.y.z-linux-x86_64.AppImage` | `chmod +x Data-Boss-*.AppImage`, then double-click or run it. |

Not sure which Mac you have? Apple menu → **About This Mac** → look for "Chip: Apple M…" (Apple silicon) or "Processor: Intel".

### First launch: security warnings

The app is not code-signed yet, so the operating system asks you to confirm the first time:

- **Windows** — "Windows protected your PC": click **More info → Run anyway**.
- **macOS** — "Data Boss can't be opened" or "Apple could not verify…": click **Done**, then open **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Data Boss. Only needed once.
- **Linux AppImage** — if it doesn't start, install FUSE 2: `sudo apt install libfuse2` (on Ubuntu 24.04 and newer: `sudo apt install libfuse2t64`).

### Updates

Windows and Linux (AppImage) installs check GitHub for a newer version when the app starts, download it in the background and show **Restart to update** in the sidebar. On macOS and with the `.deb` package, download new versions from the releases page. To turn automatic updates off, add `"autoUpdate": false` to `settings.json` in the app's data folder (Windows: `%APPDATA%\Data Boss`, Linux: `~/.config/Data Boss`).

## Privacy

Everything happens on your computer. Your files are read locally, the Python engine runs locally, and nothing you load, clean, chart or export is sent anywhere. There is no account, no analytics and no telemetry. The only network request the app makes is the update check above, which asks GitHub whether a newer release exists (it can be turned off). SQL queries cannot read or write files outside the loaded data.

## Features

### Column profile

A per-column summary table always visible after upload:


| Field              | Description                                                             |
| ------------------ | ----------------------------------------------------------------------- |
| Type               | pandas dtype of the column                                              |
| Non-null           | count of non-null values                                                |
| Missing            | count and percentage of missing values                                  |
| Unique             | number of distinct values                                               |
| Top values / Range | for strings: top 3 values with counts · for numbers: min / median / max |


A **column detail picker** below the table lets you select any column and view its full value counts (top 20).

### Data inspection

- **Overview** — data-quality checks ranked by severity, each with a one-click fix in Clean
- **Structure / Statistics** — column types, memory, distributions and summary statistics
- **Missing values / Duplicates / Outliers** — where the gaps, copies and extreme values are
- **Correlations** — strongest relationships between numeric columns
- **Target** — pick the column you want to explain (sales, rating, churned…); every other column is ranked by how strongly it relates to it (|Pearson r|, correlation ratio η or Cramér's V), with a p-value, a small chart and a plain-language sentence

### Analysis

- **Pivot table** — group by rows and columns with count, sum, mean, median and more; totals are true overall values
- **Trends** — a value per day, week, month, quarter or year with change against the previous period or the same period last year, a moving average and a running total; insight sentences name the biggest rise and drop, and incomplete first/last periods are flagged instead of faking a jump
- **Compare segment** — describe a group of rows (e.g. churned = yes, or plan = pro and fee > 40) and every other column is compared with the rest of the data: averages or category shares side by side, the fitting test per column, p-values adjusted for testing many columns (Holm), clear differences ranked first
- **Tests** — pick a measure and what to compare it by; the fitting test is chosen from the column types, group count, shape and spread (t-test / Welch, Mann-Whitney, ANOVA / Kruskal-Wallis with pairwise comparisons, chi-square / Fisher, Pearson / Spearman). Each result shows why that test was used, the p-value, effect size, confidence interval, a one-sentence interpretation and caveats, plus the scipy code that reproduces it

### Model

Pick a column to predict and the columns to learn from; the task (regression or classification) is detected automatically. Data Boss trains a baseline, a linear/logistic model and a random forest on 80% of the rows and scores them on the other 20%. Imputing, scaling and one-hot encoding happen inside a scikit-learn pipeline fitted on the training rows only, so nothing leaks from the test rows. Results include R², MAE and RMSE or accuracy, F1 and ROC-AUC, a predicted-vs-actual chart or confusion matrix, permutation feature importance, and warnings for tiny data, class imbalance, suspiciously perfect scores (leakage) and overfitting. When no model beats guessing it says so. **Code** exports the full scikit-learn script.

The **Clusters** tab groups similar rows with k-means: it tries 2–8 clusters, picks the count with the best silhouette score (or uses yours), describes each cluster in plain words (e.g. “Cluster 3: mostly plan = pro, very high fee, high visits”), shows the rows on a 2-D map, and **Add as column** stores each row's cluster as an undoable cleaning step. Results are reproducible (fixed seed, Cluster 1 is always the largest).

The **Forecast** tab projects a value per day, week, month, quarter or year with exponential smoothing (Holt-Winters, statsmodels): with or without a damped trend and seasonality, chosen by AICc. It shows 80% and 95% ranges, the seasonal high and low points, and a **backtest** that hides the last periods, forecasts them, and compares the error with a simple “same as last season” benchmark, so you can see how far to trust it. An incomplete last period is left out instead of looking like a collapse.

### Interactive charts

Charts in Visualize are interactive (Apache ECharts, bundled locally, no internet needed): hover for exact values, scroll or drag to zoom, and click a bar, box or histogram range to **keep only those rows** or **compare them with the rest**. Clicking a correlation cell opens the scatter plot of that pair. The **Image** view shows the exact Matplotlib image that PNG, SVG, copy, reports and the exported code use.

### Dashboard

**Pin** any chart (Visualize) or pivot table (Analyze) to the Dashboard. Tiles are redrawn from the current data after every cleaning step, undo or applied query, so the dashboard always shows the data as it is now; a tile that no longer fits (e.g. its column was dropped) says why. Reorder or unpin tiles, open one to edit it, and **Add to report** to include the dashboard, rendered fresh at export time.

### Report

Every chart, pivot table, trend, segment comparison and test result has a **Report** button. The Report screen collects them with your own headings and notes; reorder or remove items, then **Export HTML** (one self-contained file with images inlined, opens offline in any browser) or **Export PDF**. Charts in the report are always drawn in light colours so they print well, and the report is kept between sessions.

### Jupyter notebook export

**Notebook** (in the Clean history panel and on Visualize) saves the session as a `.ipynb`: loading the file, every cleaning step with the message the app showed, and your recent charts with their insights. Run it next to the data file and it produces exactly the same cleaned data. CI executes an exported notebook with `jupyter nbconvert --execute` on every push.

### Arabic interface

Click **العربية** at the bottom of the sidebar to switch the whole interface to Arabic, with a right-to-left layout and a bundled Arabic font (Noto Sans Arabic); click **English** to switch back. Analysis sentences from the Python engine are translated too, numbers and charts stay left to right, and reports exported in Arabic are right to left with the font embedded. Your data (column names and values) is never translated. Translations live in `renderer/i18n/ar.json`: the key is the English text and `{0}`, `{1}` mark values filled in at runtime, so adding a language is a matter of adding a file.

### Data cleaning


| Operation               | Description                                                    |
| ----------------------- | -------------------------------------------------------------- |
| Remove duplicate rows   | Drops exact duplicates and resets the index                    |
| Drop rows with NaN      | Removes any row containing at least one missing value          |
| Drop columns with NaN   | Removes any columns containing at least one missing value      |
| Strip whitespace        | Trims leading/trailing spaces from all string columns          |
| Fill NaN with mean      | Fills missing numeric values with the column mean              |
| Fill NaN with median    | Fills missing numeric values with the column median            |
| Clip outliers — IQR     | Clips values beyond 1.5×IQR per numeric column |
| Clip outliers — Z-score | Clips values beyond ±3σ per numeric column                     |
| Rename column           | Renames a selected column                                      |
| Change column type      | Converts a column to int64, float64, str, or bool              |
| Drop columns            | Removes one or more selected columns                           |
| Replace values          | Find-and-replace within a selected column                      |
| One-hot encode          | 0/1 indicator columns per category (optionally drop the first)  |
| Scale numbers           | Standard (z-score, like StandardScaler) or min-max scaling      |
| Bin into ranges         | Equal-width, equal-count (quantile) or custom-edge ranges       |
| Log transform           | log(1 + x), natural log or log10 for long-tailed numbers        |
| Group rare categories   | Merge infrequent values into "Other" (top N or minimum share)   |


Every operation supports **Do / Undo** — the full history is preserved so you can step back to the original data at any point. The **Export CSV** button always exports the current working state.

**Session History** — a collapsible panel lists every operation applied in order, with the result message and row/column delta (e.g. `rows -3`, `cols -1`). Undo removes the last entry automatically.

**Before / After Preview** — a collapsible panel shows the first 10 rows and shape of the dataframe immediately before and after the last operation, side by side.

### Visualizations


| Chart               | Description                                                              |
| ------------------- | ------------------------------------------------------------------------ |
| Histogram           | Distribution of a numeric column with KDE overlay                        |
| Box plot            | Numeric values grouped by a categorical column                           |
| Scatter plot        | Two numeric columns with optional categorical hue                        |
| Correlation heatmap | Annotated heatmap of numeric column correlations                         |
| Line chart          | Any column on X, numeric column on Y                                     |
| Bar chart           | Categorical X axis, numeric Y axis                                       |
| Pair plot           | Pairwise relationships across selected numeric columns with optional hue |


Missing values in selected columns are flagged before plotting. Rows with nulls are dropped for the chart only and do not affect the working dataframe.

### Robustness

- **200 MB file size limit** enforced before processing
- **CSV validation** — malformed files show a clear error instead of crashing
- **Error handling** on all cleaning operations — failed operations show an error and leave the dataframe unchanged

### Desktop extras

- **Drag & drop** a CSV anywhere in the window to open it
- **Native dialogs** for opening and exporting files
- **Save PNG** for any generated chart
- **Shortcuts** — `Ctrl/Cmd+O` open, `Ctrl/Cmd+S` export, `Ctrl/Cmd+Z` undo
- Follows the system **light/dark** theme

## Project structure

```
data-boss/
├── package.json            # Electron app manifest, scripts and installer config
├── .github/workflows/
│   └── release.yml         # Builds installers for Windows, macOS and Linux
├── assets/icon.png         # App icon (converted to .ico/.icns at build time)
├── electron/
│   ├── main.js             # Main process: window, dialogs, spawns the Python backend
│   └── preload.js          # Safe bridge exposing `window.api` to the UI
├── renderer/
│   ├── index.html          # UI markup and icon sprite
│   ├── styles.css          # UI styles (light + dark)
│   ├── app.js              # UI logic
│   ├── theme.js            # Applies the saved/system theme before first paint
│   ├── vendor/echarts/     # Apache ECharts 5.5.1 (Apache-2.0, see its LICENSE and NOTICE)
│   ├── i18n.js             # Interface language: translation lookup and right-to-left switch
│   ├── i18n/               # en.json (string catalogue) and ar.json (Arabic)
│   ├── report.css          # Styles for the report preview and exported HTML/PDF
│   ├── citymap.js          # Decorative city-map background
│   └── fonts/              # Bundled Geist font (SIL Open Font License)
├── server.py               # Python backend: JSON-lines over stdin/stdout, holds dataframe state
├── src/
│   ├── base.py             # Abstract base classes (BaseDataInspector, BaseDataCleaner, BaseDataVisualizer)
│   ├── inspectors.py       # DataInspector — read-only data summaries
│   ├── target.py           # Target analysis: rank columns by relationship to one column
│   ├── clusters.py         # k-means clustering with plain-language cluster profiles
│   ├── forecast.py         # Exponential smoothing forecasts with a backtest
│   ├── model.py            # Model builder: baseline, linear and random forest with honest evaluation
│   ├── notebook.py         # Writes Jupyter notebooks (.ipynb) without extra dependencies
│   ├── segments.py         # Segment vs rest comparison on every column
│   ├── trends.py           # Period-over-period trends with insight sentences
│   ├── stats.py            # Statistical tests chosen automatically, explained in plain language
│   ├── cleaners.py         # DataCleaner — dataframe mutations and CSV export
│   └── visualizers.py      # DataVisualizer — Matplotlib/Seaborn charts
└── pyproject.toml
```

## Development setup

Requirements: Node.js 18+ and npm, Python 3.10+, and [uv](https://github.com/astral-sh/uv).

Clone the repository, then install the Python and Node dependencies:

```bash
git clone https://github.com/49mg/data-boss.git
cd data-boss

# Python backend (creates .venv)
uv sync
# or: python -m venv .venv && source .venv/bin/activate && pip install -e .

# Electron frontend
npm install
```

## Usage

Start the desktop app from source:

```bash
npm start
```

The app looks for the Python interpreter in `.venv/` first and falls back to `python3` (`python` on Windows). Set `DATA_BOSS_PYTHON=/path/to/python` to use a specific interpreter.

1. Click **Open file** (or drop a file on the window): CSV, TSV, Excel (.xlsx), Parquet, JSON or JSON Lines, max 200 MB. Separator and text encoding (including Arabic Windows-1256) are detected automatically; adjust them under **Import settings** on the Data screen.
2. **Data** shows summary cards (rows, columns, missing cells, duplicates) and the rows themselves.
3. **Column profile** shows each column's type, missing share, unique count and top values.
4. **Inspect** has tabs for an overview of quality issues, structure, statistics, missing values, duplicates, outliers, correlations and target analysis.
5. **Clean**: pick an operation, fill in any inputs, then click **Apply** — or **Undo** to revert. The history timeline and before/after tables show what each step changed.
6. **Visualize**: pick a chart tile, choose columns, then **Render chart**. **Save PNG** saves it.
7. Click **Export** to save the current (cleaned) data as CSV.

## How it works

The Electron main process spawns `server.py` once at startup and talks to it with newline-delimited JSON over stdin/stdout:

```
→ {"id": 3, "cmd": "clean", "args": {"method": "DROP_NA_ROWS"}}
← {"id": 3, "ok": true, "result": {"message": "...", "state": {...}}}
```

The backend owns all dataframe state (working copy, undo stack, operation log). Charts are rendered with Matplotlib/Seaborn and returned as PNG data URLs. No web server or open port is involved.

## Building installers

Installers are built in two stages:

1. **PyInstaller** bundles `server.py` with Python, pandas, matplotlib and seaborn into a standalone `data-boss-backend` program (`build/pyinstaller/`).
2. **electron-builder** packages the Electron app with that program in `resources/backend/` and produces the installer in `dist/`.

When the app is installed (`app.isPackaged`), `electron/main.js` starts the bundled program instead of `.venv` Python.

Build for the computer you are on:

```bash
npm run dist        # current OS
npm run dist:linux  # AppImage + .deb
npm run dist:mac    # .dmg (on a Mac)
npm run dist:win    # .exe (on Windows)
```

PyInstaller cannot cross-compile, so each OS's installer has to be built on that OS. GitHub Actions does this for you.

### Publishing a release

Versions follow [semantic versioning](https://semver.org): `MAJOR.MINOR.PATCH`. Record changes in [CHANGELOG.md](CHANGELOG.md) under a new version heading.

1. Bump `version` in `package.json` and `pyproject.toml` (for example `1.0.1`), run `uv lock`, update the changelog and commit.
2. Tag and push:

   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```

3. The **Build installers** workflow builds Windows, macOS (Apple silicon + Intel) and Linux in parallel (~10–15 min) and publishes them on the [Releases page](https://github.com/49mg/data-boss/releases).

To test the builds without publishing, open **Actions → Build installers → Run workflow**. The installers appear as downloadable artifacts on the run.

Each release also carries `latest.yml` (Windows) and `latest-linux.yml` (AppImage). Installed copies read these to find and download updates, so keep them attached to the release.

### Code signing (optional, removes the security warnings)

- **macOS**: an Apple Developer account ($99/year) for a Developer ID certificate and notarization.
- **Windows**: a code-signing certificate, or Azure Trusted Signing.

electron-builder picks these up from the `CSC_LINK` / `CSC_KEY_PASSWORD` (and `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` for notarization) environment variables. Add them as repository secrets and pass them to the build step, and remove `"identity": "-"` from the `mac` config.

## Architecture

Each layer has a single responsibility:


| Layer         | Base class           | Implementation   | Role                                   |
| ------------- | -------------------- | ---------------- | -------------------------------------- |
| Inspection    | `BaseDataInspector`  | `DataInspector`  | Read-only display of data quality info |
| Cleaning      | `BaseDataCleaner`    | `DataCleaner`    | Dataframe mutations + CSV export       |
| Visualization | `BaseDataVisualizer` | `DataVisualizer` | Matplotlib/Seaborn charts → PNG bytes  |


Each concrete class registers its methods in a dictionary and dispatches through `render()` or `apply_clean()`, so new inspection types, cleaning operations, or chart types can be added without changing the UI wiring.

### Example (programmatic use)

```python
import pandas as pd
from src import DataInspector, DataCleaner, DataVisualizer

df = pd.read_csv("your_file.csv")

inspector = DataInspector(df)
print(inspector.show_info()["text"])
print(inspector.show_desc()["table"])
print(inspector.show_column_profile())

cleaner = DataCleaner(df)
cleaner.remove_duplicates()
cleaner.fill_na_median()
cleaner.strip_whitespace()
cleaner.clip_outliers_iqr()
csv_bytes = cleaner.export_data()

visualizer = DataVisualizer(cleaner.df)
fig = visualizer.draw_histogram(column="column_name")
fig.savefig("histogram.png")

fig = visualizer.draw_heatmap()
fig.savefig("correlation_heatmap.png")
```

## License

MIT — see [LICENSE](LICENSE) for details.
