# ===============================
# FoodGuard - ESP32 MicroPython
# DHT11 + MQ2 + KY018 + MQTT
# ===============================

import time
import network
import machine
import dht
from machine import Pin, ADC
from umqtt.simple import MQTTClient
import ujson

# ===============================
# CONFIGURATION
# ===============================
WIFI_SSID = "KUWIN-IOT"
WIFI_PASS = ""

MQTT_BROKER = "iot.cpe.ku.ac.th"
MQTT_PORT = 1883
MQTT_USER = "b6810045589"
MQTT_PASS = "josephjean.l@ku.th"
MQTT_CLIENT_ID = "foodguard_esp32"

TRANSPORTER_ID = 1
TOPIC = "/transport/{}/env".format(TRANSPORTER_ID)

PUBLISH_INTERVAL = 10  # seconds

# ===============================
# PIN MAPPING
# ===============================
DHT_PIN = 32
MQ2_AO_PIN = 34
MQ2_DO_PIN = 9
KY018_PIN = 33

# ===============================
# SENSOR INIT
# ===============================
dht_sensor = dht.DHT11(Pin(DHT_PIN))

mq2_adc = ADC(Pin(MQ2_AO_PIN))
mq2_adc.atten(ADC.ATTN_11DB)

mq2_do = Pin(MQ2_DO_PIN, Pin.IN)

ky018_adc = ADC(Pin(KY018_PIN))
ky018_adc.atten(ADC.ATTN_11DB)

# ===============================
# WIFI CONNECT
# ===============================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)

    wlan.active(False)
    time.sleep(1)
    wlan.active(True)

    print("[WiFi] Connecting to", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASS)

    timeout = 20
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        print("...")

    if wlan.isconnected():
        print("[WiFi] Connected:", wlan.ifconfig())
        return wlan
    else:
        print("[WiFi] Failed — restarting")
        time.sleep(3)
        machine.reset()

# ===============================
# MQTT CONNECT
# ===============================
def connect_mqtt():
    client = MQTTClient(
        MQTT_CLIENT_ID,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASS
    )
    client.connect()
    print("[MQTT] Connected")
    return client

# ===============================
# SENSOR READ FUNCTIONS
# ===============================
def read_dht():
    try:
        time.sleep(1)   # 🔴 important for DHT11 stability
        dht_sensor.measure()
        return dht_sensor.humidity(), dht_sensor.temperature()
    except Exception as e:
        print("[DHT11] Error:", e)
        return None, None

def read_mq2():
    raw = mq2_adc.read()
    gas = int((raw / 4095) * 500)
    alert = mq2_do.value()
    return raw, gas, alert

def read_light():
    raw = ky018_adc.read()
    brightness = round((1 - raw / 4095) * 100, 1)
    return raw, brightness

# ===============================
# MAIN
# ===============================
connect_wifi()
time.sleep(2)   # 🔴 let system stabilize

client = connect_mqtt()

while True:
    try:
        humidity, temperature = read_dht()
        mq_raw, gas, alert = read_mq2()
        light_raw, brightness = read_light()

        if humidity is None:
            print("[WARN] DHT failed")
            time.sleep(PUBLISH_INTERVAL)
            continue

        payload = {
            "transporter_id": TRANSPORTER_ID,
            "temperature": int(temperature),
            "humidity": int(humidity),
            "gas": gas,
            "light": brightness
        }

        msg = ujson.dumps(payload)
        client.publish(TOPIC, msg)

        print("[MQTT SENT]", msg)

    except Exception as e:
        print("[ERROR]", e)
        client = connect_mqtt()

    time.sleep(PUBLISH_INTERVAL)