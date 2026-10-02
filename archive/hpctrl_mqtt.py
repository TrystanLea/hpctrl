import os
import time
import paho.mqtt.client as mqtt
import json
import sys
import redis
import logging
import traceback

logging.basicConfig(handlers=[
    logging.FileHandler("/var/log/emoncms/hpctrl_mqtt.log"),
    logging.StreamHandler()
], level=logging.ERROR, format='%(asctime)s %(message)s')

r = redis.Redis()

# ------------------------------------------------------
# MQTT: emonSD defaults, override in config/mqtt.json
# ------------------------------------------------------
mqtt_settings = {"user":"emonpi", "password":"emonpimqtt2016", "host":"127.0.0.1", "port":1883}

mqtt_settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "mqtt.json")
if os.path.exists(mqtt_settings_file):
    with open(mqtt_settings_file) as f:
        mqtt_settings.update(json.load(f))

mqtt_user = mqtt_settings["user"]
mqtt_passwd = mqtt_settings["password"]
mqtt_host = mqtt_settings["host"]
mqtt_port = int(mqtt_settings["port"])

mqtt_connected = 0

def on_message(client, userdata, msg):
    if msg.topic=="hpctrl/config":
        config = json.loads(msg.payload)
        r.set('hpctrl:config',msg.payload)
    if msg.topic=="emon/emonth2_21/temperature":
        roomT = round(float(msg.payload),2)
        r.set('hpmon5:roomT',roomT)
        r.expire('hpmon5:roomT',1800)

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    mqtt_connected = 1
    logging.debug("MQTT Connected")
    mqttc.subscribe("hpctrl/config")
    mqttc.subscribe("emon/emonth2_21/temperature") # Livingroom temperature
    
def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = 0
    logging.debug("MQTT Disconnected")

mqttc = mqtt.Client()
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_disconnect = on_disconnect

# -----------------------------------------------------

count = 0

while True:

    if int(time.time())%10==0:
        if mqtt_connected==0:
            logging.debug("Attempting to connect to MQTT")
            try:
                mqttc.username_pw_set(mqtt_user, mqtt_passwd)
                mqttc.connect(mqtt_host, mqtt_port, 60)
                mqttc.loop_start()
            except Exception as e:
                logging.error(e)
        
        if mqtt_connected==1:
            mode = r.get("hpctrl:mode")
            if mode: 
                mode = int(mode.decode())
                mode_sh = 0
                mode_dhw = 0
                if mode==1: mode_sh = 1
                if mode==2: mode_dhw = 1

                try:                        
                    mqttc.publish("emon/hpmon5/mode",mode)
                    mqttc.publish("emon/hpmon5/mode_sh_elec",mode_sh)
                    mqttc.publish("emon/hpmon5/mode_dhw_elec",mode_dhw)
                    mqttc.publish("emon/hpmon5/mode_sh_heat",mode_sh)
                    mqttc.publish("emon/hpmon5/mode_dhw_heat",mode_dhw)

                    if count%10==0: 
                        logging.debug("Published "+str(count)+" messages")
                    count += 1
                except Exception as e:
                    logging.error(e)

       
        time.sleep(2.0)
        
    time.sleep(0.1)
    
    try:
        mqttc.loop(0)
    except Exception as e:
        logging.error(e)

# Close
mqttc.loop_stop()
mqttc.disconnect()


