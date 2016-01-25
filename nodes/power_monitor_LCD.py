#!/usr/bin/env python

import rospy,sys
from serial import *

from sensor_msgs.msg import Temperature

energy_consumed = 0
last_time = None
first_time = None

print last_time
def lcd_print(port,data,fill=16):
	out = '#' + data.ljust(fill)+'\n'
	return port.write(out)

def print_power(port, watts):
	lcd_print(port,'Total Power:     %4.3f Wh   '%watts,fill=32)
	
def callback_power(msg):

	global last_time, first_time, energy_consumed
	if last_time is None:
		first_time = msg.header.stamp
		last_time = msg.header.stamp
		return
	power = msg.temperature
	deltaT = msg.header.stamp - last_time
	rospy.loginfo("deltaT: %li ns"%deltaT.to_nsec())
	energy = power * deltaT.to_nsec()/1000000.0	#watts * milliseconds
	energy_consumed += energy	#
	
	total_time = last_time - first_time
	rospy.loginfo("TotalT: %li s"%total_time.to_sec())
	rospy.loginfo("Energy Consumed:%li"%energy_consumed)
	if total_time.to_nsec() > 0:
		energy = energy_consumed/3600000
		rospy.loginfo('Consumed %f Wh'%(energy))
		print_power(serial_port,energy)
	last_time = msg.header.stamp

rospy.init_node('power_monitor')
rospy.loginfo("ROS Power Monitor")

port_name = rospy.get_param('~port','/dev/ttyUSB0')
baud = int(rospy.get_param('~baud','57600'))
try:
	serial_port = Serial(port_name, baud)
except SerialException as e:
	rospy.logerr("Error opening serial: %s", e)
	rospy.signal_shutdown("Error opening serial: %s" % e)
	sys.exit()

lcd_print(serial_port,'Initializing... Power Meter    ')

sub_power = rospy.Subscriber('power_monitor',Temperature, callback_power, queue_size = 10)
rospy.spin()
