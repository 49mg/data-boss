"""k-means clustering with plain-language cluster profiles.

Columns are imputed, scaled and one-hot encoded (the same preprocessing as the
model builder), k is chosen with the silhouette score unless given, and the
clusters are numbered by size (Cluster 1 is the largest) so results are easy to
talk about and reproducible with the fixed seed.
"""

import math

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from .model import _is_num, _text, choose_features, make_preprocess

SEED = 42
K_RANGE = range(2, 9)
SEARCH_ROWS = 20_000
SILHOUETTE_ROWS = 3000
MAP_POINTS = 800


class ClusterError(ValueError):
    """A user-facing problem with the clustering settings."""


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _s(v):
    v = float(v)
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.3g}"


def _prepare(df, features):
    used, skipped = choose_features(df, None, features)
    numeric = [c for c in used if _is_num(df[c])]
    categorical = [c for c in used if c not in numeric]
    X = df[used].copy()
    for c in categorical:
        X[c] = _text(X[c])
    if len(X) < 10:
        raise ClusterError("Clustering needs at least 10 rows.")
    return X, used, numeric, categorical, skipped


def _renumber(labels, k):
    """Cluster 1 = largest, ties broken by the original label, so the mapping is deterministic."""
    counts = np.bincount(labels, minlength=k)
    order = sorted(range(k), key=lambda c: (-counts[c], c))
    mapping = {c: i + 1 for i, c in enumerate(order)}
    return np.array([mapping[c] for c in labels])


def fit_clusters(df, features, k):
    """Cluster numbers 1..k for every row (used by Clean › Add clusters too)."""
    X, used, numeric, categorical, _ = _prepare(df, features)
    k = int(k)
    if k < 2 or k > 20:
        raise ClusterError("Choose between 2 and 20 clusters.")
    if k >= len(X):
        raise ClusterError("There must be more rows than clusters.")
    Z = make_preprocess(numeric, categorical).fit_transform(X)
    labels = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit_predict(Z)
    return _renumber(labels, k), Z, used, numeric, categorical


def clusters(df, features=None, k=None):
    X, used, numeric, categorical, skipped = _prepare(df, features)
    Z = make_preprocess(numeric, categorical).fit_transform(X)
    Z = Z.toarray() if hasattr(Z, "toarray") else np.asarray(Z)

    rng = np.random.default_rng(SEED)
    search = Z if len(Z) <= SEARCH_ROWS else Z[rng.choice(len(Z), SEARCH_ROWS, replace=False)]
    scan = []
    for kk in K_RANGE:
        if kk >= len(search):
            break
        km = KMeans(n_clusters=kk, n_init=10, random_state=SEED).fit(search)
        sil = silhouette_score(search, km.labels_, sample_size=min(SILHOUETTE_ROWS, len(search)), random_state=SEED)
        scan.append({"k": kk, "inertia": _f(km.inertia_), "silhouette": _f(sil)})
    if not scan:
        raise ClusterError("Too few rows to compare cluster counts.")
    suggested = max(scan, key=lambda s: s["silhouette"] or -1)["k"]
    k = int(k) if k else suggested

    labels, _, _, _, _ = fit_clusters(df, used, k)
    profiles = _profiles(df, labels, k, numeric, categorical)
    sil = next((s["silhouette"] for s in scan if s["k"] == k), None)

    pca = PCA(n_components=2, random_state=SEED).fit(Z)
    xy = pca.transform(Z)
    idx = np.arange(len(Z)) if len(Z) <= MAP_POINTS else np.sort(rng.choice(len(Z), MAP_POINTS, replace=False))
    points = [[_f(xy[i, 0]), _f(xy[i, 1]), int(labels[i])] for i in idx]

    quality = ("well separated" if (sil or 0) >= 0.5 else "moderately separated" if (sil or 0) >= 0.25
               else "weakly separated: the data may not have clear groups")
    return {
        "k": k, "suggestedK": suggested, "scan": scan, "silhouette": sil, "quality": quality,
        "features": [str(c) for c in used], "skipped": skipped, "rows": int(len(Z)),
        "profiles": profiles, "points": points,
        "explained": [_f(v) for v in pca.explained_variance_ratio_],
        "summary": (f"{k} clusters, {quality} (silhouette {sil:.2f}). "
                    + ("" if k == suggested else f"The silhouette score suggests {suggested}.")).strip(),
        "code": cluster_code(numeric, categorical, k, "cluster"),
    }


def _profiles(df, labels, k, numeric, categorical):
    out = []
    n = len(df)
    for c in range(1, k + 1):
        mask = labels == c
        size = int(mask.sum())
        traits, mild, stats = [], [], []
        for col in numeric:
            s = df[col]
            mu, sd = s.mean(), s.std()
            cm = s[mask].mean()
            z = (cm - mu) / sd if sd and sd > 0 and pd.notna(cm) else 0.0
            stats.append({"column": str(col), "kind": "numeric", "mean": _f(cm), "overall": _f(mu), "z": _f(z)})
            if abs(z) >= 0.5:
                word = ("very " if abs(z) >= 1.5 else "") + ("high" if z > 0 else "low")
                traits.append((abs(z), f"{word} {col} (avg {_s(cm)} vs {_s(mu)})"))
            elif abs(z) >= 0.2:
                mild.append((abs(z), f"slightly {'higher' if z > 0 else 'lower'} {col} (avg {_s(cm)} vs {_s(mu)})"))
        for col in categorical:
            s = df[col].astype("string")
            share_all = s.value_counts(normalize=True)
            share = s[mask].value_counts(normalize=True)
            if share.empty:
                continue
            top = share.index[0]
            lift = share.iloc[0] / share_all.get(top, 1)
            stats.append({"column": str(col), "kind": "category", "top": str(top), "share": _f(share.iloc[0]),
                          "overall": _f(share_all.get(top, 0))})
            detail = f"({share.iloc[0]:.0%} vs {share_all.get(top, 0):.0%} overall)"
            if share.iloc[0] >= 0.4 and lift >= 1.3:
                traits.append((lift - 1, f"mostly {col} = {top} {detail}"))
            elif share.iloc[0] >= 0.4 and lift >= 1.1:
                mild.append((lift - 1, f"more often {col} = {top} {detail}"))
        traits.sort(key=lambda t: -t[0])
        if not traits:
            traits = sorted(mild, key=lambda t: -t[0])
        words = [t[1] for t in traits[:3]]
        short = ", ".join(w.split(" (")[0] for w in words) or "close to average on everything"
        out.append({"cluster": c, "size": size, "share": _f(size / n), "name": f"Cluster {c}: {short}",
                    "traits": words, "stats": stats})
    return out


def cluster_code(numeric, categorical, k, name):
    """Pandas + scikit-learn code that rebuilds the cluster column."""
    return "\n".join([
        "from sklearn.cluster import KMeans",
        "from sklearn.compose import ColumnTransformer",
        "from sklearn.impute import SimpleImputer",
        "from sklearn.pipeline import Pipeline",
        "from sklearn.preprocessing import OneHotEncoder, StandardScaler",
        f"numeric, categorical = {numeric!r}, {categorical!r}",
        "X = df[numeric + categorical].copy()",
        "for c in categorical:",
        "    X[c] = X[c].astype('string').astype(object).where(X[c].notna(), np.nan)",
        "parts = []",
        "if numeric:",
        "    parts.append(('num', Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), numeric))",
        "if categorical:",
        "    parts.append(('cat', Pipeline([('impute', SimpleImputer(strategy='most_frequent')),",
        "                                   ('onehot', OneHotEncoder(handle_unknown='infrequent_if_exist', max_categories=20))]),",
        "                  categorical))",
        "Z = ColumnTransformer(parts).fit_transform(X)",
        f"labels = KMeans(n_clusters={k}, n_init=10, random_state={SEED}).fit_predict(Z)",
        f"counts = np.bincount(labels, minlength={k})",
        f"order = sorted(range({k}), key=lambda c: (-counts[c], c))  # Cluster 1 = largest",
        "number = {c: i + 1 for i, c in enumerate(order)}",
        f"df[{name!r}] = [f'Cluster {{number[c]}}' for c in labels]",
    ])
