import re

def get_value(label, text):
    # Extracts the "TOT" Crore value for Bullish/Bearish Turn or specific Flows
    matches = re.findall(rf"{label}.*?([\d.]+)(Cr|L)", text)
    if not matches:
        return 0.0
    val_str, unit = matches[-1]
    value = float(val_str)
    return value if unit == "Cr" else value / 100

def get_future_price(text):
    match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", text)
    return float(match.group(1)) if match else None

def check_component_bias(text, component_name):
    # Checks if a specific bank is "STRONG BULLISH" or "VERY STRONG BULLISH"
    try:
        section = text.split(f"💎 {component_name}")[1].split("=")[0]
        return "STRONG BULLISH" in section
    except:
        return False

def parse_15m_data(text):
    data = {}
    data['price'] = get_future_price(text)
    data['bull_turn'] = get_value("Bullish Turn", text)
    data['bear_turn'] = get_value("Bearish Turn", text)
    
    # Extract Put Writing ITM value (using your dashboard's logic)
    put_wr_matches = re.findall(r"PUT_WR\s+\d+\(([\d.]+)(Cr|L)\)", text)
    data['put_wr_cr'] = (float(put_wr_matches[0][0]) if put_wr_matches[0][1] == "Cr" else float(put_wr_matches[0][0])/100) if put_wr_matches else 0.0
    
    data['hdfc_bull'] = check_component_bias(text, "HDFCBANK")
    data['icici_bull'] = check_component_bias(text, "ICICIBANK")
    
    return data
