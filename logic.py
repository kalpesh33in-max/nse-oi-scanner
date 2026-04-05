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
    
    # 1. BREAKOUT CONFIRMATION (Price Flat, but Bullish Turn Spike)
    # Price moved <0.1%, but Bullish Turn jumped >30 Crores.
    if price_delta < 0.001 and bull_delta > 30.0 and (current['hdfc_bull'] or current['icici_bull']):
        last_snap = current
        return "🚀 **15M BREAKOUT CONFIRMED** 🚀\n\nSmart Money adding massive Longs while Price is Flat.\n🔥 Bullish Turn Delta: +{:.1f}Cr".format(bull_delta)

    # 2. CONSOLIDATION ALERT (Delta in turns is small)
    turn_diff = abs(current['bull_turn'] - current['bear_turn'])
    if turn_diff < 10.0 and price_delta < 0.001:
        last_snap = current
        return "⚠️ **15M CONSOLIDATION ALERT** ⚠️\n\nRange-bound fighting between Call & Put sellers.\nAvoid aggressive breakouts right now."

    # 3. SUPPORT CONFIRMATION (Price falling, but massive Put Writing)
    if current['price'] < last_snap['price'] and current['put_wr_cr'] > (last_snap['put_wr_cr'] + 15.0):
        last_snap = current
        return "🛡️ **15M SUPPORT CONFIRMED** 🛡️\n\nPrice dropped, but massive NEW Put Writing defending current zone.\nSupport is strong here."

    # Update for next comparison
    last_snap = current
    return None
