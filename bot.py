
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OTCHARTS_KEY = os.getenv("OTCHARTS_API_KEY", "")

API_BASE = "https://otcharts.com"
TELEGRAM_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

TIMEFRAME_SECONDS = 60
CANDLE_LIMIT = 100
MIN_CANDLES = 35


def get_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def market_get(path, params=None):
    if not OTCHARTS_KEY:
        raise RuntimeError("مفتاح بيانات السوق غير مضبوط.")
    query = urllib.parse.urlencode(params or {})
    url = f"{API_BASE}{path}"
    if query:
        url += "?" + query
    return get_json(url, {
        "Authorization": f"Bearer {OTCHARTS_KEY}",
        "Accept": "application/json",
        "User-Agent": "Zoma-Quotex-Bot/1.0"
    })


def telegram(method, data=None):
    if not TELEGRAM_TOKEN:
        raise RuntimeError("توكن تيليجرام غير مضبوط.")
    body = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(
        f"{TELEGRAM_BASE}/{method}",
        data=body
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def get_otc_symbols():
    result = market_get("/v1/symbols", {"venue": "quotex"})
    symbols = result.get("symbols", [])
    return [
        item for item in symbols
        if item.get("symbol", "").lower().endswith("_otc")
    ]


def get_candles(symbol):
    result = market_get("/v1/candles", {
        "venue": "quotex",
        "symbol": symbol,
        "tf": TIMEFRAME_SECONDS,
        "limit": CANDLE_LIMIT
    })
    candles = result.get("candles", [])
    if not isinstance(candles, list) or len(candles) < MIN_CANDLES:
        raise ValueError("عدد الشموع المتاحة غير كافٍ للتحليل.")
    if result.get("gaps", {}).get("runs", 0):
        raise ValueError("البيانات فيها فجوات؛ تم إيقاف الإشارة للحماية.")
    candles.sort(key=lambda c: c.get("time", 0))
    return candles


def ema(values, period):
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1]
               for i in range(1, len(values))]
    gains = [max(change, 0) for change in changes[-period:]]
    losses = [max(-change, 0) for change in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze(symbol):
    candles = get_candles(symbol)
    closes = [float(c["close"]) for c in candles]
    latest = candles[-1]
    price = closes[-1]

    # لا نصدر إشارة إذا كانت آخر شمعة قديمة أكثر من 3 دقائق.
    now = time.time()
    candle_time = float(latest.get("time", 0))
    if candle_time <= 0 or now - candle_time > 180:
        raise ValueError("آخر شمعة قديمة؛ لا توجد بيانات حديثة كفاية.")

    fast = ema(closes, 9)
    slow = ema(closes, 21)
    momentum = rsi(closes, 14)

    if fast is None or slow is None or momentum is None:
        raise ValueError("بيانات المؤشرات غير مكتملة.")

    if fast > slow and 50 < momentum < 68:
        direction = "CALL ⬆️"
        reason = "المتوسط السريع أعلى من البطيء وRSI يدعم الزخم الصاعد."
    elif fast < slow and 32 < momentum < 50:
        direction = "PUT ⬇️"
        reason = "المتوسط السريع أقل من البطيء وRSI يدعم الزخم الهابط."
    else:
        direction = "لا توجد إشارة واضحة"
        reason = "المؤشرات غير متوافقة بما يكفي؛ الأفضل الانتظار."

    return (
        f"📊 Zoma | QUOTEX BOT VIP\n\n"
        f"💱 الزوج: {symbol}\n"
        f"💰 آخر سعر شمعة: {price}\n"
        f"⏱ الإطار: دقيقة واحدة\n"
        f"📈 EMA 9: {fast:.6f}\n"
        f"📉 EMA 21: {slow:.6f}\n"
        f"📊 RSI 14: {momentum:.2f}\n\n"
        f"🔔 النتيجة: {direction}\n"
        f"🧠 التحليل: {reason}\n"
        f"🕒 وقت آخر شمعة: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(candle_time))} UTC\n\n"
        f"⚠️ تحليل آلي غير مضمون الربح، وليس توصية مالية."
    )


def send_message(chat_id, text):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text
    })


def handle_message(message):
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    if not chat_id or not text:
        return

    if text.startswith("/start"):
        send_message(
            chat_id,
            "👑 أهلاً بك في Zoma | QUOTEX BOT VIP\n\n"
            "الأوامر المتاحة:\n"
            "/pairs - عرض أزواج OTC المتاحة من مصدر البيانات\n"
            "/signal EURUSD_otc - تحليل زوج محدد\n\n"
            "⚠️ الإشارات لا تضمن الربح. لن يرسل البوت إشارة "
            "إذا كانت البيانات قديمة أو غير كافية."
        )

    elif text.startswith("/pairs"):
        try:
            symbols = get_otc_symbols()
            if not symbols:
                send_message(chat_id, "مصدر البيانات لم يُرجع أزواج OTC.")
                return
            lines = [item["symbol"] for item in symbols]
            send_message(
                chat_id,
                "💱 أزواج OTC التي أرجعها المصدر:\n\n" +
                "\n".join(lines[:100]) +
                ("\n\nتم عرض أول 100 زوج." if len(lines) > 100 else "")
            )
        except Exception:
            send_message(
                chat_id,
                "تعذر جلب الأزواج. راجع مفتاح مصدر البيانات وحدود خطتك."
            )

    elif text.startswith("/signal"):
        parts = text.split()
        if len(parts) != 2:
            send_message(chat_id, "اكتب الأمر هكذا:\n/signal EURUSD_otc")
            return
        symbol = parts[1]
        try:
            available = {x["symbol"] for x in get_otc_symbols()}
            if symbol not in available:
                send_message(
                    chat_id,
                    "الزوج غير موجود في قائمة OTC الحالية لمصدر البيانات."
                )
                return
            send_message(chat_id, analyze(symbol))
        except Exception as exc:
            send_message(
                chat_id,
                f"⛔ لم أرسل إشارة لهذا الزوج.\nالسبب: {str(exc)[:250]}"
            )

    else:
        send_message(
            chat_id,
            "استخدم /pairs أو /signal EURUSD_otc"
        )


def main():
    if not TELEGRAM_TOKEN or not OTCHARTS_KEY:
        raise RuntimeError(
            "أضف TELEGRAM_BOT_TOKEN وOTCHARTS_API_KEY "
            "في إعدادات الاستضافة قبل تشغيل البوت."
        )

    print("Zoma bot started.")
    try:
        telegram("deleteWebhook", {"drop_pending_updates": "true"})
    except Exception:
        pass

    offset = 0
    while True:
        try:
            result = telegram("getUpdates", {
                "timeout": "20",
                "offset": str(offset)
            })
            if not result.get("ok"):
                time.sleep(3)
                continue
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    try:
                        handle_message(message)
                    except Exception as exc:
                        print("Message handling error:", str(exc)[:250])
        except Exception as exc:
            print("Polling error:", str(exc)[:250])
            time.sleep(5)


if __name__ == "__main__":
    main()
