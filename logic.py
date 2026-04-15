# Logic to store and compare the previous message with the current one
last_snap = None
last_trade_day = None


def reset_snapshot(trade_day=None):
    global last_snap, last_trade_day
    last_snap = None
    last_trade_day = trade_day


def sync_trade_day(trade_day):
    global last_trade_day

    if not trade_day:
        return False

    if last_trade_day is None:
        last_trade_day = trade_day
        return False

    if trade_day != last_trade_day:
        reset_snapshot(trade_day)
        return True

    return False


def get_confirmation(current, return_debug=False, trade_day=None):
    global last_snap, last_trade_day

    debug = {
        "reason": "no_match",
        "trade_day": trade_day,
        "price_delta": 0.0,
        "bull_delta": 0.0,
        "bear_delta": 0.0,
        "bull_banks_count": 0,
        "bear_banks_count": 0,
        "turn_diff": 0.0,
        "price_ok": False,
        "bull_flow_ok": False,
        "bear_flow_ok": False,
        "bull_banks_ok": False,
        "bear_banks_ok": False,
        "support_ok": False,
        "resistance_ok": False,
        "consolidation_ok": False,
    }

    if trade_day and last_trade_day is None:
        last_trade_day = trade_day

    if not last_snap:
        last_snap = current
        debug["reason"] = "baseline_snapshot_saved"
        return (None, debug) if return_debug else None

    if not last_snap["price"] or not current["price"]:
        last_snap = current
        debug["reason"] = "missing_price"
        return (None, debug) if return_debug else None

    price_delta = abs(current["price"] - last_snap["price"]) / last_snap["price"]

    bull_delta = current["bull_turn"] - last_snap["bull_turn"]
    bear_delta = current["bear_turn"] - last_snap["bear_turn"]

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

    idx_opt_bull_d = current["index_opt_bull"] - last_snap["index_opt_bull"]
    stk_opt_bull_d = current["stock_opt_bull"] - last_snap["stock_opt_bull"]
    idx_fut_bull_d = current["index_fut_bull"] - last_snap["index_fut_bull"]
    stk_fut_bull_d = current["stock_fut_bull"] - last_snap["stock_fut_bull"]

    idx_opt_bear_d = current["index_opt_bear"] - last_snap["index_opt_bear"]
    stk_opt_bear_d = current["stock_opt_bear"] - last_snap["stock_opt_bear"]
    idx_fut_bear_d = current["index_fut_bear"] - last_snap["index_fut_bear"]
    stk_fut_bear_d = current["stock_fut_bear"] - last_snap["stock_fut_bear"]

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

    debug.update(
        {
            "price_delta": price_delta,
            "bull_delta": bull_delta,
            "bear_delta": bear_delta,
            "bull_banks_count": bull_banks_count,
            "bear_banks_count": bear_banks_count,
            "price_ok": price_delta < 0.003,
            "bull_flow_ok": bull_delta > 12.0,
            "bear_flow_ok": bear_delta > 12.0,
            "bull_banks_ok": bull_banks_count >= 2,
            "bear_banks_ok": bear_banks_count >= 2,
            "support_ok": (
                current["price"] < last_snap["price"]
                and current["put_wr_cr"] > (last_snap["put_wr_cr"] + 7.0)
            ),
            "resistance_ok": (
                current["price"] > last_snap["price"]
                and current["call_wr_cr"] > (last_snap["call_wr_cr"] + 7.0)
            ),
        }
    )

    if price_delta < 0.003 and bull_delta > 12.0 and bull_banks_count >= 2:
        outlier_str = ""
        if bull_banks_count == 4:
            outlier_str = " (All Strong)"
        else:
            others = [b for b in banks if b not in strong_list]
            actual_weak = [b for b in others if b in weak_list]
            if actual_weak:
                outlier_str = f" (Weak: {', '.join(actual_weak)})"
            elif others:
                outlier_str = f" (Neutral: {', '.join(others)})"

        last_snap = current
        debug["reason"] = "bullish_breakout"
        message = (
            "15M BULLISH BREAKOUT CONFIRMED\n\n"
            "Smart Money adding massive Longs.\n"
            f"Total Bullish Turn Delta: +{bull_delta:.1f}Cr\n"
            f"   - Options: +{opt_bull_delta:.1f}Cr (index-{idx_opt_bull_d:.1f}cr+stock-{stk_opt_bull_d:.1f}cr)\n"
            f"   - Futures: +{fut_bull_delta:.1f}Cr (index-{idx_fut_bull_d:.1f}cr+stock-{stk_fut_bull_d:.1f}cr)\n"
            f"Strong Banks: {bull_banks_count}/4{outlier_str}"
        )
        return (message, debug) if return_debug else message

    if price_delta < 0.003 and bear_delta > 12.0 and bear_banks_count >= 2:
        outlier_str = ""
        if bear_banks_count == 4:
            outlier_str = " (All Weak)"
        else:
            others = [b for b in banks if b not in weak_list]
            actual_strong = [b for b in others if b in strong_list]
            if actual_strong:
                outlier_str = f" (Strong: {', '.join(actual_strong)})"
            elif others:
                outlier_str = f" (Neutral: {', '.join(others)})"

        last_snap = current
        debug["reason"] = "bearish_breakdown"
        message = (
            "15M BEARISH BREAKDOWN CONFIRMED\n\n"
            "Smart Money adding massive Shorts.\n"
            f"Total Bearish Turn Delta: +{bear_delta:.1f}Cr\n"
            f"   - Options: +{opt_bear_delta:.1f}Cr (index-{idx_opt_bear_d:.1f}cr+stock-{stk_opt_bear_d:.1f}cr)\n"
            f"   - Futures: +{fut_bear_delta:.1f}Cr (index-{idx_fut_bear_d:.1f}cr+stock-{stk_fut_bear_d:.1f}cr)\n"
            f"Weak Banks: {bear_banks_count}/4{outlier_str}"
        )
        return (message, debug) if return_debug else message

    if current["price"] < last_snap["price"] and current["put_wr_cr"] > (last_snap["put_wr_cr"] + 7.0):
        support_delta = current["put_wr_cr"] - last_snap["put_wr_cr"]
        price_change = current["price"] - last_snap["price"]
        last_snap = current
        debug["reason"] = "support_confirmed"
        message = (
            "15M SUPPORT CONFIRMED\n\n"
            "Price dipped but fresh Put Writing emerged.\n"
            f"PUT_WR Delta: +{support_delta:.1f}Cr\n"
            f"Price Change: {price_change:+.1f} pts"
        )
        return (message, debug) if return_debug else message

    if current["price"] > last_snap["price"] and current["call_wr_cr"] > (last_snap["call_wr_cr"] + 7.0):
        res_delta = current["call_wr_cr"] - last_snap["call_wr_cr"]
        price_change = current["price"] - last_snap["price"]
        last_snap = current
        debug["reason"] = "resistance_confirmed"
        message = (
            "15M RESISTANCE CONFIRMED\n\n"
            "Price rose but fresh Call Writing emerged.\n"
            f"CALL_WR Delta: +{res_delta:.1f}Cr\n"
            f"Price Change: {price_change:+.1f} pts"
        )
        return (message, debug) if return_debug else message

    turn_diff = abs(current["bull_turn"] - current["bear_turn"])
    debug["turn_diff"] = turn_diff
    debug["consolidation_ok"] = turn_diff < 10.0 and price_delta < 0.001
    if turn_diff < 10.0 and price_delta < 0.001:
        last_snap = current
        debug["reason"] = "consolidation_alert"
        message = (
            "15M CONSOLIDATION ALERT\n\n"
            "Both sides are balanced.\n"
            f"Bull-Bear Difference: {turn_diff:.1f}Cr\n"
            f"Price Change: {price_delta * 100:.2f}%\n\n"
            "No directional trade yet.\n"
            "Wait for fresh breakout, breakdown, support, or resistance confirmation."
        )
        return (message, debug) if return_debug else message

    if price_delta >= 0.003:
        debug["reason"] = "price_moved_too_much"
    elif bull_delta <= 12.0 and bear_delta <= 12.0:
        debug["reason"] = "flow_delta_too_small"
    elif bull_delta > 12.0 and bull_banks_count < 2:
        debug["reason"] = "bullish_banks_not_confirmed"
    elif bear_delta > 12.0 and bear_banks_count < 2:
        debug["reason"] = "bearish_banks_not_confirmed"
    else:
        debug["reason"] = "conditions_not_aligned"

    last_snap = current
    return (None, debug) if return_debug else None
