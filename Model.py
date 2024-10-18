import numpy as np
from Pacer import Pacer
from blehrm.interface import BlehrmClientInterface
import logging
from PySide6.QtCore import QObject, Signal
from analysis.HrvAnalyser import HrvAnalyser
from analysis.BreathAnalyser import BreathAnalyser

class Model(QObject):
    
    sensor_connected = Signal()
    
    def __init__(self):
        super().__init__()  
        self.logger = logging.getLogger(__name__)
        self.sensor_client = None
        self.pacer = Pacer()

        self.hrv_analyser = HrvAnalyser()
        self.breath_analyser = BreathAnalyser()
        
    async def set_and_connect_sensor(self, sensor: BlehrmClientInterface):
        self.sensor_client = sensor
        await self.sensor_client.connect()    
        await self.sensor_client.get_device_info()
        await self.sensor_client.print_device_info()
        
        await self.sensor_client.start_ibi_stream(callback=self.handle_ibi_callback)
        await self.sensor_client.start_acc_stream(callback=self.handle_acc_callback)
        
        self.sensor_connected.emit()

    async def disconnect_sensor(self):
        await self.sensor_client.disconnect()

    def handle_ibi_callback(self, data):

        t, ibi = data
        self.hrv_analyser.update(t, ibi)

    def handle_acc_callback(self, data):
        '''
        Handles reading accelerometer for the sensor
        Updates the breath_analyser which calculates breathing rate
        One each breath, hrv_analyser calculates metrics
        '''
        t = data[0]
        acc = data[1:]
        self.breath_analyser.update_chest_acc(t, acc)
        
        # Breath-by-breath analysis
        if self.breath_analyser.is_end_of_breath and not self.breath_analyser.br_history.is_empty():
            
            t_range = self.breath_analyser.get_last_breath_t_range()                    
            self.hrv_analyser.update_breath_by_breath_metrics(t_range)
    