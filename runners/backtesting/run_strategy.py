from .strategy import StrategyEngine
from .config import STRATEGY_CONFIG
import polars as pl

def run_strategy_on_df(df: pl.DataFrame, config=STRATEGY_CONFIG) -> pl.DataFrame:
    """
    Run the full strategy on a Polars DataFrame.

    Parameters:
    -----------
    df : pl.DataFrame
        Must contain columns: date, open, high, low, close, volume
    config : dict
        Strategy configuration including conditions, stoploss%, trailing%, target%, quantity, max capital, max cycles

    Returns:
    --------
    pl.DataFrame
        Original dataframe with additional columns:
        - Signal : BUY/SELL
        - EntryPrice
        - ExitPrice
        - StopLoss
        - Target
    """
    # Ensure datetime is naive (no timezone)
    df = df.with_columns(pl.col("date").dt.replace_time_zone(None))
    
    # Initialize StrategyEngine
    engine = StrategyEngine(df, config)
    
    # Run strategy (indicators + conditions + trade engine)
    result_df = engine.run_strategy()
    
    return result_df
