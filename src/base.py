from abc import ABC, abstractmethod
from matplotlib.figure import Figure


class BaseDataInspector(ABC):
    def __init__(self, dataframe):
        self.df = dataframe

    @abstractmethod
    def show_info(self):
        pass

    @abstractmethod
    def show_desc(self):
        pass

    @abstractmethod
    def show_duplicated_value(self):
        pass

    @abstractmethod
    def show_non_value(self):
        pass

    @abstractmethod
    def show_column_profile(self):
        pass


class BaseDataCleaner(ABC):
    def __init__(self, dataframe):
        self.df = dataframe.copy()

    @abstractmethod
    def remove_duplicates(self):
        pass

    @abstractmethod
    def drop_na_rows(self):
        pass

    @abstractmethod
    def drop_na_columns(self):
        pass

    @abstractmethod
    def fill_na_mean(self):
        pass

    @abstractmethod
    def fill_na_median(self):
        pass

    @abstractmethod
    def strip_whitespace(self):
        pass

    @abstractmethod
    def clip_outliers_iqr(self):
        pass

    @abstractmethod
    def clip_outliers_zscore(self):
        pass

    @abstractmethod
    def apply_clean(self, method_key, **kwargs):
        pass

    @abstractmethod
    def export_data(self):
        pass


class BaseDataVisualizer(ABC):
    def __init__(self, dataframe):
        self.df = dataframe.copy()

    @abstractmethod
    def draw_histogram(self, column) -> Figure:
        pass

    @abstractmethod
    def draw_boxplot(self, x_col, y_col) -> Figure:
        pass

    @abstractmethod
    def scatter_plot(self, x_col, y_col) -> Figure:
        pass

    @abstractmethod
    def draw_heatmap(self) -> Figure:
        pass

    @abstractmethod
    def draw_line_chart(self, x_col, y_col) -> Figure:
        pass

    @abstractmethod
    def draw_bar_chart(self, x_col, y_col) -> Figure:
        pass

    @abstractmethod
    def draw_pairplot(self) -> Figure:
        pass
