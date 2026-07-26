def apply_conditions(data, conditions):

    for c in conditions:
        key = c["key"]
        operator = c["operator"]
        value = c["value"]

        stock_value = data.get(key)

        if stock_value is None:
            return False

        if operator == ">":
            if not stock_value > value:
                return False
        elif operator == "<":
            if not stock_value < value:
                return False
        elif operator == ">=":
            if not stock_value >= value:
                return False
        elif operator == "<=":
            if not stock_value <= value:
                return False
        elif operator == "==":
            if not stock_value == value:
                return False

    return True


def run_stage(stocks, stage_conditions, snapshot):

    filtered = []

    for s in stocks:

        data = snapshot.get(s)

        if not data:
            continue

        if apply_conditions(data, stage_conditions):
            filtered.append({
                "symbol": s
            })

    return filtered