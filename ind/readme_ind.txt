# Call indicators with default parameters
print("RSI:", ind.rsi(df).to_list())  # Default period=14 → You can change it by passing period=21, period=7, etc.
print("MACD:", ind.macd(df))  # Default fast=12, slow=26, signal=9 → Override with macd(df, fast=8, slow=21, signal=5)
print("Bollinger Bands:", ind.bollinger_bands(df))  # Default period=20, std=2 → Override with bollinger_bands(df, period=14, std=2.5)
print("VWAP:", ind.vwap(df).to_list())  # VWAP is cumulative → No main parameter, but you must ensure df has 'volume'
print("ADX:", ind.adx(df).to_list())  # Default period=14 → Override with adx(df, period=10)
print("EMV:", ind.emv(df).to_list())  # Default period=14 → Override with emv(df, period=20)

# Override parameters easily
print("Custom RSI:", ind.rsi(df, period=21).to_list())  # Example: RSI with 21-period instead of 14
print("Custom MACD:", ind.macd(df, fast=8, slow=21, signal=5))  # Example: Faster MACD settings
print("Custom Bollinger Bands:", ind.bollinger_bands(df, period=14, std=2.5))  # Example: Narrower period, higher deviation
print("Custom ADX:", ind.adx(df, period=10).to_list())  # Example: Shorter ADX period
print("Custom EMV:", ind.emv(df, period=20).to_list())  # Example: Longer EMV period
