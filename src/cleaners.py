import pandas as pd
from .base import BaseDataCleaner


class DataCleaner(BaseDataCleaner):

    def __init__(self, dataframe):
        super().__init__(dataframe)
        self.clean_methods = {
            "REMOVE_DUPLICATES": self.remove_duplicates,
            "DROP_NA_ROWS": self.drop_na_rows,
            "FILL_NA_MEAN": self.fill_na_mean,
            "FILL_NA_MEDIAN": self.fill_na_median,
            "STRIP_WHITESPACE": self.strip_whitespace,
            "CLIP_IQR": self.clip_outliers_iqr,
            "CLIP_ZSCORE": self.clip_outliers_zscore,
            "RENAME_COLUMN": self.rename_column,
            "CHANGE_DTYPE": self.change_dtype,
            "DROP_COLUMNS": self.drop_columns,
            "REPLACE_VALUES": self.replace_values,
        }

    def remove_duplicates(self):
        before = len(self.df)
        self.df = self.df.drop_duplicates().reset_index(drop=True)
        removed = before - len(self.df)
        return f"Removed {removed} duplicate row(s)."

    def drop_na_rows(self):
        before = len(self.df)
        self.df = self.df.dropna().reset_index(drop=True)
        removed = before - len(self.df)
        return f"Dropped {removed} row(s) with missing values."

    def fill_na_mean(self):
        numeric_cols = self.df.select_dtypes(include=["number"]).columns
        self.df[numeric_cols] = self.df[numeric_cols].fillna(self.df[numeric_cols].mean())
        return "Filled NaN values with column mean (numeric columns)."

    def fill_na_median(self):
        numeric_cols = self.df.select_dtypes(include=["number"]).columns
        self.df[numeric_cols] = self.df[numeric_cols].fillna(self.df[numeric_cols].median())
        return "Filled NaN values with column median (numeric columns)."

    def strip_whitespace(self):
        str_cols = self.df.select_dtypes(include=["object"]).columns
        self.df[str_cols] = self.df[str_cols].apply(lambda col: col.str.strip())
        return f"Stripped whitespace from {len(str_cols)} string column(s)."

    def clip_outliers_iqr(self):
        numeric_cols = self.df.select_dtypes(include=["number"]).columns
        for col in numeric_cols:
            q1 = self.df[col].quantile(0.25)
            q3 = self.df[col].quantile(0.75)
            iqr = q3 - q1
            self.df[col] = self.df[col].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
        return "Clipped outliers using IQR method (1.5×IQR)."

    def clip_outliers_zscore(self):
        numeric_cols = self.df.select_dtypes(include=["number"]).columns
        for col in numeric_cols:
            mean = self.df[col].mean()
            std = self.df[col].std()
            if std > 0:
                self.df[col] = self.df[col].clip(mean - 3 * std, mean + 3 * std)
        return "Clipped outliers using Z-score method (±3σ)."

    def rename_column(self, old_name, new_name):
        if new_name in self.df.columns and new_name != old_name:
            raise ValueError(f"Column '{new_name}' already exists.")
        self.df = self.df.rename(columns={old_name: new_name})
        return f"Renamed '{old_name}' to '{new_name}'."

    def change_dtype(self, column, dtype):
        try:
            self.df[column] = self.df[column].astype(dtype)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot convert '{column}' to {dtype}: {e}")
        return f"Changed '{column}' type to {dtype}."

    def drop_columns(self, columns):
        if len(columns) == 0:
            raise ValueError("No columns selected to drop.")
        if len(columns) >= len(self.df.columns):
            raise ValueError("Cannot drop all columns. Keep at least one.")
        self.df = self.df.drop(columns=columns)
        return f"Dropped {len(columns)} column(s): {', '.join(columns)}."

    def replace_values(self, column, find, replace):
        if pd.api.types.is_numeric_dtype(self.df[column]):
            try:
                find = float(find)
                replace = float(replace) if str(replace).strip() != "" else float("nan")
            except (ValueError, TypeError):
                pass
        count = int((self.df[column] == find).sum())
        self.df[column] = self.df[column].replace(find, replace)
        return f"Replaced {count} occurrence(s) of '{find}' with '{replace}' in '{column}'."

    def apply_clean(self, method_key, **kwargs):
        if method_key and method_key in self.clean_methods:
            return self.clean_methods[method_key](**kwargs)
        return None

    def export_data(self):
        return self.df.to_csv(index=False).encode("utf-8")
