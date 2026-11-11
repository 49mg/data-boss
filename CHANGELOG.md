# Changelog

All notable changes to Data Boss. Versions follow [semantic versioning](https://semver.org).
Milestones before 1.0 were developed on the `desktop-application` branch and not published as releases.

## [1.0.0] – 2026-11-11

### Added
- **Arabic interface** with a right-to-left layout, a bundled Arabic font (Noto Sans Arabic) and translated analysis sentences; switch with **العربية / English** in the sidebar. Reports exported in Arabic are right to left.
- **Interactive charts** (Apache ECharts, bundled): tooltips, zoom, and click a bar, box or histogram range to keep only those rows or compare them with the rest. The **Image** view and all exports still use Matplotlib.
- **Dashboard** of pinned charts and pivot tables that redraws after every cleaning step; can be added to reports.
- **Automatic updates** for Windows and Linux AppImage installs (can be turned off).
- README screenshots, demo GIF and a privacy section; this changelog.

### Fixed
- Pin, Report and SVG export could pair a newly selected chart type with the previous chart's settings while the new chart was still drawing.

## [0.5.0] – Machine learning
### Added
- **Model › Predict:** baseline, linear/logistic regression and random forest on a stratified 80/20 split with leakage-safe preprocessing, test metrics, predicted-vs-actual or confusion matrix, permutation importance and warnings (small data, imbalance, leakage, overfitting). Exports a scikit-learn script.
- **Model › Clusters:** k-means with an elbow/silhouette scan, plain-language cluster profiles, a 2-D map and **Add as column**.
- **Model › Forecast:** exponential smoothing (Holt-Winters) with 80%/95% ranges and a backtest against a naive benchmark.

## [0.4.0] – Communication
### Added
- **Analyze › Trends:** period-over-period and year-over-year change, moving average, running total and insight sentences.
- **Analyze › Compare segment:** a filtered group against the rest on every column, with Holm-adjusted tests.
- **Report builder:** collect charts, tables, trends and test results with notes; export self-contained HTML or PDF.
- **Jupyter notebook export** of the whole session (checked in CI with `nbconvert --execute`).

### Fixed
- Applying a query while a newer query was still running applied the previous result.

## [0.3.0] – Statistics
### Added
- **Inspect › Target:** rank every column by its relationship to a chosen column.
- **Analyze › Tests:** the right statistical test chosen automatically and explained in plain language, with effect sizes and confidence intervals.
- **Feature engineering** in Clean: one-hot encode, scale, bin, log transform, group rare categories.

### Fixed
- Exported chart and pivot code now replays the cleaning steps.

## [0.2.0] – Analyst core
### Added
- **Query** screen (SQL via DuckDB), Excel/Parquet/JSON files, **Analyze › Pivot table**, calculated columns and date parts, joining another file.

## [0.1.0] – Desktop app
### Added
- Electron desktop app with a bundled Python engine, redesigned Inspect, Clean and Visualize screens, background work with cancel, installers for Windows, macOS and Linux, and CI.
