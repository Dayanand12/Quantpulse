from backend.utils.market_data import get_live_data

def apply_conditions(stock, conditions):
    data = get_live_data(stock)

    for c in conditions:
        expr = c['condition']

        try:
            if not eval(expr, {}, data):
                return False
        except Exception:
            return False

    return True


def run_stage(stocks, stage_conditions):
    return [s for s in stocks if apply_conditions(s, stage_conditions)]