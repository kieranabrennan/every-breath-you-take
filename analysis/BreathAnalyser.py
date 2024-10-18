import numpy as np
from .HistoryBuffer import HistoryBuffer
from .utils import exp_moving_average
from scipy import signal

class BreathAnalyser:

    def __init__(self):
        self.breathing_circle_radius = -0.5
        theta = np.linspace(0, 2 * np.pi, 40)
        self.cos_theta = np.cos(theta)
        self.sin_theta = np.sin(theta)

        self.BR_ACC_HIST_SIZE = 10000 # Up to 16 minutes at 10 Hz
        self.BR_HIST_SIZE = 500 

        self.set_analysis_params()
        self.sensor_class = None

        self.BR_MAX_FILTER = 30 # breaths per minute maximum

        self.gravity = np.full(3, np.nan)
        self.acc_filtered = np.zeros(3)
        self.t_last_breath_acc_update = 0
        self.breathing_rate = 0
        self.chest_phase_last = 0
        self.is_end_of_breath = False
        self.start_of_breath_t = np.nan

        self.chest_acc_history = HistoryBuffer(self.BR_ACC_HIST_SIZE) # TODO: Remove history size parameters
        self.br_history = HistoryBuffer(self.BR_HIST_SIZE)
        self.breath_end_ids = np.full(self.BR_HIST_SIZE, -1, dtype=int)
        self.br_psd_freqs_hist = []
        self.br_psd_values_hist = []

    def set_analysis_params_by_sensor_class(self, sensor_class):
        self.sensor_class = sensor_class
        if sensor_class == "PolarH10Client":
            self.set_analysis_params(chest_acc_sample_rate=10, gravity_alpha=0.999, acc_mean_alpha=0.98, chest_axis=np.array([0, 0, 1]))
        elif sensor_class == "CL800Client":
            self.set_analysis_params(chest_acc_sample_rate=10, gravity_alpha=0.99, acc_mean_alpha=0.9, chest_axis=np.array([0, 0, 1]))
        elif sensor_class == "SmartBeltClient":
            self.set_analysis_params(chest_acc_sample_rate=10, gravity_alpha=0.9999, acc_mean_alpha=0.1, chest_axis=np.array([-0.5550, -0.5522, -0.6221]))
        else:
            raise ValueError("Sensor model not valid")

    def set_analysis_params(self, chest_acc_sample_rate=10, gravity_alpha=0.999, acc_mean_alpha=0.98, chest_axis=np.array([0, 0, 1])):
        self.CHEST_ACC_SAMPLE_RATE = chest_acc_sample_rate # Hz, rate to subsample breathing acceleration
        self.GRAVITY_ALPHA = gravity_alpha # Exponential mean filter for gravity
        self.ACC_MEAN_ALPHA = acc_mean_alpha # Exponential mean filter for noise
        self.chest_axis = chest_axis # Positive z-axis is the direction out of sensor unit (away from chest)

    def update_chest_acc(self, time, acc):
        '''
        Updates the chest acceleration history, and checks for end of breath
        Inputs: time: time of sample, acc: accelerometer sample (x,y,z)
        If it is the end of the breath, adds to history, updates is_end_of_breath
        '''
        # Remove gravity and filter
        self.gravity = exp_moving_average(self.gravity, acc, self.GRAVITY_ALPHA) if not np.isnan(self.gravity).any() else acc 
        acc_unbiased = acc - self.gravity
        self.acc_filtered = exp_moving_average(self.acc_filtered, acc_unbiased, self.ACC_MEAN_ALPHA)

        # Subsampling for Polar
        if self.sensor_class == "PolarH10" or self.sensor_class == "SmartBelt":
            time_elapsed = time - self.t_last_breath_acc_update
            if time_elapsed < 1.0/self.CHEST_ACC_SAMPLE_RATE:
                self.is_end_of_breath = False
                return # Not sampling chest acc this cycle
            self.t_last_breath_acc_update = time

        # Updating chest expansion
        chest_acc = np.dot(self.acc_filtered, self.chest_axis)
        self.chest_acc_history.update(time, chest_acc)

        # Check for breath (descending zero-crossing)
        chest_phase = np.sign(chest_acc)
        if chest_phase == self.chest_phase_last or chest_phase >= 0:
            self.is_end_of_breath = False
            self.chest_phase_last = chest_phase
            return
        self.chest_phase_last = chest_phase

        # Calculate breathing rate
        breathing_rate = 60.0 / (time - self.start_of_breath_t)
        self.start_of_breath_t = time
        if breathing_rate > self.BR_MAX_FILTER:
            self.is_end_of_breath = False
            return
        self.is_end_of_breath = True
        
        # Update history
        self.br_history.update(time, breathing_rate)
        self.chest_acc_history.add_marker(self.BR_ACC_HIST_SIZE-1)

    def get_last_breath_t_range(self):
        '''
        Returns the start and end times (epoch s) of the last full breath
        '''
        return (self.br_history.times[-2], self.br_history.times[-1])

    def get_breath_circle_coords(self):
        '''
        Returns the x,y coordinates of a circle whos radius tracks chest acc
        TODO: Move this to a visualisation widget
        '''
        if not self.chest_acc_history.is_empty():
            self.breathing_circle_radius = 0.7*self.chest_acc_history.values[-1] + (1-0.7)*self.breathing_circle_radius
        else: 
            self.breathing_circle_radius = -0.5
        self.breathing_circle_radius = np.min([np.max([self.breathing_circle_radius + 0.5, 0]), 1])

        x = self.breathing_circle_radius * self.cos_theta
        y = self.breathing_circle_radius * self.sin_theta
        return (x, y)

    def update_breathing_spectrum(self):
        '''
        Updates breathing coherence score, by calculating the frequency spectrum of the breathing signal
        '''

        if self.chest_acc_history.n_values() < 3:
            return

        ids = self.chest_acc_history.times > (self.chest_acc_history.times[-1] - 30) # Hardcode 30 seconds
        values = self.chest_acc_history.values[ids]
        times = self.chest_acc_history.times[ids]
        dt = times[-1] - times[-2]

        # Calculate the spectrum
        self.br_psd_freqs_hist, self.br_psd_values_hist = signal.periodogram(values, fs=1/dt, window='hann', detrend='linear')
        self.br_psd_values_hist /= np.sum(self.br_psd_values_hist)
        
        # Interpolating the power spectral density, to get sub-bin integration
        br_psd_freqs_interp = np.arange(self.br_psd_freqs_hist[0], self.br_psd_freqs_hist[-1], 0.005)
        br_psd_interp = np.interp(br_psd_freqs_interp, self.br_psd_freqs_hist, self.br_psd_values_hist)
        
        # Calculating total power and peak power
        peak_freq = br_psd_freqs_interp[np.argmax(br_psd_interp)]
        total_power = np.trapz(br_psd_interp, br_psd_freqs_interp)
        peak_indices = np.where((br_psd_freqs_interp >= peak_freq - 0.015) & (br_psd_freqs_interp <= peak_freq + 0.015)) # 0.03 Hz around the peak is recommended by R. McCraty
        peak_power = np.trapz(br_psd_interp[peak_indices], br_psd_freqs_interp[peak_indices])

        self.br_coherence = peak_power/total_power

    def get_chest_acc_sub_history(self, start_time, end_time):
        '''
        Returns the chest_acc_history between start_time and end_time in epoch seconds
        '''
        sub_history = self.chest_acc_history.get_sub_buffer(start_time, end_time)
        return sub_history