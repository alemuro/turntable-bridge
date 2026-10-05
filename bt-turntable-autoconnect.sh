#!/bin/bash
DEVICE_MAC="${TURNTABLE_MAC:-AD:60:17:9B:D5:AC}"

echo "Starting Bluetooth autoconnect daemon for $DEVICE_MAC..."

bluetoothctl power on >/dev/null 2>&1
bluetoothctl discoverable on >/dev/null 2>&1
bluetoothctl pairable on >/dev/null 2>&1

WAS_CONNECTED=0

while true; do
    IS_CONNECTED=0
    if bluetoothctl info "$DEVICE_MAC" 2>/dev/null | grep -q "Connected: yes"; then
        IS_CONNECTED=1
    fi

    if [ "$IS_CONNECTED" -eq 1 ]; then
        if [ "$WAS_CONNECTED" -eq 0 ]; then
            echo "[$(date)] Turntable connected! Setting audio routing and restarting DarkIce..."
            WAS_CONNECTED=1
            # Wait for PulseAudio to register the bluetooth source
            sleep 2
            # Set bluetooth source as default if present
            BT_SOURCE=$(pactl list sources short 2>/dev/null | grep "bluez_source" | awk '{print $2}' | head -n 1)
            if [ -n "$BT_SOURCE" ]; then
                pactl set-default-source "$BT_SOURCE" 2>/dev/null
                echo "[$(date)] Set default source to $BT_SOURCE"
            fi
            pkill -f darkice || true
            sleep 1
            darkice -c /etc/darkice.cfg >/dev/null 2>&1 &
        fi
        sleep 4
    else
        if [ "$WAS_CONNECTED" -eq 1 ]; then
            echo "[$(date)] Turntable disconnected."
            WAS_CONNECTED=0
        fi

        # Attempt connection with timeout
        timeout 5 bluetoothctl connect "$DEVICE_MAC" >/dev/null 2>&1
        sleep 3
    fi
done
