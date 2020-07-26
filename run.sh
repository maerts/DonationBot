#!/bin/bash

donbot(){
    python3.8 DonationBot.py
}

until donbot; do
    echo "'donationbot' crashed with exit code $?. Restarting..." >&2
    sleep 1
done
