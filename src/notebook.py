"""Build Jupyter notebooks (.ipynb, nbformat 4.5) as plain JSON.

No Jupyter packages are needed to write one; the format is a JSON document
with a list of markdown and code cells.
"""

import hashlib
import json


def _source(text):
    """Notebook sources are lists of lines that keep their newline characters."""
    lines = str(text).splitlines(keepends=True)
    return lines or [""]


def markdown(text):
    return {"cell_type": "markdown", "metadata": {}, "source": _source(text)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": _source(text)}


def notebook(cells):
    out = []
    for i, cell in enumerate(cells):
        digest = hashlib.sha1(f"{i}:{''.join(cell['source'])}".encode()).hexdigest()[:12]
        out.append({"id": f"cell-{i}-{digest}", **cell})
    return {
        "cells": out,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            "generator": "Data Boss",
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def dumps(nb):
    return json.dumps(nb, ensure_ascii=False, indent=1) + "\n"
