import pandas as pd
import os

df = pd.read_parquet('data/processed/fused.parquet')
df = df.sort_values('timestamp').reset_index(drop=True)

print('Data Summary:')
print(f'  Total samples: {len(df)}')
print(f'  Date range: {df["timestamp"].min()} to {df["timestamp"].max()}')
print(f'  Soft range: {df["soft"].min():.1f} to {df["soft"].max():.1f}')
print(f'  Hard range: {df["hard"].min():.1f} to {df["hard"].max():.1f}')

df['soft_p99'] = df['soft'].rolling(1000).quantile(0.99)
df['hard_p99'] = df['hard'].rolling(1000).quantile(0.99)
df['is_flare'] = ((df['soft'] > df['soft_p99']) & (df['hard'] > df['hard_p99'])).astype(int)
print(f'Flare periods detected: {df["is_flare"].sum()}')

print()
print('Data files:')
for root, dirs, files in os.walk('data'):
    for f in files:
        if f.endswith(('.zip', '.parquet', '.csv', '.json')):
            path = os.path.join(root, f)
            size = os.path.getsize(path) / 1024 / 1024
            print(f'  {os.path.relpath(path)}: {size:.1f} MB')