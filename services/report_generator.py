# backend/report_generator.py

import os
import datetime as dt

def generate_report(data, index_symbol):

    os.makedirs("reports", exist_ok=True)

    filename = f"reports/{index_symbol}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(filename, "w") as f:
        f.write("=== MARKET ANALYSIS REPORT ===\n")
        for k, v in data.items():
            f.write(f"{k}: {v}\n")

    return filename