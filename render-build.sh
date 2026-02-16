#!/usr/bin/env bash
apt-get update && apt-get install -y gcc build-essential
pip install --upgrade pip wheel
pip install -r requirements.txt
