from blehrm import blehrm
from bleak import BleakScanner, BLEDevice
import asyncio
from typing import Dict
import logging

class SensorHandler():

    def __init__(self):
        super().__init__()
        self.valid_devices: Dict[str, BLEDevice] = {} 
        self.logger = logging.getLogger(__name__)

    def get_valid_device_names(self):
        return list(self.valid_devices.keys())

    async def scan(self):
        '''
        Scans for compatible BLE heart rate monitor devices
        Emits the list of devices to devices_found
        valid_devices is a list of strings, with the name of all valid sensors found
        '''
        self.logger.info('Scanning for devices...')

        self.valid_devices = {}
        while len(self.valid_devices) == 0: # Loop until supported device is found
            ble_devices = await BleakScanner.discover()

            supported_devices = blehrm.get_supported_devices(ble_devices)
            
            self.valid_devices = {device.name: device for device, device_type in supported_devices}
            self.logger.info(f"Found {len(ble_devices)} BLE devices, {len(self.valid_devices)} of which were valid")
            await asyncio.sleep(1)

    def create_sensor_client(self, device_name):
        return blehrm.create_client(self.valid_devices[device_name])
