import io
import pandas as pd
import streamlit as st
from .base import BaseDataInspector


class DataInspector(BaseDataInspector):

    def __init__(self, dataframe):
        super().__init__(dataframe)
        self.methods = {
            "INFO": self.show_info,
            "DESC": self.show_desc,
            "DUPLICATED": self.show_duplicated_value,
            "NON_VALUE": self.show_non_value,
        }

    def show_info(self):
        buffer = io.StringIO()
        self.df.info(buf=buffer)
        st.text(buffer.getvalue())

    def show_desc(self):
        st.dataframe(self.df.describe())

    def show_duplicated_value(self):
        duplicated_sum = self.df.duplicated().sum()
        st.write(f"Duplicate rows: {duplicated_sum}")

        if duplicated_sum > 0:
            st.dataframe(self.df[self.df.duplicated(keep=False)])

    def show_non_value(self):
        missing = self.df.isna().sum()
        missing_cols = missing[missing > 0]

        if len(missing_cols) > 0:
            st.dataframe(missing_cols.rename("missing_count"))
        else:
            st.write("No missing values found.")

        st.write(f"Total missing: {missing.sum()}")

    def show_column_profile(self):
        rows = []
        for col in self.df.columns:
            series = self.df[col]
            non_null = int(series.notna().sum())
            missing = int(series.isna().sum())
            missing_pct = series.isna().mean() * 100
            unique = int(series.nunique())

            if pd.api.types.is_numeric_dtype(series):
                s = series.dropna()
                if len(s) > 0:
                    range_str = f"min={s.min():.4g}  ·  med={s.median():.4g}  ·  max={s.max():.4g}"
                else:
                    range_str = "—"
            else:
                top = series.value_counts().head(3)
                range_str = "  ·  ".join([f"{v} ({c})" for v, c in top.items()]) if len(top) > 0 else "—"

            rows.append({
                "Column": col,
                "Type": str(series.dtype),
                "Non-null": non_null,
                "Missing": f"{missing} ({missing_pct:.1f}%)",
                "Unique": unique,
                "Top values / Range": range_str,
            })

        st.dataframe(
            pd.DataFrame(rows).set_index("Column"),
            use_container_width=True,
        )

    def render(self, method_key):
        if method_key and method_key in self.methods:
            return self.methods[method_key]()
