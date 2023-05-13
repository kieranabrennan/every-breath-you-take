import sys
import random
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCharts import QChart, QLineSeries, QValueAxis, QChartView

class RandomPlot(QMainWindow):
    def __init__(self):
        super().__init__()

        self.series = QLineSeries()
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.createDefaultAxes()

        self.axis_x = QValueAxis()
        self.axis_y = QValueAxis()
        self.chart.setAxisX(self.axis_x, self.series)
        self.chart.setAxisY(self.axis_y, self.series)
        self.axis_x.setRange(-10, 0)
        self.axis_y.setRange(0, 1)

        chart_view = QChartView(self.chart)
        self.setCentralWidget(chart_view)
        self.resize(800, 400)

        self.data_points = [0] * 10

        self.random_data_timer = QTimer()
        self.random_data_timer.setInterval(1000)
        self.random_data_timer.timeout.connect(self.update_random_data)
        self.random_data_timer.start()

        self.plot_timer = QTimer()
        self.plot_timer.setInterval(100)
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start()

    def update_random_data(self):
        self.data_points.pop(0)
        self.data_points.append(random.random())

    def update_plot(self):
        self.series.clear()
        for i, y in enumerate(self.data_points):
            self.series.append(QPointF(i - 10, y))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    plot = RandomPlot()
    plot.show()
    sys.exit(app.exec())
