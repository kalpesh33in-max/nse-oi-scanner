# Logic to store and compare the previous message with the current one
last_snap = None

def get_confirmation(current):
    global last_snap
    
    # If this is the first message of the day, store and exit
    if not last_snap:
        last_snap = current
        return None

    # Calculate Changes (Deltas)
    price_delta = abs(current['price'] - last_snap['price']) / last_snap['price']
    bull_delta = current['bull_turn'] - last_snap['bull_turn']
    bear_delta = current['bear_turn'] - last_snap['bear_turn']
    
    # Count Bullish and Bearish Banks
    bull_banks = [current['hdfc_bull'], current['icici_bull'], current['sbin_bull'], current['axis_bull']].count(True)
    bear_banks = [current['hdfc_bear'], current['icici_bear'], current['sbin_bear'], current['axis_bear']].count(True)

    # 1. BULLISH BREAKOUT CONFIRMATION
    if price_delta < 0.001 and bull_delta > 30.0 and bull_banks >= 2:
        last_snap = current
        return "🟢 🚀 **15M BULLISH BREAKOUT CONFIRMED** 🟢\n\nSmart Money adding massive Longs while Price is Flat.\n🟢 🔥 Bullish Turn Delta: +{:.1f}Cr\n🏦 Strong Banks: {}/4".format(bull_delta, bull_banks)

    # 2. BEARISH BREAKDOWN CONFIRMATION
    if price_delta < 0.001 and bear_delta > 30.0 and bear_banks >= 2:
        last_snap = current
        return "🔴 📉 **15M BEARISH BREAKDOWN CONFIRMED** 🔴\n\nSmart Money adding massive Shorts while Price is Flat.\n🔴 🔥 Bearish Turn Delta: +{:.1f}Cr\n🏦 Weak Banks: {}/4".format(bear_delta, bear_banks)

    # 3. SUPPORT CONFIRMATION (Bullish Support)
    if current['price'] < last_snap['price'] and current['put_wr_cr'] > (last_snap['put_wr_cr'] + 15.0):
        last_snap = current
        return "🟢 🛡️ **15M SUPPORT CONFIRMED** 🟢\n\nPrice dropped, but massive NEW Put Writing defending current zone.\n🟢 🛡️ Support is strong here (+{:.1f}Cr Put Writing)".format(current['put_wr_cr'] - last_snap['put_wr_cr'])

    # 4. RESISTANCE CONFIRMATION (Bearish Resistance)
    if current['price'] > last_snap['price'] and current['call_wr_cr'] > (last_snap['call_wr_cr'] + 15.0):
        last_snap = current
        return "🔴 🧱 **15M RESISTANCE CONFIRMED** 🔴\n\nPrice rose, but massive NEW Call Writing capping the upside.\n🔴 🧱 Resistance is strong here (+{:.1f}Cr Call Writing)".format(current['call_wr_cr'] - last_snap['call_wr_cr'])

    # 5. CONSOLIDATION ALERT (Neutral)
    turn_diff = abs(current['bull_turn'] - current['bear_turn'])
    if turn_diff < 10.0 and price_delta < 0.001:
        last_snap = current
        return "⚠️ **15M CONSOLIDATION ALERT** ⚠️\n\nRange-bound fighting between Call & Put sellers.\nAvoid aggressive breakouts right now."

    # Update for next comparison
    last_snap = current
    return None
