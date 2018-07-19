import pandas as pd

print('Reading data')
data = pd.read_csv('data/weather_yvr_messy.csv')

print('Standardizing data')
data['Conditions'] = data['Conditions'].str.lower().str.strip()

print('Saving output')
data.to_csv('data/weather_yvr_cleaned.csv', index=False)