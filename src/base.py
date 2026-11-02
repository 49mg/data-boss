from abc import ABC, abstractmethod
from matplotlib.figure import Figure
from pandas import DataFrame


class BaseDataInspector(ABC):
    def __init__(self, dataframe):
        self.df = dataframe

    @abstractmethod
    def show_info(self) -> dict:
        pass

    @abstractmethod
    def show_desc(self) -> dict:
        pass

    @abstractmethod
    def show_duplicated_value(self) -> dict:
        pass

    @abstractmethod
    def show_non_value(self) -> dict:
        pass

    @abstractmethod
    def show_column_profile(self) -> DataFrame:
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
    """Chart builders. Each draw_* returns (figure, insights, notes, code)."""

    def __init__(self, dataframe):
        self.df = dataframe.copy()

    @abstractmethod
    def draw_histogram(self, column, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def draw_boxplot(self, y, x=None, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def scatter_plot(self, x, y, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def draw_heatmap(self, columns=None, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def draw_line_chart(self, x, y, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def draw_bar_chart(self, x, y=None, **options) -> tuple[Figure, list, list, list]:
        pass

    @abstractmethod
    def draw_pairplot(self, columns=None, **options) -> tuple[Figure, list, list, list]:
        pass
