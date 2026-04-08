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

def get_future_component(text, type_list):
    total = 0.0
    try:
        if "---- FUTURES FLOW ----" in text:
            fut_section = text.split("---- FUTURES FLOW ----")[1]
            for label in type_list:
                matches = re.findall(rf"{label}.*?\(([\d.]+)(Cr|L)\)", fut_section)
                for val_str, unit in matches:
                    val = float(val_str)
                    total += val if unit == "Cr" else val / 100
    except:
        pass
    return total

def parse_15m_data(text):
    # To handle HTML and raw text
    text = text.replace("<br>", "\n").replace("</pre>", "")
    
    data = {
        'price': 0.0,
        
        'index_opt_bull': 0.0, 'index_opt_bear': 0.0,
        'index_fut_bull': 0.0, 'index_fut_bear': 0.0,
        
        'stock_opt_bull': 0.0, 'stock_opt_bear': 0.0,
        'stock_fut_bull': 0.0, 'stock_fut_bear': 0.0,
        
        'put_wr_cr': 0.0, 'call_wr_cr': 0.0,
        
        'hdfc_bull': False, 'icici_bull': False, 'sbin_bull': False, 'axis_bull': False,
        'hdfc_bear': False, 'icici_bear': False, 'sbin_bear': False, 'axis_bear': False
    }
    
    price_match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    if price_match:
        data['price'] = float(price_match.group(1))
        
    put_wr_matches = re.findall(r"PUT_WR\s+\d+\(([\d.]+)(Cr|L)\)", text)
    data['put_wr_cr'] = sum([(float(v) if u == "Cr" else float(v)/100) for v, u in put_wr_matches])

    call_wr_matches = re.findall(r"CALL_WR\s+\d+\(([\d.]+)(Cr|L)\)", text)
    data['call_wr_cr'] = sum([(float(v) if u == "Cr" else float(v)/100) for v, u in call_wr_matches])
    
    sections = text.split("💎 ")
    
    for section in sections[1:]:
        lines = section.split("\n")
        symbol_line = lines[0] if lines else ""
        
        opt_bull = get_value_from_text("Bullish Turn", section)
        opt_bear = get_value_from_text("Bearish Turn", section)
        
        fut_bull = get_future_component(section, ["FUTURE_BUY", "FUTURE_SC"])
        fut_bear = get_future_component(section, ["FUTURE_SELL", "FUTURE_UNW"])
        
        if "BANKNIFTY" in symbol_line:
            data['index_opt_bull'] = opt_bull
            data['index_opt_bear'] = opt_bear
            data['index_fut_bull'] = fut_bull
            data['index_fut_bear'] = fut_bear
        elif any(s in symbol_line for s in ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK"]):
            data['stock_opt_bull'] += opt_bull
            data['stock_opt_bear'] += opt_bear
            data['stock_fut_bull'] += fut_bull
            data['stock_fut_bear'] += fut_bear
            
            if "HDFCBANK" in symbol_line:
                data['hdfc_bull'] = "STRONG BULLISH" in section
                data['hdfc_bear'] = "STRONG BEARISH" in section
            elif "ICICIBANK" in symbol_line:
                data['icici_bull'] = "STRONG BULLISH" in section
                data['icici_bear'] = "STRONG BEARISH" in section
            elif "SBIN" in symbol_line:
                data['sbin_bull'] = "STRONG BULLISH" in section
                data['sbin_bear'] = "STRONG BEARISH" in section
            elif "AXISBANK" in symbol_line:
                data['axis_bull'] = "STRONG BULLISH" in section
                data['axis_bear'] = "STRONG BEARISH" in section
                
    data['bull_turn'] = data['index_opt_bull'] + data['index_fut_bull'] + data['stock_opt_bull'] + data['stock_fut_bull']
    data['bear_turn'] = data['index_opt_bear'] + data['index_fut_bear'] + data['stock_opt_bear'] + data['stock_fut_bear']
    
    return data
