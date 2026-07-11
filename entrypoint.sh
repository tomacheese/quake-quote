#!/bin/sh
set -e

# 常駐はmain.py内のWebSocket再接続ループが担うため、ここでは単純に起動するだけでよい。
exec python3 src/main.py
