from .HistoryBuffer import HistoryBuffer
import numpy as np
from scipy import signal

def ibi_to_hr(ibi):
    return 60.0/(ibi/1000.0)

def calculate_rmssd(ibi, ibi_shifted):    
    return np.sqrt(np.mean((ibi - ibi_shifted)**2))

def calculate_maxmin(ibi):
    return np.max(ibi) - np.min(ibi)

def calculate_sdnn(ibi):
    return np.std(ibi, ddof=1)

class HrvAnalyser:
    def __init__(self):
        self.IBI_MIN_FILTER = 300 # ms
        self.IBI_MAX_FILTER = 1600 # ms
        self.HRV_MIN_FILTER = 0.2 # percentage allowable of last two HRV values

        self.ibi_latest_phase_duration = 0
        self.ibi_last_phase = 0
        self.ibi_last_extreme = 0
        
        self.ibi_history = HistoryBuffer(1500)
        self.hr_history = HistoryBuffer(500)

        self.hrv_history = HistoryBuffer(500)
        self.rmssd_history = HistoryBuffer(500)
        self.maxmin_history = HistoryBuffer(500)
        self.sdnn_history = HistoryBuffer(500)
        self.nn50_history = HistoryBuffer(500)
        self.pnn50_history = HistoryBuffer(500)
        self.coherence_history = HistoryBuffer(500)

        self.ibi_values_interp_hist = [] # Interpolated IBI values
        self.ibi_times_interp_hist = [] # Interpolated IBI times
        self.hrv_psd_freqs_hist = []
        self.hrv_psd_values_hist = []

        self.hr_coherence = np.nan

    def update(self, t, ibi):
        '''
        Updates the history of inter-beat-interval and heart rate
        Update heart rate variability when there is a maximum
        '''
        if ibi < self.IBI_MIN_FILTER or ibi > self.IBI_MAX_FILTER:
            return
        
        hr = ibi_to_hr(ibi)
        self.ibi_history.update(t, ibi) # TODO: Handle multiple points arriving at the same time
        self.hr_history.update(t, hr)

        # Update duration and determine the current phase
        self.ibi_latest_phase_duration += ibi
        current_ibi_phase = np.sign(ibi - self.ibi_history.values[-2])
        
        # Exit if the phase is constant or zero
        if current_ibi_phase == 0 or current_ibi_phase == self.ibi_last_phase:
            return

        # Calculate latest HRV and phase duration
        current_ibi_extreme = self.ibi_history.values[-2]
        latest_hrv = abs(self.ibi_last_extreme - current_ibi_extreme)
        seconds_current_phase = np.ceil(self.ibi_latest_phase_duration / 1000.0)

        # Exit if the HRV is too low
        if latest_hrv < self.HRV_MIN_FILTER*(np.amin(self.hrv_history.values[-2:])):
            print(f"Rejected low HRV value")
            return

        # Update HRV and IBI history
        self.hrv_history.update(t, latest_hrv)
        
        self.ibi_latest_phase_duration = 0
        self.ibi_last_extreme = current_ibi_extreme
        self.ibi_last_phase = current_ibi_phase

    def update_breath_by_breath_metrics(self, t_range):
        '''
        Updates the metrics calcuated on each breath, rmssd and maxmin
        t_range is the time_range of the breath
        ''' 
        
        ibi_ids = self.ibi_history.times > t_range[0]
        ibi_values = self.ibi_history.values[ibi_ids]
        ibi_values_shifted = np.roll(self.ibi_history.values, 1)[ibi_ids]
        
        rmssd = calculate_rmssd(ibi_values, ibi_values_shifted)
        maxmin = calculate_maxmin(ibi_values)
        sdnn = calculate_sdnn(ibi_values)

        self.rmssd_history.update(t_range[1], rmssd)
        self.maxmin_history.update(t_range[1], maxmin)
        self.sdnn_history.update(t_range[1], sdnn)

    def update_coherence(self):
        '''
        Updates the coherence score, calculated based on the frequency spectrum of heart rate
        '''
        # Taking only last 30 seconds
        ids = self.ibi_history.times > (self.ibi_history.times[-1] - 30) # Hardcode 30 seconds
        ids = np.logical_and(ids, ~np.isnan(self.ibi_history.values))
        
        # Interpolate with fixed interval
        values = self.ibi_history.values[ids]
        times = self.ibi_history.times[ids]
        t_start = times[0] 
        t_end = times[-1]
        dt = 60.0/90.0 # Assume a max of 90 bpm, maximum of 0.75 Hz
        self.ibi_times_interp_hist = np.arange(t_start, t_end+dt, dt)
        self.ibi_values_interp_hist = np.interp(self.ibi_times_interp_hist, times, values)
        
        # Calculate HRV spectrum
        self.hrv_psd_freqs_hist, self.hrv_psd_values_hist = signal.periodogram(self.ibi_values_interp_hist, fs=1/dt, window='hann', detrend='linear')
        self.hrv_psd_values_hist /= np.sum(self.hrv_psd_values_hist)

        # Interpolating the power spectral density, to get sub-bin integration
        hrv_psd_freqs_interp = np.arange(self.hrv_psd_freqs_hist[0], self.hrv_psd_freqs_hist[-1], 0.005)
        hrv_psd_interp = np.interp(hrv_psd_freqs_interp, self.hrv_psd_freqs_hist, self.hrv_psd_values_hist)
        
        # Calculating total power and peak power
        peak_freq = hrv_psd_freqs_interp[np.argmax(hrv_psd_interp)]
        peak_indices = np.where((hrv_psd_freqs_interp >= peak_freq - 0.015) & (hrv_psd_freqs_interp <= peak_freq + 0.015)) # 0.03 Hz around the peak is recommended by R. McCraty
        peak_power = np.trapz(hrv_psd_interp[peak_indices], hrv_psd_freqs_interp[peak_indices])
        total_power = np.trapz(hrv_psd_interp, hrv_psd_freqs_interp)

        self.hr_coherence = 10*peak_power/(total_power - peak_power)

        self.coherence_history.update(t_end, self.hr_coherence)

    def update_nn50_metrics(self):
        # Taking only last 30 seconds
        ids = self.ibi_history.times > (self.ibi_history.times[-1] - 30) # Hardcode 30 seconds
        ids = np.logical_and(ids, ~np.isnan(self.ibi_history.values))

        ibi_values = self.ibi_history.values[ids]
        ibi_values_shifted = np.roll(ibi_values, -1)

        nn50 = np.sum(np.abs(ibi_values[:-1] - ibi_values_shifted[:-1]) > 50)
        pnn50 = (nn50 / len(ibi_values[:-1]))*100

        self.nn50_history.update(self.ibi_history.times[-1], nn50)
        self.pnn50_history.update(self.ibi_history.times[-1], pnn50)

    def get_ibi_sub_history(self, start_time, end_time):
        '''
        Returns the ibi_history between start_time and end_time in epoch seconds
        '''
        sub_history = self.ibi_history.get_sub_buffer(start_time, end_time)
        return sub_history