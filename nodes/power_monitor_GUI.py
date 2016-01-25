#!/usr/bin/env python

"""
The monitor expects to receive single-byte data packets on the 
serial port. Each received byte is understood as a current
reading and is shown on a live chart.
When the monitor is active, you can turn the 'Update speed' knob
to control the frequency of screen updates.
Eli Bendersky (eliben@gmail.com)
License: this code is in the public domain
Last modified: 07.08.2009
"""
import random, sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import PyQt4.Qwt5 as Qwt
import Queue

import rospy
from std_msgs.msg import Float32, Float32MultiArray

class LiveDataFeed(object):
    """ A simple "live data feed" abstraction that allows a reader 
        to read the most recent data and find out whether it was 
        updated since the last read. 
        
        Interface to data writer:
        
        add_data(data):
            Add new data to the feed.
        
        Interface to reader:
        
        read_data():
            Returns the most recent data.
            
        has_new_data:
            A boolean attribute telling the reader whether the
            data was updated since the last read.    
    """
    def __init__(self):
        self.cur_data = None
        self.has_new_data = False
    
    def add_data(self, data):
        self.cur_data = data
        self.has_new_data = True
    
    def read_data(self):
        self.has_new_data = False
        return self.cur_data


class PlottingDataMonitor(QMainWindow):
    def __init__(self, parent=None,num_cells=8):
	self.num_cells = num_cells
        super(PlottingDataMonitor, self).__init__(parent)
        
        self.monitor_active = False
        self.com_monitor = None
        self.com_data_q = None
        self.com_error_q = None
        self.livefeed = LiveDataFeed()
        self.ampere_samples = []
        self.timer = QTimer()
        
        self.create_menu()
        self.create_main_frame()
        self.create_status_bar()
	self.on_start()
        
    def make_data_box(self, name):
        label = QLabel(name)
        qle = QLineEdit()
        qle.setEnabled(False)
        qle.setFrame(False)
        return (label, qle)
        
    def create_plot(self,xaxis,yaxis,xaxis_label='Time',yaxis_label='Measurement',color='limegreen'):
        plot = Qwt.QwtPlot(self)
        plot.setCanvasBackground(Qt.black)
        plot.setAxisTitle(Qwt.QwtPlot.xBottom, xaxis_label)
        plot.setAxisScale(Qwt.QwtPlot.xBottom, xaxis[0],xaxis[1],xaxis[2])
        plot.setAxisTitle(Qwt.QwtPlot.yLeft, yaxis_label)
        plot.setAxisScale(Qwt.QwtPlot.yLeft, yaxis[0],yaxis[1],yaxis[2])
        plot.replot()
        
        curve = Qwt.QwtPlotCurve('')
        curve.setRenderHint(Qwt.QwtPlotItem.RenderAntialiased)
        pen = QPen(QColor(color))
        pen.setWidth(2)
        curve.setPen(pen)
        curve.attach(plot)
        
        return plot, curve

    def create_ampere(self):
        ampere = Qwt.QwtThermo(self)
        ampere.setPipeWidth(6)
        ampere.setRange(0, 120)
        ampere.setAlarmLevel(80)
        ampere.setAlarmEnabled(True)
        ampere.setFillColor(Qt.green)
        ampere.setAlarmColor(Qt.red)
        ampere.setOrientation(Qt.Horizontal, Qwt.QwtThermo.BottomScale)
        
        return ampere
        
    def create_scale(self,info,width=6,orientation=Qt.Horizontal,scale=Qwt.QwtThermo.BottomScale,alarm=True):
        ampere = Qwt.QwtThermo(self)
        ampere.setPipeWidth(width)
        ampere.setRange(info[0], info[1])
        ampere.setAlarmLevel(info[2])
        ampere.setAlarmEnabled(alarm)
        ampere.setFillColor(Qt.green)
        ampere.setAlarmColor(Qt.red)
        ampere.setOrientation(orientation, scale)
        
        return ampere

    def create_knob(self):
        knob = Qwt.QwtKnob(self)
        knob.setRange(0, 20, 0, 1)
        knob.setScaleMaxMajor(10)
        knob.setKnobWidth(50)
        knob.setValue(10)
        return knob

    def create_status_bar(self):
        self.status_text = QLabel('Monitor idle')
        self.statusBar().addWidget(self.status_text, 1)

    def create_main_frame(self):
        # Plot and ampere
        #
        self.ampere_plot, self.curve = self.create_plot(
        	xaxis=(0, 10, 1),yaxis=(0, 250, 40),
        	yaxis_label='Current (mA)',color='blue')
        self.ampere = self.create_scale((0,200,180))
        
        ampere_l = QLabel('Average')
        ampere_layout = QHBoxLayout()
        ampere_layout.addWidget(ampere_l)
        ampere_layout.addWidget(self.ampere)
        ampere_layout.setSpacing(5)
        
        o=Qt.Vertical
        s=Qwt.QwtThermo.RightScale
        
        colorMap = Qwt.QwtLinearColorMap(Qt.green, Qt.red)
        #colorMap.addColorStop(0.2, Qt.Qt.blue)
        #colorMap.addColorStop(0.4, Qt.Qt.green)
        
        self.voltage_pack = self.create_scale((self.num_cells*3.7,self.num_cells*4.2,self.num_cells*3.8),40,o,alarm=False)
	self.cellvoltages=[self.create_scale((3.7,4.2,3.8),6,o,s,alarm=False)
        	 for x in range(self.num_cells)]
        	 
        pack_voltage = QVBoxLayout()
        voltage_l = QLabel('Pack Voltage')
        pack_voltage.addWidget(voltage_l)
        pack_voltage.addWidget(self.voltage_pack)
        
        voltages_layout = QHBoxLayout()
        voltages_layout.addLayout(pack_voltage)
        for x in range(self.num_cells):
        	layout = QVBoxLayout()
        	layout.addWidget(QLabel('Cell_%d'%(x+1)))
        	layout.addWidget(self.cellvoltages[x])
        	layout.setSpacing(5)
        	voltages_layout.addLayout(layout)
        
        
        self.updatespeed_knob = self.create_knob()
        self.connect(self.updatespeed_knob, SIGNAL('valueChanged(double)'),
            self.on_knob_change)
        self.knob_l = QLabel('Update speed = %s (Hz)' % self.updatespeed_knob.value())
        self.knob_l.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        knob_layout = QVBoxLayout()
        knob_layout.addWidget(self.updatespeed_knob)
        knob_layout.addWidget(self.knob_l)
        
        ampere_plot_layout = QVBoxLayout()
        ampere_plot_layout.addWidget(self.ampere_plot)
        ampere_plot_layout.addLayout(ampere_layout)
        
        plots_layout = QHBoxLayout()
        plots_layout.addLayout(ampere_plot_layout)
        plots_layout.addStretch(1)
                
        plot_groupbox = QGroupBox('Current Monitor')
        plot_groupbox.setLayout(plots_layout)
        
        voltage_groupbox = QGroupBox('Voltage Monitor')
        voltage_groupbox.setLayout(voltages_layout)
        
        # Main frame and layout
        #
        self.main_frame = QWidget()
        main_layout = QVBoxLayout()
        sub_layout = QHBoxLayout()
        sub_layout.addWidget(plot_groupbox)
        sub_layout.addWidget(voltage_groupbox)
        main_layout.addLayout(sub_layout)
        main_layout.addLayout(knob_layout)
        main_layout.addStretch(1)
        self.main_frame.setLayout(main_layout)
        
        self.setCentralWidget(self.main_frame)
        self.set_actions_enable_state()

    def create_menu(self):
        self.file_menu = self.menuBar().addMenu("&File")
        
        '''
	selectport_action = self.create_action("Select COM &Port...",
            shortcut="Ctrl+P", slot=self.on_select_port, tip="Select a COM port")
	'''
        self.start_action = self.create_action("&Start monitor",
            shortcut="Ctrl+M", slot=self.on_start, tip="Start the data monitor")
        self.stop_action = self.create_action("&Stop monitor",
            shortcut="Ctrl+T", slot=self.on_stop, tip="Stop the data monitor")
        exit_action = self.create_action("E&xit", slot=self.close, 
            shortcut="Ctrl+X", tip="Exit the application")
        
        self.start_action.setEnabled(False)
        self.stop_action.setEnabled(False)
        
        self.add_actions(self.file_menu, 
            (   self.start_action, self.stop_action,
                None, exit_action))
         
        self.help_menu = self.menuBar().addMenu("&Help")
        about_action = self.create_action("&About", 
            shortcut='F1', slot=self.on_about, 
            tip='About the monitor')
        
        self.add_actions(self.help_menu, (about_action,))

    def set_actions_enable_state(self):
        start_enable = not self.monitor_active
        stop_enable = self.monitor_active
        
        self.start_action.setEnabled(start_enable)
        self.stop_action.setEnabled(stop_enable)

    def on_about(self):
        msg = __doc__
        QMessageBox.about(self, "About the demo", msg.strip())

    def on_stop(self):
        """ Stop the monitor
        """
        if self.com_monitor is not None:
            self.com_monitor.join(0.01)
            self.com_monitor = None

        self.monitor_active = False
        self.timer.stop()
        self.set_actions_enable_state()
        
        self.status_text.setText('Monitor idle')
    
    def on_start(self):
        """ Start the monitor: com_monitor thread and the update
            timer
        """
        
        self.ampere_samples = []
	self.t=0#reset time
        self.monitor_active = True
        self.set_actions_enable_state()
        
        self.timer = QTimer()
        self.connect(self.timer, SIGNAL('timeout()'), self.on_timer)
        
        update_freq = self.updatespeed_knob.value()
        if update_freq > 0:
            self.timer.start(1000.0 / update_freq)
        
        self.status_text.setText('Monitor running')
    
    def on_timer(self):
        """ Executed periodically when the monitor update timer
            is fired.
        """
        #self.read_data()
        self.update_monitor()

    def on_knob_change(self):
        """ When the knob is rotated, it sets the update interval
            of the timer.
        """
        update_freq = self.updatespeed_knob.value()
        self.knob_l.setText('Update speed = %s (Hz)' % self.updatespeed_knob.value())

        if self.timer.isActive():
            update_freq = max(0.01, update_freq)
            self.timer.setInterval(1000.0 / update_freq)

    def update_monitor(self):
        """ Updates the state of the monitor window with new 
            data. The livefeed is used to find out whether new
            data was received since the last update. If not, 
            nothing is updated.
        """
        if self.livefeed.has_new_data:
            data = self.livefeed.read_data()
            
            self.ampere_samples.append(
                (data['timestamp'], data['ampere']))
            if len(self.ampere_samples) > 100:
                self.ampere_samples.pop(0)
            
            xdata = [s[0] for s in self.ampere_samples]
            ydata = [s[1] for s in self.ampere_samples]
            
            avg = sum(ydata) / float(len(ydata))
                
            self.ampere_plot.setAxisScale(Qwt.QwtPlot.xBottom, xdata[0], max(20, xdata[-1]))
            self.curve.setData(xdata, ydata)
            self.ampere_plot.replot()
            
            self.ampere.setValue(avg)
        
    def cb_cellVoltages(self,msg):
	if not self.monitor_active:
		return
	for x in range(0,self.num_cells):
		if x >= len(msg.data):
			break
		self.cellvoltages[x].setValue(msg.data[x]/1000)		
		#print 'Cell_%d Voltage:'%x,msg.data[x]
    def cb_busVoltage(self,msg):
	if not self.monitor_active:
		return
	self.voltage_pack.setValue(msg.data)
	#print 'Pack Voltage:',msg.data
    def cb_busPower(self,msg):
	pass
    def cb_shuntCurrent(self,msg):
	if not self.monitor_active:
		return
	#print 'Current:',msg.data
	data = dict(timestamp=self.t,ampere=msg.data*1000)
	self.livefeed.add_data(data)
        self.t+=1

    # The following two methods are utilities for simpler creation
    # and assignment of actions
    #
    def add_actions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)

    def create_action(  self, text, slot=None, shortcut=None, 
                        icon=None, tip=None, checkable=False, 
                        signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action


def main():
    app = QApplication(sys.argv)

    rospy.init_node("power_monitor_GUI")
    cells = rospy.get_param("~num_cells",8)
    print "Cells",cells
    form = PlottingDataMonitor(num_cells=cells);#int(rospy.get_param("~cell_num",8)))

    sub_bV = rospy.Subscriber("busVoltage",Float32, form.cb_busVoltage, queue_size = 10)
    sub_bP = rospy.Subscriber("busPower",Float32, form.cb_busPower, queue_size = 10)
    sub_sC = rospy.Subscriber("shuntCurrent",Float32, form.cb_shuntCurrent, queue_size = 10)
    sub_cV = rospy.Subscriber("cellVoltages",Float32MultiArray, form.cb_cellVoltages, queue_size = 10)
    form.show()

    app.exec_()


if __name__ == "__main__":
    main()
