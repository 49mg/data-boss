"""Train and compare simple predictive models with scikit-learn.

Everything that learns from data (imputing, scaling, one-hot encoding) sits
inside a scikit-learn Pipeline that is fitted on the training rows only, so
the test rows stay unseen. Three models are compared on the same split:

* a baseline that always predicts the mean / the most common class
* linear regression / logistic regression
* a random forest

Results are reported on the test rows, with permutation feature importance
for the best model and warnings for tiny data, class imbalance, suspiciously
perfect scores (leakage) and overfitting. ``code`` reproduces it all.
"""

import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    make_scorer,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
TEST_SIZE = 0.2
MAX_ROWS = 100_000
MAX_CLASSES = 20
MAX_LEVELS_FRACTION = 0.9
IMPORTANCE_ROWS = 2000
POINTS = 400
MODEL_NAMES = {"baseline": "Baseline", "linear": "Linear model", "forest": "Random forest"}


class ModelError(ValueError):
    """A user-facing problem with the model settings."""


def _f(v):
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _s(v):
    v = float(v)
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.3g}"


def _is_num(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def detect_task(y):
    """'regression' for a number with many values, otherwise 'classification'."""
    y = y.dropna()
    if not _is_num(y):
        return "classification"
    if y.nunique() <= 10 and np.allclose(y, np.round(y)):
        return "classification"
    return "regression"


def choose_features(df, target, features=None):
    """Usable feature columns plus notes on the ones left out."""
    candidates = [c for c in (features or df.columns) if c != target and c in df.columns]
    used, skipped = [], []
    for c in candidates:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            skipped.append({"column": str(c), "reason": "Date column. Add date parts in Clean to use it."})
        elif s.notna().sum() == 0:
            skipped.append({"column": str(c), "reason": "Empty."})
        elif s.nunique() < 2:
            skipped.append({"column": str(c), "reason": "The same value in every row."})
        elif not _is_num(s) and s.nunique() > 50 and s.nunique() > MAX_LEVELS_FRACTION * s.notna().sum():
            skipped.append({"column": str(c), "reason": "Almost every value is different (an ID or free text)."})
        else:
            used.append(c)
    if not used:
        raise ModelError("No usable feature columns. Pick columns with numbers or a limited number of categories.")
    return used, skipped


def _text(series):
    """Categories as text, missing values kept as NaN (what the imputer expects)."""
    return series.astype("string").astype(object).where(series.notna(), np.nan)


def make_preprocess(numeric, categorical):
    parts = []
    if numeric:
        parts.append(("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
    if categorical:
        parts.append(("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                                       ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", max_categories=20))]),
                      categorical))
    return ColumnTransformer(parts)


def make_models(task):
    if task == "regression":
        return {"baseline": DummyRegressor(strategy="mean"), "linear": LinearRegression(),
                "forest": RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)}
    return {"baseline": DummyClassifier(strategy="most_frequent"), "linear": LogisticRegression(max_iter=1000),
            "forest": RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=-1)}


def train_models(df, target, features=None, task="auto"):
    if target not in df.columns:
        raise ModelError(f"Unknown column: {target}.")
    if pd.api.types.is_datetime64_any_dtype(df[target]):
        raise ModelError("A date can't be the target. Pick the column you want to predict.")
    used, skipped = choose_features(df, target, features)
    data = df[used + [target]].dropna(subset=[target])
    notes = []
    dropped = len(df) - len(data)
    if dropped:
        notes.append(f"{dropped:,} row(s) without a {target} value were left out.")
    if len(data) < 20:
        raise ModelError(f"Only {len(data)} rows have a {target} value; at least 20 are needed to train and test a model.")
    detected = detect_task(data[target])
    task = detected if task in (None, "", "auto") else task
    if task not in ("regression", "classification"):
        raise ModelError("Task must be regression or classification.")
    if task == "regression" and not _is_num(data[target]):
        raise ModelError(f"“{target}” is not numeric, so it can only be predicted as categories (classification).")
    sampled = len(data) > MAX_ROWS
    if sampled:
        data = data.sample(MAX_ROWS, random_state=SEED)
        notes.append(f"Trained on a random sample of {MAX_ROWS:,} rows to keep it fast.")

    numeric = [c for c in used if _is_num(data[c])]
    categorical = [c for c in used if c not in numeric]
    X = data[used].copy()
    for c in categorical:
        X[c] = _text(X[c])
    y = data[target]
    stratify = None
    pos = None
    if task == "classification":
        y = y.astype(str)
        counts = y.value_counts()
        if len(counts) < 2:
            raise ModelError(f"“{target}” has only one value here; there is nothing to predict.")
        if len(counts) > MAX_CLASSES:
            raise ModelError(f"“{target}” has {len(counts)} different values; at most {MAX_CLASSES} classes are supported. "
                             "Group rare categories first, or predict it as a number.")
        if counts.min() >= 2:
            stratify = y
        else:
            notes.append("Some classes have a single row, so the split could not keep class proportions (no stratification).")
        pos = counts.index[-1] if len(counts) == 2 else None
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=TEST_SIZE, random_state=SEED, stratify=stratify)

    results, fitted = [], {}
    for key, estimator in make_models(task).items():
        pipe = Pipeline([("prep", make_preprocess(numeric, categorical)), ("model", estimator)])
        pipe.fit(X_train, y_train)
        fitted[key] = pipe
        results.append({"key": key, "name": MODEL_NAMES[key], **_metrics(task, pipe, X_train, y_train, X_test, y_test, pos)})

    primary = "r2" if task == "regression" else "f1"
    best = max((r for r in results if r["key"] != "baseline"), key=lambda r: -math.inf if r[primary] is None else r[primary])
    for r in results:
        r["best"] = r["key"] == best["key"]
    importance = _importance(task, fitted[best["key"]], X_test, y_test, pos, used)
    details = _details(task, fitted[best["key"]], X_test, y_test)
    baseline = next(r for r in results if r["key"] == "baseline")
    warnings = _warnings(task, data, y, best, baseline, importance, pos, results)

    return {
        "task": task, "detectedTask": detected, "target": str(target), "features": [str(c) for c in used],
        "numeric": [str(c) for c in numeric], "categorical": [str(c) for c in categorical], "skipped": skipped,
        "rows": int(len(data)), "trainRows": int(len(X_train)), "testRows": int(len(X_test)),
        "positiveClass": pos, "classes": sorted(y.unique().tolist()) if task == "classification" else None,
        "models": results, "best": best["key"], "importance": importance, "details": details,
        "summary": _summary(task, target, best, baseline, pos), "weak": weak(task, best, baseline),
        "warnings": warnings, "notes": notes,
        "code": _code(target, used, numeric, categorical, task, sampled, stratify is not None, pos),
    }


def _metrics(task, pipe, X_train, y_train, X_test, y_test, pos):
    pred = pipe.predict(X_test)
    if task == "regression":
        return {"r2": _f(r2_score(y_test, pred)), "mae": _f(mean_absolute_error(y_test, pred)),
                "rmse": _f(math.sqrt(mean_squared_error(y_test, pred))), "trainScore": _f(r2_score(y_train, pipe.predict(X_train)))}
    def f1(truth, guess):
        if pos is not None:
            return f1_score(truth, guess, pos_label=pos, average="binary", zero_division=0)
        return f1_score(truth, guess, average="macro", zero_division=0)

    out = {"accuracy": _f(accuracy_score(y_test, pred)), "f1": _f(f1(y_test, pred)),
           "trainScore": _f(f1(y_train, pipe.predict(X_train)))}
    smallest = int(y_test.value_counts().min()) if y_test.nunique() > 1 else 0
    try:
        proba = pipe.predict_proba(X_test)
        classes = list(pipe.classes_)
        if pos is not None:
            out["rocAuc"] = _f(roc_auc_score(y_test == pos, proba[:, classes.index(pos)]))
        else:
            out["rocAuc"] = _f(roc_auc_score(y_test, proba, multi_class="ovr", average="macro", labels=classes))
    except ValueError:
        out["rocAuc"] = None  # e.g. a class missing from the test rows
    if out["rocAuc"] is not None and smallest:
        # Hanley & McNeil-style rough standard error: with few test rows, AUC wobbles a lot.
        out["rocAucSe"] = _f(math.sqrt(out["rocAuc"] * (1 - out["rocAuc"]) / smallest))
    return out


def _scorer(task, pos):
    if task == "regression":
        return "r2"
    if pos is not None:
        return make_scorer(f1_score, pos_label=pos, average="binary", zero_division=0)
    return make_scorer(f1_score, average="macro", zero_division=0)


def _importance(task, pipe, X_test, y_test, pos, used):
    Xs, ys = X_test, y_test
    if len(Xs) > IMPORTANCE_ROWS:
        Xs = X_test.sample(IMPORTANCE_ROWS, random_state=SEED)
        ys = y_test.loc[Xs.index]
    imp = permutation_importance(pipe, Xs, ys, scoring=_scorer(task, pos), n_repeats=5, random_state=SEED)
    order = np.argsort(-imp.importances_mean)
    return [{"feature": str(used[i]), "mean": _f(imp.importances_mean[i]), "std": _f(imp.importances_std[i])} for i in order]


def _details(task, pipe, X_test, y_test):
    pred = pipe.predict(X_test)
    if task == "regression":
        idx = np.arange(len(y_test))
        if len(idx) > POINTS:
            idx = np.random.default_rng(SEED).choice(idx, POINTS, replace=False)
        return {"points": [[_f(y_test.iloc[i]), _f(pred[i])] for i in idx]}
    labels = sorted(pd.unique(pd.concat([y_test, pd.Series(pred)])).tolist())
    if len(labels) > 10:
        return {"confusion": None}
    return {"confusion": {"labels": labels, "matrix": confusion_matrix(y_test, pred, labels=labels).tolist()}}


def weak(task, best, baseline):
    """True when the best model is not clearly better than guessing."""
    if task == "regression":
        return best["r2"] is None or best["r2"] < 0.1
    auc = best.get("rocAuc")
    if auc is not None and auc - 2 * (best.get("rocAucSe") or 0) < 0.55:
        return True  # not clearly above 0.5 given the size of the test set
    return (best["f1"] or 0) <= (baseline["f1"] or 0) + 0.05


def _summary(task, target, best, baseline, pos):
    if weak(task, best, baseline):
        auc = best.get("rocAuc")
        auc_text = f", ROC-AUC {auc:.2f} where 0.5 is guessing" if auc is not None else ""
        score = f"R² {best['r2']:.2f}" if task == "regression" else f"F1 {best['f1']:.2f}{auc_text}"
        return (f"No model predicts {target} much better than guessing from these columns: the best, {best['name'].lower()}, "
                f"reaches {score}. The columns may not hold the information, or there is too little data.")
    if task == "regression":
        return (f"{best['name']} predicts {target} best. On rows it never saw it explains {max(best['r2'], 0):.0%} of the "
                f"variation (R² {best['r2']:.2f}) and is typically off by {_s(best['mae'])} (MAE). Always guessing the "
                f"average would be off by {_s(baseline['mae'])}.")
    f1_what = f"F1 {best['f1']:.2f} for {target} = {pos}" if pos is not None else f"macro F1 {best['f1']:.2f}"
    return (f"{best['name']} predicts {target} best: {best['accuracy']:.0%} of unseen rows right ({f1_what}). "
            f"Always guessing the most common value would get {baseline['accuracy']:.0%} right.")


def _warnings(task, data, y, best, baseline, importance, pos, models):
    out = []
    n = len(data)
    if n < 100:
        out.append({"kind": "small", "text": f"Only {n} rows: the test set has about {round(n * TEST_SIZE)} rows, so scores can "
                                             "change a lot with a different split. Treat them as rough."})
    if task == "classification":
        share = y.value_counts(normalize=True)
        if share.min() < 0.1:
            out.append({"kind": "imbalance", "text": f"Class imbalance: “{share.idxmin()}” is only {share.min():.0%} of rows. "
                                                     "Accuracy looks good just by guessing the common class; judge by F1 and ROC-AUC."})
    score = best["r2"] if task == "regression" else best["accuracy"]
    base = baseline["r2"] if task == "regression" else baseline["accuracy"]
    top = importance[0] if importance else None
    if score is not None and score >= 0.98 and (base is None or score - base > 0.2):
        who = f" Most of it comes from “{top['feature']}”." if top else ""
        out.append({"kind": "leakage", "text": f"Suspiciously near-perfect score ({score:.3f}).{who} Check that no feature is "
                                               "derived from the target or only known after the outcome (data leakage)."})
    metric = "r2" if task == "regression" else "f1"
    label = "R²" if task == "regression" else "F1"
    for m in models:
        if m["key"] == "baseline" or m["trainScore"] is None or m[metric] is None:
            continue
        if m["trainScore"] - m[metric] > 0.15:
            out.append({"kind": "overfit", "text": f"{m['name']} scores {label} {m['trainScore']:.2f} on the training rows but "
                                                   f"{m[metric]:.2f} on the test rows: it memorises more than it generalises "
                                                   "(overfitting)."})
    return out


def _code(target, used, numeric, categorical, task, sampled, stratified, pos):
    q = repr
    lines = [
        "from sklearn.compose import ColumnTransformer",
        "from sklearn.dummy import DummyClassifier, DummyRegressor",
        "from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor",
        "from sklearn.impute import SimpleImputer",
        "from sklearn.linear_model import LinearRegression, LogisticRegression",
        "from sklearn import metrics",
        "from sklearn.inspection import permutation_importance",
        "from sklearn.model_selection import train_test_split",
        "from sklearn.pipeline import Pipeline",
        "from sklearn.preprocessing import OneHotEncoder, StandardScaler",
        "",
        f"target = {q(target)}",
        f"numeric = {q(numeric)}",
        f"categorical = {q(categorical)}",
        "data = df[numeric + categorical + [target]].dropna(subset=[target])",
    ]
    if sampled:
        lines.append(f"data = data.sample({MAX_ROWS}, random_state={SEED})")
    lines += [
        "X = data[numeric + categorical].copy()",
        "for c in categorical:",
        "    X[c] = X[c].astype('string').astype(object).where(X[c].notna(), np.nan)",
        "y = data[target]" + (".astype(str)" if task == "classification" else ""),
        f"X_train, X_test, y_train, y_test = train_test_split(X, y, test_size={TEST_SIZE}, random_state={SEED}"
        + (", stratify=y)" if stratified else ")"),
        "",
        "def preprocess():",
        "    parts = []",
        "    if numeric:",
        "        parts.append(('num', Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), numeric))",
        "    if categorical:",
        "        parts.append(('cat', Pipeline([('impute', SimpleImputer(strategy='most_frequent')),",
        "                                       ('onehot', OneHotEncoder(handle_unknown='infrequent_if_exist', max_categories=20))]),",
        "                      categorical))",
        "    return ColumnTransformer(parts)",
        "",
    ]
    if task == "regression":
        lines += [
            "models = {",
            "    'Baseline': DummyRegressor(strategy='mean'),",
            "    'Linear model': LinearRegression(),",
            f"    'Random forest': RandomForestRegressor(n_estimators=200, random_state={SEED}, n_jobs=-1),",
            "}",
            "fitted, scores = {}, {}",
            "for name, model in models.items():",
            "    pipe = fitted[name] = Pipeline([('prep', preprocess()), ('model', model)]).fit(X_train, y_train)",
            "    pred = pipe.predict(X_test)",
            "    scores[name] = metrics.r2_score(y_test, pred)",
            "    print(f\"{name}: R2={scores[name]:.4f} MAE={metrics.mean_absolute_error(y_test, pred):.4f}\")",
        ]
        scoring = "'r2'"
    else:
        f1 = (f"metrics.f1_score(y_test, pred, pos_label={q(pos)}, average='binary', zero_division=0)" if pos is not None
              else "metrics.f1_score(y_test, pred, average='macro', zero_division=0)")
        lines += [
            "models = {",
            "    'Baseline': DummyClassifier(strategy='most_frequent'),",
            "    'Linear model': LogisticRegression(max_iter=1000),",
            f"    'Random forest': RandomForestClassifier(n_estimators=200, random_state={SEED}, n_jobs=-1),",
            "}",
            "fitted, scores = {}, {}",
            "for name, model in models.items():",
            "    pipe = fitted[name] = Pipeline([('prep', preprocess()), ('model', model)]).fit(X_train, y_train)",
            "    pred = pipe.predict(X_test)",
            f"    scores[name] = {f1}",
            "    print(f\"{name}: accuracy={metrics.accuracy_score(y_test, pred):.4f} F1={scores[name]:.4f}\")",
        ]
        scoring = (f"metrics.make_scorer(metrics.f1_score, pos_label={q(pos)}, average='binary', zero_division=0)" if pos is not None
                   else "metrics.make_scorer(metrics.f1_score, average='macro', zero_division=0)")
    lines += [
        "",
        "best = max((n for n in scores if n != 'Baseline'), key=scores.get)",
        "print('Best:', best)",
        "# Which columns matter for the best model (permutation importance on the test rows)",
        f"imp = permutation_importance(fitted[best], X_test, y_test, scoring={scoring}, n_repeats=5, random_state={SEED})",
        "print(pd.Series(imp.importances_mean, index=X_test.columns).sort_values(ascending=False))",
    ]
    return "\n".join(lines)
