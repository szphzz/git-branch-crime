import pandas as pd
from cleaning_eda import inspect_data

url = "https://data.sfgov.org/resource/tkzw-k3nq.csv?$limit=1000"

tree_df = pd.read_csv(url)

inspect_data(tree_df)

print("\nSample rows:")
print(tree_df.head())

print("\nUnique values per column:")
print(tree_df.nunique().sort_values())

print("\nColumns with missing values:")
missing = tree_df.isna().sum()
print(missing[missing > 0].sort_values(ascending=False))



