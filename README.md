# Every Breath You Take – Heart Rate Variability Training with the Polar H10 Monitor

Through controlled breathing it is possible to regulate your body's stress reponse. This application allows you to measure and train this effect with a Polar H10 Heart Rate monitor.

Heart rate variability, the small changes in heart rate from beat-to-beat, is a reliable measure of stress response. Heart rate variability reflects the balance between the two sides of the autonomic nervous system: the fight-or-flight response (from the sympathetic nervous system) and the rest-and-digest response (from the parasympathetic nervous system).

In any moment it is possible to restore balance to the autonomic nervous system by breathing slower and deeper. With every breath you take, you can set the pace of your breathing rate, measure your breathing control with the chest accelerometer, and see how heart rate variability responds.

![](img/screen_record.gif)

## Features

- Connect and stream from a Polar H10, acceleration and heart rate data
- Live breathing control feedback and adjustable pace setting
- Track breathing and heart rate oscillations in real-time
- Explore how heart rate vairability repsonses to different breathing rates

## Installation and usage

Works with Polar H10, with Firmware Version 5.0.0 or later
    
    python -m venv venv
    source venv/bin/activate  # On Windows, use `my_project_env\Scripts\activate`
    pip install -r requirements.txt
    python EBYT.py 

Tested with Python 3.9, 3.10, 3.11, 3.12

Bundle into an application with pyinstaller:

    pyinstaller EBYT.spec

The program will automatically connect to your Polar device. For best breathing detection, ensure the Polar H10 is fitted around the widest part of the ribcage, stay seated and still while recording.

Set the breathing pace with the slider (in breaths per minute), and follow the cadence as the gold circle expands and contracts. The blue circle shows your breathing control.

Track each breath cycle in the top graph, and how heart rate oscillates in repsonse.

Adjust breathing pace and control to target the green zone of heart rate variability in the bottom graph (> 150 ms).

## Contributing
Feedback, bug reports, and pull requests are welcome. Feel free to submit an issue or create a pull request on GitHub.
