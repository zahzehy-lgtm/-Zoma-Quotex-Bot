
#!/bin/bash
set -e

echo "=================================="
echo "   Zoma | QUOTEX BOT VIP"
echo "   Manual Startup"
echo "=================================="

if [ ! -f "bot.py" ]; then
    echo "ERROR: bot.py not found"
    exit 1
fi

python3 bot.py
