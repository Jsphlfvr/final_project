# ============================================================
# Food Delivery IoT Monitor — ESP32 Firmware
# MicroPython
#
# Wiring:
#   DHT11           → GPIO 32
#   MQ2 AOUT        → GPIO 34  (ADC)
#   MQ2 DOUT        → GPIO 9   (digital)
#   KY-018 (LDR)    → GPIO 33  (ADC)
#
# NOTE: copy .env.example to .env and fill in real values,
#       then update the constants below before flashing.
# ============================================================

import machine
import network
import time
import json
import dht
from machine import ADC, Pin
from umqtt.simple import MQTTClient

# ── Configuration ────────────────────────────────────────────
WIFI_SSID       = "YourSSID"
WIFI_PASSWORD   = "YourPassword"

MQTT_BROKER     = "iot.cpe.ku.ac.th"
MQTT_PORT       = 1883
MQTT_CLIENT_ID  = "esp32_food_monitor"

TRANSPORTER_ID  = 1
PUBLISH_INTERVAL_MS = 10_000   # 10 seconds

# ── GPIO Setup ───────────────────────────────────────────────
dht_sensor  = dht.DHT11(Pin(32))

adc_mq2     = ADC(Pin(34))
adc_mq2.atten(ADC.ATTN_11DB)      # 0–3.3 V range
adc_mq2.width(ADC.WIDTH_12BIT)

dout_mq2    = Pin(9, Pin.IN)       # HIGH = alert threshold exceeded

adc_ldr     = ADC(Pin(33))
adc_ldr.atten(ADC.ATTN_11DB)
adc_ldr.width(ADC.WIDTH_12BIT)

# ── MQTT topic ───────────────────────────────────────────────
TOPIC_ENV = "/transport/{}/env".format(TRANSPORTER_ID).encode()

# ── WiFi connection ──────────────────────────────────────────
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan
    print("[WiFi] Connecting to", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            print("[WiFi] Connected:", wlan.ifconfig())
            return wlan
        time.sleep(1)
    print("[WiFi] Connection failed — retrying next cycle")
    return wlan

# ── MQTT connection ──────────────────────────────────────────
_mqtt_client = None

def get_mqtt():
    global _mqtt_client
    try:
        if _mqtt_client is None:
            _mqtt_client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
        _mqtt_client.connect()
        print("[MQTT] Connected to", MQTT_BROKER)
    except Exception as e:
        print("[MQTT] Connect error:", e)
        _mqtt_client = None
    return _mqtt_client

# ── Sensor reading ───────────────────────────────────────────
def read_dht():
    try:
        dht_sensor.measure()
        return dht_sensor.humidity(), dht_sensor.temperature()
    except Exception as e:
        print("[DHT11] Read error:", e)
        return None, None

def read_mq2():
    raw = adc_mq2.read()
    # Rough linear mapping: 0→4095 ADC maps to 0→4000 ppm
    ppm = int(raw * 4000 / 4095)
    alert = 1 if dout_mq2.value() == 1 else 0
    return ppm, raw, alert

def read_ldr():
    raw = adc_ldr.read()
    # Invert: low ADC = bright; map to 0-100 lux-equivalent
    brightness = round((4095 - raw) * 100.0 / 4095, 1)
    return brightness, raw

# ── Main loop ────────────────────────────────────────────────
def main():
    wlan = connect_wifi()
    client = get_mqtt()

    while True:
        # Ensure WiFi is alive
        if not wlan.isconnected():
            wlan = connect_wifi()
            client = None

        # Ensure MQTT is alive
        if client is None:
            client = get_mqtt()

        # Read sensors
        humidity, temperature = read_dht()
        gas_concentration, gas_raw, gas_alert = read_mq2()
        brightness, ldr_raw = read_ldr()

        if humidity is None or temperature is None:
            print("[Sensor] DHT read failed, skipping publish")
            time.sleep_ms(PUBLISH_INTERVAL_MS)
            continue

        payload = {
            "transporter_id":    TRANSPORTER_ID,
            "humidity":          humidity,
            "temperature":       temperature,
            "gas_concentration": gas_concentration,
            "gas_raw":           gas_raw,
            "gas_alert":         gas_alert,
            "brightness":        brightness,
            "ldr_raw":           ldr_raw,
        }

        msg = json.dumps(payload).encode()

        try:
            client.publish(TOPIC_ENV, msg)
            print("[MQTT] Published:", payload)
        except Exception as e:
            print("[MQTT] Publish error:", e)
            _mqtt_client = None
            client = None

        time.sleep_ms(PUBLISH_INTERVAL_MS)

main()
