#!/usr/bin/python3
# Open camera preview, wait for button/key press event on raspi and react by
# adapting camera parameters
import asyncio
from datetime import datetime
import evdev                   # for input from mouse and command line
from gpiozero import Button    # for external buttons

# load available camera lib (picamera on legacy, picamera2 on newer OS) 
try:
    from picamera import PiCamera  # Import camera functions
    print("Using picamera")
except ImportError:
    pass
try:
    from picamera2 import Picamera2, Preview, MappedArray
    from libcamera import Transform
    print("Using picamera2 and libcamera")
except ImportError:
    pass

import re                      # for parsing fbset output
import subprocess              # for calling fbset to detect screen resolution

# you can adapt this script to your specific setup, by setting either
# SCALE_FACTORS can be modified for a fixed set of scale factors
# PIN_NUMBER_... can be changed if you connect buttons to different GPIO pins

# Picamera2 needs the screen resolution for preview
# set default to full hd, will try to use actual values in init_camera
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# rotate view by 180 degrees for the typical use-case with camera behind object
ROTATION = 180

# Pre-defined scale factors to cycle through with button/enter
# These factors are camera pixels to screen pixels ratio, the actual
# magnification depends also on the camera, the screen size and the distance
# between camera and object
DEFAULT_FACTOR = 2
SCALE_FACTORS = [DEFAULT_FACTOR, 3, 4.5, 8]
factor = SCALE_FACTORS[0]  # use first entry as initial factor on boot up

# define GPIO pins for (optional) push buttons
PIN_NUMBER_SCALE =  4 # physical 7, scale button
PIN_NUMBER_COLOR = 18 # physical 12, colour mode button

# fbset is supported on new and legacy OS
# shows actual framebuffer resolution instead of physical screen size
def screen_resolution_fbset():
    try:
        result = subprocess.run(['fbset'], capture_output=True)
        output = result.stdout.decode('utf-8')
        #  shows resolution e.g. as 'mode "1920x1080"'
        m = re.search('mode "([0-9]+)x([0-9]+)"', output)
        if m:
            width = int(m.group(1))
            height = int(m.group(2))
            print('fbset screen resolution (w, h): ', width, height)
            return width, height
        else:
            print('Could not match fbset output:', output)
    except:
        pass
    return SCREEN_WIDTH, SCREEN_HEIGHT

def picamera2_invert(request):
    # picamera2 doesn't support image_effect, need to invert manually instead
    if hasattr(invert, 'is_inverted') and invert.is_inverted:
        with MappedArray(request, "main") as m:
            array = m.array
            for i in range(len(array)):
                array[i] = 255 - array[i]


# toggle between normal and inverted colours
def invert():
    global camera
    if hasattr(camera, 'image_effect'):
        # image_effect is not supported in picamera2
        camera.image_effect = 'none' if camera.image_effect == 'negative' else 'negative'
    else:
        # toggle state variable which is used in picamera2_invert
        if not hasattr(invert, 'is_inverted'):
            invert.is_inverted = False
        invert.is_inverted = not invert.is_inverted

# react on button pressed
def next_factor():
    global factor
        
    # find the highest entry in SCALE_FACTORS that is <= current factor
    # if the current factor is less due to direct input, switch to default value
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
    global screen
    
    factor = max(new_factor, DEFAULT_FACTOR)
    # print("Scale factor", factor)

    # update roi value in legacy OS
    if hasattr(camera, 'crop'):
        # offset and width / height in range [0,1]
        diameter = min(1 / factor, 1)
        camera.crop = (0, 0, diameter, diameter)
        return

    # update crop in current OS
    camera_w, camera_h = camera.camera_properties['PixelArraySize']
    # print('PixelArraySize:', camera_w, camera_h)

    screen_w, screen_h = screen
    screen_ratio = screen_w / screen_h
    crop_w = int(camera_w / factor)
    crop_h = min(int(crop_w / screen_ratio), camera_h)

    # always start at the top left position regardless of scale factor
    top_x = 0
    top_y = 0
    if ROTATION == 180:
        # if the camera is rotated, always start at the lower bottom
        top_x = camera_w - crop_w
        top_y = camera_h - crop_h

    window = [top_x, top_y, crop_w, crop_h]
    # print(factor, window)
    camera.set_controls({'ScalerCrop': window})
    
    # focus on cropped area if camera supports autofocus
    if 'AfMode' in camera.camera_controls:
        camera.set_controls({'AfWindows': [(top_x, top_y, crop_w, crop_h)]})
        camera.autofocus_cycle()

# focus on whole sensor field regardless of current preview area
def focus():
    global camera

    # update autofocus (only supported on picamera2)
    if hasattr(camera, 'camera_controls') and 'AfMode' in camera.camera_controls:
        print('ScalerCrop', camera.camera_controls['ScalerCrop'])
        print('PixelArrayActiveAreas', camera.camera_properties['PixelArrayActiveAreas'])
        print('PixelArraySize:', camera.camera_properties['PixelArraySize'])
        x, y, w, h = camera.camera_controls['ScalerCrop'][-1]
        print('focus:', x, y, w, h)
        camera.set_controls({'AfWindows': [(0, 0, w, h)]})
        camera.autofocus_cycle()

def quit():
    global devices    
    asyncio.get_event_loop().stop()
    for dev in devices:
        dev.ungrab()

def save_photo():
    global camera
    camera.stop_preview()
    timestamp = datetime.now().isoformat()
    camera.capture('/home/pi/{}.jpg'.format(timestamp))
    camera.start_preview()

# start displaying the default camera view
def init_camera(width, height):
    try:
        # for current OS use picamera2
        picam2 = Picamera2()
        config = picam2.create_preview_configuration({'size': (width, height)})
        picam2.configure(config)
        transform = Transform()
        if ROTATION == 180:
            transform = Transform(hflip=1, vflip=1)
        picam2.pre_callback = picamera2_invert
        picam2.start_preview(Preview.DRM, x=0, y=0, width=width, height=height,
            transform=transform)
        picam2.start()
        print('Started picamera2', ROTATION)
        return picam2
    except:
        # for legacy OS use picamera
        camera = PiCamera()
        camera.rotation = ROTATION
        camera.start_preview()
        print('Started legacy picamera', ROTATION)
        return camera


async def handle_events(device):
    async for event in device.async_read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 0:
            code = event.code
            # mouse buttons
            if code == evdev.ecodes.BTN_MOUSE: next_factor()
            elif code == evdev.ecodes.BTN_RIGHT: invert()
            # elif code == evdev.ecodes.BTN_MIDDLE: save_photo()

            # regular keys
            elif code == evdev.ecodes.KEY_F: focus()
            elif code == evdev.ecodes.KEY_Q: quit()
            elif code == evdev.ecodes.KEY_ESC: quit()
            elif code == evdev.ecodes.KEY_ENTER: next_factor()
            elif code == evdev.ecodes.KEY_SLASH: invert()
            elif code == evdev.ecodes.KEY_0: scale(10)
            elif code == evdev.ecodes.KEY_1: scale(1)
            elif code == evdev.ecodes.KEY_2: scale(2)
            elif code == evdev.ecodes.KEY_3: scale(3)
            elif code == evdev.ecodes.KEY_4: scale(4)
            elif code == evdev.ecodes.KEY_5: scale(5)
            elif code == evdev.ecodes.KEY_6: scale(6)
            elif code == evdev.ecodes.KEY_7: scale(7)
            elif code == evdev.ecodes.KEY_8: scale(8)
            elif code == evdev.ecodes.KEY_9: scale(9)

            # numeric keypad
            elif code == evdev.ecodes.KEY_KPENTER: next_factor()
            elif code == evdev.ecodes.KEY_KPSLASH: invert()
            elif code == evdev.ecodes.KEY_KP0: scale(10)
            elif code == evdev.ecodes.KEY_KP1: scale(1)
            elif code == evdev.ecodes.KEY_KP2: scale(2)
            elif code == evdev.ecodes.KEY_KP3: scale(3)
            elif code == evdev.ecodes.KEY_KP4: scale(4)
            elif code == evdev.ecodes.KEY_KP5: scale(5)
            elif code == evdev.ecodes.KEY_KP6: scale(6)
            elif code == evdev.ecodes.KEY_KP7: scale(7)
            elif code == evdev.ecodes.KEY_KP8: scale(8)
            elif code == evdev.ecodes.KEY_KP9: scale(9)

button1 = Button(PIN_NUMBER_SCALE)
button1.when_pressed = next_factor
button2 = Button(PIN_NUMBER_COLOR)
button2.when_pressed = invert

screen = screen_resolution_fbset()
width, height = screen
camera = init_camera(width, height)
scale(factor)

try:
    devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
    for device in devices:
        device.grab()
        asyncio.ensure_future(handle_events(device))
    loop = asyncio.get_event_loop()
    loop.run_forever()

finally:
    camera.stop_preview()
    camera.close()
