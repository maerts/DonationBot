#!/bin/bash

keywordbot(){
    cd "$(dirname "$0")"
    SCRIPT_DIR=$(pwd)
    /usr/bin/python3.8 DonationBot.py
}

until keywordbot; do
    echo "'keywordbot' crashed with exit code $?. Restarting..." >&2
    sleep 1
done
