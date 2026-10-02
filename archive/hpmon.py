import time
import redis
import serial
import json
from cn105 import CN105

r = redis.Redis()

ecodan = CN105("/dev/ecodan", 2400)
ecodan.connect()

lastupdate = 0
while True:
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
