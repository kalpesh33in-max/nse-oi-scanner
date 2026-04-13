import os
import asyncio
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv
from utils import parse_15m_data
from logic import get_confirmation, sync_trade_day

# ---------------- CONFIG ---------------- #
load_dotenv()
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")
SOURCE_BOT_RAW = os.getenv("SOURCE_BOT", "")
SOURCE_IDS = [int(i.strip()) for i in SOURCE_BOT_RAW.split(",") if i.strip()]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT", 0))
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


def get_atm_strike(price, step=100):
    if not price:
        return 0
    return int(round(price / step) * step)


def build_trade_block(current_data, alert_message):
    price = current_data.get("price", 0.0)
    atm = get_atm_strike(price)
    if not atm or not alert_message:
        return ""

    if "BULLISH BREAKOUT" in alert_message or "SUPPORT CONFIRMED" in alert_message:
        side = "BUY ATM CE"
        symbol = f"BANKNIFTY {atm} CE"
        sl = "Below alert candle low on underlying"
    elif "BEARISH BREAKDOWN" in alert_message or "RESISTANCE CONFIRMED" in alert_message:
        side = "BUY ATM PE"
        symbol = f"BANKNIFTY {atm} PE"
        sl = "Above alert candle high on underlying"
    else:
        return ""

    return (
        "\n\n"
        f"Trade Idea: {side}\n"
        f"ATM Strike: {atm}\n"
        f"Suggested Symbol: {symbol}\n"
        f"Reference Price: {price:.2f}\n"
        "Entry Zone: Near alert trigger, avoid chasing premium spike\n"
        f"Stop Loss: {sl}\n"
        "Target: Partial at 1:1.5 RR, trail/exit at 1:2 RR or opposite alert\n"
        "Avoid: Skip if consolidation appears or next 1-2 candles show no follow-through"
    )


async def main():
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()

    print("[BOOT] Meta Delta Scanner active")
    print(f"[BOOT] Listening source chats: {SOURCE_IDS}")
    print(f"[BOOT] Target bot/chat: {TARGET_BOT_ID}")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text or ""
        chat_id = event.chat_id
        msg_id = getattr(event.message, "id", None)
        text_len = len(text)
        message_dt = getattr(event.message, "date", None)
        trade_day = None
        if message_dt:
            trade_day = message_dt.astimezone(LOCAL_TZ).date().isoformat()

        print(f"[RECV] chat={chat_id} msg_id={msg_id} chars={text_len} trade_day={trade_day}")

        if "CUMULATIVE FLOW" not in text.upper():
            print(f"[SKIP] msg_id={msg_id} reason=missing_cumulative_flow")
            return

        try:
            if sync_trade_day(trade_day):
                print(f"[SNAPSHOT_RESET] msg_id={msg_id} trade_day={trade_day} reason=new_trading_day")

            current_data = parse_15m_data(text)
            print(
                "[PARSE] "
                f"msg_id={msg_id} price={current_data['price']:.2f} "
                f"bull_turn={current_data['bull_turn']:.1f}Cr "
                f"bear_turn={current_data['bear_turn']:.1f}Cr "
                f"put_wr={current_data['put_wr_cr']:.1f}Cr "
                f"call_wr={current_data['call_wr_cr']:.1f}Cr"
            )

            alert_message, debug = get_confirmation(
                current_data, return_debug=True, trade_day=trade_day
            )
            print(
                "[DECISION] "
                f"msg_id={msg_id} "
                f"price_ok={debug['price_ok']} "
                f"bull_flow_ok={debug['bull_flow_ok']} "
                f"bear_flow_ok={debug['bear_flow_ok']} "
                f"bull_banks_ok={debug['bull_banks_ok']} "
                f"bear_banks_ok={debug['bear_banks_ok']} "
                f"support_ok={debug['support_ok']} "
                f"resistance_ok={debug['resistance_ok']} "
                f"consolidation_ok={debug['consolidation_ok']}"
            )

            if alert_message:
                atm = get_atm_strike(current_data["price"])
                trade_block = build_trade_block(current_data, alert_message)
                final_alert = f"{alert_message}{trade_block}"
                print(
                    f"[ALERT] msg_id={msg_id} headline={alert_message.splitlines()[0]} "
                    f"atm={atm} reason={debug['reason']}"
                )
                await client.send_message(TARGET_BOT_ID, final_alert)
                print(f"[SEND] msg_id={msg_id} status=sent")
            else:
                print(
                    "[NO_ALERT] "
                    f"msg_id={msg_id} reason={debug['reason']} "
                    f"price_delta={debug['price_delta']:.4f} "
                    f"bull_delta={debug['bull_delta']:.1f} "
                    f"bear_delta={debug['bear_delta']:.1f} "
                    f"bull_banks={debug['bull_banks_count']} "
                    f"bear_banks={debug['bear_banks_count']} "
                    f"turn_diff={debug['turn_diff']:.1f}"
                )

        except Exception as e:
            print(f"[ERROR] msg_id={msg_id} detail={e}")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
