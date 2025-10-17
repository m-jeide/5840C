# ---------------------------------------------------------------------------- #
#                                                                              #
# 	Module:       main.py                                                      #
# 	Author:       jeide                                                        #
# 	Created:      10/16/2025, 3:43:36 PM                                       #
# 	Description:  V5 project                                                   #
#                                                                              #
# ---------------------------------------------------------------------------- #

# Library imports
from vex import *

# Brain should be defined by default
brain=Brain()

brain.screen.print("Hello V5")


RIGHT_MOTORS: list[Motor] = [Motor(Ports.PORT3), Motor(Ports.PORT4)] 
LEFT_MOTORS: list[Motor] = [Motor(Ports.PORT1), Motor(Ports.PORT2)] 
# one of these should be reversed, depends on the build
REVERSE_RIGHT: bool = True
REVERSE_LEFT: bool = False

# suction motor
SUCTION_MOTOR: Motor = Motor(Ports.PORT9)
SUCTION_POWER: int = 100  # percent


def command_move(x: int | float, y: int | float):
    """Command the robot to move in the two axises."""
    # x is left/right
    # y is forward/backward
    right_speed = y - x
    left_speed = y + x
    # review notebook for a diagram

    # sanity check
    max_input = abs(max(right_speed, left_speed))
    if max_input > 100:  # exceeded 100%
        # let's scale it down
        right_speed = right_speed / max_input * 100 
        left_speed = left_speed / max_input * 100 
    
    # now let's command the motors
    for right_motor in RIGHT_MOTORS:
        right_motor: Motor
        right_motor.spin(FORWARD if not REVERSE_RIGHT else REVERSE, right_speed, PERCENT)
    
    for left_motor in LEFT_MOTORS:
        left_motor: Motor
        left_motor.spin(FORWARD if not REVERSE_LEFT else REVERSE, left_speed, PERCENT)


def command_move_via_controller(controller: Controller):
    """Give movement commands via the controller."""
    # you could choose any axis you want, we chose these because we like how they feel while driving
    # get the joystick positions
    x = controller.axis1.position()
    y = controller.axis3.position() 
    # pass to the movement function
    command_move(x, y)


def driver_control():
    """Driver control function."""
    # create a controller object
    controller = Controller()

    timer = Timer()

    def start_suction_motor():
        """Start the suction motor on."""
        SUCTION_MOTOR.spin(FORWARD, SUCTION_POWER, PERCENT)
    
    def stop_suction_motor():
        """Stop the suction motor."""
        SUCTION_MOTOR.stop()
    
    # set up button callbacks
    controller.buttonA.pressed(start_suction_motor)
    controller.buttonB.pressed(stop_suction_motor)

    # loop forever
    while True:
        command_move_via_controller(controller)
        wait(20, MSEC)  # don't hog the CPU


def autonomous():
    """Autonomous function."""
    # example autonomous code
    command_move(0, 50)  # move forward at 50% speed
    wait(2, SECONDS)     # for 2 seconds
    command_move(0, 0)   # stop


if __name__ == "__main__":
    # setup the competition instance
    Competition(driver_control, autonomous)
    driver_control()  # run driver control by default