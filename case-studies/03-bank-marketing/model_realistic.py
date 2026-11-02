import numpy as np
import pandas as pd

df = pd.read_csv('bank-full.csv', sep=';')

# Step 1: Added column 'contacted_before' = CASE WHEN pdays = -1 THEN 'no' ELSE 'yes' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['contacted_before'] = con.sql("""SELECT (CASE WHEN pdays = -1 THEN 'no' ELSE 'yes' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()
# Step 2: Replaced 36954 occurrence(s) of '-1.0' with missing (NaN) in 'pdays'.
df['pdays'] = df['pdays'].replace(-1.0, np.nan)
df = df.reset_index(drop=True)

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn import metrics
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

target = 'y'
numeric = ['age', 'balance', 'day', 'campaign', 'pdays', 'previous']
categorical = ['job', 'marital', 'education', 'default', 'housing', 'loan', 'contact', 'month', 'poutcome', 'contacted_before']
data = df[numeric + categorical + [target]].dropna(subset=[target])
X = data[numeric + categorical].copy()
for c in categorical:
    X[c] = X[c].astype('string').astype(object).where(X[c].notna(), np.nan)
y = data[target].astype(str)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

def preprocess():
    parts = []
    if numeric:
        parts.append(('num', Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), numeric))
    if categorical:
        parts.append(('cat', Pipeline([('impute', SimpleImputer(strategy='most_frequent')),
                                       ('onehot', OneHotEncoder(handle_unknown='infrequent_if_exist', max_categories=20))]),
                      categorical))
    return ColumnTransformer(parts)

models = {
    'Baseline': DummyClassifier(strategy='most_frequent'),
    'Linear model': LogisticRegression(max_iter=1000),
    'Random forest': RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1),
}
fitted, scores = {}, {}
for name, model in models.items():
    pipe = fitted[name] = Pipeline([('prep', preprocess()), ('model', model)]).fit(X_train, y_train)
    pred = pipe.predict(X_test)
    scores[name] = metrics.f1_score(y_test, pred, pos_label='yes', average='binary', zero_division=0)
    print(f"{name}: accuracy={metrics.accuracy_score(y_test, pred):.4f} F1={scores[name]:.4f}")

best = max((n for n in scores if n != 'Baseline'), key=scores.get)
print('Best:', best)
# Which columns matter for the best model (permutation importance on the test rows)
imp = permutation_importance(fitted[best], X_test, y_test, scoring=metrics.make_scorer(metrics.f1_score, pos_label='yes', average='binary', zero_division=0), n_repeats=5, random_state=42)
print(pd.Series(imp.importances_mean, index=X_test.columns).sort_values(ascending=False))
