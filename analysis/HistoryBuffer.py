
import numpy as np
import time
from PySide6.QtCore import QPointF
class HistoryBuffer:

    def __init__(self, buffer_size):
        '''
        Rolling history buffer of values, times is in epoch seconds
        '''        
        self.values = np.full(buffer_size, np.nan)
        self.times = np.full(buffer_size, np.nan)
        self.markers = np.full(buffer_size, -1, dtype=int) # To store indices of interest for values/times

    def update(self, new_time, new_value):
        '''
        Adds a new value and timestamp to the end of the buffer, moving every element one step to the left
        The marker indic
        '''
        self.times = np.roll(self.times, -1)
        self.times[-1] = new_time
        self.values = np.roll(self.values, -1)
        self.values[-1] = new_value

        self.markers = self.markers - 1 # Index of marker shifts with the rolling buffers
        self.markers[self.markers < -1] = -1

    def add_marker(self, index):
        '''
        Adds a marker to the specified index
        '''
        self.markers = np.roll(self.markers, -1)
        self.markers[-1] = index

    def get_relative_times(self):
        '''
        Returns the times array as seconds from current time, i.e. 5 seconds in the past is -5
        '''
        return self.times - time.time_ns()/1.0e9

    def get_qpoint_list(self, use_relative_time=True):
        '''
        Returns a list of QPointF, for using with Qseries.replace
        '''
        series = []
        rel_t = self.get_relative_times()
        for i, value in enumerate(self.values):
            if not np.isnan(value):
                series.append(QPointF(rel_t[i], value))
        return series

    def get_qpoint_marker_list(self, use_relative_time=True):
        '''
        Returns a list of QPointF of values at the marker indices
        '''
        series = []
        rel_t = self.get_relative_times()
        for _, marker_id in enumerate(self.markers):
            if marker_id >= 0:
                series.append(QPointF(rel_t[marker_id], self.values[marker_id]))
        return series

    def get_values_range(self, rel_t_range):
        '''
        Returns the range of the values in the specified relative time range
        '''
        rel_t = self.get_relative_times()
        ids = (rel_t > rel_t_range[0]) & (rel_t <= rel_t_range[1])
        if not self.is_empty():
            min = np.floor(np.nanmin(self.values[ids]))
            max = np.ceil(np.nanmax(self.values[ids]))
            return (min, max)        
        else:
            return None

    def is_empty(self):
        return np.isnan(self.values).all()
    
    def n_values(self):
        return np.count_nonzero(~np.isnan(self.values))

    def is_full(self):
        return not np.isnan(self.values).any()

    def get_sub_buffer(self, t_start, t_end):
        '''
        Returns a new HistoryBuffer instance with values and times between t_start and t_end
        '''
        mask = (self.times >= t_start) & (self.times <= t_end)
        sub_values = self.values[mask]
        sub_times = self.times[mask]

        sub_buffer_size = len(sub_values)
        sub_buffer = HistoryBuffer(sub_buffer_size)

        # Add the filtered values and times to the new buffer
        sub_buffer.values[:sub_buffer_size] = sub_values
        sub_buffer.times[:sub_buffer_size] = sub_times

        # Handle markers within the specified range
        sub_buffer.markers = np.full(sub_buffer_size, -1, dtype=int)
        for i, marker in enumerate(self.markers):
            if marker >= 0 and self.times[marker] >= t_start and self.times[marker] <= t_end:
                new_marker_index = np.where(self.times[mask] == self.times[marker])[0][0]
                sub_buffer.markers[new_marker_index] = new_marker_index

        return sub_buffer