
import asyncio
import time

import numpy as np
from bleak import BleakScanner
from PySide6.QtCharts import QAreaSeries, QChart, QChartView, QLineSeries, QScatterSeries, QSplineSeries, QValueAxis
from PySide6.QtCore import QFile, QMargins, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QSlider, QVBoxLayout, QWidget

from Model import Model

'''
TODO: 
- Abstract the historic series type
- Exit the program nicely
'''

class CirclesWidget(QChartView):
    def __init__(self, x_values=None, y_values=None, pacer_color=None, breathing_color=None, hr_color=None):
        super().__init__()

        self.setSizePolicy(
            QSizePolicy(
                QSizePolicy.Fixed,  # enforce self.sizeHint by fixing horizontal (width) policy
                QSizePolicy.Preferred,
            )
        )
        
        self.scene().setBackgroundBrush(Qt.white)
        self.setAlignment(Qt.AlignCenter)

        self.plot = QChart()
        self.plot.legend().setVisible(False)
        self.plot.setBackgroundRoundness(0)
        self.plot.setMargins(QMargins(0, 0, 0, 0))

        # Pacer disc
        self.pacer_circumference_coord = QSplineSeries()
        self.disk = QAreaSeries(self.pacer_circumference_coord)
        self.disk.setColor(pacer_color)
        self.plot.addSeries(self.disk)

        # Breathing disc
        self.breath_circumference_coord = QSplineSeries()
        pen = QPen(breathing_color)
        pen.setWidth(2)
        self.breath_circumference_coord.setPen(pen)
        self.plot.addSeries(self.breath_circumference_coord)   

        if x_values is not None and y_values is not None:
            self._instantiate_series(x_values, y_values)

        # Axes
        self.x_axis = QValueAxis()
        self.x_axis.setRange(-1, 1)
        self.x_axis.setVisible(False)
        self.plot.addAxis(self.x_axis, Qt.AlignBottom)
        self.disk.attachAxis(self.x_axis)
        self.breath_circumference_coord.attachAxis(self.x_axis)

        self.y_axis = QValueAxis()
        self.y_axis.setRange(-1, 1)
        self.y_axis.setVisible(False)
        self.plot.addAxis(self.y_axis, Qt.AlignLeft)
        self.disk.attachAxis(self.y_axis)
        self.breath_circumference_coord.attachAxis(self.y_axis)
        
        self.setChart(self.plot)

    def _instantiate_series(self, x_values, y_values):
        for x, y in zip(x_values, y_values):
            self.pacer_circumference_coord.append(x, y)
            self.breath_circumference_coord.append(0, 0)

    def update_pacer_series(self, x_values, y_values):
        for i, (x, y) in enumerate(zip(x_values, y_values)):
            self.pacer_circumference_coord.replace(i, x, y)

    def update_breath_series(self, x_values, y_values):
        for i, (x, y) in enumerate(zip(x_values, y_values)):
            self.breath_circumference_coord.replace(i, x, y)

    def sizeHint(self):
        height = self.size().height()
        return QSize(height, height)  # force square aspect ratio

    def resizeEvent(self, event):
        if self.size().width() != self.size().height():
            self.updateGeometry()  # adjusts geometry based on sizeHint
        return super().resizeEvent(event)

class SquareWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
    def sizeHint(self):
        return QSize(100, 100)

    def resizeEvent(self, event):
        side = min(self.width(), self.height())
        if self.width() > self.height():
            self.setMaximumHeight(side)
            self.setMaximumWidth(side)
        else:
            self.setMaximumWidth(side)
            self.setMaximumHeight(side)

class View(QChartView):
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = Model()

        # Load the stylesheet from the file
        style_file = QFile("style.qss")
        style_file.open(QFile.ReadOnly | QFile.Text)
        stylesheet = style_file.readAll()
        stylesheet = str(stylesheet, encoding="utf-8")

        # Set the stylesheet
        self.setStyleSheet(stylesheet)

        # Plot parameters
        self.RED = QColor(200, 30, 45)
        self.YELLOW = QColor(254, 191, 0)
        self.ORANGE = QColor(255, 130, 0)
        self.GREEN = QColor(50, 177, 108)
        self.BLUE = QColor(0, 119, 190)
        self.GRAY = QColor(34, 34, 34)
        self.GOLD = QColor(212, 175, 55)
        self.LINEWIDTH = 2.5
        self.DOTSIZE_SMALL = 4
        self.DOTSIZE_LARGE = 5

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
        self.chart_acc = self.create_chart(title='Breathing Acceleration', showTitle=False, showLegend=False)
        self.series_pacer = self.create_line_series(self.GOLD, self.LINEWIDTH)
        self.series_breath_acc = self.create_line_series(self.BLUE, self.LINEWIDTH)
        self.series_breath_cycle_marker = self.create_scatter_series(self.GRAY, self.DOTSIZE_SMALL)
        self.axis_acc_x = self.create_axis(title=None, tickCount=10, rangeMin=-self.BREATH_ACC_TIME_RANGE, rangeMax=0, labelSize=10, flip=False)
        # self.axis_y_pacer = self.create_axis(title="Pacer", color=self.GOLD, rangeMin=-1, rangeMax=1)
        self.axis_y_breath_acc = self.create_axis("Chest expansion (m/s2)", self.BLUE, rangeMin=-1, rangeMax=1, labelSize=10)

        # Heart rate chart
        self.chart_hr = self.create_chart(title='Heart rate', showTitle=False, showLegend=False)
        self.series_hr = self.create_scatter_series(self.RED, self.DOTSIZE_SMALL)
        self.axis_hr_y = self.create_axis(title="HR (bpm)", color=self.RED, rangeMin=50, rangeMax=80, labelSize=10)

        # Breathing rate
        self.series_br = self.create_spline_series(self.BLUE, self.LINEWIDTH)
        self.series_br_marker = self.create_scatter_series(self.BLUE, self.DOTSIZE_SMALL)
        self.series_br_marker.setMarkerShape(QScatterSeries.MarkerShapeTriangle)
        self.axis_br_y = self.create_axis(title="BR (bpm)", color=self.BLUE, rangeMin=0, rangeMax=20, labelSize=10)
        
        # Heart rate variability chart
        self.chart_hrv = self.create_chart(title='Heart rate variability', showTitle=False, showLegend=False)
        # self.series_hrv = self.create_spline_series(self.RED, self.LINEWIDTH)
        self.series_maxmin = self.create_spline_series(self.RED, self.LINEWIDTH)
        self.series_maxmin_marker = self.create_scatter_series(self.RED, self.DOTSIZE_SMALL)
        self.axis_hrv_x = self.create_axis(title=None, tickCount=10, rangeMin=-self.HRV_SERIES_TIME_RANGE, rangeMax=0, labelSize=10)
        self.axis_hrv_y = self.create_axis(title="HRV (ms)", color=self.RED, rangeMin=0, rangeMax=250, labelSize=10)

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
        self.hrv_band_0.setColor(self.RED)
        self.hrv_band_0.setOpacity(0.2)
        self.hrv_band_0.setPen(QPen(Qt.NoPen))
        self.hrv_band_1 = QAreaSeries(self.hrv_band_line_1, self.hrv_band_line_2)
        self.hrv_band_1.setColor(self.YELLOW)
        self.hrv_band_1.setOpacity(0.2)
        self.hrv_band_1.setPen(QPen(Qt.NoPen))
        self.hrv_band_2 = QAreaSeries(self.hrv_band_line_2, self.hrv_band_line_3)
        self.hrv_band_2.setColor(self.GREEN)
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
    
        self.circles_widget = CirclesWidget(*self.model.pacer.update(self.pacer_rate), self.GOLD, self.BLUE, self.RED)
        
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

    def create_chart(self, title=None, showTitle=False, showLegend=False, margins=None):
        chart = QChart()
        chart.legend().setVisible(showLegend)
        chart.setTitle(title)
        if margins:
            chart.setMargins(margins)
            chart.layout().setContentsMargins(margins)
        return chart
    
    def create_scatter_series(self, color=None, size=5):
        if color is None:
            color = self.GRAY
        series = QScatterSeries()
        series.setMarkerSize(size)
        series.setMarkerShape(QScatterSeries.MarkerShapeCircle)
        series.setColor(color)
        series.setBorderColor(color)
        return series

    def create_line_series(self, color=None, width=2, style=None):
        if color is None:
            color = self.GRAY
        series = QLineSeries()
        pen = QPen(color)
        pen.setWidth(width)
        if style:
            pen.setStyle(style)
        series.setPen(pen)
        return series

    def create_spline_series(self, color=None, width=2):
        if color is None:
            color = self.GRAY
        series = QSplineSeries()
        pen = QPen(color)
        pen.setWidth(width)
        series.setPen(pen)
        return series

    def create_axis(self, title=None, color=None, tickCount=None, rangeMin=None, rangeMax=None, labelSize=None, flip=False):
        if color is None:
            color = self.GRAY
        axis = QValueAxis()
        axis.setTitleText(title)
        axis.setLabelsColor(color)
        axis.setTitleBrush(color)
        axis.setGridLineVisible(False)
        if tickCount:
            axis.setTickCount(tickCount)
        if rangeMin:
            axis.setMin(rangeMin)
        if rangeMax:
            axis.setMax(rangeMax)
        if labelSize:
            font = QFont()
            font.setPointSize(labelSize)
            axis.setLabelsFont(font)
        if flip:
            axis.setReverse(True)
        return axis        

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
        
        self.model.set_polar_sensor(device)
        await self.model.connect_sensor()

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

    async def main(self):
        await self.connect_polar()
        await asyncio.gather(self.model.update_ibi(), self.model.update_acc())
    