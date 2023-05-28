import numpy as np
import asyncio
from PolarH10 import PolarH10
import time
from Pacer import Pacer

class Model:

    def __init__(self):
        
        self.polar_sensor = None
        self.pacer = Pacer()

        self.ACC_HIST_SIZE = 1200 # Raw data comes in at 200 Hz, subsampled at 20 Hz, 
        self.acc_hist = np.full((self.ACC_HIST_SIZE, 3), np.nan)
        self.acc_times_hist = np.full(self.ACC_HIST_SIZE, np.nan) # epoch seconds
        self.acc_times_hist_rel_s = np.full(self.ACC_HIST_SIZE, np.nan) # relative seconds
        # self.pacer_values_hist = np.full((self.ACC_HIST_SIZE, 1), np.nan)
        # self.pacer_times_hist = np.full((self.ACC_HIST_SIZE, 1), np.nan)
        # self.pacer_times_hist_rel_s = np.full(self.ACC_HIST_SIZE, np.nan) # relative seconds
        
        self.GRAVITY_ALPHA = 0.999
        self.acc_gravity = np.full(3, np.nan)
        self.ACC_MEAN_ALPHA = 0.98
        self.acc_zero_centred_exp_mean = np.zeros(3)
        self.acc_principle_axis = np.array([0, 0, 1]) # positive z-axis is the direction out of sensor unit (away from chest)

        self.BR_ACC_HIST_SIZE = 3000
        self.breath_acc_hist = np.full(self.BR_ACC_HIST_SIZE, np.nan)
        self.breath_acc_times = np.full(self.BR_ACC_HIST_SIZE, np.nan)
        self.breath_acc_times_rel_s = np.full(self.BR_ACC_HIST_SIZE, np.nan)
        self.t_last_acc = 0
        self.t_last_acc_norm = 0
        
        self.IBI_HIST_SIZE = 200
        self.ibi_values_hist = np.full(self.IBI_HIST_SIZE, np.nan)
        self.ibi_times_hist = np.arange(-self.IBI_HIST_SIZE, 0) # relative seconds
        self.ibi_times_hist_rel_s = np.full(self.IBI_HIST_SIZE, np.nan) # relative seconds
        self.hr_values_hist = np.full(self.IBI_HIST_SIZE, np.nan)
        
        self.HRV_HIST_SIZE = 300
        self.ibi_latest_phase_duration = 0
        self.ibi_last_phase = 0
        self.ibi_last_extreme = 0
        self.hrv_values_hist = np.full(self.HRV_HIST_SIZE, np.nan)
        self.hrv_times_hist = np.arange(-self.HRV_HIST_SIZE, 0) # relative seconds
        self.hr_extrema_ids = np.full(self.HRV_HIST_SIZE, -1, dtype=int)
        
        self.BR_HIST_SIZE = 300 # Fast breathing 30 bpm, sampled twice every breathing cycle, over 5 minutes this is 300 values
        self.br_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        self.br_times_hist = np.full(self.BR_HIST_SIZE, np.nan) # relative seconds
        self.br_times_hist_rel_s = np.full(self.BR_HIST_SIZE, np.nan) # relative seconds
        self.br_latest_halfphase_duration = 0
        self.br_last_phase = 0
        self.breath_cycle_ids = np.full(self.BR_HIST_SIZE, -1, dtype=int)
        self.br_pace_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        self.hrv_br_interp_values_hist = np.full(self.BR_HIST_SIZE, np.nan)

    def set_polar_sensor(self, device):
        self.polar_sensor = PolarH10(device)

    async def connect_sensor(self):
        await self.polar_sensor.connect()
        await self.polar_sensor.get_device_info()
        await self.polar_sensor.print_device_info()
        
    async def disconnect_sensor(self):
        await self.polar_sensor.disconnect()

    def update_hrv(self):

        print("HRV Is updating baby")
        self.ibi_latest_phase_duration += self.ibi_values_hist[-1]
        # 1: IBI rises, -1: IBI falls, 0: IBI constant
        current_ibi_phase = np.sign(self.ibi_values_hist[-1] - self.ibi_values_hist[-2])
        if current_ibi_phase == 0 or current_ibi_phase == self.ibi_last_phase:
            return

        current_ibi_extreme = self.ibi_values_hist[-2]
        latest_hrv = abs(self.ibi_last_extreme - current_ibi_extreme)
        seconds_current_phase = np.ceil(self.ibi_latest_phase_duration / 1000.0)

        if latest_hrv < 0.2*(np.amin(self.hrv_values_hist[-2:])):
            print(f"Rejected low HRV value")
            return

        self.hrv_values_hist = np.roll(self.hrv_values_hist, -1)
        self.hrv_values_hist[-1] = latest_hrv

        self.hr_extrema_ids = np.roll(self.hr_extrema_ids, -1)
        self.hr_extrema_ids[-1] = self.IBI_HIST_SIZE - 2
        
        self.hrv_times_hist = self.hrv_times_hist - seconds_current_phase
        self.hrv_times_hist = np.roll(self.hrv_times_hist, -1)
        self.hrv_times_hist[-1] = 0
        
        self.ibi_latest_phase_duration = 0

        self.ibi_last_extreme = current_ibi_extreme
        self.ibi_last_phase = current_ibi_phase

    async def update_ibi(self):
        await self.polar_sensor.start_hr_stream()

        while True:
            await asyncio.sleep(0.01)
            
            t_now = time.time_ns()/1.0e9
            # Updating IBI history
            while not self.polar_sensor.ibi_queue_is_empty():
                t, ibi = self.polar_sensor.dequeue_ibi() # t is when value was added to the queue
                
                if ibi < 300 or ibi > 1600:
                    continue

                self.ibi_values_hist = np.roll(self.ibi_values_hist, -1)
                self.ibi_values_hist[-1] = ibi
                self.hr_values_hist = 60.0/(self.ibi_values_hist/1000.0)

                self.ibi_times_hist = -np.flip(np.cumsum(np.flip(self.ibi_values_hist)))/1000.0 # seconds relative to the last value
                self.ibi_times_hist = np.roll(self.ibi_times_hist, -1)
                self.ibi_times_hist[-1] = 0

                self.hr_extrema_ids = self.hr_extrema_ids - 1
                self.hr_extrema_ids[self.hr_extrema_ids < -1] = -1
                
                self.update_hrv()

    def update_breathing_rate(self):

        current_br_phase = np.sign(self.breath_acc_hist[-1])

        if current_br_phase == self.br_last_phase:
            self.br_last_phase = current_br_phase
            return
        if current_br_phase >= 0:
            self.br_last_phase = current_br_phase
            return

        self.breath_cycle_ids = np.roll(self.breath_cycle_ids, -1)
        self.breath_cycle_ids[-1] = self.BR_ACC_HIST_SIZE - 1

        if np.isnan(self.br_times_hist[-1]):
            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = 0

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = 0

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.breath_acc_times[-1]
        else:
            seconds_current_phase = self.breath_acc_times[-1] - self.br_times_hist[-1]
            current_breathing_rate = 60.0 / (seconds_current_phase)

            if current_breathing_rate > 60:
                return

            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = current_breathing_rate

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = self.pacer.last_breathing_rate  

            self.hrv_br_interp_values_hist = np.roll(self.hrv_br_interp_values_hist, -1)
            self.hrv_br_interp_values_hist[-1] = self.hrv_values_hist[-1]

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.breath_acc_times[-1]

        self.br_last_phase = current_br_phase

    async def update_pmd(self): # pmd: polar measurement data
        
        await self.polar_sensor.start_acc_stream()
        
        while True:
            await asyncio.sleep(0.01)
            
            # Updating the acceleration history
            while not self.polar_sensor.acc_queue_is_empty():
                t, acc = self.polar_sensor.dequeue_acc()
                t_now = time.time_ns()/1.0e9

                if np.isnan(self.acc_gravity).any():
                    self.acc_gravity = acc
                else:
                    self.acc_gravity = self.GRAVITY_ALPHA*self.acc_gravity + (1-self.GRAVITY_ALPHA)*acc

                acc_zero_centred = acc - self.acc_gravity
                self.acc_zero_centred_exp_mean = self.ACC_MEAN_ALPHA*self.acc_zero_centred_exp_mean + (1-self.ACC_MEAN_ALPHA)*acc_zero_centred
                
                if (t - self.t_last_acc) > 0.05: # subsampling at 20 Hz
                    self.acc_hist = np.roll(self.acc_hist, -1, axis=0)
                    self.acc_hist[-1, :] = self.acc_zero_centred_exp_mean
                    self.acc_times_hist = np.roll(self.acc_times_hist, -1)
                    self.acc_times_hist[-1] = t
                    self.t_last_acc = t
            
                if (t - self.t_last_acc_norm) > 0.1: # subsampling
        
                    self.breath_acc_hist = np.roll(self.breath_acc_hist, -1)
                    self.breath_acc_hist[-1] = np.dot(self.acc_zero_centred_exp_mean, self.acc_principle_axis)
                    self.breath_acc_times = np.roll(self.breath_acc_times, -1)
                    self.breath_acc_times[-1] = t

                    self.breath_cycle_ids = self.breath_cycle_ids - 1
                    self.breath_cycle_ids[self.breath_cycle_ids < -1] = -1

                    self.t_last_acc_norm = t
                
                self.update_breathing_rate()

    