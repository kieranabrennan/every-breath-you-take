
import asyncio
from PySide6.QtCore import QTimer, Qt, QPointF, QMargins, QSize
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QSizePolicy, QSlider, QLabel, QTabWidget, QWidget
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QScatterSeries, QSplineSeries, QAreaSeries
from PySide6.QtGui import QPen, QColor
from bleak import BleakScanner
import time
import numpy as np
from Model import Model

'''
TODO: 
- Explore other HRV calculations
- Tidy the view initialisation
- Abstract the historic series type
- Exit the program nicely
'''
RED = QColor(200, 30, 45)
YELLOW = QColor(254, 191, 0)
ORANGE = QColor(255, 130, 0)
GREEN = QColor(50, 177, 108)
BLUE = QColor(0, 119, 190)
GRAY = QColor(34, 34, 34)
GOLD = QColor(212, 175, 55)

class PacerWidget(QChartView):
    def __init__(self, x_values=None, y_values=None, color=GOLD):
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

class View(QChartView):
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = Model()

        self.LINEWIDTH = 2.5
        self.pacer_rate = 6

        # Breathing acceleration
        self.chart_acc = self.create_chart(title='Breathing Acceleration', showTitle=False, showLegend=False)
        self.series_pacer = self.create_line_series(GOLD, self.LINEWIDTH)
        self.series_breath_acc = self.create_line_series(BLUE, self.LINEWIDTH)
        self.series_breath_cycle_marker = self.create_scatter_series(GRAY, 4)
        self.axis_acc_x = self.create_axis(title="Time (s)", tickCount=10, rangeMin=-60, rangeMax=0)
        self.axis_y_pacer = self.create_axis(title="Pacer", color=GOLD, rangeMin=-1, rangeMax=2)
        self.axis_y_breath_acc = self.create_axis("Breath accel. (m/s)", BLUE, rangeMin=-1, rangeMax=1)

        # Configure
        self.chart_acc.addSeries(self.series_pacer)
        self.chart_acc.addAxis(self.axis_acc_x, Qt.AlignBottom)
        self.chart_acc.addAxis(self.axis_y_pacer, Qt.AlignLeft)
        self.series_pacer.attachAxis(self.axis_acc_x)
        self.series_pacer.attachAxis(self.axis_y_pacer)
        self.chart_acc.addSeries(self.series_breath_acc)
        self.chart_acc.addSeries(self.series_breath_cycle_marker)
        self.chart_acc.addAxis(self.axis_y_breath_acc, Qt.AlignRight)
        self.series_breath_acc.attachAxis(self.axis_acc_x)
        self.series_breath_acc.attachAxis(self.axis_y_breath_acc)
        self.series_breath_cycle_marker.attachAxis(self.axis_acc_x)
        self.series_breath_cycle_marker.attachAxis(self.axis_y_breath_acc)

        # Heart rate chart
        self.chart_hr = self.create_chart(title='Heart rate', showTitle=False, showLegend=False)
        self.series_hr = self.create_line_series(RED, self.LINEWIDTH)
        self.series_hr_extreme_marker = self.create_scatter_series(GRAY, 4)
        self.axis_hr_x = self.create_axis(title="Time (s)", tickCount=10, rangeMin=-150, rangeMax=0)
        self.axis_hr_y = self.create_axis(title="HR (bpm)", color=RED, rangeMin=50, rangeMax=80)

        # Breathing rate
        self.series_br = self.create_line_series(BLUE, self.LINEWIDTH)
        self.series_br_marker = self.create_scatter_series(GRAY, 4)
        self.axis_br_y = self.create_axis(title="BR (bpm)", color=BLUE, rangeMin=0, rangeMax=20)
        
        # Heart rate variability chart
        self.chart_hrv = self.create_chart(title='Heart rate variability', showTitle=False, showLegend=False)
        self.series_hrv = self.create_spline_series(RED, self.LINEWIDTH)
        self.axis_hrv_x = self.create_axis(title="Time (s)", tickCount=10, rangeMin=-300, rangeMax=0)
        self.axis_hrv_y = self.create_axis(title="HRV (ms)", color=RED, rangeMin=0, rangeMax=250)
        
        # Breathing target vs measured chart
        self.chart_br_ctrl = self.create_chart(title='Breathing control', showTitle=True, showLegend=False, margins=QMargins(10,20,10,10))
        self.series_br_ctrl = self.create_scatter_series(BLUE, 5)
        self.axis_br_ctrl_x = self.create_axis(title="Target BR (bpm)", rangeMin=0, rangeMax=10)
        self.axis_br_ctrl_y = self.create_axis(title="Measured BR (bpm)", color=BLUE, rangeMin=0, rangeMax=10)
        self.series_br_ctrl_line = self.create_line_series(BLUE, self.LINEWIDTH, Qt.DotLine)
        self.series_br_ctrl_line.append([QPointF(0, 0), QPointF(30, 30)])

        # HRV vs BR chart
        self.chart_hrv_br = self.create_chart(title='Respiratory Sinus Arhythmia', showTitle=True, showLegend=False, margins=QMargins(10,20,10,10))
        self.series_hrv_br = self.create_scatter_series(RED, 5)
        self.axis_hrv_br_x = self.create_axis(title="BR (bpm)", color=BLUE, rangeMin=0, rangeMax=10)
        self.axis_hrv_br_y = self.create_axis(title="HRV (ms)", color=RED, rangeMin=0, rangeMax=250)
        
        # Poincare plot
        self.chart_poincare = self.create_chart(title='Poincare Plot', showTitle=True, showLegend=False, margins=QMargins(10,20,10,10))
        self.series_poincare = self.create_scatter_series(ORANGE, 5)
        self.axis_poincare_x = self.create_axis(title="RR_n (ms)", rangeMin=600, rangeMax=1100)
        self.axis_poincare_y = self.create_axis(title="RR_n+1 (ms)", rangeMin=600, rangeMax=1100)
        
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
        self.pacer_label = QLabel()
        self.pacer_label.setStyleSheet("QLabel {color: black}")
        self.pacer_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.pacer_label.setText(f"{self.pacer_rate}")
        
        # Heart rate chart
        self.chart_hr.addSeries(self.series_hr)
        self.chart_hr.addSeries(self.series_hr_extreme_marker)
        self.chart_hr.addAxis(self.axis_hr_x, Qt.AlignBottom)
        self.chart_hr.addAxis(self.axis_hr_y, Qt.AlignLeft)
        self.series_hr.attachAxis(self.axis_hr_x)
        self.series_hr.attachAxis(self.axis_hr_y)
        self.series_hr_extreme_marker.attachAxis(self.axis_hr_x)
        self.series_hr_extreme_marker.attachAxis(self.axis_hr_y)

        # Heart rate variability chart
        self.chart_hrv.addSeries(self.series_hrv)
        self.chart_hrv.addAxis(self.axis_hrv_x, Qt.AlignBottom)
        self.chart_hrv.addAxis(self.axis_hrv_y, Qt.AlignLeft)
        self.series_hrv.attachAxis(self.axis_hrv_x)
        self.series_hrv.attachAxis(self.axis_hrv_y)

        # Breathing rate on HRV chart
        self.chart_hrv.addSeries(self.series_br)
        self.chart_hrv.addSeries(self.series_br_marker)
        self.chart_hrv.addAxis(self.axis_br_y, Qt.AlignRight)
        self.series_br.attachAxis(self.axis_hrv_x)
        self.series_br.attachAxis(self.axis_br_y)
        self.series_br_marker.attachAxis(self.axis_hrv_x)
        self.series_br_marker.attachAxis(self.axis_br_y)

        # Breathing target vs measured
        self.chart_br_ctrl.addSeries(self.series_br_ctrl)
        self.chart_br_ctrl.addSeries(self.series_br_ctrl_line)
        self.chart_br_ctrl.addAxis(self.axis_br_ctrl_x, Qt.AlignBottom)
        self.chart_br_ctrl.addAxis(self.axis_br_ctrl_y, Qt.AlignLeft)
        self.series_br_ctrl.attachAxis(self.axis_br_ctrl_x)
        self.series_br_ctrl.attachAxis(self.axis_br_ctrl_y)
        self.series_br_ctrl_line.attachAxis(self.axis_br_ctrl_x)
        self.series_br_ctrl_line.attachAxis(self.axis_br_ctrl_y)

        # HRV vs BR
        self.chart_hrv_br.addSeries(self.series_hrv_br)
        self.chart_hrv_br.addAxis(self.axis_hrv_br_x, Qt.AlignBottom)
        self.chart_hrv_br.addAxis(self.axis_hrv_br_y, Qt.AlignLeft)
        self.series_hrv_br.attachAxis(self.axis_hrv_br_x)
        self.series_hrv_br.attachAxis(self.axis_hrv_br_y)
        
        # Poincare
        self.chart_poincare.addSeries(self.series_poincare)
        self.chart_poincare.addAxis(self.axis_poincare_x, Qt.AlignBottom)
        self.chart_poincare.addAxis(self.axis_poincare_y, Qt.AlignLeft)
        self.series_poincare.attachAxis(self.axis_poincare_x)
        self.series_poincare.attachAxis(self.axis_poincare_y)
        
        # Create a layout
        layout = QVBoxLayout()
        tab_widget = QTabWidget()

        acc_widget = QChartView(self.chart_acc)
        br_ctrl_widget = QChartView(self.chart_br_ctrl)
        hr_widget = QChartView(self.chart_hr)
        hrv_br_widget = QChartView(self.chart_hrv_br)        
        hrv_widget = QChartView(self.chart_hrv)
        poincare_widget = QChartView(self.chart_poincare)

        # self.pacer = Pacer()
        self.pacer_widget = PacerWidget(*self.model.pacer.update(self.pacer_rate))

        # Create QChartView widgets for both charts
        hlayout0_slider = QVBoxLayout()
        hlayout0_slider.addWidget(self.pacer_slider)
        hlayout0_slider.addWidget(self.pacer_label)

        hlayout0 = QHBoxLayout()
        hlayout0.addLayout(hlayout0_slider)
        hlayout0.addWidget(self.pacer_widget)
        hlayout0.addWidget(acc_widget)

        tab1_vlayout = QVBoxLayout()
        tab1_vlayout.addWidget(hr_widget, stretch=1)
        tab1_vlayout.addWidget(hrv_widget, stretch=1)

        tab2_hlayout = QHBoxLayout()
        tab2_hlayout.addWidget(br_ctrl_widget, stretch=1)
        tab2_hlayout.addWidget(hrv_br_widget, stretch=1)
        tab2_hlayout.addWidget(poincare_widget, stretch=1)

        tab1 = QWidget()
        tab2 = QWidget()
        tab1.setLayout(tab1_vlayout)
        tab2.setLayout(tab2_hlayout)
        tab_widget.addTab(tab1, "Biofeeback")
        tab_widget.addTab(tab2, "Analysis")
        tab_widget.setStyleSheet("""
            QTabBar::tab:selected {
                background: lightgray;
                color: black;
            }
            QTabBar::tab:!selected {
                background: gray;
                color: white;
            }
        """)

        layout.addLayout(hlayout0, stretch=1)
        layout.addWidget(tab_widget, stretch=2.5)
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

        self.PACER_HIST_SIZE = 1200
        self.pacer_values_hist = np.full((self.PACER_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist = np.full((self.PACER_HIST_SIZE, 1), np.nan)
        self.pacer_times_hist_rel_s = np.full(self.PACER_HIST_SIZE, np.nan) # relative seconds

    def create_chart(self, title=None, showTitle=False, showLegend=False, margins=None):
        chart = QChart()
        chart.legend().setVisible(showLegend)
        chart.setTitle(title)
        if margins:
            chart.setMargins(margins)
        return chart
    
    def create_scatter_series(self, color=BLUE, size=5):
        series = QScatterSeries()
        series.setMarkerSize(size)
        series.setBorderColor(Qt.transparent)
        series.setColor(color)
        return series

    def create_line_series(self, color=BLUE, width=2, style=None):
        series = QLineSeries()
        pen = QPen(color)
        pen.setWidth(width)
        if style:
            pen.setStyle(style)
        series.setPen(pen)
        return series

    def create_spline_series(self, color=BLUE, width=2):
        series = QSplineSeries()
        pen = QPen(color)
        pen.setWidth(width)
        series.setPen(pen)
        return series

    def create_axis(self, title=None, color=GRAY, tickCount=None, rangeMin=None, rangeMax=None):
        axis = QValueAxis()
        axis.setTitleText(title)
        axis.setLabelsColor(color)
        axis.setTitleBrush(color)
        if tickCount:
            axis.setTickCount(tickCount)
        if rangeMin:
            axis.setMin(rangeMin)
        if rangeMax:
            axis.setMax(rangeMax)
        return axis        

    def update_pacer_rate(self):
        self.pacer_rate = self.pacer_slider.value()
        self.pacer_label.setText(f"{self.pacer_slider.value()}")

    def plot_pacer_disk(self):
        coordinates = self.model.pacer.update(self.pacer_rate)
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
                series_hr_new.append(QPointF(self.model.ibi_times_hist[i], value))
        self.series_hr.replace(series_hr_new)

        series_hr_extreme_marker_new = []
        for i, value in enumerate(self.model.hr_extrema_ids):
            if not value < 0:
                series_hr_extreme_marker_new.append(QPointF(self.model.ibi_times_hist[value], self.model.hr_values_hist[value]))
        self.series_hr_extreme_marker.replace(series_hr_extreme_marker_new)   

        if np.any(~np.isnan(self.model.hr_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.hr_values_hist[self.model.ibi_times_hist > -150])/5)*5
            min_val = np.floor(np.nanmin(self.model.hr_values_hist[self.model.ibi_times_hist > -150])/5)*5
            self.axis_hr_y.setRange(min_val, max_val)

        # Breathing rate plot
        series_br_new = []
        for i, value in enumerate(self.model.br_values_hist):
            if not np.isnan(value):
                series_br_new.append(QPointF(self.br_times_hist_rel_s[i], value))
        self.series_br.replace(series_br_new)
        self.series_br_marker.replace(series_br_new)
        
        if np.any(~np.isnan(self.model.br_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.br_values_hist[self.br_times_hist_rel_s > -300])/5)*5
            self.axis_br_y.setRange(0, max_val)
        
        # HRV plot
        series_hrv_new = []
        for i, value in enumerate(self.model.hrv_values_hist):
            if not np.isnan(value):
                series_hrv_new.append(QPointF(self.model.hrv_times_hist[i], value))
        self.series_hrv.replace(series_hrv_new)   

        if np.any(~np.isnan(self.model.hrv_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.hrv_values_hist[self.model.hrv_times_hist > -300])/10)*10
            self.axis_hrv_y.setRange(0, max_val)

        # Breathing control plot
        series_br_ctrl_new = []
        for i, value in enumerate(self.model.br_values_hist):
            if not np.isnan(value):
                series_br_ctrl_new.append(QPointF(self.model.br_pace_values_hist[i], value))
        self.series_br_ctrl.replace(series_br_ctrl_new)

        if np.any(~np.isnan(self.model.br_values_hist)):
                max_val = np.ceil(np.nanmax(self.model.br_values_hist)/2)*2
                self.axis_br_ctrl_x.setRange(0, max_val)
                self.axis_br_ctrl_y.setRange(0, max_val)
        
        # HRV vs BR plot
        series_hrv_br_new = []
        for i, value in enumerate(self.model.hrv_br_interp_values_hist):
            if not np.isnan(value):
                series_hrv_br_new.append(QPointF(self.model.br_values_hist[i], value))
        self.series_hrv_br.replace(series_hrv_br_new)

        if np.any(~np.isnan(self.model.hrv_br_interp_values_hist)):
            self.axis_hrv_br_x.setRange(0, np.ceil(np.nanmax(self.model.br_values_hist)/2)*2)
            self.axis_hrv_br_y.setRange(0, np.ceil(np.nanmax(self.model.hrv_br_interp_values_hist)/10)*10)

        # Poincare plot
        series_poincare_new = []
        for i, value in enumerate(self.model.ibi_values_hist[:-1]):
            if not np.isnan(value):
                series_poincare_new.append(QPointF(value, self.model.ibi_values_hist[i+1]))
        self.series_poincare.replace(series_poincare_new)

        if np.any(~np.isnan(self.model.ibi_values_hist)):
            max_val = np.ceil(np.nanmax(self.model.ibi_values_hist)/25)*25
            min_val = np.floor(np.nanmin(self.model.ibi_values_hist)/25)*25
            self.axis_poincare_x.setRange(min_val, max_val)
            self.axis_poincare_y.setRange(min_val, max_val)

    async def main(self):
        await self.connect_polar()
        await asyncio.gather(self.model.update_ibi(), self.model.update_pmd())
    