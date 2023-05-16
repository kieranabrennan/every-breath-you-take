import os
os.environ['QT_API'] = 'PySide6'
os.environ['QT_LOGGING_RULES'] = 'qt.pointer.dispatch=false' # Disable pointer logging

import sys
import asyncio
from PySide6.QtCore import QTimer, Qt, QPointF, QMargins, QSize, Property
from PySide6.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QSizePolicy, QSlider
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QScatterSeries, QSplineSeries, QAreaSeries
from PySide6.QtGui import QPen, QColor
from asyncqt import QEventLoop
from PolarH10 import PolarH10, CircularBuffer2D
from bleak import BleakScanner
import time
import numpy as np
import argparse
from Pacer import Pacer

'''
TODO: 
- Plot the pacer rate on the acceleration plot
- Filter small blips in heart rate from the HRV calculation
- Make breathing rate more responsive to fast breathing
- Change the relative seconds arrays to only be calculated with the series is plotted
- Indicate the sample points on the HR and BR plots
- Modularise the historic window arrays
- Exit the program nicely
'''

RED = QColor(200, 30, 45)
YELLOW = QColor(254, 191, 0)
ORANGE = QColor(255, 130, 0)
GREEN = QColor(50, 177, 108)
BLUE = QColor(0, 119, 190)
GRAY = QColor(34, 34, 34)

class PacerWidget(QChartView):
    def __init__(self, x_values=None, y_values=None, color=BLUE):
        super().__init__()

        self.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Fixed,  # enforce self.sizeHint by fixing horizontal (width) policy
                QSizePolicy.Preferred,
            )
        )

        self.plot = QChart()
        self.plot.legend().setVisible(False)
        self.plot.setBackgroundRoundness(0)
        self.plot.setMargins(QMargins(0, 0, 0, 0))

        self.disc_circumference_coord = QSplineSeries()
        if x_values is not None and y_values is not None:
            self._instantiate_series(x_values, y_values)
        self.disk = QAreaSeries(self.disc_circumference_coord)
        self.disk.setColor(color)
        self.plot.addSeries(self.disk)

        self.x_axis = QValueAxis()
        self.x_axis.setRange(-1, 1)
        self.x_axis.setVisible(False)
        self.plot.addAxis(self.x_axis, Qt.AlignBottom)
        self.disk.attachAxis(self.x_axis)

        self.y_axis = QValueAxis()
        self.y_axis.setRange(-1, 1)
        self.y_axis.setVisible(False)
        self.plot.addAxis(self.y_axis, Qt.AlignLeft)
        self.disk.attachAxis(self.y_axis)

        self.setChart(self.plot)

    def _instantiate_series(self, x_values, y_values):
        for x, y in zip(x_values, y_values):
            self.disc_circumference_coord.append(x, y)

    def update_series(self, x_values, y_values):
        for i, (x, y) in enumerate(zip(x_values, y_values)):
            self.disc_circumference_coord.replace(i, x, y)

    def sizeHint(self):
        height = self.size().height()
        return QSize(height, height)  # force square aspect ratio

    def resizeEvent(self, event):
        if self.size().width() != self.size().height():
            self.updateGeometry()  # adjusts geometry based on sizeHint
        return super().resizeEvent(event)

class RollingPlot(QChartView):
    def __init__(self, measurement_type="ACC", parent=None):
        super().__init__(parent)
        self.measurement_type = measurement_type

        self.LINEWIDTH = 2.5
        self.pacer_rate = 6

        # Heart rate chart
        self.chart_hr = QChart()
        self.chart_hr.legend().setVisible(False)
        self.series_hr = QLineSeries()
        pen = QPen(RED)
        pen.setWidth(self.LINEWIDTH)
        self.series_hr.setPen(pen)
        self.series_hr_marker = QScatterSeries()
        self.series_hr_marker.setMarkerSize(5)
        self.series_hr_marker.setBorderColor(Qt.transparent)
        self.series_hr_marker.setColor(GRAY)
        self.axis_hr_x = QValueAxis()
        self.axis_hr_y = QValueAxis()
        self.axis_hr_x.setTitleText("Time (s)")
        self.axis_hr_y.setTitleText("HR (bpm)")
        self.axis_hr_y.setLabelsColor(RED)
        self.axis_hr_y.setTitleBrush(RED)  # Set the font color of the axis title to red

        # Breathing rate
        if self.measurement_type == "ACC":
            self.series_br = QLineSeries()
            pen = QPen(BLUE)
            pen.setWidth(self.LINEWIDTH)
            self.series_br.setPen(pen)
            self.series_br_marker = QScatterSeries()
            self.series_br_marker.setMarkerSize(5)
            self.series_br_marker.setBorderColor(Qt.transparent)
            self.series_br_marker.setColor(GRAY)
            self.axis_hr_y_2 = QValueAxis()
            self.axis_hr_y_2.setTitleText("BR (bpm)")
            self.axis_hr_y_2.setLabelsColor(BLUE)
            self.axis_hr_y_2.setTitleBrush(BLUE) 

        # Acceleration chart
        self.chart_acc = QChart()
        self.chart_acc.legend().setVisible(False)
        if self.measurement_type == "ACC":
            self.series_acc_x = QScatterSeries()
            self.series_acc_x.setMarkerSize(2)
            self.series_acc_x.setBorderColor(Qt.transparent)
            self.series_acc_x.setColor(YELLOW)
            self.series_acc_y = QScatterSeries()
            self.series_acc_y.setMarkerSize(2)
            self.series_acc_y.setBorderColor(Qt.transparent)
            self.series_acc_y.setColor(ORANGE)
            self.series_acc_z = QScatterSeries()
            self.series_acc_z.setMarkerSize(2)
            self.series_acc_z.setBorderColor(Qt.transparent)
            self.series_acc_z.setColor(GREEN)
            self.series_pacer = QLineSeries()
            pen = QPen(BLUE)
            pen.setWidth(self.LINEWIDTH)
            self.series_pacer.setPen(pen)
            self.axis_acc_x = QValueAxis()
            self.axis_acc_y = QValueAxis()
            self.axis_acc_y2 = QValueAxis()
            self.axis_acc_x.setTitleText("Time (s)")
            self.axis_acc_y.setTitleText("Acceleration (m/s)")
            self.axis_acc_y2.setTitleText("Pacer")

            self.series_breath_signal = QLineSeries()
            pen = QPen(BLUE)
            pen.setWidth(self.LINEWIDTH)
            self.series_breath_signal.setPen(pen)
            self.axis_y_breath_signal = QValueAxis()
            self.axis_y_breath_signal.setTitleText("Breath Acc (m/s)")
            self.axis_y_breath_signal.setLabelsColor(BLUE)
            self.axis_y_breath_signal.setTitleBrush(BLUE)

        elif self.measurement_type == "ECG":
            self.series_ecg = QLineSeries()
            pen = QPen(BLUE)
            pen.setWidth(self.LINEWIDTH)
            self.series_ecg.setPen(pen)
            self.axis_acc_x = QValueAxis()
            self.axis_acc_y = QValueAxis()
            self.axis_acc_y.setTitleText("ECG (mV)")
            self.axis_acc_x.setTitleText("Time (s)")

        # Heart rate variability chart
        self.chart_hrv = QChart()
        self.chart_hrv.legend().setVisible(False)
        self.series_hrv = QLineSeries()
        pen = QPen(RED)
        pen.setWidth(self.LINEWIDTH)
        self.series_hrv.setPen(pen)
        self.series_hrv_marker = QScatterSeries()
        self.series_hrv_marker.setMarkerSize(5)
        self.series_hrv_marker.setBorderColor(Qt.transparent)
        self.series_hrv_marker.setColor(GRAY)
        self.axis_hrv_x = QValueAxis()
        self.axis_hrv_y = QValueAxis()
        self.axis_hrv_x.setTitleText("Time (s)")
        self.axis_hrv_y.setTitleText("HRV (ms)")
        self.axis_hrv_y.setLabelsColor(RED)
        self.axis_hrv_y.setTitleBrush(RED) 

        # Breathing target vs measured chart
        self.chart_br_ctrl = QChart()
        self.chart_br_ctrl.legend().setVisible(False)
        self.chart_br_ctrl.setMargins(QMargins(0,0,0,0))
        self.series_br_ctrl = QScatterSeries()
        self.series_br_ctrl.setMarkerSize(5)
        self.series_br_ctrl.setBorderColor(Qt.transparent)
        self.series_br_ctrl.setColor(BLUE)
        self.axis_br_ctrl_x = QValueAxis()
        self.axis_br_ctrl_y = QValueAxis()
        self.axis_br_ctrl_x.setTitleText("Target BR (bpm)")
        self.axis_br_ctrl_y.setTitleText("Measured BR (bpm)")

        # HRV vs BR chart
        self.chart_hrv_br = QChart()
        self.chart_hrv_br.legend().setVisible(False)
        self.chart_hrv_br.setMargins(QMargins(0,0,0,0))
        self.series_hrv_br = QScatterSeries()
        self.series_hrv_br.setMarkerSize(5)
        self.series_hrv_br.setBorderColor(Qt.transparent)
        self.series_hrv_br.setColor(RED)
        self.axis_hrv_br_x = QValueAxis()
        self.axis_hrv_br_y = QValueAxis()
        self.axis_hrv_br_x.setTitleText("BR (bpm)")
        self.axis_hrv_br_y.setTitleText("HRV (ms)")

        self.pacer_slider = QSlider(Qt.Vertical)
        self.pacer_slider.setStyleSheet("""QSlider {
            border: 1px solid #aaa;
        }
        """)
        self.pacer_slider.setTickPosition(QSlider.TicksBelow)
        self.pacer_slider.setTracking(False)
        self.pacer_slider.setRange(1,10)
        self.pacer_slider.setValue(self.pacer_rate)
        self.pacer_slider.valueChanged.connect(self.update_pacer_rate)

        self.init_charts()

        self.IBI_HIST_SIZE = 100
        self.ibi_values_hist = np.full(self.IBI_HIST_SIZE, 1000)
        self.ibi_times_hist = np.arange(-self.IBI_HIST_SIZE, 0) # relative seconds
        self.ibi_times_hist_rel_s = np.full(self.IBI_HIST_SIZE, np.nan) # relative seconds
        self.hr_values_hist = np.full(self.IBI_HIST_SIZE, np.nan)
        self.HRV_HIST_SIZE = 50
        self.ibi_latest_phase_duration = 0
        self.ibi_last_phase = 0
        self.ibi_last_extreme = 0
        self.hrv_values_hist = np.full(self.HRV_HIST_SIZE, np.nan)
        self.hrv_times_hist = np.arange(-self.HRV_HIST_SIZE, 0) # relative seconds

        self.ACC_HIST_SIZE = 12000 # Raw data comes in at 200 Hz
        self.acc_hist = np.full((self.ACC_HIST_SIZE, 3), np.nan)
        self.acc_times_hist = np.full(self.ACC_HIST_SIZE, np.nan) # epoch seconds
        self.acc_times_hist_rel_s = np.full(self.ACC_HIST_SIZE, np.nan) # relative seconds
        self.acc_hist_last_plotted_id = -1
        self.GRAVITY_ALPHA = 0.999
        self.acc_gravity = np.zeros(3)
        self.ACC_MEAN_ALPHA = 0.995
        self.acc_norm_exp_mean = 0
        self.acc_norm_hist = np.full(self.ACC_HIST_SIZE, np.nan)
        self.acc_norm_times = np.full(self.ACC_HIST_SIZE, np.nan)
        self.acc_norm_times_rel_s = np.full(self.ACC_HIST_SIZE, np.nan)
        self.t_last_acc = 0
        self.t_last_acc_norm = 0
        self.pacer_values_hist = np.full((self.ACC_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist = np.full((self.ACC_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist_rel_s = np.full(self.ACC_HIST_SIZE, np.nan) # relative seconds
        
        self.BR_HIST_SIZE = 60
        self.br_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        self.br_times_hist = np.full(self.BR_HIST_SIZE, np.nan) # relative seconds
        self.br_times_hist_rel_s = np.full(self.BR_HIST_SIZE, np.nan) # relative seconds
        self.br_latest_halfphase_duration = 0
        self.br_last_phase = 0
        self.br_pace_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        self.hrv_br_interp_values_hist = np.full(self.BR_HIST_SIZE, np.nan)
        
        self.ECG_HIST_SIZE = 3000 # Raw data comes in at 130 Hz
        self.ecg_hist = np.full(self.ECG_HIST_SIZE, np.nan)
        self.ecg_times_hist = np.full(self.ECG_HIST_SIZE, np.nan) # epoch seconds
        self.ecg_times_hist_rel_s = np.full(self.ECG_HIST_SIZE, np.nan) # relative seconds 
        
        self.polar_device = None

    def init_charts(self):
        
        # Initialize second chart
        if self.measurement_type == "ACC":

            # Acceleration chart
            self.chart_acc.addSeries(self.series_acc_x)
            self.chart_acc.addSeries(self.series_acc_y)
            self.chart_acc.addSeries(self.series_acc_z)
            self.chart_acc.addSeries(self.series_pacer)
            self.chart_acc.addAxis(self.axis_acc_x, Qt.AlignBottom)
            self.chart_acc.addAxis(self.axis_acc_y, Qt.AlignLeft)
            self.chart_acc.addAxis(self.axis_acc_y2, Qt.AlignRight)
            self.series_acc_x.attachAxis(self.axis_acc_x)
            self.series_acc_x.attachAxis(self.axis_acc_y)
            self.series_acc_y.attachAxis(self.axis_acc_x)
            self.series_acc_y.attachAxis(self.axis_acc_y)
            self.series_acc_z.attachAxis(self.axis_acc_x)
            self.series_acc_z.attachAxis(self.axis_acc_y)
            self.series_pacer.attachAxis(self.axis_acc_x)
            self.series_pacer.attachAxis(self.axis_acc_y2)
            self.axis_acc_x.setTickCount(10)
            self.axis_acc_y.setRange(-1, 1)
            self.axis_acc_y2.setRange(0, 1)
            self.axis_acc_x.setRange(-60, 0)

        elif self.measurement_type == "ECG":
            self.chart_acc.addSeries(self.series_ecg)
            self.chart_acc.addAxis(self.axis_acc_x, Qt.AlignBottom)
            self.chart_acc.addAxis(self.axis_acc_y, Qt.AlignLeft)
            self.series_ecg.attachAxis(self.axis_acc_x)
            self.series_ecg.attachAxis(self.axis_acc_y)
            self.axis_acc_x.setTickCount(10)
            self.axis_acc_y.setRange(-600, 1800)
            self.axis_acc_x.setRange(-60, 0)
        
        # Heart rate chart
        self.chart_hr.addSeries(self.series_hr)
        self.chart_hr.addSeries(self.series_hr_marker)
        self.chart_hr.addAxis(self.axis_hr_x, Qt.AlignBottom)
        self.chart_hr.addAxis(self.axis_hr_y, Qt.AlignLeft)
        self.series_hr.attachAxis(self.axis_hr_x)
        self.series_hr.attachAxis(self.axis_hr_y)
        self.series_hr_marker.attachAxis(self.axis_hr_x)
        self.series_hr_marker.attachAxis(self.axis_hr_y)
        self.axis_hr_x.setTickCount(10)
        self.axis_hr_y.setRange(50, 100)
        self.axis_hr_x.setRange(-60, 0)

        if self.measurement_type == "ACC":
            self.chart_hr.addSeries(self.series_breath_signal)
            self.chart_hr.addAxis(self.axis_y_breath_signal, Qt.AlignRight)
            self.series_breath_signal.attachAxis(self.axis_hr_x)
            self.series_breath_signal.attachAxis(self.axis_y_breath_signal)
            self.axis_y_breath_signal.setRange(-1, 1)

        # Heart rate variability chart
        self.chart_hrv.addSeries(self.series_hrv)
        self.chart_hrv.addSeries(self.series_hrv_marker)    
        self.chart_hrv.addAxis(self.axis_hrv_x, Qt.AlignBottom)
        self.chart_hrv.addAxis(self.axis_hrv_y, Qt.AlignLeft)
        self.series_hrv.attachAxis(self.axis_hrv_x)
        self.series_hrv.attachAxis(self.axis_hrv_y)
        self.series_hrv_marker.attachAxis(self.axis_hrv_x)
        self.series_hrv_marker.attachAxis(self.axis_hrv_y)
        self.axis_hrv_x.setTickCount(10)
        self.axis_hrv_y.setRange(0, 250)
        self.axis_hrv_x.setRange(-60, 0)

        if self.measurement_type == "ACC":
            # Breathing rate on HRV chart
            self.chart_hrv.addSeries(self.series_br)
            self.chart_hrv.addSeries(self.series_br_marker)
            self.chart_hrv.addAxis(self.axis_hr_y_2, Qt.AlignRight)
            self.series_br.attachAxis(self.axis_hrv_x)
            self.series_br.attachAxis(self.axis_hr_y_2)
            self.series_br_marker.attachAxis(self.axis_hrv_x)
            self.series_br_marker.attachAxis(self.axis_hr_y_2)
            self.axis_hr_y_2.setRange(0, 30)

        # Breathing target vs measured
        self.chart_br_ctrl.addSeries(self.series_br_ctrl)
        self.chart_br_ctrl.addAxis(self.axis_br_ctrl_x, Qt.AlignBottom)
        self.chart_br_ctrl.addAxis(self.axis_br_ctrl_y, Qt.AlignLeft)
        self.series_br_ctrl.attachAxis(self.axis_br_ctrl_x)
        self.series_br_ctrl.attachAxis(self.axis_br_ctrl_y)
        self.axis_br_ctrl_x.setRange(0,10)
        self.axis_br_ctrl_y.setRange(0,10)

        # HRV vs BR
        self.chart_hrv_br.addSeries(self.series_hrv_br)
        self.chart_hrv_br.addAxis(self.axis_hrv_br_x, Qt.AlignBottom)
        self.chart_hrv_br.addAxis(self.axis_hrv_br_y, Qt.AlignLeft)
        self.series_hrv_br.attachAxis(self.axis_hrv_br_x)
        self.series_hrv_br.attachAxis(self.axis_hrv_br_y)
        self.axis_hrv_br_x.setRange(0,10)
        self.axis_hrv_br_y.setRange(0,250)
        
        # Create a layout
        layout = QVBoxLayout()
        
        acc_widget = QChartView(self.chart_acc)
        br_ctrl_widget = QChartView(self.chart_br_ctrl)
        hr_widget = QChartView(self.chart_hr)
        hrv_br_widget = QChartView(self.chart_hrv_br)        
        hrv_widget = QChartView(self.chart_hrv)

        self.pacer = Pacer()
        self.pacer_widget = PacerWidget(*self.pacer.update(self.pacer_rate))

        # Create QChartView widgets for both charts
        hlayout0 = QHBoxLayout()
        hlayout0.addWidget(self.pacer_slider)
        hlayout0.addWidget(self.pacer_widget)
        hlayout0.addWidget(acc_widget)
        
        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(br_ctrl_widget, stretch=1)
        hlayout1.addWidget(hr_widget, stretch=3)
        
        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(hrv_br_widget, stretch=1)
        hlayout2.addWidget(hrv_widget, stretch=3)

        # Add chart views to the layout
        layout.addLayout(hlayout0, stretch=1)
        layout.addLayout(hlayout1, stretch=1)
        layout.addLayout(hlayout2, stretch=1)

        # Set the layout for the QWidget
        self.setLayout(layout)

        # Kick off the timer
        self.update_series_timer = QTimer()
        self.update_series_timer.timeout.connect(self.update_series)
        self.update_series_timer.setInterval(100)

        self.update_acc_series_timer = QTimer()
        self.update_acc_series_timer.timeout.connect(self.update_acc_series)
        self.update_acc_series_timer.setInterval(50)
        
        self.pacer_timer = QTimer()
        self.pacer_timer.setInterval(50)  # ms (20 Hz)
        self.pacer_timer.timeout.connect(self.plot_pacer_disk)

        self.update_acc_series_timer.start()
        self.update_series_timer.start()
        self.pacer_timer.start()

    def update_pacer_rate(self):
        self.pacer_rate = self.pacer_slider.value()

    def plot_pacer_disk(self):
        coordinates = self.pacer.update(self.pacer_rate)
        self.pacer_widget.update_series(*coordinates)

        self.pacer_values_hist = np.roll(self.pacer_values_hist, -1)
        self.pacer_values_hist[-1] = np.linalg.norm([coordinates[0][0],coordinates[1][0]])
        self.pacer_times_hist = np.roll(self.pacer_times_hist, -1)
        self.pacer_times_hist[-1] = time.time_ns()/1.0e9

    async def connect_polar(self):

        polar_device_found = False
        print("Looking for Polar device...")
        while not polar_device_found:

            devices = await BleakScanner.discover()
            print(f"Found {len(devices)} BLE devices")
            for device in devices:
                if device.name is not None and "Polar" in device.name:
                    polar_device_found = True
                    print(f"Found Polar device")
                    break
            if not polar_device_found:
                print("Polar device not found, retrying in 1 second")
                await asyncio.sleep(1)

        self.polar_device = PolarH10(device)
        await self.polar_device.connect()
        await self.polar_device.get_device_info()
        await self.polar_device.print_device_info()
        self.session_start_t = time.time_ns()/1.0e9

    async def disconnect_polar(self):
        await self.polar_device.disconnect()

    def update_hrv(self):
        self.ibi_latest_phase_duration += self.ibi_values_hist[-1]
        # 1: IBI rises, -1: IBI falls, 0: IBI constant
        current_ibi_phase = np.sign(self.ibi_values_hist[-1] - self.ibi_values_hist[-2])
        if current_ibi_phase == 0:
            return
        if current_ibi_phase == self.ibi_last_phase:
            return

        current_ibi_extreme = self.ibi_values_hist[-2]
        latest_hrv = abs(self.ibi_last_extreme - current_ibi_extreme)
        self.hrv_values_hist = np.roll(self.hrv_values_hist, -1)
        self.hrv_values_hist[-1] = latest_hrv

        seconds_current_phase = np.ceil(self.ibi_latest_phase_duration / 1000.0)
        self.hrv_times_hist = self.hrv_times_hist - seconds_current_phase
        self.hrv_times_hist = np.roll(self.hrv_times_hist, -1)
        self.hrv_times_hist[-1] = 0
        
        self.ibi_latest_phase_duration = 0

        self.ibi_last_extreme = current_ibi_extreme
        self.ibi_last_phase = current_ibi_phase

    async def update_ibi(self):
        await self.polar_device.start_hr_stream()

        while True:
            await asyncio.sleep(0.01)
            
            t_now = time.time_ns()/1.0e9
            # Updating IBI history
            while not self.polar_device.ibi_queue_is_empty():
                t, ibi = self.polar_device.dequeue_ibi() # t is when value was added to the queue
                
                self.ibi_values_hist = np.roll(self.ibi_values_hist, -1)
                self.ibi_values_hist[-1] = ibi
                self.hr_values_hist = 60.0/(self.ibi_values_hist/1000.0)

                self.ibi_times_hist = -np.flip(np.cumsum(np.flip(self.ibi_values_hist)))/1000.0 # seconds relative to the last value
                self.ibi_times_hist = np.roll(self.ibi_times_hist, -1)
                self.ibi_times_hist[-1] = 0
                
                self.update_hrv()

    def update_breathing_rate(self):
        current_br_phase = np.sign(self.acc_norm_hist[-1] - self.acc_norm_hist[-2])
        
        if current_br_phase <= 0:
            self.br_last_phase = current_br_phase
            return
        if current_br_phase == self.br_last_phase:
            return
    
        if np.isnan(self.br_times_hist[-1]):
            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = 0

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = 0

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.acc_norm_times[-1]
        else:
            seconds_current_halfphase = self.acc_norm_times[-1] - self.br_times_hist[-1]
            current_breathing_rate = 60.0 / (seconds_current_halfphase*2)

            self.br_values_hist = np.roll(self.br_values_hist, -1)
            self.br_values_hist[-1] = current_breathing_rate

            self.br_pace_values_hist = np.roll(self.br_pace_values_hist, -1)
            self.br_pace_values_hist[-1] = self.pacer_rate  

            self.hrv_br_interp_values_hist = np.roll(self.hrv_br_interp_values_hist, -1)
            self.hrv_br_interp_values_hist[-1] = self.hrv_values_hist[-1]

            self.br_times_hist = np.roll(self.br_times_hist, -1)
            self.br_times_hist[-1] = self.acc_norm_times[-1]

        self.br_times_hist_rel_s = self.br_times_hist - time.time_ns()/1.0e9

        self.br_last_phase = current_br_phase


    async def update_pmd(self): # pmd: polar measurement data
        
        if self.measurement_type == "ACC":

            await self.polar_device.start_acc_stream()
            
            while True:
                # await asyncio.sleep(0.01)
                await asyncio.sleep(0.01)
                
                # Updating the acceleration history
                while not self.polar_device.acc_queue_is_empty():
                    t, row = self.polar_device.dequeue_acc()
                    t_now = time.time_ns()/1.0e9

                    self.acc_gravity = self.GRAVITY_ALPHA*self.acc_gravity + (1-self.GRAVITY_ALPHA)*row
                    acc_no_gravity = row - self.acc_gravity
                    
                    if (t - self.t_last_acc) > 0.05: # subsampling
                        self.acc_hist = np.roll(self.acc_hist, -1, axis=0)
                        self.acc_hist[-1, :] = acc_no_gravity
                        self.acc_times_hist = np.roll(self.acc_times_hist, -1)
                        self.acc_times_hist[-1] = t
                        self.t_last_acc = t
                
                    self.acc_norm_exp_mean = self.ACC_MEAN_ALPHA*self.acc_norm_exp_mean + (1-self.ACC_MEAN_ALPHA)*np.linalg.norm(acc_no_gravity)
                    
                    if (t - self.t_last_acc_norm) > 0.1: # subsampling
                        self.acc_norm_hist = np.roll(self.acc_norm_hist, -1)
                        self.acc_norm_hist[-1] = self.acc_norm_exp_mean
                        self.acc_norm_times = np.roll(self.acc_norm_times, -1)
                        self.acc_norm_times[-1] = t
                        
                        self.t_last_acc_norm = t
                    
                    self.update_breathing_rate()

        
        elif self.measurement_type == "ECG":

            await self.polar_device.start_ecg_stream()

            while True:
                await asyncio.sleep(0.01)
                
                t_now = time.time_ns()/1.0e9
                
                # Updating the ECG history
                while not self.polar_device.ecg_queue_is_empty():
                    t, value = self.polar_device.dequeue_ecg()
                    self.ecg_times_hist = np.roll(self.ecg_times_hist, -1)
                    self.ecg_times_hist[-1] = t
                    
                    self.ecg_hist = np.roll(self.ecg_hist, -1)
                    self.ecg_hist[-1] = value
                
                self.ecg_times_hist_rel_s = self.ecg_times_hist - t_now 

    def update_acc_series(self):
        
        # Acceleration plot
        series_acc_x_new = []
        series_acc_y_new = []
        series_acc_z_new = []

        self.acc_times_hist_rel_s = self.acc_times_hist - time.time_ns()/1.0e9
        self.pacer_times_hist_rel_s = self.pacer_times_hist - time.time_ns()/1.0e9
        
        for i, value in enumerate(self.acc_times_hist_rel_s):
            if not np.isnan(value):
                series_acc_x_new.append(QPointF(value, self.acc_hist[i, 0]))
                series_acc_y_new.append(QPointF(value, self.acc_hist[i, 1]))
                series_acc_z_new.append(QPointF(value, self.acc_hist[i, 2]))

        if series_acc_x_new:
            self.series_acc_x.replace(series_acc_x_new)
            self.series_acc_y.replace(series_acc_y_new)
            self.series_acc_z.replace(series_acc_z_new)

        series_pacer_new = []
        for i, value in enumerate(self.pacer_times_hist_rel_s):
            if not np.isnan(value):
                series_pacer_new.append(QPointF(value, self.pacer_values_hist[i]))
                
        if series_pacer_new:
            self.series_pacer.replace(series_pacer_new)

    def update_series(self):

        series_hr_new = []
        for i, value in enumerate(self.hr_values_hist):
            if not np.isnan(value):
                series_hr_new.append(QPointF(self.ibi_times_hist[i], value))
        self.series_hr.replace(series_hr_new)
        self.series_hr_marker.replace(series_hr_new)

        if self.measurement_type == "ACC":

            self.acc_norm_times_rel_s = self.acc_norm_times - time.time_ns()/1.0e9
            
            series_2_norm_new = []
            for i, value in enumerate(self.acc_norm_times_rel_s):
                if not np.isnan(value):
                    series_2_norm_new.append(QPointF(value, self.acc_norm_hist[i]))
            self.series_breath_signal.replace(series_2_norm_new)
            
            # Breathing rate plot
            series_br_new = []
            for i, value in enumerate(self.br_values_hist):
                if not np.isnan(value):
                    series_br_new.append(QPointF(self.br_times_hist_rel_s[i], value))
            self.series_br.replace(series_br_new)
            self.series_br_marker.replace(series_br_new)
        
        elif self.measurement_type == "ECG":
            # ECG plot
            series_2_new = []
            for i, value in enumerate(self.ecg_times_hist_rel_s):
                if not np.isnan(value):
                    series_2_new.append(QPointF(value, self.ecg_hist[i]))
            
            self.series_ecg.replace(series_2_new)     

        # HRV plot
        series_hrv_new = []
        for i, value in enumerate(self.hrv_values_hist):
            if not np.isnan(value):
                series_hrv_new.append(QPointF(self.hrv_times_hist[i], value))
        self.series_hrv.replace(series_hrv_new)
        self.series_hrv_marker.replace(series_hrv_new)       

        # Breathing control plot
        series_br_ctrl_new = []
        for i, value in enumerate(self.br_values_hist):
            if not np.isnan(value):
                series_br_ctrl_new.append(QPointF(self.br_pace_values_hist[i], value))
        self.series_br_ctrl.replace(series_br_ctrl_new)

        # HRV vs BR plot
        series_hrv_br_new = []
        for i, value in enumerate(self.br_values_hist):
            if not np.isnan(value):
                series_hrv_br_new.append(QPointF(value, self.hrv_br_interp_values_hist[i]))
        self.series_hrv_br.replace(series_hrv_br_new)


    async def main(self):
        await self.connect_polar()
        await asyncio.gather(self.update_ibi(), self.update_pmd())
    
def get_arguments():
    parser = argparse.ArgumentParser(description="Real-time Breathing Feedback with the Polar H10 Heart Rate Monitor")
    parser.add_argument("measurement_type", choices=["ACC", "ECG"], default="ACC", help="Measurement Type")
    return parser.parse_args()

if __name__ == "__main__":

    args = get_arguments()

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    plot = RollingPlot(args.measurement_type)
    plot.setWindowTitle("Rolling Plot")
    plot.resize(1200, 800)
    plot.show()

    loop.run_until_complete(plot.main())
