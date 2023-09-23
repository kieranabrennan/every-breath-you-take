import math
import time

import numpy as np
from bleak import BleakClient


class CircularBuffer2D:
    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.buffer = np.full((rows, cols), np.nan) 
        self.head = 0
        self.tail = 0
        self.dequeued_row = np.full((1,3), np.nan) 
    
    def enqueue(self, new_row):
        if len(new_row) != self.cols:
            raise ValueError("New row must have the same number of columns as the buffer")
        
        if self.is_full():
            print("Overwriting circular buffer!")
            print(f"Head id: {self.head}, Number of rows: {self.rows}")
            self.tail = (self.tail + 1) % self.rows
        
        self.buffer[self.head] = new_row
        self.head = (self.head + 1) % self.rows

    def dequeue(self):
        if self.is_empty():
            print(f"Circular buffer is empty! Head id: {self.head}")
            print(f"value at head: {self.buffer[self.head]}")
            print(f"value befor head: {self.buffer[self.head-1]}")
            return None
        
        self.dequeued_row = np.array(self.buffer[self.tail]) # Returns nan without np.array()
        self.buffer[self.tail] = np.full(self.cols, np.nan)
        self.tail = (self.tail + 1) % self.rows

        return self.dequeued_row
    
    def is_full(self):
        return (self.head == self.tail) and not np.isnan(np.array(self.buffer[self.tail])).all()

    def is_empty(self):
        return np.isnan(np.array(self.buffer[self.tail])).any()
    
    def get_num_in_queue(self):
        if self.is_empty():
            return 0
        else:
            if self.head > self.tail:
                return self.head - self.tail
            else:
                return self.rows - (self.tail - self.head)
    

class PolarH10:
    ## HEART RATE SERVICE
    HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
    # Characteristics
    HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"    # notify
    BODY_SENSOR_LOCATION_UUID = "00002a38-0000-1000-8000-00805f9b34fb"      # read

    ## USER DATA SERVICE
    USER_DATA_SERVICE_UUID = "0000181c-0000-1000-8000-00805f9b34fb"
    # Charateristics
    # ...

    ## DEVICE INFORMATION SERVICE
    DEVICE_INFORMATION_SERVICE = "0000180a-0000-1000-8000-00805f9b34fb"
    MANUFACTURER_NAME_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
    MODEL_NBR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
    SERIAL_NUMBER_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
    HARDWARE_REVISION_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
    FIRMWARE_REVISION_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
    SOFTWARE_REVISION_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
    SYSTEM_ID_UUID = "00002a23-0000-1000-8000-00805f9b34fb"

    ## BATERY SERIVCE
    BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
    BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

    ## UNKNOWN 1 SERVICE
    U1_SERVICE_UUID = "6217ff4b-fb31-1140-ad5a-a45545d7ecf3"
    U1_CHAR1_UUID = "6217ff4c-c8ec-b1fb-1380-3ad986708e2d"      # read
    U1_CHAR2_UUID = "6217ff4d-91bb-91d0-7e2a-7cd3bda8a1f3"      # write-without-response, indicate

    ## Polar Measurement Data (PMD) Service
    PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
    PMD_CHAR1_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8" #read, write, indicate – Request stream settings?
    PMD_CHAR2_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8" #notify – Start the notify stream?

    # POLAR ELECTRO Oy SERIVCE
    ELECTRO_SERVICE_UUID = "0000feee-0000-1000-8000-00805f9b34fb"
    ELECTRO_CHAR1_UUID = "fb005c51-02e7-f387-1cad-8acd2d8df0c8" #write-without-response, write, notify
    ELECTRO_CHAR2_UUID = "fb005c52-02e7-f387-1cad-8acd2d8df0c8" #notify
    ELECTRO_CHAR3_UUID = "fb005c53-02e7-f387-1cad-8acd2d8df0c8" #write-without-response, write

    # START PMD STREAM REQUEST
    HR_ENABLE = bytearray([0x01, 0x00])
    HR_DISABLE = bytearray([0x00, 0x00])

    # ECG and ACC Notify Requests
    ECG_WRITE = bytearray([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
    ACC_WRITE = bytearray([0x02, 0x02, 0x00, 0x01, 0xC8, 0x00, 0x01, 0x01, 0x10, 0x00, 0x02, 0x01, 0x08, 0x00])

    ACC_SAMPLING_FREQ = 200
    ECG_SAMPLING_FREQ = 130

    def __init__(self, bleak_device):
        self.bleak_device = bleak_device
        self.acc_stream_start_time = None
        self.ibi_data = None
        self.ibi_queue_values = CircularBuffer2D(200,1)
        self.ibi_queue_times = CircularBuffer2D(200,1)
        self.acc_queue_values = CircularBuffer2D(200,3)
        self.acc_queue_times = CircularBuffer2D(200,1)
        self.ecg_queue_values = CircularBuffer2D(200,1)
        self.ecg_queue_times = CircularBuffer2D(200,1)
        self.polar_to_epoch_s = 0
        self.first_acc_record = True
        self.first_ecg_record = True
    
    def hr_data_conv(self, sender, data):  
        """
        `data` is formatted according to the GATT Characteristic and Object Type 0x2A37 Heart Rate Measurement which is one of the three characteristics included in the "GATT Service 0x180D Heart Rate".
        `data` can include the following bytes:
        - flags
            Always present.
            - bit 0: HR format (uint8 vs. uint16)
            - bit 1, 2: sensor contact status
            - bit 3: energy expenditure status
            - bit 4: RR interval status
        - HR
            Encoded by one or two bytes depending on flags/bit0. One byte is always present (uint8). Two bytes (uint16) are necessary to represent HR > 255.
        - energy expenditure
            Encoded by 2 bytes. Only present if flags/bit3.
        - inter-beat-intervals (IBIs)
            One IBI is encoded by 2 consecutive bytes. Up to 18 bytes depending on presence of uint16 HR format and energy expenditure.
        """
        byte0 = data[0] # heart rate format
        uint8_format = (byte0 & 1) == 0
        energy_expenditure = ((byte0 >> 3) & 1) == 1
        rr_interval = ((byte0 >> 4) & 1) == 1

        if not rr_interval:
            return

        first_rr_byte = 2
        if uint8_format:
            pass
        else:
            first_rr_byte += 1
        
        if energy_expenditure:
            # ee = (data[first_rr_byte + 1] << 8) | data[first_rr_byte]
            first_rr_byte += 2

        for i in range(first_rr_byte, len(data), 2):
            ibi = (data[i + 1] << 8) | data[i]
            # Polar H7, H9, and H10 record IBIs in 1/1024 seconds format.
            # Convert 1/1024 sec format to milliseconds.
            # TODO: move conversion to model and only convert if sensor doesn't
            # transmit data in milliseconds.
            ibi = np.ceil(ibi / 1024 * 1000)            
            self.ibi_queue_values.enqueue(np.array([ibi]))
            self.ibi_queue_times.enqueue(np.array([time.time_ns()/1.0e9]))

    def acc_data_conv(self, sender, data): 
    # [02 EA 54 A2 42 8B 45 52 08 01 45 FF E4 FF B5 03 45 FF E4 FF B8 03 ...]
    # 02=ACC, 
    # EA 54 A2 42 8B 45 52 08 = last sample timestamp in nanoseconds, 
    # 01 = ACC frameType, 
    # sample0 = [45 FF E4 FF B5 03] x-axis(45 FF=-184 millig) y-axis(E4 FF=-28 millig) z-axis(B5 03=949 millig) , 
    # sample1, sample2,

        if data[0] == 0x02:
            time_step = 0.005 # 200 Hz sample rate
            timestamp = PolarH10.convert_to_unsigned_long(data, 1, 8)/1.0e9 # timestamp of the last sample in the record
            
            frame_type = data[9]
            resolution = (frame_type + 1) * 8 # 16 bit
            step = math.ceil(resolution / 8.0)
            samples = data[10:] 
            n_samples = math.floor(len(samples)/(step*3))
            record_duration = (n_samples-1)*time_step # duration of the current record received in seconds

            if self.first_acc_record: # First record at the start of the stream
                stream_start_t_epoch_s = time.time_ns()/1.0e9 - record_duration
                stream_start_t_polar_s = timestamp - record_duration
                self.polar_to_epoch_s = stream_start_t_epoch_s - stream_start_t_polar_s
                self.first_acc_record = False

            sample_timestamp = timestamp - record_duration + self.polar_to_epoch_s # timestamp of the first sample in the record in epoch seconds
            offset = 0
            while offset < len(samples):
                x = PolarH10.convert_array_to_signed_int(samples, offset, step)/100.0
                offset += step
                y = PolarH10.convert_array_to_signed_int(samples, offset, step)/100.0
                offset += step
                z = PolarH10.convert_array_to_signed_int(samples, offset, step)/100.0
                offset += step

                self.acc_queue_times.enqueue(np.array([sample_timestamp]))
                self.acc_queue_values.enqueue(np.array([x, y, z]))

                sample_timestamp += time_step
    
    def ecg_data_conv(self, sender, data):
    # [00 EA 1C AC CC 99 43 52 08 00 68 00 00 58 00 00 46 00 00 3D 00 00 32 00 00 26 00 00 16 00 00 04 00 00 ...]
    # 00 = ECG; EA 1C AC CC 99 43 52 08 = last sample timestamp in nanoseconds; 00 = ECG frameType, sample0 = [68 00 00] microVolts(104) , sample1, sample2, ....
        if data[0] == 0x00:
            timestamp = PolarH10.convert_to_unsigned_long(data, 1, 8)/1.0e9
            step = 3
            time_step = 1.0/ self.ECG_SAMPLING_FREQ
            samples = data[10:]
            n_samples = math.floor(len(samples)/step)
            offset = 0
            recordDuration = (n_samples-1)*time_step

            if self.first_ecg_record:
                stream_start_t_epoch_s = time.time_ns()/1.0e9 - recordDuration
                stream_start_t_polar_s = timestamp - recordDuration
                self.polar_to_epoch_s = stream_start_t_epoch_s - stream_start_t_polar_s
                self.first_ecg_record = False

            sample_timestamp = timestamp - recordDuration + self.polar_to_epoch_s # timestamp of the first sample in the record in epoch seconds
            while offset < len(samples):
                ecg = PolarH10.convert_array_to_signed_int(samples, offset, step)       
                offset += step
                self.ecg_queue_values.enqueue(np.array([ecg]))
                self.ecg_queue_times.enqueue(np.array([sample_timestamp]))
                sample_timestamp += time_step

    @staticmethod
    def convert_array_to_signed_int(data, offset, length):
        return int.from_bytes(
            bytearray(data[offset : offset + length]), byteorder="little", signed=True,
        )
    @staticmethod
    def convert_to_unsigned_long(data, offset, length):
        return int.from_bytes(
            bytearray(data[offset : offset + length]), byteorder="little", signed=False,
        )
    
    async def connect(self):
        self.bleak_client = BleakClient(self.bleak_device)
        await self.bleak_client.connect()
    
    async def disconnect(self):
        await self.bleak_client.disconnect()

    async def get_device_info(self):
        self.model_number = await self.bleak_client.read_gatt_char(PolarH10.MODEL_NBR_UUID)
        self.manufacturer_name = await self.bleak_client.read_gatt_char(PolarH10.MANUFACTURER_NAME_UUID)
        self.serial_number = await self.bleak_client.read_gatt_char(PolarH10.SERIAL_NUMBER_UUID)
        self.battery_level = await self.bleak_client.read_gatt_char(PolarH10.BATTERY_LEVEL_UUID)
        self.firmware_revision = await self.bleak_client.read_gatt_char(PolarH10.FIRMWARE_REVISION_UUID)
        self.hardware_revision = await self.bleak_client.read_gatt_char(PolarH10.HARDWARE_REVISION_UUID)
        self.software_revision = await self.bleak_client.read_gatt_char(PolarH10.SOFTWARE_REVISION_UUID)
    
    async def print_device_info(self):
        BLUE = "\033[94m"
        RESET = "\033[0m"
        print(f"Model Number: {BLUE}{''.join(map(chr, self.model_number))}{RESET}\n"
            f"Manufacturer Name: {BLUE}{''.join(map(chr, self.manufacturer_name))}{RESET}\n"
            f"Serial Number: {BLUE}{''.join(map(chr, self.serial_number))}{RESET}\n"
            f"Address: {BLUE}{self.bleak_device.address}{RESET}\n"
            f"Battery Level: {BLUE}{int(self.battery_level[0])}%{RESET}\n"
            f"Firmware Revision: {BLUE}{''.join(map(chr, self.firmware_revision))}{RESET}\n"
            f"Hardware Revision: {BLUE}{''.join(map(chr, self.hardware_revision))}{RESET}\n"
            f"Software Revision: {BLUE}{''.join(map(chr, self.software_revision))}{RESET}")

    async def start_acc_stream(self):
        await self.bleak_client.write_gatt_char(PolarH10.PMD_CHAR1_UUID, PolarH10.ACC_WRITE, response=True)
        await self.bleak_client.start_notify(PolarH10.PMD_CHAR2_UUID, self.acc_data_conv)
        print("Collecting ACC data...", flush=True)

    async def stop_acc_stream(self):
        await self.bleak_client.stop_notify(PolarH10.PMD_CHAR2_UUID)
        print("Stopping ACC data...", flush=True)

    async def start_ecg_stream(self):
        await self.bleak_client.write_gatt_char(PolarH10.PMD_CHAR1_UUID, PolarH10.ECG_WRITE, response=True)
        await self.bleak_client.start_notify(PolarH10.PMD_CHAR2_UUID, self.ecg_data_conv)
        print("Collecting ECG data...", flush=True)

    async def stop_ecg_stream(self):
        await self.bleak_client.stop_notify(PolarH10.PMD_CHAR2_UUID)
        print("Stopping ECG data...", flush=True)

    async def start_hr_stream(self):
        await self.bleak_client.start_notify(PolarH10.HEART_RATE_MEASUREMENT_UUID, self.hr_data_conv)
        print("Collecting HR data...", flush=True)

    async def stop_hr_stream(self):
        await self.bleak_client.stop_notify(PolarH10.HEART_RATE_MEASUREMENT_UUID)
        print("Stopping HR data...", flush=True)

    def dequeue_acc(self):
        value_row = self.acc_queue_values.dequeue()
        time_row = self.acc_queue_times.dequeue()
        return time_row, value_row

    def acc_queue_is_full(self):
        return self.acc_queue_values.is_full()
    
    def acc_queue_is_empty(self):
        return self.acc_queue_values.is_empty() or self.acc_queue_times.is_empty()

    def get_num_in_acc_queue(self):
        return self.acc_queue_values.get_num_in_queue()

    def dequeue_ecg(self):
        value_row = self.ecg_queue_values.dequeue()
        time_row = self.ecg_queue_times.dequeue()
        return time_row, value_row
    
    def ecg_queue_is_full(self):
        return self.ecg_queue_values.is_full()
    
    def ecg_queue_is_empty(self):
        return self.ecg_queue_values.is_empty() or self.ecg_queue_times.is_empty()
    
    def get_num_in_ecg_queue(self):
        return self.ecg_queue_values.get_num_in_queue()

    def dequeue_ibi(self):
        value_row = self.ibi_queue_values.dequeue()
        time_row = self.ibi_queue_times.dequeue()
        return time_row, value_row
    
    def ibi_queue_is_full(self):
        return self.ibi_queue_values.is_full()
    
    def ibi_queue_is_empty(self):
        return self.ibi_queue_values.is_empty() or self.ibi_queue_times.is_empty()
    
    def get_num_in_ibi_queue(self):
        return self.ibi_queue_values.get_num_in_queue()

    
