import gpiozero
import time
import redis
import serial
import json

r = redis.Redis()
r4 = gpiozero.LED(17)
r4.on()
