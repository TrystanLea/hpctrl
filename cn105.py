import serial
import time

class CN105:
    ser = False
    last_temp = -1
    last_power = -1

    def __init__(self,port,baud,control_enabled=True):
        self.ser = serial.Serial("/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0", 2400, 8, 'E', 1, 0.5)
        self.control_enabled = control_enabled
            
    def calc_checksum(self,frame):
        frame_sum = 0
        for i in range(0,len(frame)-1):
            frame_sum += frame[i]
        frame[len(frame)-1] = (0xfc - frame_sum) & 0xff
        return frame

    def read_reply(self,timeout=1.0):
        bid = 0
        length = 0
        data = []
        start_time = time.time()
        
        while (time.time()-start_time)<timeout:
            while self.ser.in_waiting:
                # Read in byte
                val = ord(self.ser.read(1))

                if len(data)<=bid:
                    data.append(val)
                else:
                    data[bid] = val

                # reset bid to 0 if first not sync byte
                if data[0]!=0xfc:
                    bid = 0
                # Find length
                if bid==4:
                    length = val + 5
                # Parse frame if we reach checksum
                if length!=0 and bid==length:
                    return data
                    bid = 0
                else: 
                    # Increment byte id
                    bid += 1

            time.sleep(0.1)
        return data

    def parse_frame(self,data):
        result = {}
        # print(list(map(hex,data)))
        # for i in range(0,length+1):
        #   print(str(i)+" "+hex(data[i])+" "+str(data[i]))
        
        rtype = data[1]
        if rtype==0x61:
            print("ack")
            return True
        
        response = data[5:]
        cmd = response[0]
       
        # GET Compressor frequency
        if cmd==0x04:
            # sync, type, ?   , ?   , len , cmd , freq
            # 0xfc, 0x62, 0x02, 0x7a, 0x10, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0e
            result['freq'] = response[1]
       
        # GET Temperatures of some kind?
        elif cmd==0x11:   
            #                               0     1     2     3     4     5     6     7    8     9    10    11   12   13   14   15   16
            # sync, type, ?   , ?   , len , cmd ,
            # 0xfc, 0x62, 0x02, 0x7a, 0x10, 0x11, 0xb0, 0x3, 0xd8, 0x3, 0x4, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x6f
            val = (response[2]<<8)+response[3]
            result['temp1'] = val*0.01
            val = (response[4]<<8)+response[5]
            result['temp2'] = val*0.01
       
        # GET Flow, Return and DHW Temperatures
        elif cmd==0x0c:
            #                               0    1     2     3     4     5     6     7    8     9    10    11   12   13   14   15   16
            #  sync, type, ?  , ?   , len , cmd, flow, flow        ret   ret         dhw  dhw
            # [0xfc, 0x62, 0x2, 0x7a, 0x10, 0xc, 0x08, 0xfc, 0x78, 0x08, 0x66, 0x74, 0xb, 0xb8, 0x89, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x5c]
            val = (response[1]<<8)+response[2]
            result['flowT'] = val*0.01
            val = (response[4]<<8)+response[5]
            result['returnT'] = val*0.01
            val = (response[7]<<8)+response[8]
            result['dhwT'] = val*0.01
        
        elif cmd==0x0b:
            # GET Zone 1 & 2 and Outside Temperature
            #                              0     1     2     3     4     5     6     7     8     9     10    11    12    13    14    15    16
            #                              cmd   z1T   z1T   ?     ?                 z2T   z2T               out
            # 0xfc, 0x62, 0x2, 0x7a, 0x10, 0x0b, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0f, 0xa0, 0x0b, 0x70, 0x00, 0x00, 0x00, 0x00, 0xdd
            val = (response[1]<<8)+response[2]
            result['zone1T'] = val*0.01
            # val = (response[3]<<8)+response[4]
            # result['zone?T'] = val*0.01
            val = (response[8]<<8)+response[9] # changed to 8 & 9 from 7, 8?? result = 40, possibly gas return temp?
            result['zone2T'] = val*0.01
            result['outside'] = (response[11]/2)-40
            
        elif cmd==0x26:
            # GET System State
            #                              0     1     2     3     4     5     6     7     8     9     10    11    12    13    14    15    16
            #                              cmd               pwr   op1   dhw   op2         dhwT  dhwT  sp    sp
            # 0xfc, 0x62, 0x2, 0x7a, 0x10, 0x26, 0x00, 0x00, 0x01, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0c, 0x80, 0x00, 0x00, 0x00, 0x00, 0x5d
            result['power'] = response[3]
            result['opmode1'] = response[4]
            result['dhwmode'] = response[5]    
            result['opmode2'] = response[6]
            val = (response[8]<<8)+response[9]
            result['dhw_setpoint'] = val*0.01
            val = (response[10]<<8)+response[11]
            result['heating_setpoint'] = val*0.01       
            val = (response[12]<<8)+response[13]
            result['unknown_setpoint'] = val*0.01 
        elif cmd==0x29:
            # Zone temperatures?
            # 0xfc, 0x62, 0x2, 0x7a, 0x10, 0x29, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0xe9
            self.print_hex_str(data)
        else:
            self.print_hex_str(data)
            
        return result

    def print_hex_str(self,data):
        hexdata = []
        for i in range(0,len(data)):
          hexdata.append("0x{:02x}".format(data[i]))
        hexstr = ",".join(hexdata)
        
        desc = "sync,type,?   ,?   ,len ,cmd "
        response = data[5:]
        sum_response = 0
        for i in range(1,len(response)-1):
            sum_response += response[i]
            desc += (","+str(i)).ljust(5,' ')  
        print(desc)
        print(hexstr+" ("+str(sum_response)+")")
            
    def get_flow_return_dhw(self):
        return self.get_request(0x0c)

    def get_compressor_frequency(self):
        return self.get_request(0x04)

    def get_zone_and_outside(self):
        return self.get_request(0x0b)

    def get_modes(self):
        return self.get_request(0x26)

    def get_request(self,cmd):
        msg = [0xfc,0x42,0x02,0x7a,0x01,cmd,0x00]
        msg = self.calc_checksum(msg)
        self.ser.write(msg)
        data = self.read_reply()
        return self.parse_frame(data)

    def get_request_raw(self,cmd):
        msg = [0xfc,0x42,0x02,0x7a,0x01,cmd,0x00]
        msg = self.calc_checksum(msg)
        self.ser.write(msg)
        data = self.read_reply()
        if data:
            self.print_hex_str(data)

    def connect(self):
        msg = [0xfc,0x5a,0x02,0x7a,0x02,0xca,0x01,0x00]
        msg = self.calc_checksum(msg)
        self.ser.write(msg)
        data = self.read_reply()

    def set_power(self,power):
        if not self.control_enabled: return False
        
        if power!=self.last_power:
            self.last_power = power
            print("Sending power cmd "+str(power))
            msg = [0xfc,0x41,0x02,0x7a,16,0x32,0x01,0x00,power,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
            msg = self.calc_checksum(msg)
            self.ser.write(msg)
            data = self.read_reply()
            return self.parse_frame(data)

    def set_temp(self,temp):
        if not self.control_enabled: return False
        
        # reduce to 1 dp resolution
        temp = int(temp*10)*0.1
        # only update if state has changed
        if temp!=self.last_temp:
            self.last_temp = temp
            
            z1sp_a = int(temp*100)>>8
            z1sp_b = int(temp*100) - (z1sp_a<<8)
            
            print("Sending temp cmd "+str(temp))
            #                 Update settings: FLAG, Z  ,P   , ?  ,DHW, HC1, HC2, DHWSP, DHWSP, Z1, Z1  , Z2,  Z2
            msg = [0xfc,0x41,0x02,0x7a,16,0x32,0x80,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,z1sp_a,z1sp_b,0x00,0x00,0x00,0x00,0x00]
            msg = self.calc_checksum(msg)
            self.ser.write(msg)
            data = self.read_reply()
            return self.parse_frame(data)
