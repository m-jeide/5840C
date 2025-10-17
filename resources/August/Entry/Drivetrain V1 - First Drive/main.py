# ---------------------------------------------------------------------------- #
#                                                                              #
# 	Module:       main.py                                                      #
# 	Author:       jeide                                                        #
# 	Created:      8/28/2025, 4:09:25 PM                                        #
# 	Description:  V5 project                                                   #
#                                                                              #
# ---------------------------------------------------------------------------- #

# Library imports
from vex import *

# Brain should be defined by default
brain=Brain()

brain.screen.print("Hello V5")


MOTOR_CONFIG = {
    Ports.PORT1: True,
    Ports.PORT2: True,
    Ports.PORT3: False,
    Ports.PORT4: False
} 
RIGHT_MOTORS: list[Motor] = [] 
LEFT_MOTORS: list[Motor] = [] 

for motor_port in MOTOR_CONFIG:
    if MOTOR_CONFIG[motor_port]:
        RIGHT_MOTORS.append(Motor(motor_port, True))
    else:
        LEFT_MOTORS.append(Motor(motor_port, True))


for motor in RIGHT_MOTORS + LEFT_MOTORS:
    motor: Motor
    motor.spin(FORWARD)
    motor.set_velocity(100, PERCENT)


my_controller = Controller(PRIMARY)

def move(controller: Controller):
    x = controller.axis1.position() / 100  # Normalized to -1 to 1
    y = controller.axis3.position() / 100  # Normalized to -1 to 1

    # Calculate motor speeds with improved distribution
    right_speed = y - x
    left_speed = y + x

    max_input = max(abs(right_speed), abs(left_speed))
    if max_input > 1:
        right_speed /= max_input
        left_speed /= max_input

    # Apply to motor groups with max RPM scaling
    max_rpm = 200 
    
    for motor in RIGHT_MOTORS:
        motor.spin(REVERSE, int(right_speed * max_rpm), RPM)
        """brain.screen.set_cursor(1,1)
        brain.screen.print(int(right_speed * max_rpm))"""
    
    for motor in LEFT_MOTORS:
        motor.spin(FORWARD, int(left_speed * max_rpm), RPM)



while True:
    move(my_controller)
    wait(20, MSEC)  # Small delay to prevent overwhelming the system