import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from cn105 import CN105, DEFAULT_PORT
import time
ecodan = CN105(DEFAULT_PORT, 2400)

ecodan.connect()

commands = [1,2,3,4,5,6,7,9,11,12,13,14,16,17,19,20,21,23,24,25,26,28,29,163]
for i in commands:
  result = ecodan.get_request_raw(i)
  time.sleep(0.2)
