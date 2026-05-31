import matplotlib.pyplot as plt
import seaborn as sns
from .base import BaseDataVisualizer
import streamlit as st


class DataVisualizer(BaseDataVisualizer):

    def __init__(self, dataframe):
        super().__init__(dataframe)
        self.methods = {
            "HIST": self.draw_histogram,
            "BOX": self.draw_boxplot,
            "SCAT": self.scatter_plot,
            "HEAT": self.draw_heatmap,
            "LINE": self.draw_line_chart,
            "BAR": self.draw_bar_chart,
            "PAIR": self.draw_pairplot,
        }

    def draw_histogram(self, column, df=None):
        data = df if df is not None else self.df
        fig, ax = plt.subplots()
        sns.histplot(data=data, x=column, kde=True, ax=ax)
        return fig

    def draw_boxplot(self, x_col, y_col, df=None):
        data = df if df is not None else self.df
        fig, ax = plt.subplots()
        sns.boxplot(data=data, x=x_col, y=y_col, ax=ax)
        return fig

    def scatter_plot(self, x_col, y_col, df=None, hue_col=None):
        data = df if df is not None else self.df
        g = sns.relplot(data=data, x=x_col, y=y_col, hue=hue_col, kind="scatter")
        return g.figure

    def draw_heatmap(self, df=None):
        data = df if df is not None else self.df
        numeric_df = data.select_dtypes(include=["number"])
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(numeric_df.corr(), annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
        return fig

    def draw_line_chart(self, x_col, y_col, df=None):
        data = df if df is not None else self.df
        fig, ax = plt.subplots()
        ax.plot(data[x_col], data[y_col])
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.tick_params(axis="x", rotation=45)
        return fig

    def draw_bar_chart(self, x_col, y_col, df=None):
        data = df if df is not None else self.df
        fig, ax = plt.subplots()
        sns.barplot(data=data, x=x_col, y=y_col, ax=ax)
        ax.tick_params(axis="x", rotation=45)
        return fig

    def draw_pairplot(self, df=None, hue_col=None):
        data = df if df is not None else self.df
        g = sns.pairplot(data, hue=hue_col)
        return g.figure

    def render(self, method_key, df=None, **kwargs):
        if method_key not in self.methods:
            return
        fig = self.methods[method_key](df=df, **kwargs)
        if fig is not None:
            st.pyplot(fig)
            plt.close(fig)
