import gpiozero
import time
import redis
import serial
import json
from cn105 import CN105

r = redis.Redis()
r4 = gpiozero.LED(27)

ecodan = CN105("/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0", 2400)
ecodan.connect()

lastupdate = 0
while True:

    # r1 ------------------------------------     HP ON OFF
    x = r.get("hpctrl:r1")
    if x:
        x = int(x.decode())
        if x==1:
            ecodan.set_power(1)
        else:
            ecodan.set_power(0)
    else:
        ecodan.set_power(0)

    # ac1 -----------------------------------      3 WAY VALVE 
    x = r.get("hpctrl:ac1")
    if x:
        x = int(x.decode())
        if x==1:
            r4.on()
        else:
            r4.off()
    else:
        r4.off()

    # dac -----------------------------------     FLOW TEMP  
    x = r.get("hpctrl:temp")
    if x:
        ecodan.set_temp(float(x))
    else:
        ecodan.set_temp(float(0))

    # Read data from ecodan
    if (time.time()-lastupdate)>=10.0:
        lastupdate = time.time()
        
        all_results = {"time":int(lastupdate),"node":"ecodan"}
        
        result = ecodan.get_flow_return_dhw()
        for key in result: all_results[key] = result[key]
        
        result = ecodan.get_compressor_frequency()
        for key in result: all_results[key] = result[key]

        result = ecodan.get_zone_and_outside()
        for key in result: all_results[key] = result[key]

        result = ecodan.get_modes()
        for key in result: all_results[key] = result[key]
        
        # print(all_results)
        
        r.rpush("emonhub:sub",json.dumps(all_results))

    time.sleep(1)
