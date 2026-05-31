import pandas as pd
import streamlit as st
from src import DataInspector, DataCleaner, DataVisualizer

st.set_page_config(layout="wide")

MAX_FILE_SIZE_MB = 200

uploaded_file = st.file_uploader(label="Choose a CSV file", type="csv")

if uploaded_file is not None:

    if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        st.error(
            f"File is too large ({uploaded_file.size / 1024 / 1024:.1f} MB). "
            f"Maximum allowed size is {MAX_FILE_SIZE_MB} MB."
        )
        st.stop()

    file_key = uploaded_file.name + str(uploaded_file.size)

    if st.session_state.get("file_key") != file_key:
        try:
            raw_df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Could not read the CSV file: {e}")
            st.stop()

        st.session_state.file_key = file_key
        st.session_state.working_df = raw_df
        st.session_state.df_history = []
        st.session_state.operation_log = []
        st.session_state.clean_message = None

    df = st.session_state.working_df

    inspector = DataInspector(df)
    cleaner = DataCleaner(df)
    visualizer = DataVisualizer(df)

    st.download_button(
        label="Download CSV",
        data=cleaner.export_data(),
        file_name="data.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    st.write("### Data Frame")
    st.dataframe(df)

    st.write("### Column Profile")
    inspector.show_column_profile()

    st.write("**Top values by column**")
    detail_col = st.selectbox("Select column to inspect", df.columns, key="profile_detail_col")
    vc = df[detail_col].value_counts(dropna=False).head(20).reset_index()
    vc.columns = ["Value", "Count"]
    st.dataframe(vc, use_container_width=True)

    st.write("### Cleaning Way")

    DISPLAY_OPTIONS = {
        "Select display way": None,
        "Display info": "INFO",
        "Display description": "DESC",
        "Display missing values": "NON_VALUE",
        "Display duplicated rows": "DUPLICATED",
    }

    choice = st.selectbox("Display way", list(DISPLAY_OPTIONS.keys()))

    if DISPLAY_OPTIONS[choice] is not None:
        inspector.render(DISPLAY_OPTIONS[choice])

    st.write("#### Apply Cleaning")

    CLEAN_OPTIONS = {
        "Select cleaning method": None,
        "Remove duplicate rows": "REMOVE_DUPLICATES",
        "Drop rows with NaN": "DROP_NA_ROWS",
        "Strip whitespace (strings)": "STRIP_WHITESPACE",
        "Fill NaN with mean": "FILL_NA_MEAN",
        "Fill NaN with median": "FILL_NA_MEDIAN",
        "Clip outliers — IQR": "CLIP_IQR",
        "Clip outliers — Z-score": "CLIP_ZSCORE",
        "Rename column": "RENAME_COLUMN",
        "Change column type": "CHANGE_DTYPE",
        "Drop columns": "DROP_COLUMNS",
        "Replace values": "REPLACE_VALUES",
    }

    DTYPE_MAP = {
        "Integer (int64)": "int64",
        "Float (float64)": "float64",
        "Text (str)": "str",
        "Boolean (bool)": "bool",
    }

    clean_choice = st.selectbox("Cleaning method", list(CLEAN_OPTIONS.keys()))
    clean_key = CLEAN_OPTIONS[clean_choice]

    extra_kwargs = {}
    do_disabled = clean_key is None

    if clean_key == "RENAME_COLUMN":
        col_to_rename = st.selectbox("Column to rename", df.columns, key="rename_col")
        new_col_name = st.text_input("New column name", key="rename_new")
        extra_kwargs = {"old_name": col_to_rename, "new_name": new_col_name.strip()}
        do_disabled = not new_col_name.strip() or new_col_name.strip() == col_to_rename

    elif clean_key == "CHANGE_DTYPE":
        col_to_convert = st.selectbox("Column", df.columns, key="dtype_col")
        dtype_label = st.selectbox("Target type", list(DTYPE_MAP.keys()), key="dtype_target")
        extra_kwargs = {"column": col_to_convert, "dtype": DTYPE_MAP[dtype_label]}

    elif clean_key == "DROP_COLUMNS":
        cols_to_drop = st.multiselect("Columns to drop", df.columns, key="drop_cols")
        extra_kwargs = {"columns": cols_to_drop}
        do_disabled = len(cols_to_drop) == 0

    elif clean_key == "REPLACE_VALUES":
        replace_col = st.selectbox("Column", df.columns, key="replace_col")
        find_val = st.text_input("Find value", key="replace_find")
        replace_val = st.text_input("Replace with", key="replace_with")
        extra_kwargs = {"column": replace_col, "find": find_val, "replace": replace_val}
        do_disabled = not find_val

    if st.session_state.get("clean_message"):
        level, msg = st.session_state.clean_message
        if level == "success":
            st.success(msg)
        else:
            st.error(msg)
        st.session_state.clean_message = None

    do_col, undo_col = st.columns([1, 1])

    with do_col:
        if st.button("Do", disabled=do_disabled, use_container_width=True):
            shape_before = st.session_state.working_df.shape
            st.session_state.df_history.append(st.session_state.working_df.copy())
            try:
                temp_cleaner = DataCleaner(st.session_state.working_df)
                msg = temp_cleaner.apply_clean(clean_key, **extra_kwargs)
                st.session_state.working_df = temp_cleaner.df
                shape_after = st.session_state.working_df.shape
                st.session_state.operation_log.append({
                    "step": len(st.session_state.operation_log) + 1,
                    "msg": msg,
                    "shape_before": shape_before,
                    "shape_after": shape_after,
                })
                st.session_state.clean_message = ("success", msg)
            except Exception as e:
                st.session_state.df_history.pop()
                st.session_state.clean_message = ("error", str(e))
            st.rerun()

    with undo_col:
        undo_disabled = len(st.session_state.get("df_history", [])) == 0
        if st.button("Undo", disabled=undo_disabled, use_container_width=True):
            st.session_state.working_df = st.session_state.df_history.pop()
            undone_msg = ""
            if st.session_state.operation_log:
                undone = st.session_state.operation_log.pop()
                undone_msg = f" (undone: {undone['msg']})"
            st.session_state.clean_message = ("success", f"Last step undone.{undone_msg}")
            st.rerun()

    operation_log = st.session_state.get("operation_log", [])
    with st.expander(f"Session History — {len(operation_log)} operation(s) applied", expanded=False):
        if not operation_log:
            st.write("No cleaning operations applied yet.")
        else:
            for entry in reversed(operation_log):
                r_before, c_before = entry["shape_before"]
                r_after, c_after = entry["shape_after"]
                delta_rows = r_after - r_before
                delta_cols = c_after - c_before

                deltas = []
                if delta_rows != 0:
                    deltas.append(f"rows {delta_rows:+d}")
                if delta_cols != 0:
                    deltas.append(f"cols {delta_cols:+d}")
                delta_str = f"  ·  {', '.join(deltas)}" if deltas else ""

                st.markdown(f"**Step {entry['step']}** — {entry['msg']}{delta_str}")

    history = st.session_state.get("df_history", [])
    if history:
        with st.expander("Before / After Preview", expanded=False):
            before_df = history[-1]
            after_df = st.session_state.working_df

            before_col, after_col = st.columns(2)
            with before_col:
                st.markdown(f"**Before** — {before_df.shape[0]:,} rows × {before_df.shape[1]} cols")
                st.dataframe(before_df.head(10), use_container_width=True)
            with after_col:
                st.markdown(f"**After** — {after_df.shape[0]:,} rows × {after_df.shape[1]} cols")
                st.dataframe(after_df.head(10), use_container_width=True)

    st.write("### Visualization Way")

    VISUALIZATION_OPTIONS = {
        "Select visualization way": None,
        "Histogram": "HIST",
        "Box plot": "BOX",
        "Scatter plot": "SCAT",
        "Correlation heatmap": "HEAT",
        "Line chart": "LINE",
        "Bar chart": "BAR",
        "Pair plot": "PAIR",
    }

    v_choice = st.selectbox("Visualization way", list(VISUALIZATION_OPTIONS.keys()))
    method_key = VISUALIZATION_OPTIONS[v_choice]

    if method_key is not None:

        if method_key == "HIST":
            numeric_cols = df.select_dtypes(include=["number"]).columns

            if len(numeric_cols) > 0:
                selected_column = st.selectbox("Select numeric column for Histogram", numeric_cols)

                nan_count = df[selected_column].isna().sum()
                if nan_count > 0:
                    st.warning(f"Warning: This column contains {nan_count} missing value(s) (NaN).")

                if st.button("Generate Histogram"):
                    clean_df = df[[selected_column]].dropna()
                    visualizer.render(method_key, df=clean_df, column=selected_column)
            else:
                st.warning("No numeric columns found in this dataset to draw a histogram.")

        elif method_key == "BOX":
            categorical_cols = df.select_dtypes(include=["object", "category", "bool"]).columns
            numeric_cols = df.select_dtypes(include=["number"]).columns

            if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                x_column = st.selectbox("Select X axis (Categorical)", categorical_cols)
                y_column = st.selectbox("Select Y axis (Numerical)", numeric_cols)

                x_nan = df[x_column].isna().sum()
                y_nan = df[y_column].isna().sum()
                if x_nan > 0 or y_nan > 0:
                    st.warning(f"Warning: Selected columns contain missing values! (X: {x_nan} | Y: {y_nan})")

                if st.button("Generate Box Plot"):
                    clean_df = df[[x_column, y_column]].dropna()
                    visualizer.render(method_key, df=clean_df, x_col=x_column, y_col=y_column)
            else:
                st.warning("Need at least one categorical and one numeric column for a box plot.")

        elif method_key == "SCAT":
            numeric_cols = df.select_dtypes(include=["number"]).columns
            categorical_cols = df.select_dtypes(include=["object", "category", "bool"]).columns

            if len(numeric_cols) >= 2:
                x_column = st.selectbox("Select X axis (Numerical)", numeric_cols, index=0)
                y_column = st.selectbox("Select Y axis (Numerical)", numeric_cols, index=1 if len(numeric_cols) > 1 else 0)

                hue_options = ["None"] + list(categorical_cols)
                hue_column = st.selectbox("Color grouping (Hue)", hue_options)

                x_nan = df[x_column].isna().sum()
                y_nan = df[y_column].isna().sum()
                hue_nan = df[hue_column].isna().sum() if hue_column != "None" else 0
                if x_nan > 0 or y_nan > 0 or hue_nan > 0:
                    st.warning(f"Warning: Missing values in selected columns! (X: {x_nan} | Y: {y_nan} | Hue: {hue_nan})")

                if st.button("Generate Scatter Plot"):
                    required_cols = [x_column, y_column]
                    if hue_column != "None":
                        required_cols.append(hue_column)
                    clean_df = df[required_cols].dropna()
                    passed_hue = hue_column if hue_column != "None" else None
                    visualizer.render(method_key, df=clean_df, x_col=x_column, y_col=y_column, hue_col=passed_hue)
            else:
                st.warning("Need at least two numeric columns for a scatter plot.")

        elif method_key == "HEAT":
            numeric_cols = list(df.select_dtypes(include=["number"]).columns)

            if len(numeric_cols) >= 2:
                selected_cols = st.multiselect(
                    "Select numeric columns (default: all)",
                    numeric_cols,
                    default=numeric_cols,
                    key="heat_cols",
                )
                if st.button("Generate Heatmap"):
                    if len(selected_cols) >= 2:
                        visualizer.render(method_key, df=df[selected_cols].dropna())
                    else:
                        st.warning("Select at least 2 columns.")
            else:
                st.warning("Need at least 2 numeric columns for a correlation heatmap.")

        elif method_key == "LINE":
            numeric_cols = df.select_dtypes(include=["number"]).columns

            if len(numeric_cols) > 0:
                x_column = st.selectbox("Select X axis", df.columns, key="line_x")
                y_column = st.selectbox("Select Y axis (Numeric)", numeric_cols, key="line_y")

                if st.button("Generate Line Chart"):
                    visualizer.render(method_key, df=df, x_col=x_column, y_col=y_column)
            else:
                st.warning("Need at least one numeric column for the Y axis.")

        elif method_key == "BAR":
            categorical_cols = df.select_dtypes(include=["object", "category", "bool"]).columns
            numeric_cols = df.select_dtypes(include=["number"]).columns

            if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                x_column = st.selectbox("Select X axis (Categorical)", categorical_cols, key="bar_x")
                y_column = st.selectbox("Select Y axis (Numeric)", numeric_cols, key="bar_y")

                x_nan = df[x_column].isna().sum()
                y_nan = df[y_column].isna().sum()
                if x_nan > 0 or y_nan > 0:
                    st.warning(f"Warning: Missing values in selected columns! (X: {x_nan} | Y: {y_nan})")

                if st.button("Generate Bar Chart"):
                    clean_df = df[[x_column, y_column]].dropna()
                    visualizer.render(method_key, df=clean_df, x_col=x_column, y_col=y_column)
            else:
                st.warning("Need at least one categorical and one numeric column for a bar chart.")

        elif method_key == "PAIR":
            numeric_cols = list(df.select_dtypes(include=["number"]).columns)
            categorical_cols = df.select_dtypes(include=["object", "category", "bool"]).columns

            if len(numeric_cols) >= 2:
                if len(numeric_cols) > 6:
                    st.info(
                        f"Dataset has {len(numeric_cols)} numeric columns. "
                        "Pair plot may be slow — consider selecting fewer columns."
                    )
                default_cols = numeric_cols[:min(5, len(numeric_cols))]
                selected_cols = st.multiselect(
                    "Select numeric columns",
                    numeric_cols,
                    default=default_cols,
                    key="pair_cols",
                )
                hue_options = ["None"] + list(categorical_cols)
                hue_column = st.selectbox("Color grouping (Hue)", hue_options, key="pair_hue")

                if st.button("Generate Pair Plot"):
                    if len(selected_cols) >= 2:
                        passed_hue = hue_column if hue_column != "None" else None
                        cols_to_use = selected_cols + ([hue_column] if passed_hue else [])
                        subset = df[cols_to_use].dropna()
                        visualizer.render(method_key, df=subset, hue_col=passed_hue)
                    else:
                        st.warning("Select at least 2 columns for a pair plot.")
            else:
                st.warning("Need at least 2 numeric columns for a pair plot.")
