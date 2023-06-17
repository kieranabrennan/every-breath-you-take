
import asyncio
from PySide6.QtCore import QTimer, Qt, QPointF, QMargins, QSize, QFile
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QSizePolicy, QSlider, QLabel, QWidget, QGridLayout
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QScatterSeries, QSplineSeries, QAreaSeries
from PySide6.QtGui import QPen, QColor, QPainter, QFont
from bleak import BleakScanner
import time
import numpy as np
from Model import Model

'''
TODO: 
- Abstract the historic series type
- Exit the program nicely
'''

class PacerWidget(QChartView):
    def __init__(self, x_values=None, y_values=None, color=None):
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

class InfoBox(QWidget):
    def __init__(self, title, valueTitle1=None, value1=None, valueTitle2=None, value2=None, titlePosition="top"):
        super().__init__()
        layout = QGridLayout()
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 24px; color: black")
        
        self.valueTitle1_label = QLabel(valueTitle1)
        self.valueTitle1_label.setAlignment(Qt.AlignCenter)
        self.valueTitle1_label.setStyleSheet("color: black")
        self.value1_label = QLabel(f"{value1}")
        self.value1_label.setAlignment(Qt.AlignCenter)
        self.value1_label.setStyleSheet("color: black")
        self.valueTitle2_label = QLabel(valueTitle2)
        self.valueTitle2_label.setAlignment(Qt.AlignCenter)
        self.valueTitle2_label.setStyleSheet("color: black")
        self.value2_label = QLabel(f"{value2}")
        self.value2_label.setAlignment(Qt.AlignCenter)
        self.value2_label.setStyleSheet("color: black")

        if titlePosition == "bottom":
            layout.addWidget(self.valueTitle1_label, 0, 0)
            layout.addWidget(self.valueTitle2_label, 0, 1)
            layout.addWidget(self.value1_label, 1, 0)
            layout.addWidget(self.value2_label, 1, 1)
            layout.addWidget(self.title_label, 2, 0, 1, 2)
        else:
            layout.addWidget(self.title_label, 0, 0, 1, 2)
            layout.addWidget(self.valueTitle1_label, 1, 0)
            layout.addWidget(self.valueTitle2_label, 1, 1)
            layout.addWidget(self.value1_label, 2, 0)
            layout.addWidget(self.value2_label, 2, 1)

        self.setLayout(layout)

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
        self.UPDATE_PACER_PERIOD = 20 # ms
        self.PACER_HIST_SIZE = 6000
        self.BREATH_ACC_TIME_RANGE = 30 # s
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
        self.axis_y_breath_acc = self.create_axis("Breath (m/s2)", self.BLUE, rangeMin=-1, rangeMax=1, labelSize=10)

        # Heart rate chart
        self.chart_hr = self.create_chart(title='Heart rate', showTitle=False, showLegend=False)
        self.series_hr = self.create_scatter_series(self.RED, self.DOTSIZE_SMALL)
        self.axis_hr_y = self.create_axis(title="HR (bpm)", color=self.RED, rangeMin=50, rangeMax=80, labelSize=10)

        # Breathing rate
        self.series_br = self.create_spline_series(self.BLUE, self.LINEWIDTH)
        self.series_br_marker = self.create_scatter_series(self.GRAY, self.DOTSIZE_SMALL)
        self.axis_br_y = self.create_axis(title="BR (bpm)", color=self.BLUE, rangeMin=0, rangeMax=20, labelSize=10)
        
        # Heart rate variability chart
        self.chart_hrv = self.create_chart(title='Heart rate variability', showTitle=False, showLegend=False)
        # self.series_hrv = self.create_spline_series(self.RED, self.LINEWIDTH)
        self.series_maxmin = self.create_spline_series(self.RED, self.LINEWIDTH)
        self.axis_hrv_x = self.create_axis(title=None, tickCount=10, rangeMin=-self.HRV_SERIES_TIME_RANGE, rangeMax=0, labelSize=10)
        self.axis_hrv_y = self.create_axis(title="HRV (ms)", color=self.RED, rangeMin=0, rangeMax=250, labelSize=10)

        # Poincare plot
        self.chart_poincare = self.create_chart(title='Poincare Plot', showTitle=True, showLegend=False, margins=QMargins(0,0,0,0))
        self.series_poincare = self.create_scatter_series(self.RED, self.DOTSIZE_SMALL)
        self.axis_poincare_x = self.create_axis(title="RR_n (ms)", rangeMin=800, rangeMax=1200, labelSize=10)
        self.axis_poincare_y = self.create_axis(title="RR_n+1 (ms)", rangeMin=800, rangeMax=1200, labelSize=10)
        self.series_poincare_identity = self.create_line_series(self.RED, 1, Qt.DashLine)
        self.series_poincare_identity.append([QPointF(0, 0), QPointF(1500, 1500)])
        self.series_poincare_last_cycle = self.create_spline_series(self.BLUE, self.LINEWIDTH)

        # HRV spectrum
        self.chart_hrv_spectrum = self.create_chart(title='HRV Spectrum', showTitle=True, showLegend=False, margins=QMargins(0,0,0,0))
        self.series_hrv_spectrum = self.create_line_series(self.RED, self.LINEWIDTH)
        self.series_breath_spectrum = self.create_line_series(self.BLUE, self.LINEWIDTH)
        self.axis_hrv_spectrum_x = self.create_axis(title="Frequency (Hz)", rangeMin=0, rangeMax=0.5, labelSize=10)
        self.axis_hrv_spectrum_y = self.create_axis(title="Power (s^2/Hz)", rangeMin=0, rangeMax=1, labelSize=10)
        self.series_pacer_line = self.create_line_series(self.GOLD, self.LINEWIDTH, Qt.DotLine)
        
        self.pacer_slider = QSlider(Qt.Horizontal)
        self.pacer_slider.setRange(3,10)
        self.pacer_slider.setSingleStep(0.5)
        self.pacer_slider.setValue(self.pacer_rate)
        self.pacer_slider.valueChanged.connect(self.update_pacer_rate)
        
        self.pacer_label = QLabel()
        self.pacer_label.setStyleSheet("QLabel {color: black}")
        self.pacer_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.pacer_label.setText(f"{self.pacer_rate}")
        
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
        self.chart_hrv.addSeries(self.series_maxmin)
        self.chart_hrv.addAxis(self.axis_hrv_x, Qt.AlignBottom)
        self.chart_hrv.addAxis(self.axis_hrv_y, Qt.AlignLeft)
        # self.series_hrv.attachAxis(self.axis_hrv_x)
        # self.series_hrv.attachAxis(self.axis_hrv_y)
        self.series_maxmin.attachAxis(self.axis_hrv_x)
        self.series_maxmin.attachAxis(self.axis_hrv_y)

        # Breathing rate on HRV chart
        self.chart_hrv.addSeries(self.series_br)
        self.chart_hrv.addSeries(self.series_br_marker)
        self.chart_hrv.addAxis(self.axis_br_y, Qt.AlignRight)
        self.series_br.attachAxis(self.axis_hrv_x)
        self.series_br.attachAxis(self.axis_br_y)
        self.series_br_marker.attachAxis(self.axis_hrv_x)
        self.series_br_marker.attachAxis(self.axis_br_y)

        # Poincare
        self.chart_poincare.addSeries(self.series_poincare)
        self.chart_poincare.addSeries(self.series_poincare_identity)
        self.chart_poincare.addSeries(self.series_poincare_last_cycle)
        self.chart_poincare.addAxis(self.axis_poincare_x, Qt.AlignBottom)
        self.chart_poincare.addAxis(self.axis_poincare_y, Qt.AlignLeft)
        self.series_poincare.attachAxis(self.axis_poincare_x)
        self.series_poincare.attachAxis(self.axis_poincare_y)
        self.series_poincare_identity.attachAxis(self.axis_poincare_x)
        self.series_poincare_identity.attachAxis(self.axis_poincare_y)
        self.series_poincare_last_cycle.attachAxis(self.axis_poincare_x)
        self.series_poincare_last_cycle.attachAxis(self.axis_poincare_y)

        # HRV spectrum
        self.chart_hrv_spectrum.addSeries(self.series_hrv_spectrum)
        self.chart_hrv_spectrum.addSeries(self.series_breath_spectrum)
        self.chart_hrv_spectrum.addSeries(self.series_pacer_line)
        self.chart_hrv_spectrum.addAxis(self.axis_hrv_spectrum_x, Qt.AlignBottom)
        self.chart_hrv_spectrum.addAxis(self.axis_hrv_spectrum_y, Qt.AlignLeft)
        self.series_hrv_spectrum.attachAxis(self.axis_hrv_spectrum_x)
        self.series_hrv_spectrum.attachAxis(self.axis_hrv_spectrum_y)
        self.series_breath_spectrum.attachAxis(self.axis_hrv_spectrum_x)
        self.series_breath_spectrum.attachAxis(self.axis_hrv_spectrum_y)
        self.series_pacer_line.attachAxis(self.axis_hrv_spectrum_x)
        self.series_pacer_line.attachAxis(self.axis_hrv_spectrum_y)
        
        # Create a layout
        layout = QVBoxLayout()

        acc_widget = QChartView(self.chart_acc)
        acc_widget.setStyleSheet("background-color: transparent;")
        hrv_widget = QChartView(self.chart_hrv)
        hrv_widget.setStyleSheet("background-color: transparent;")
        poincare_widget = QChartView(self.chart_poincare)
        poincare_widget.setStyleSheet("background-color: transparent;")
        hrv_spectrum_widget = QChartView(self.chart_hrv_spectrum)
        hrv_spectrum_widget.setStyleSheet("background-color: transparent;")

        self.pacer_widget = PacerWidget(*self.model.pacer.update(self.pacer_rate), self.GOLD)
        
        acc_widget.setRenderHint(QPainter.Antialiasing)
        hrv_widget.setRenderHint(QPainter.Antialiasing)
        poincare_widget.setRenderHint(QPainter.Antialiasing)
        self.pacer_widget.setRenderHint(QPainter.Antialiasing)
        hrv_spectrum_widget.setRenderHint(QPainter.Antialiasing)

        # Create QChartView widgets for both charts
        sliderLayout = QHBoxLayout()
        sliderLayout.addWidget(self.pacer_slider)
        sliderLayout.addWidget(self.pacer_label)
        
        # Create the horizontal layout and add the widgets
        pacerLayout = QVBoxLayout()
        pacerLayout.addWidget(self.pacer_widget, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        pacerLayout.addLayout(sliderLayout)

        hlayout0 = QHBoxLayout()
        self.coherenceInfo = InfoBox(title="Coherence", valueTitle1="Breath", value1=0.0, valueTitle2="Heart", value2=0.0)
        hlayout0.addWidget(acc_widget, stretch=3)
        hlayout0.addWidget(self.coherenceInfo, stretch=1)

        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(poincare_widget, stretch=4)
        hlayout1.addLayout(pacerLayout, stretch=3)
        hlayout1.addWidget(hrv_spectrum_widget, stretch=4)

        hlayout2 = QHBoxLayout()
        self.variabilityInfo = InfoBox(title="Variability", valueTitle1="Width", value1=0.0, valueTitle2="Height", value2=0.0, titlePosition="bottom")
        hlayout2.addWidget(self.variabilityInfo, stretch=1)
        hlayout2.addWidget(hrv_widget, stretch=4)

        layout.addLayout(hlayout0, stretch=4)
        layout.addLayout(hlayout1, stretch=5)
        layout.addLayout(hlayout2, stretch=4)
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
        self.pacer_timer.timeout.connect(self.plot_pacer_disk)

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
        series.setColor(Qt.transparent)
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
        self.pacer_rate = self.pacer_slider.value()
        self.pacer_label.setText(f"{self.pacer_slider.value()}")

    def plot_pacer_disk(self):
        coordinates = self.model.pacer.update(self.pacer_rate)
        self.pacer_widget.update_series(*coordinates)

        self.pacer_values_hist = np.roll(self.pacer_values_hist, -1)
        self.pacer_values_hist[-1] = np.linalg.norm([coordinates[0][0],coordinates[1][0]]) - 0.5
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
            self.axis_hrv_y.setRange(0, max_val)

        # RMSSD Series
        series_maxmin_new = []
        for i, value in enumerate(self.model.maxmin_values_hist):
            if not np.isnan(value):
                series_maxmin_new.append(QPointF(self.br_times_hist_rel_s[i], value))
        self.series_maxmin.replace(series_maxmin_new)
    
        # Poincare plot
        series_poincare_new = []
        for i, value in enumerate(self.model.ibi_values_hist[:-1]):
            if not np.isnan(value):
                series_poincare_new.append(QPointF(value, self.model.ibi_values_hist[i+1]))
        self.series_poincare.replace(series_poincare_new)

        if len(self.model.ibi_values_last_cycle) > 2:
            series_poincare_last_new = []
            for i, value in enumerate(self.model.ibi_values_last_cycle[:-1]):
                if not np.isnan(value):
                    series_poincare_last_new.append(QPointF(value, self.model.ibi_values_last_cycle[i+1]))
            series_poincare_last_new.append(QPointF(self.model.ibi_values_last_cycle[0], self.model.ibi_values_last_cycle[1])) # Close the loop
            self.series_poincare_last_cycle.replace(series_poincare_last_new)

        if np.any(~np.isnan(self.model.ibi_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.ibi_values_hist)/100)*100
            min_val = np.floor(np.nanmin(self.model.ibi_values_hist)/100)*100
            if max_val > self.axis_poincare_x.max():
                self.axis_poincare_x.setRange(self.axis_poincare_x.min(), max_val)
                self.axis_poincare_y.setRange(self.axis_poincare_y.min(), max_val)
            if min_val < self.axis_poincare_x.min():
                self.axis_poincare_x.setRange(min_val, self.axis_poincare_x.max())
                self.axis_poincare_y.setRange(min_val, self.axis_poincare_y.max())

        maxmin_last = self.model.maxmin_values_hist[-1]
        rmssd_last = self.model.rmssd_values_hist[-1]
        if not np.isnan(maxmin_last):
            color = self.RED.name() if maxmin_last < 50 else self.ORANGE.name() if maxmin_last < 150 else self.GREEN.name()
            variability_length_str = "<font color='{}'>{:.0f} ms</font>".format(color, maxmin_last)
            self.variabilityInfo.value1_label.setText(variability_length_str)
        if not np.isnan(rmssd_last):
            color = self.RED.name() if rmssd_last < 10 else self.ORANGE.name() if rmssd_last < 40 else self.GREEN.name()
            varaibilility_width_str = "<br><font color='{}'>{:.0f} ms</font>".format(color, rmssd_last)
            self.variabilityInfo.value2_label.setText(varaibilility_width_str)

        # HRV Spectrum plot
        series_hrv_spectrum_new = []
        for i, value in enumerate(self.model.hrv_psd_values_hist):
            if not np.isnan(value):
                series_hrv_spectrum_new.append(QPointF(self.model.hrv_psd_freqs_hist[i], value))
        self.series_hrv_spectrum.replace(series_hrv_spectrum_new)

        if not np.isnan(self.model.br_coherence):
            color = self.RED.name() if self.model.br_coherence < 0.15 else self.ORANGE.name() if self.model.br_coherence < 0.4 else self.GREEN.name()
            breath_coherence_str = "<font color='{}'>{:4.2f}</font>".format(color, self.model.br_coherence)
            self.coherenceInfo.value1_label.setText(breath_coherence_str)
        if not np.isnan(self.model.hr_coherence):
            color = self.RED.name() if self.model.hr_coherence < 0.15 else self.ORANGE.name() if self.model.hr_coherence < 0.4 else self.GREEN.name()
            heart_coherence_str = "<font color='{}'>{:4.2f}</font>".format(color, self.model.hr_coherence)
            self.coherenceInfo.value2_label.setText(heart_coherence_str)

        series_breath_spectrum_new = []
        for i, value in enumerate(self.model.br_psd_values_hist):
            if not np.isnan(value):
                series_breath_spectrum_new.append(QPointF(self.model.br_psd_freqs_hist[i], value))
        self.series_breath_spectrum.replace(series_breath_spectrum_new)

        # Pacer line and label
        pacer_freq = self.pacer_rate/60.0
        self.series_pacer_line.replace([QPointF(pacer_freq, self.axis_hrv_spectrum_y.min()), QPointF(pacer_freq, self.axis_hrv_spectrum_y.max())])

    async def main(self):
        await self.connect_polar()
        await asyncio.gather(self.model.update_ibi(), self.model.update_acc())
    