#!/usr/bin/python3
# Open camera preview, wait for button/key press event on raspi and react by
# adapting camera parameters
import asyncio
import evdev                   # for input from mouse and command line
from gpiozero import Button    # for external buttons
from picamera import PiCamera  # Import camera functions
import sys
import time

# you can adapt this script to your specific setup, by setting either
# DISTANCE_TO_SURFACE_CM or DEFAULT_WIDTH_CM to your local measurements
# WIDTHS_CM or SCALE_FACTORS can be modified for a fixed set of scale factors
# PIN_NUMBER_... can be changed if you connect buttons to different GPIO pins

# rotate view by 180 degrees for the typical use-case with camera behind object
ROTATION = 180

# distance in cm between camera objective and the surface (e.g. table)
# adapt this to your setup, or directly set the value DEFAULT_WIDTH_CM below
DISTANCE_TO_SURFACE_CM = 24.5

# visible width when calling "raspivid -f -rot 180" (measure with a ruler)
# adapt this to your setup, as it depends on the camera and screen
DEFAULT_WIDTH_CM = DISTANCE_TO_SURFACE_CM * 0.67
# uncomment the following line to overwrite with your own measured value
# DEFAULT_WIDTH_CM = 16.5

# typical line widths to cycle through by pressing the scale button / enter
# set your desired line widths here, e.g. from the newspaper, typical books or magazines
WIDTHS_CM = [DEFAULT_WIDTH_CM, 12.5, 9, 5]


# magnification when calling raspivid without parameters
# value is from my initial setup, matters only if you set SCALE_FACTORS manually
DEFAULT_FACTOR = 2.5

# pre-defined scale factors to cycle through with button/enter
SCALE_FACTORS = [DEFAULT_FACTOR * DEFAULT_WIDTH_CM / x for x in WIDTHS_CM]
# uncomment the following line if you rather want to define the scale factors manually
# SCALE_FACTORS = [DEFAULT_FACTOR, 5, 10]

factor = SCALE_FACTORS[0]  # use first entry as initial factor on boot up


# define GPIO pins for (optional) push buttons
PIN_NUMBER_SCALE =  4 # physical 7, scale button
PIN_NUMBER_COLOR = 18 # physical 12, colour mode button

# toggle between normal colours and inverted colours
def invert():
    global camera
    camera.image_effect = 'none' if camera.image_effect == 'negative' else 'negative'

# convert a scale factor to the values needed by raspivid's roi/crop parameter
def scale2roi(scale_factor):
    diameter = DEFAULT_FACTOR / scale_factor
    radius = diameter / 2
    start = 0.5 - radius
    
    # assure that values are in allowed range (e.g. factor 1 is not supported on bigger screens)
    start = max(start, 0)
    diameter = min(diameter, 1)
    
    # y value is always 0, to have the same upper position regardless of scale factor
    return (start, 0, diameter, diameter)
    

# react on button pressed
def next_factor():
    global factor
        
    # find the highest entry in SCALE_FACTORS that is <= current factor
    # if the current factor is less (due to direct factor input), switch to default value
    same_or_less = [v for v in SCALE_FACTORS if v <= factor]
    if len(same_or_less) == 0:
        factor = DEFAULT_FACTOR
    else:
        # step to next scale factor, after last entry go back to first
        closest_factor = max(same_or_less)
        i = SCALE_FACTORS.index(closest_factor)
        i_next = (i + 1) % len(SCALE_FACTORS)
        factor = SCALE_FACTORS[i_next]
    
    scale(factor)
    
    
# change to given scale factor
def scale(new_factor):
    global camera
    global factor
    
    factor = max(new_factor, DEFAULT_FACTOR)
    #print("Scale factor", factor)
    
    # update crop / roi value
    camera.crop = scale2roi(factor)

def quit():
    global devices    
    asyncio.get_event_loop().stop()
    for dev in devices:
        dev.ungrab()

# start displaying the default camera view
def init_camera():
    camera = PiCamera()
    camera.rotation = ROTATION
    camera.start_preview()
    return camera


devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
for dev in devices:
    dev.grab()
key2function = {
    # mouse buttons
    evdev.ecodes.BTN_MOUSE: next_factor,
    evdev.ecodes.BTN_RIGHT: invert,
    # evdev.ecodes.BTN_MIDDLE: mouse_mid,

    # regular keys
    evdev.ecodes.KEY_Q: quit,
    evdev.ecodes.KEY_ESC: quit,
    evdev.ecodes.KEY_ENTER: next_factor,
    evdev.ecodes.KEY_SLASH: invert,
    evdev.ecodes.KEY_0: lambda: scale(10),
    evdev.ecodes.KEY_1: lambda: scale(1),
    evdev.ecodes.KEY_2: lambda: scale(2),
    evdev.ecodes.KEY_3: lambda: scale(3),
    evdev.ecodes.KEY_4: lambda: scale(4),
    evdev.ecodes.KEY_5: lambda: scale(5),
    evdev.ecodes.KEY_6: lambda: scale(6),
    evdev.ecodes.KEY_7: lambda: scale(7),
    evdev.ecodes.KEY_8: lambda: scale(8),
    evdev.ecodes.KEY_9: lambda: scale(9),

    # numeric keypad
    evdev.ecodes.KEY_KPENTER: next_factor,
    evdev.ecodes.KEY_KPSLASH: invert,
    evdev.ecodes.KEY_KP0: lambda: scale(10),
    evdev.ecodes.KEY_KP1: lambda: scale(1),
    evdev.ecodes.KEY_KP2: lambda: scale(2),
    evdev.ecodes.KEY_KP3: lambda: scale(3),
    evdev.ecodes.KEY_KP4: lambda: scale(4),
    evdev.ecodes.KEY_KP5: lambda: scale(5),
    evdev.ecodes.KEY_KP6: lambda: scale(6),
    evdev.ecodes.KEY_KP7: lambda: scale(7),
    evdev.ecodes.KEY_KP8: lambda: scale(8),
    evdev.ecodes.KEY_KP9: lambda: scale(9),
}
async def handle_events(device):
    async for event in device.async_read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 0 and event.code in key2function:
            key2function[event.code]()

button1 = Button(PIN_NUMBER_SCALE)
button1.when_pressed = next_factor
button2 = Button(PIN_NUMBER_COLOR)
button2.when_pressed = invert

camera = init_camera()

try:
    for device in devices:
        asyncio.ensure_future(handle_events(device))
    loop = asyncio.get_event_loop()
    loop.run_forever()

finally:
    camera.stop_preview()
    camera.close()
