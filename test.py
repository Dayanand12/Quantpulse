# test_imports.py
import sys
import os

# Print current working directory and Python path
print("Current working directory:", os.getcwd())
print("sys.path:")
for p in sys.path:
    print("  ", p)

# Try importing IndicatorCalculator
try:
    from backtest.indicators import IndicatorCalculator
    print("\n✅ Successfully imported IndicatorCalculator!")
    
    # Quick test of EMA method
    import polars as pl
    import numpy as np
    import talib

    df = pl.DataFrame({
        "close": np.random.rand(10)
    })

    ema_result = IndicatorCalculator.ema(df, period=3)
    print("EMA output:", ema_result)

except ModuleNotFoundError as e:
    print("\n❌ Import failed:", e)
except Exception as e:
    print("\n⚠️ Other error:", e)


