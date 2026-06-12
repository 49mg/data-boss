# Data Boss

A Streamlit app for exploring and cleaning CSV datasets. Upload a file, profile columns, inspect data quality, apply cleaning operations with full undo history, and generate charts — all from the browser.

Built around three focused classes: `DataInspector` for summaries, `DataCleaner` for mutations, and `DataVisualizer` for plots.

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

- **Info** — column types, non-null counts, and memory usage
- **Description** — statistical summary of numeric columns
- **Missing values** — count of null entries per column
- **Duplicates** — duplicate row detection and count

### Data cleaning


| Operation               | Description                                                    |
| ----------------------- | -------------------------------------------------------------- |
| Remove duplicate rows   | Drops exact duplicates and resets the index                    |
| Drop rows with NaN      | Removes any row containing at least one missing value          |
| Drop columns with NaN   | Removes any columns containing at least one missing value      |
| Strip whitespace        | Trims leading/trailing spaces from all string columns          |
| Fill NaN with mean      | Fills missing numeric values with the column mean              |
| Fill NaN with median    | Fills missing numeric values with the column median            |
| Clip outliers — IQR     | Clips values beyond 1.5×IFeaturesFeaturesQR per numeric column |
| Clip outliers — Z-score | Clips values beyond ±3σ per numeric column                     |
| Rename column           | Renames a selected column                                      |
| Change column type      | Converts a column to int64, float64, str, or bool              |
| Drop columns            | Removes one or more selected columns                           |
| Replace values          | Find-and-replace within a selected column                      |


Every operation supports **Do / Undo** — the full history is preserved so you can step back to the original data at any point. The **Download CSV** button always exports the current working state.

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

## Project structure

```
data-boss/
├── main.py                 # Streamlit entry point
├── src/
│   ├── base.py             # Abstract base classes (BaseDataInspector, BaseDataCleaner, BaseDataVisualizer)
│   ├── inspectors.py       # DataInspector — read-only data summaries
│   ├── cleaners.py         # DataCleaner — dataframe mutations and CSV export
│   └── visualizers.py      # DataVisualizer — Matplotlib/Seaborn charts
└── pyproject.toml
```

## Requirements

- Python 3.10+
- pandas
- streamlit
- matplotlib
- seaborn

## Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd data-boss
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

## Usage

Start the app:

```bash
streamlit run main.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

1. Upload a CSV file (max 200 MB) via the file uploader.
2. Browse the raw dataframe and **Column Profile** for a per-column summary.
3. Pick a **Display way** option for deeper data quality inspection.
4. Pick a **Cleaning method**, configure any extra inputs, then click **Do** to apply or **Undo** to revert.
5. Check the **Session History** panel to review all applied operations and their shape impact.
6. Check the **Before / After Preview** panel to compare the dataframe before and after the last operation.
7. Pick a **Visualization way**, choose columns, and click the generate button.
8. Click **Download CSV** to export the current (cleaned) dataframe.

## Architecture

Each layer has a single responsibility:


| Layer         | Base class           | Implementation   | Role                                   |
| ------------- | -------------------- | ---------------- | -------------------------------------- |
| Inspection    | `BaseDataInspector`  | `DataInspector`  | Read-only display of data quality info |
| Cleaning      | `BaseDataCleaner`    | `DataCleaner`    | Dataframe mutations + CSV export       |
| Visualization | `BaseDataVisualizer` | `DataVisualizer` | Matplotlib/Seaborn charts              |


Each concrete class registers its methods in a dictionary and dispatches through `render()` or `apply_clean()`, so new inspection types, cleaning operations, or chart types can be added without changing the UI wiring.

### Example (programmatic use)

```python
import pandas as pd
from src import DataInspector, DataCleaner, DataVisualizer

df = pd.read_csv("your_file.csv")

inspector = DataInspector(df)
inspector.show_info()
inspector.show_desc()
inspector.show_column_profile()

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
