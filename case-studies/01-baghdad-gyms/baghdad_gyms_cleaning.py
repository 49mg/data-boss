# Cleaning steps exported from Data Boss for Baghdad_gym_dataset.csv
import numpy as np
import pandas as pd

df = pd.read_csv('Baghdad_gym_dataset.csv')

# Step 1: Dropped 5 column(s): state, countryCode, categories/1, categories/2, categoryName.
df = df.drop(columns=['state', 'countryCode', 'categories/1', 'categories/2', 'categoryName'])

# Step 2: Replaced 1 occurrence(s) of 'الكمالية،' with 'Baghdad' in 'city'.
df['city'] = df['city'].replace('الكمالية،', 'Baghdad')

# Step 3: Dropped 10 rows with missing values in totalScore.
df = df.dropna(subset=['totalScore'])

# Step 4: Added column 'has_website' = CASE WHEN website IS NULL THEN 'no' ELSE 'yes' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['has_website'] = con.sql("""SELECT (CASE WHEN website IS NULL THEN 'no' ELSE 'yes' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()

# Step 5: Added column 'site_type' = CASE WHEN website IS NULL THEN 'none' WHEN website ILIKE '%facebook%' OR website ILIKE '%instagram%' THEN 'social page' ELSE 'own website' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['site_type'] = con.sql("""SELECT (CASE WHEN website IS NULL THEN 'none' WHEN website ILIKE '%facebook%' OR website ILIKE '%instagram%' THEN 'social page' ELSE 'own website' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()

# Step 6: Added column 'has_phone' = CASE WHEN phone IS NULL THEN 'no' ELSE 'yes' END.
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['has_phone'] = con.sql("""SELECT (CASE WHEN phone IS NULL THEN 'no' ELSE 'yes' END) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()

# Step 7: Binned reviewsCount into 4 custom ranges as review_band.
df['review_band'] = pd.cut(df['reviewsCount'], bins=[0.0, 5.0, 20.0, 100.0, float('inf')], labels=['0–5', '5–20', '20–100', '> 100'], include_lowest=True)

# Step 8: Added column 'adjusted_rating' = ROUND((totalScore * reviewsCount + 4.31 * 12) / (reviewsCount + 12), 2).
import duckdb
con = duckdb.connect()
con.register('data', df.assign(__databoss_row=range(len(df))))
df['adjusted_rating'] = con.sql("""SELECT (ROUND((totalScore * reviewsCount + 4.31 * 12) / (reviewsCount + 12), 2)) AS v FROM data ORDER BY __databoss_row""").df()['v'].to_numpy()

df = df.reset_index(drop=True)
df.to_csv('Baghdad_gym_dataset_cleaned.csv', index=False)
