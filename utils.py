import re


def get_value_from_text(label, text):
    # Search for "Bullish Turn: 123.4Cr" or "Bearish Turn: 56.7L" or "0"
    matches = re.search(rf"{label}:\s*([\d.]+)(Cr|L)?", text)
    if not matches:
        return 0.0
    val_str = matches.group(1)
    unit = matches.group(2) if len(matches.groups()) > 1 else ""
    value = float(val_str)
    if unit == "Cr":
        return value
    elif unit == "L":
        return value / 100
    return value


def get_pair_value_from_text(text, left_label="Bull", right_label="Bear"):
    matches = re.search(
        rf"{left_label}:\s*([\d.]+)(Cr|L)?\s*\|\s*{right_label}:\s*([\d.]+)(Cr|L)?",
        text,
    )
    if not matches:
        return None, None

    left_value = float(matches.group(1))
    left_unit = matches.group(2) or ""
    right_value = float(matches.group(3))
    right_unit = matches.group(4) or ""

    if left_unit == "L":
        left_value /= 100
    if right_unit == "L":
        right_value /= 100

    return left_value, right_value


def get_future_component(text, type_list):
    total = 0.0
    try:
        if "---- FUTURES FLOW ----" in text:
            fut_section = text.split("---- FUTURES FLOW ----", 1)[1]
            for label in type_list:
                matches = re.findall(rf"{re.escape(label)}.*?\(([\d.]+)(Cr|L)\)", fut_section)
                for val_str, unit in matches:
                    val = float(val_str)
                    total += val if unit == "Cr" else val / 100
    except Exception:
        pass
    return total


def get_option_bias_line(section):
    match = re.search(r"Option Bias:\s*([^\n\r]+)", section, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def has_bullish_bias(section):
    option_bias = get_option_bias_line(section)
    return "BULLISH" in option_bias and "BEARISH" not in option_bias


def has_bearish_bias(section):
    option_bias = get_option_bias_line(section)
    return "BEARISH" in option_bias and "BULLISH" not in option_bias


def parse_15m_data(text):
    # To handle HTML and raw text
    text = text.replace("<pre>", "").replace("<br>", "\n").replace("</pre>", "")

    data = {
        "price": 0.0,
        "index_opt_bull": 0.0,
        "index_opt_bear": 0.0,
        "index_fut_bull": 0.0,
        "index_fut_bear": 0.0,
        "stock_opt_bull": 0.0,
        "stock_opt_bear": 0.0,
        "stock_fut_bull": 0.0,
        "stock_fut_bear": 0.0,
        "put_wr_cr": 0.0,
        "call_wr_cr": 0.0,
        "hdfc_bull": False,
        "icici_bull": False,
        "sbin_bull": False,
        "axis_bull": False,
        "hdfc_bear": False,
        "icici_bear": False,
        "sbin_bear": False,
        "axis_bear": False,
    }

    price_match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    if not price_match:
        price_match = re.search(r"BANKNIFTY \(([\d.]+)\)\s+OPTIONS FLOW", text)
    if price_match:
        data["price"] = float(price_match.group(1))

    put_wr_matches = re.findall(r"PUT_WR\s+\d+\(([\d.]+)(Cr|L)\)", text)
    data["put_wr_cr"] = sum(
        [(float(v) if u == "Cr" else float(v) / 100) for v, u in put_wr_matches]
    )

    call_wr_matches = re.findall(r"CALL_WR\s+\d+\(([\d.]+)(Cr|L)\)", text)
    data["call_wr_cr"] = sum(
        [(float(v) if u == "Cr" else float(v) / 100) for v, u in call_wr_matches]
    )

    sections = re.split(r"(?=(?:BANKNIFTY|HDFCBANK|ICICIBANK|AXISBANK|SBIN)\s*\()", text)

    for section in sections[1:]:
        lines = section.split("\n")
        symbol_line = lines[0] if lines else ""

        opt_bull = get_value_from_text("Bullish Turn", section)
        opt_bear = get_value_from_text("Bearish Turn", section)
        if opt_bull == 0.0 and opt_bear == 0.0:
            pair_bull, pair_bear = get_pair_value_from_text(section, "Bull", "Bear")
            if pair_bull is not None:
                opt_bull, opt_bear = pair_bull, pair_bear

        fut_bull = get_future_component(section, ["FUTURE_BUY", "FUTURE_SC"])
        fut_bear = get_future_component(section, ["FUTURE_SELL", "FUTURE_UNW"])
        if fut_bull == 0.0 and fut_bear == 0.0:
            fut_bull = get_future_component(section, ["F_BUY", "F_SC"])
            fut_bear = get_future_component(section, ["F_SEL", "F_UNW"])

        if "BANKNIFTY" in symbol_line:
            data["index_opt_bull"] = opt_bull
            data["index_opt_bear"] = opt_bear
            data["index_fut_bull"] = fut_bull
            data["index_fut_bear"] = fut_bear
        elif any(s in symbol_line for s in ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK"]):
            data["stock_opt_bull"] += opt_bull
            data["stock_opt_bear"] += opt_bear
            data["stock_fut_bull"] += fut_bull
            data["stock_fut_bear"] += fut_bear

            if "HDFCBANK" in symbol_line:
                data["hdfc_bull"] = has_bullish_bias(section)
                data["hdfc_bear"] = has_bearish_bias(section)
            elif "ICICIBANK" in symbol_line:
                data["icici_bull"] = has_bullish_bias(section)
                data["icici_bear"] = has_bearish_bias(section)
            elif "SBIN" in symbol_line:
                data["sbin_bull"] = has_bullish_bias(section)
                data["sbin_bear"] = has_bearish_bias(section)
            elif "AXISBANK" in symbol_line:
                data["axis_bull"] = has_bullish_bias(section)
                data["axis_bear"] = has_bearish_bias(section)

    data["bull_turn"] = (
        data["index_opt_bull"]
        + data["index_fut_bull"]
        + data["stock_opt_bull"]
        + data["stock_fut_bull"]
    )
    data["bear_turn"] = (
        data["index_opt_bear"]
        + data["index_fut_bear"]
        + data["stock_opt_bear"]
        + data["stock_fut_bear"]
    )

    return data
