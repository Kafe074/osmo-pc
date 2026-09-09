#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "$0")")/pc"
exec python3 gui.py
