import numpy as np
import pandas as pd

df = pd.read_csv('day.csv')

# Step 1: Converted 1 column to dates.
for col in ['dteday']:
    df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=False, format='mixed')
# Step 2: Added column 'weather' = CASE weathersit WHEN 1 THEN 'clear' WHEN 2 THEN 'mist / cloudy' WHEN 3 THEN 'light rain / snow' ELSE 'heavy rain / snow' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['weather'] = con.sql("""SELECT (CASE weathersit WHEN 1 THEN 'clear' WHEN 2 THEN 'mist / cloudy' WHEN 3 THEN 'light rain / snow' ELSE 'heavy rain / snow' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()
# Step 3: Added column 'day_type' = CASE WHEN workingday = 1 THEN 'working day' ELSE 'weekend / holiday' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['day_type'] = con.sql("""SELECT (CASE WHEN workingday = 1 THEN 'working day' ELSE 'weekend / holiday' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()
# Step 4: Added column 'year' = CASE yr WHEN 0 THEN '2011' ELSE '2012' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['year'] = con.sql("""SELECT (CASE yr WHEN 0 THEN '2011' ELSE '2012' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()
# Step 5: Added column 'temp_c' = ROUND(temp * 47 - 8, 1).
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['temp_c'] = con.sql("""SELECT (ROUND(temp * 47 - 8, 1)) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()
# Step 6: Added 1 column from dteday: dteday_weekday.
df['dteday_weekday'] = df['dteday'].dt.day_name().astype(pd.CategoricalDtype(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], ordered=True))
# Step 7: Dropped 9 column(s): instant, season, yr, mnth, weathersit, temp, atemp, hum, windspeed.
df = df.drop(columns=['instant', 'season', 'yr', 'mnth', 'weathersit', 'temp', 'atemp', 'hum', 'windspeed'])
df = df.reset_index(drop=True)

from statsmodels.tsa.holtwinters import ExponentialSmoothing

periods = df['dteday'].dt.to_period('D')
series = df.groupby(periods)['cnt'].agg('sum')
series = series.reindex(pd.period_range(series.index.min(), series.index.max(), freq=series.index.freq))
series = series.fillna(0)
y = series.to_numpy(dtype=float)

def fit(values):
    model = ExponentialSmoothing(values, trend=None, damped_trend=False, seasonal='add',
                                 seasonal_periods=7, initialization_method='estimated')
    return model.fit(optimized=True)

model = fit(y)
forecast = model.forecast(7)
sims = model.simulate(7, repetitions=1000, error='add', anchor='end', rng=np.random.default_rng(42))
forecast, sims = np.maximum(forecast, 0), np.maximum(sims, 0)  # values can't be negative
future = pd.period_range(series.index[-1] + 1, periods=7, freq=series.index.freq)
print(pd.DataFrame({'forecast': forecast, 'low80': np.percentile(sims, 10, axis=1),
                    'high80': np.percentile(sims, 90, axis=1)}, index=future))

# Backtest: forecast the last 7 periods from the ones before
bt = fit(y[:-7]).forecast(7)
print('backtest MAE:', np.mean(np.abs(y[-7:] - bt)))
