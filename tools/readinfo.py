import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from cn105 import CN105, DEFAULT_PORT
import time
ecodan = CN105(DEFAULT_PORT, 2400)

ecodan.connect()

result = ecodan.get_flow_return_dhw()
print(result)

result = ecodan.get_compressor_frequency()
print(result)

result = ecodan.get_zone_and_outside()
print(result)

result = ecodan.get_modes()
print(result)
