# Logic to store and compare the previous message with the current one
last_snap = None


def get_confirmation(current):
    global last_snap

    # If this is the first message of the day, store and exit
    if not last_snap:
        last_snap = current
        return None

    # Skip broken snapshots instead of crashing on division by zero.
    if not last_snap["price"] or not current["price"]:
        last_snap = current
        return None

    # Calculate Changes (Deltas)
    price_delta = abs(current["price"] - last_snap["price"]) / last_snap["price"]

    # Total Deltas
    bull_delta = current["bull_turn"] - last_snap["bull_turn"]
    bear_delta = current["bear_turn"] - last_snap["bear_turn"]

    # Options & Futures Totals Deltas
    opt_bull_delta = (current["index_opt_bull"] + current["stock_opt_bull"]) - (
        last_snap["index_opt_bull"] + last_snap["stock_opt_bull"]
    )
    fut_bull_delta = (current["index_fut_bull"] + current["stock_fut_bull"]) - (
        last_snap["index_fut_bull"] + last_snap["stock_fut_bull"]
    )

    opt_bear_delta = (current["index_opt_bear"] + current["stock_opt_bear"]) - (
        last_snap["index_opt_bear"] + last_snap["stock_opt_bear"]
    )
    fut_bear_delta = (current["index_fut_bear"] + current["stock_fut_bear"]) - (
        last_snap["index_fut_bear"] + last_snap["stock_fut_bear"]
    )

    # Index vs Stock Deltas
    idx_opt_bull_d = current["index_opt_bull"] - last_snap["index_opt_bull"]
    stk_opt_bull_d = current["stock_opt_bull"] - last_snap["stock_opt_bull"]
    idx_fut_bull_d = current["index_fut_bull"] - last_snap["index_fut_bull"]
    stk_fut_bull_d = current["stock_fut_bull"] - last_snap["stock_fut_bull"]

    idx_opt_bear_d = current["index_opt_bear"] - last_snap["index_opt_bear"]
    stk_opt_bear_d = current["stock_opt_bear"] - last_snap["stock_opt_bear"]
    idx_fut_bear_d = current["index_fut_bear"] - last_snap["index_fut_bear"]
    stk_fut_bear_d = current["stock_fut_bear"] - last_snap["stock_fut_bear"]

    # Bank Analysis
    banks = ["HDFC", "ICICI", "SBIN", "AXIS"]
    bull_statuses = [
        current["hdfc_bull"],
        current["icici_bull"],
        current["sbin_bull"],
        current["axis_bull"],
    ]
    bear_statuses = [
        current["hdfc_bear"],
        current["icici_bear"],
        current["sbin_bear"],
        current["axis_bear"],
    ]

    strong_list = [banks[i] for i, status in enumerate(bull_statuses) if status]
    weak_list = [banks[i] for i, status in enumerate(bear_statuses) if status]

    bull_banks_count = len(strong_list)
    bear_banks_count = len(weak_list)

    # 1. BULLISH BREAKOUT CONFIRMATION
    if price_delta < 0.003 and bull_delta > 12.0 and bull_banks_count >= 2:
        outlier_str = ""
        if bull_banks_count == 4:
            outlier_str = " (All Strong ðŸš€)"
        else:
            others = [b for b in banks if b not in strong_list]
            actual_weak = [b for b in others if b in weak_list]
            if actual_weak:
                outlier_str = f" (Weak: {', '.join(actual_weak)})"
            elif others:
                outlier_str = f" (Neutral: {', '.join(others)})"

        last_snap = current
        return (
            "ðŸŸ¢ ðŸš€ **15M BULLISH BREAKOUT CONFIRMED** ðŸŸ¢\n\n"
            "Smart Money adding massive Longs.\n"
            f"ðŸ”¥ **Total Bullish Turn Delta: +{bull_delta:.1f}Cr**\n"
            f"   - ðŸ’Ž Options: +{opt_bull_delta:.1f}Cr (index-{idx_opt_bull_d:.1f}cr+stock-{stk_opt_bull_d:.1f}cr)\n"
            f"   - âš¡ Futures: +{fut_bull_delta:.1f}Cr (index-{idx_fut_bull_d:.1f}cr+stock-{stk_fut_bull_d:.1f}cr)\n"
            f"ðŸ¦ Strong Banks: {bull_banks_count}/4{outlier_str}"
        )

    # 2. BEARISH BREAKDOWN CONFIRMATION
    if price_delta < 0.003 and bear_delta > 12.0 and bear_banks_count >= 2:
        outlier_str = ""
        if bear_banks_count == 4:
            outlier_str = " (All Weak ðŸ“‰)"
        else:
            others = [b for b in banks if b not in weak_list]
            actual_strong = [b for b in others if b in strong_list]
            if actual_strong:
                outlier_str = f" (Strong: {', '.join(actual_strong)})"
            elif others:
                outlier_str = f" (Neutral: {', '.join(others)})"

        last_snap = current
        return (
            "ðŸ”´ ðŸ“‰ **15M BEARISH BREAKDOWN CONFIRMED** ðŸ”´\n\n"
            "Smart Money adding massive Shorts.\n"
            f"ðŸ”¥ **Total Bearish Turn Delta: +{bear_delta:.1f}Cr**\n"
            f"   - ðŸ’Ž Options: +{opt_bear_delta:.1f}Cr (index-{idx_opt_bear_d:.1f}cr+stock-{stk_opt_bear_d:.1f}cr)\n"
            f"   - âš¡ Futures: +{fut_bear_delta:.1f}Cr (index-{idx_fut_bear_d:.1f}cr+stock-{stk_fut_bear_d:.1f}cr)\n"
            f"ðŸ¦ Weak Banks: {bear_banks_count}/4{outlier_str}"
        )

    # 3. SUPPORT CONFIRMATION (Bullish Support)
    if current["price"] < last_snap["price"] and current["put_wr_cr"] > (last_snap["put_wr_cr"] + 7.0):
        support_delta = current["put_wr_cr"] - last_snap["put_wr_cr"]
        last_snap = current
        return (
            "ðŸŸ¢ ðŸ›¡ï¸ **15M SUPPORT CONFIRMED** ðŸŸ¢\n\n"
            "Price dropped, but NEW Put Writing defending current zone.\n"
            f"ðŸŸ¢ ðŸ›¡ï¸ Support Delta: +{support_delta:.1f}Cr (Put Writing)"
        )

    # 4. RESISTANCE CONFIRMATION (Bearish Resistance)
    if current["price"] > last_snap["price"] and current["call_wr_cr"] > (last_snap["call_wr_cr"] + 7.0):
        res_delta = current["call_wr_cr"] - last_snap["call_wr_cr"]
        last_snap = current
        return (
            "ðŸ”´ ðŸ§± **15M RESISTANCE CONFIRMED** ðŸ”´\n\n"
            "Price rose, but NEW Call Writing capping the upside.\n"
            f"ðŸ”´ ðŸ§± Resistance Delta: +{res_delta:.1f}Cr (Call Writing)"
        )

    # 5. CONSOLIDATION ALERT (Neutral)
    turn_diff = abs(current["bull_turn"] - current["bear_turn"])
    if turn_diff < 10.0 and price_delta < 0.001:
        last_snap = current
        return (
            "âš ï¸ **15M CONSOLIDATION ALERT** âš ï¸\n\n"
            "Range-bound fighting between Call & Put sellers.\n"
            "Avoid aggressive breakouts right now."
        )

    # Update for next comparison
    last_snap = current
    return None
