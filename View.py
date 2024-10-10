import sys
from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QSlider, QLabel
from PySide6.QtCharts import QChartView, QLineSeries, QScatterSeries, QAreaSeries
from PySide6.QtGui import QPen, QPainter
import time
import numpy as np
import logging
from Model import Model
from sensor import SensorHandler
from views.widgets import CirclesWidget, SquareWidget
from views.charts import create_chart, create_scatter_series, create_line_series, create_spline_series, create_axis
from styles.colours import RED, YELLOW, ORANGE, GREEN, BLUE, GRAY, GOLD, LINEWIDTH, DOTSIZE_LARGE, DOTSIZE_SMALL
from styles.utils import get_stylesheet

'''
TODO: 
- Abstract the historic series type
- Exit the program nicely
'''

class View(QChartView):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.model = Model()
        self.sensor_handler = SensorHandler()

        self.setStyleSheet(get_stylesheet("styles/style.qss"))

        # Series parameters
        self.UPDATE_SERIES_PERIOD = 100 # ms
        self.UPDATE_BREATHING_SERIES_PERIOD = 50 # ms
        self.UPDATE_PACER_PERIOD = 10 # 20 # ms
        self.PACER_HIST_SIZE = 6000
        self.BREATH_ACC_TIME_RANGE = 60 # s
        self.HR_SERIES_TIME_RANGE = 300 # s
        self.HRV_SERIES_TIME_RANGE = 300 # s

        # Initialisation
        self.pacer_rate = 6

        # Breathing acceleration
        self.chart_acc = create_chart(title='Breathing Acceleration', showTitle=False, showLegend=False)
        self.series_pacer = create_line_series(GOLD, LINEWIDTH)
        self.series_breath_acc = create_line_series(BLUE, LINEWIDTH)
        self.series_breath_cycle_marker = create_scatter_series(GRAY, DOTSIZE_SMALL)
        self.axis_acc_x = create_axis(title=None, tickCount=10, rangeMin=-self.BREATH_ACC_TIME_RANGE, rangeMax=0, labelSize=10, flip=False)
        # self.axis_y_pacer = create_axis(title="Pacer", color=GOLD, rangeMin=-1, rangeMax=1)
        self.axis_y_breath_acc = create_axis("Chest expansion (m/s2)", BLUE, rangeMin=-1, rangeMax=1, labelSize=10)

        # Heart rate chart
        self.chart_hr = create_chart(title='Heart rate', showTitle=False, showLegend=False)
        self.series_hr = create_scatter_series(RED, DOTSIZE_SMALL)
        self.axis_hr_y = create_axis(title="HR (bpm)", color=RED, rangeMin=50, rangeMax=80, labelSize=10)

        # Breathing rate
        self.series_br = create_spline_series(BLUE, LINEWIDTH)
        self.series_br_marker = create_scatter_series(BLUE, DOTSIZE_SMALL)
        self.series_br_marker.setMarkerShape(QScatterSeries.MarkerShapeTriangle)
        self.axis_br_y = create_axis(title="BR (bpm)", color=BLUE, rangeMin=0, rangeMax=20, labelSize=10)
        
        # Heart rate variability chart
        self.chart_hrv = create_chart(title='Heart rate variability', showTitle=False, showLegend=False)
        # self.series_hrv = create_spline_series(RED, LINEWIDTH)
        self.series_maxmin = create_spline_series(RED, LINEWIDTH)
        self.series_maxmin_marker = create_scatter_series(RED, DOTSIZE_SMALL)
        self.axis_hrv_x = create_axis(title=None, tickCount=10, rangeMin=-self.HRV_SERIES_TIME_RANGE, rangeMax=0, labelSize=10)
        self.axis_hrv_y = create_axis(title="HRV (ms)", color=RED, rangeMin=0, rangeMax=250, labelSize=10)

        self.hrv_band_line_0 = QLineSeries()
        self.hrv_band_line_0.append(-self.HRV_SERIES_TIME_RANGE, 0)
        self.hrv_band_line_0.append(0, 0)
        self.hrv_band_line_1 = QLineSeries()
        self.hrv_band_line_1.append(-self.HRV_SERIES_TIME_RANGE, 50)
        self.hrv_band_line_1.append(0, 50)
        self.hrv_band_line_2 = QLineSeries()
        self.hrv_band_line_2.append(-self.HRV_SERIES_TIME_RANGE, 150)
        self.hrv_band_line_2.append(0, 150)
        self.hrv_band_line_3 = QLineSeries()
        self.hrv_band_line_3.append(-self.HRV_SERIES_TIME_RANGE, 2000)
        self.hrv_band_line_3.append(0, 2000)
        self.hrv_band_0 = QAreaSeries(self.hrv_band_line_0, self.hrv_band_line_1)
        self.hrv_band_0.setColor(RED)
        self.hrv_band_0.setOpacity(0.2)
        self.hrv_band_0.setPen(QPen(Qt.NoPen))
        self.hrv_band_1 = QAreaSeries(self.hrv_band_line_1, self.hrv_band_line_2)
        self.hrv_band_1.setColor(YELLOW)
        self.hrv_band_1.setOpacity(0.2)
        self.hrv_band_1.setPen(QPen(Qt.NoPen))
        self.hrv_band_2 = QAreaSeries(self.hrv_band_line_2, self.hrv_band_line_3)
        self.hrv_band_2.setColor(GREEN)
        self.hrv_band_2.setOpacity(0.2)
        self.hrv_band_2.setPen(QPen(Qt.NoPen))

        self.pacer_slider = QSlider(Qt.Horizontal)
        self.pacer_slider.setRange(3*2,10*2)
        self.pacer_slider.setValue(self.pacer_rate*2)
        self.pacer_slider.valueChanged.connect(self.update_pacer_rate)
        
        self.pacer_label = QLabel()
        self.pacer_label.setStyleSheet("QLabel {color: black}")
        self.pacer_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.pacer_label.setText(f"{self.pacer_rate}")
        self.pacer_label.setFixedWidth(40)
        
        # Configure
        self.chart_acc.addSeries(self.series_pacer)
        self.chart_acc.addSeries(self.series_breath_acc)
        self.chart_acc.addSeries(self.series_breath_cycle_marker)
        self.chart_acc.addSeries(self.series_hr)
        self.chart_acc.addAxis(self.axis_acc_x, Qt.AlignBottom)
        self.chart_acc.addAxis(self.axis_y_breath_acc, Qt.AlignRight)
        self.chart_acc.addAxis(self.axis_hr_y, Qt.AlignLeft)
        self.series_pacer.attachAxis(self.axis_acc_x)
        self.series_pacer.attachAxis(self.axis_y_breath_acc)
        self.series_breath_acc.attachAxis(self.axis_acc_x)
        self.series_breath_acc.attachAxis(self.axis_y_breath_acc)
        self.series_breath_cycle_marker.attachAxis(self.axis_acc_x)
        self.series_breath_cycle_marker.attachAxis(self.axis_y_breath_acc)
        self.series_hr.attachAxis(self.axis_acc_x)
        self.series_hr.attachAxis(self.axis_hr_y)

        # Heart rate variability chart
        # self.chart_hrv.addSeries(self.series_hrv)
        self.chart_hrv.addSeries(self.hrv_band_0)
        self.chart_hrv.addSeries(self.hrv_band_1)
        self.chart_hrv.addSeries(self.hrv_band_2)
        self.chart_hrv.addSeries(self.series_maxmin)
        self.chart_hrv.addSeries(self.series_maxmin_marker)
        self.chart_hrv.addAxis(self.axis_hrv_x, Qt.AlignBottom)
        self.chart_hrv.addAxis(self.axis_hrv_y, Qt.AlignLeft)
        self.series_maxmin.attachAxis(self.axis_hrv_x)
        self.series_maxmin.attachAxis(self.axis_hrv_y)
        self.series_maxmin_marker.attachAxis(self.axis_hrv_x)
        self.series_maxmin_marker.attachAxis(self.axis_hrv_y)
        self.hrv_band_0.attachAxis(self.axis_hrv_x)
        self.hrv_band_0.attachAxis(self.axis_hrv_y)
        self.hrv_band_1.attachAxis(self.axis_hrv_x)
        self.hrv_band_1.attachAxis(self.axis_hrv_y)
        self.hrv_band_2.attachAxis(self.axis_hrv_x)
        self.hrv_band_2.attachAxis(self.axis_hrv_y)

        # Breathing rate on HRV chart
        # self.chart_hrv.addSeries(self.series_br)
        self.chart_hrv.addSeries(self.series_br_marker)
        self.chart_hrv.addAxis(self.axis_br_y, Qt.AlignRight)
        # self.series_br.attachAxis(self.axis_hrv_x)
        # self.series_br.attachAxis(self.axis_br_y)
        self.series_br_marker.attachAxis(self.axis_hrv_x)
        self.series_br_marker.attachAxis(self.axis_br_y)

        # Create a layout
        layout = QVBoxLayout()

        acc_widget = QChartView(self.chart_acc)
        acc_widget.setStyleSheet("background-color: transparent;")
        hrv_widget = QChartView(self.chart_hrv)
        hrv_widget.setStyleSheet("background-color: transparent;")
    
        self.circles_widget = CirclesWidget(*self.model.pacer.update(self.pacer_rate), GOLD, BLUE, RED)
        
        acc_widget.setRenderHint(QPainter.Antialiasing)
        hrv_widget.setRenderHint(QPainter.Antialiasing)
        self.circles_widget.setRenderHint(QPainter.Antialiasing)

        sliderLayout = QHBoxLayout()
        sliderLayout.addWidget(self.pacer_label)
        sliderLayout.addWidget(self.pacer_slider)
        sliderLayout.addSpacing(20)
        
        circlesLayout = QVBoxLayout()
        circlesLayout.addWidget(self.circles_widget, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        circlesLayout.addLayout(sliderLayout)

        squareContainer = SquareWidget()
        squareContainer.setLayout(circlesLayout)

        topRowLayout = QHBoxLayout()
        topRowLayout.addWidget(squareContainer, stretch=1)
        topRowLayout.addWidget(acc_widget, stretch=3)

        layout.addLayout(topRowLayout, stretch=1)
        layout.addWidget(hrv_widget, stretch=1)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Kick off the timer
        self.update_series_timer = QTimer()
        self.update_series_timer.timeout.connect(self.update_series)
        self.update_series_timer.setInterval(self.UPDATE_SERIES_PERIOD)

        self.update_acc_series_timer = QTimer()
        self.update_acc_series_timer.timeout.connect(self.update_acc_series)
        self.update_acc_series_timer.setInterval(self.UPDATE_BREATHING_SERIES_PERIOD)
        
        self.pacer_timer = QTimer()
        self.pacer_timer.setInterval(self.UPDATE_PACER_PERIOD)  # ms (20 Hz)
        self.pacer_timer.timeout.connect(self.plot_circles)

        self.update_acc_series_timer.start()
        self.update_series_timer.start()
        self.pacer_timer.start()

        self.pacer_values_hist = np.full((self.PACER_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist = np.full((self.PACER_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist_rel_s = np.full(self.PACER_HIST_SIZE, np.nan) # relative seconds

    def update_pacer_rate(self):
        self.pacer_rate = self.pacer_slider.value()/2
        self.pacer_label.setText(f"{self.pacer_slider.value()/2}")

    def plot_circles(self):
        # Pacer
        coordinates = self.model.pacer.update(self.pacer_rate)
        self.circles_widget.update_pacer_series(*coordinates)

        self.pacer_values_hist = np.roll(self.pacer_values_hist, -1)
        self.pacer_values_hist[-1] = np.linalg.norm([coordinates[0][0],coordinates[1][0]]) - 0.5
        self.pacer_times_hist = np.roll(self.pacer_times_hist, -1)
        self.pacer_times_hist[-1] = time.time_ns()/1.0e9

        # Breathing
        breath_coordinates = self.model.get_breath_circle_coords()
        self.circles_widget.update_breath_series(*breath_coordinates)

    async def disconnect_polar(self):
        await self.model.disconnect_sensor()

    def update_acc_series(self):
        
        self.pacer_times_hist_rel_s = self.pacer_times_hist - time.time_ns()/1.0e9
            
        self.breath_acc_times_rel_s = self.model.breath_acc_times - time.time_ns()/1.0e9
        series_breath_acc_new = []

        for i, value in enumerate(self.breath_acc_times_rel_s):
            if not np.isnan(value):
                series_breath_acc_new.append(QPointF(value, self.model.breath_acc_hist[i]))
        self.series_breath_acc.replace(series_breath_acc_new)
        
        series_breath_cycle_marker_new = []
        for i, value in enumerate(self.model.breath_cycle_ids):
            if not value < 0:
                series_breath_cycle_marker_new.append(QPointF(self.breath_acc_times_rel_s[value], self.model.breath_acc_hist[value]))
        self.series_breath_cycle_marker.replace(series_breath_cycle_marker_new)

        series_pacer_new = []
        for i, value in enumerate(self.pacer_times_hist_rel_s):
            if not np.isnan(value):
                series_pacer_new.append(QPointF(value, self.pacer_values_hist[i]))
                
        if series_pacer_new:
            self.series_pacer.replace(series_pacer_new)

    def update_series(self):

        self.br_times_hist_rel_s = self.model.br_times_hist - time.time_ns()/1.0e9

        series_hr_new = []
        for i, value in enumerate(self.model.hr_values_hist):
            if not np.isnan(value):
                series_hr_new.append(QPointF(self.model.ibi_times_hist_rel_s[i], value))
        self.series_hr.replace(series_hr_new)
        
        if np.any(~np.isnan(self.model.hr_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.hr_values_hist[self.model.ibi_times_hist_rel_s > -self.HR_SERIES_TIME_RANGE])/5)*5
            min_val = np.floor(np.nanmin(self.model.hr_values_hist[self.model.ibi_times_hist_rel_s > -self.HR_SERIES_TIME_RANGE])/5)*5
            self.axis_hr_y.setRange(min_val, max_val)

        # Breathing rate plot
        series_br_new = []
        for i, value in enumerate(self.model.br_values_hist):
            if not np.isnan(value):
                series_br_new.append(QPointF(self.br_times_hist_rel_s[i], value))
        self.series_br.replace(series_br_new)
        self.series_br_marker.replace(series_br_new)
        
        if np.any(~np.isnan(self.model.br_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.br_values_hist[self.br_times_hist_rel_s > -self.HRV_SERIES_TIME_RANGE])/5)*5
            self.axis_br_y.setRange(0, max_val)

        if np.any(~np.isnan(self.model.hrv_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.hrv_values_hist[self.model.hrv_times_hist > -self.HRV_SERIES_TIME_RANGE])/10)*10
            max_val = max(max_val, 150)
            self.axis_hrv_y.setRange(0, max_val)

        # RMSSD Series
        series_maxmin_new = []
        for i, value in enumerate(self.model.maxmin_values_hist):
            if not np.isnan(value):
                series_maxmin_new.append(QPointF(self.br_times_hist_rel_s[i], value))
        self.series_maxmin.replace(series_maxmin_new)
        self.series_maxmin_marker.replace(series_maxmin_new)

    async def set_first_sensor_found(self):
        ''' List valid devices and connect to first one'''
        
        valid_devices = self.sensor_handler.get_valid_device_names()
        
        selected_device_name = str(valid_devices[0]) # Select first device
        self.logger.info(f"Connecting to {selected_device_name}")
        sensor = self.sensor_handler.create_sensor_client(selected_device_name)
        try:
            await self.model.set_and_connect_sensor(sensor)
        except Exception as e:
            self.logger.error(f"Error: Failed to connect – {e}")
            sys.exit(1)

    async def main(self):
        await self.sensor_handler.scan()
        await self.set_first_sensor_found()
