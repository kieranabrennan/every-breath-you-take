import numpy as np
import time
from Pacer import Pacer
from scipy import signal
from blehrm.interface import BlehrmClientInterface
import logging
from PySide6.QtCore import QObject, Signal
from analysis.HrvAnalyser import HrvAnalyser

class Model(QObject):
    
    sensor_connected = Signal()
    
    def __init__(self):
        super().__init__()  
        self.logger = logging.getLogger(__name__)
        self.sensor_client = None
        self.pacer = Pacer()
        self.breathing_circle_radius = -0.5
        self.hr_circle_radius = -0.5

        self.hrv_analyser = HrvAnalyser()

        # Sample rates
        self.BR_ACC_SAMPLE_RATE = 10 # Hz, rate to subsample breathing acceleration
        
        # History sizes
        self.BR_ACC_HIST_SIZE = 1200 # 
        self.HRV_HIST_SIZE = 500 
        self.BR_HIST_SIZE = 500 # Fast breathing 20 breaths per minute, sampled once every breathing cycle, over 10 minutes this is 200 values

        # Accelerometer signal parameters
        self.GRAVITY_ALPHA = 0.999 # Exponential mean filter for gravity
        self.ACC_MEAN_ALPHA = 0.98 # Exponential mean filter for noise
        self.acc_principle_axis = np.array([0, 0, 1]) # Positive z-axis is the direction out of sensor unit (away from chest)
        
        # Breathing signal parameters
        self.BR_MAX_FILTER = 30 # breaths per minute maximum

        # Initialisation
        self.acc_gravity = np.full(3, np.nan)
        self.acc_zero_centred_exp_mean = np.zeros(3)
        self.t_last_breath_acc_update = 0
        self.br_last_phase = 0
        self.current_br = 0

        # History array initialisation
        self.breath_acc_hist = np.full(self.BR_ACC_HIST_SIZE, np.nan)
        self.breath_acc_times = np.full(self.BR_ACC_HIST_SIZE, np.nan)
        self.breath_acc_times_rel_s = np.full(self.BR_ACC_HIST_SIZE, np.nan)

        self.br_psd_freqs_hist = []
        self.br_psd_values_hist = []

        self.br_coherence = np.nan
        
        self.br_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        self.br_times_hist = np.full(self.BR_HIST_SIZE, np.nan) 
        self.br_times_hist_rel_s = np.full(self.BR_HIST_SIZE, np.nan) 

        self.br_pace_values_hist = np.full(self.BR_HIST_SIZE, np.nan)

        self.breath_cycle_ids = np.full(self.BR_HIST_SIZE, -1, dtype=int)
        
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

    def update_breathing_rate(self):

        # Update the breathing rate and pacer history
        if np.isnan(self.br_times_hist[-1]): # First value
            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = self.current_br

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = 0

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.breath_acc_times[-1]

        else:
            # Update the breathing rate history
            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = self.current_br

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = self.pacer.last_breathing_rate  

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.breath_acc_times[-1]

            # Update hrv metrics
            t_range = (self.br_times_hist[-2], self.br_times_hist[-1])
            self.hrv_analyser.update_breath_by_breath_metrics(t_range)


    def update_breathing_spectrum(self):
        if np.sum(~np.isnan(self.breath_acc_times)) < 3:
            return

        ids = self.breath_acc_times > (self.breath_acc_times[-1] - 30) # Hardcode 30 seconds
        values = self.breath_acc_hist[ids]
        times = self.breath_acc_times[ids]
        dt = times[-1] - times[-2]

        # Calculate the spectrum
        self.br_psd_freqs_hist, self.br_psd_values_hist = signal.periodogram(values, fs=1/dt, window='hann', detrend='linear')
        self.br_psd_values_hist /= np.sum(self.br_psd_values_hist)

        # Interpolating the power spectral density, to get sub-bin integration
        br_psd_freqs_interp = np.arange(self.br_psd_freqs_hist[0], self.br_psd_freqs_hist[-1], 0.005)
        br_psd_interp = np.interp(br_psd_freqs_interp, self.br_psd_freqs_hist, self.br_psd_values_hist)
        
        # Calculating total power and peak power
        pacer_freq = self.pacer.last_breathing_rate/60.0
        total_power = np.trapz(br_psd_interp, br_psd_freqs_interp)
        peak_indices = np.where((br_psd_freqs_interp >= pacer_freq - 0.015) & (br_psd_freqs_interp <= pacer_freq + 0.015)) # 0.03 Hz around the peak is recommended by R. McCraty
        peak_power = np.trapz(br_psd_interp[peak_indices], br_psd_freqs_interp[peak_indices])

        self.br_coherence = peak_power/total_power

    def update_acc_vectors(self, acc):
        # Update the gravity acc estimate (intialised to the first value)
        if np.isnan(self.acc_gravity).any():
            self.acc_gravity = acc
        else:
            self.acc_gravity = self.GRAVITY_ALPHA*self.acc_gravity + (1-self.GRAVITY_ALPHA)*acc

        # Unbias and denoise the acceleration
        acc_zero_centred = acc - self.acc_gravity
        self.acc_zero_centred_exp_mean = self.ACC_MEAN_ALPHA*self.acc_zero_centred_exp_mean + (1-self.ACC_MEAN_ALPHA)*acc_zero_centred

    def update_breathing_cycle(self):
        # Returns new_breathing_cycle

        self.breath_cycle_ids = self.breath_cycle_ids - 1
        self.breath_cycle_ids[self.breath_cycle_ids < -1] = -1

        current_br_phase = np.sign(self.breath_acc_hist[-1])

        # Exit if the phase hasn't changed or is non-negative
        if current_br_phase == self.br_last_phase or current_br_phase >= 0:
            self.br_last_phase = current_br_phase
            return 0

        # Calculate the breathing rate
        self.current_br = 60.0 / (self.breath_acc_times[-1] - self.br_times_hist[-1])

        # Filter out high breathing rates
        if self.current_br > self.BR_MAX_FILTER:
            return 0 

        # Save the index of the end of the cycle, the point of descending zero-crossing
        self.breath_cycle_ids = np.roll(self.breath_cycle_ids, -1)
        self.breath_cycle_ids[-1] = self.BR_ACC_HIST_SIZE - 1

        self.br_last_phase = current_br_phase

        if self.breath_cycle_ids[-2] < 0:
            return 0
        else: 
            return 1

    def update_breathing_acc(self, t):
        # Returns new_breathing_acc

        if t - self.t_last_breath_acc_update > 1/self.BR_ACC_SAMPLE_RATE:
            self.breath_acc_hist = np.roll(self.breath_acc_hist, -1)
            self.breath_acc_hist[-1] = np.dot(self.acc_zero_centred_exp_mean, self.acc_principle_axis)
            self.breath_acc_times = np.roll(self.breath_acc_times, -1)
            self.breath_acc_times[-1] = t
            self.t_last_breath_acc_update = t
            return 1
        else:  
            return 0

    def get_breath_circle_coords(self):
        
        if ~np.isnan(self.breath_acc_hist[-1]):
            self.breathing_circle_radius = 0.7*self.breath_acc_hist[-1] + (1-0.7)*self.breathing_circle_radius
        else: 
            self.breathing_circle_radius = -0.5
        self.breathing_circle_radius = np.min([np.max([self.breathing_circle_radius + 0.5, 0]), 1])

        x = self.breathing_circle_radius * self.pacer.cos_theta
        y = self.breathing_circle_radius * self.pacer.sin_theta
        return (x, y)

    def handle_acc_callback(self, data):
        # Get the latest sensor data
        t = data[0]
        acc = data[1:]

        # Update the acceleration vectors
        self.update_acc_vectors(acc)

        # Update breathing acceleration history
        new_breathing_acc = self.update_breathing_acc(t)

        # Update the breathing acceleration history
        if new_breathing_acc:
            self.update_breathing_spectrum()
            new_breathing_cycle = self.update_breathing_cycle()
            
            if new_breathing_cycle:
                self.update_breathing_rate()


    