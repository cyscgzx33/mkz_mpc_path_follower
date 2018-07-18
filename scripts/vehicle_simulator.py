#!/usr/bin/env python
import rospy
import numpy as np
import math
from mkz_mpc_path_follower.msg import state_est
from mkz_mpc_path_follower.msg import MPC_cmd

class VehicleSimulator():
	'''
	A vehicle dynamics simulator using a linear tire model.
	Modified from Ugo Rosolia's Code: https://github.com/urosolia/RacingLMPC/blob/master/src/fnc/SysModel.py
	'''
	def __init__(self):
		rospy.init_node('vehicle_simulator', anonymous=True)
		rospy.Subscriber('mpc_cmd', MPC_cmd, self._mpc_cmd_callback, queue_size=1)
		self.state_pub = rospy.Publisher('state_est', state_est, queue_size=1)

		self.tcmd = None	# rostime (s) of received acc command
		self.acc = 0.0		# actual acceleration (m/s^2)
		self.df = 0.0		# actual steering angle (rad)
		self.acc_des = 0.0	# desired acceleration	(m/s^2)
		self.df_des = 0.0	# desired steering_angle (rad)

		self.dt_model = 0.01				# vehicle model update period (s)
		self.hz = int(1.0/self.dt_model)
		self.r = rospy.Rate(self.hz)
		
		self.X   = rospy.get_param('X0', -300.0)
		self.Y   = rospy.get_param('Y0', -450.0)
		self.psi = rospy.get_param('Psi0', 1.0)
		self.vx  = 0.0
		self.vy  = 0.0
		self.wz  = 0.0

		self.pub_loop()

	def pub_loop(self):
		while not rospy.is_shutdown():
			self._update_vehicle_model()
			
			curr_state = state_est()
			curr_state.header.stamp = rospy.Time.now()
			curr_state.x   = self.X
			curr_state.y   = self.Y
			curr_state.psi = self.psi
			curr_state.v   = self.vx
			curr_state.a   = self.acc
			curr_state.df  = self.df

			self.state_pub.publish(curr_state)
			self.r.sleep()

	def _mpc_cmd_callback(self, msg):
		self.tcmd = rospy.Time.now()
		self.acc_des = msg.accel_cmd
		self.df_des  = msg.steer_angle_cmd

	def _update_vehicle_model(self, disc_steps = 10):
		# Azera Params taken from:
		# https://github.com/MPC-Car/Controller/blob/master/LearningController/RaceCar_ILMPC_4_NewFormulation/src/init/genHeader_data_vehicle.m
		lf = 1.152  			# m  	(CoG to front axle)
		lr = 1.693  			# m  	(CoG to rear axle)
		d  = 0.8125 			# m  	(half-width, currently unused)
		m  = 1840   			# kg 	(vehicle mass)
		Iz  = 3477				# kg*m2 (vehicle inertia)
		C_alpha_f = 4.0703e4    # N 	(front tire cornering stiffness)
		C_alpha_r = 6.4495e4	# N 	(rear tire cornering stiffness)

		deltaT = self.dt_model/disc_steps
		for i in range(disc_steps):			

			# Compute tire slip angle
			alpha_f = 0.0
			alpha_r = 0.0
			if math.fabs(self.vx) > 1e-6:
				alpha_f = self.df - np.arctan2( self.vy+lf*self.wz, self.vx )
				alpha_r = - np.arctan2( self.vy-lf*self.wz , self.vx)        		
			
			# Compute lateral force at front and rear tire (linear model)
			Fyf = C_alpha_f * alpha_f
			Fyr = C_alpha_r * alpha_r

			# Propagate the vehicle dynamics deltaT seconds ahead.			
			vx_n  = max(0.0, self.vx  + deltaT * ( self.acc - 1/m*Fyf*np.sin(self.df) + self.wz*self.vy ) )
			
			# Ensure only forward driving.
			if vx_n > 1e-6:
				vy_n  = self.vy  + deltaT * ( 1.0/m*(Fyf*np.cos(self.df) + Fyr) - self.wz*self.vx )
				wz_n  = self.wz  + deltaT * ( 1.0/Iz*(lf*Fyf*np.cos(self.df) - lr*Fyr) )
			else:
				vy_n = 0.0
				wz_n = 0.0

			psi_n = self.psi + deltaT * ( self.wz )
			X_n   = self.X   + deltaT * ( self.vx*np.cos(self.psi) - self.vy*np.sin(self.psi) )
			Y_n   = self.Y   + deltaT * ( self.vx*np.sin(self.psi) + self.vy*np.cos(self.psi) )


			self.X 	 = X_n
			self.Y   = Y_n
			self.psi = (psi_n + np.pi) % (2.0 * np.pi) - np.pi # https://stackoverflow.com/questions/15927755/opposite-of-numpy-unwrap
			self.vx  = vx_n
			self.vy  = vy_n
			self.wz  = wz_n

			self._update_low_level_control(deltaT)

	def _update_low_level_control(self, dt_control):
		# e_<n> = self.<n> - self.<n>_des
		# d/dt e_<n> = - kp * e_<n>
		self.acc = 5.0 * (self.acc_des - self.acc) * dt_control + self.acc
		self.df  = 5.0  * (self.df_des  - self.df) * dt_control + self.df

if __name__=='__main__':
	print 'Starting Simulator.'
	try:
		v = VehicleSimulator()
	except rospy.ROSInterruptException:
		pass
