# magni
Software for a simple video magnifier running on Raspberry Pi. Click the image for a short demo video.

[![Preview for demo video of the video magnifier](https://img.youtube.com/vi/_3VD43FgGWs/0.jpg)](https://www.youtube.com/watch?v=_3VD43FgGWs&t=80s "3d printed DIY video magnifier")

## Description
This project aims to build a video magnifier based on Raspberry Pi and its camera. It can be used to see printed text or images at a larger scale, or to identify small parts like SMD electronics. The device has to be connected to a monitor which will display the image from the camera at a specific magnification level. The user can step through predefined scale factors with a button or the Enter key, and switch to colour-inversion with a second button or the "/" key.
After the initial setup, the device works fully offline and does not need an internet connection.

![Magnifier with low magnification](docs/magni-small-300x225.jpg)
![Magnifier with medium magnification](docs/magni-mid-300x225.jpg)
![Magnifier with high magnification](docs/magni-big-300x225.jpg)

## Hardware
To build the magnifier, you need at least the following
* Raspberry Pi
  * Any model you have will do, but if you're going to buy one I'd recommend the Pi 3 or Zero 2 W
  * Raspberry Pi Zeros are nice for their size, but need specific cables/adapters for camera and USB
  * Raspberry Pi 4 and 5 need specific cables/adapters and may also need cooling. They are overpowered for the magnification task but could be handy for Text-To-Speech (reading out content)
* Raspberry Pi camera
  * Strongly recommended is an official Raspberry Pi camera v2 or v3, due to better image quality and flexible focus compared to the original 5MP ones. The v3 has autofocus which can be handy when supporting different distances to surface, however the autofocus is not always accurate, so a v2 camera that is tuned to the right distance can be the better choice if you have a fixed distance to the surface. The high quality camera with additional lenses is not needed
* Raspberry Pi camera cable
  * only if the standard 15cm cable is too short or you need the smaller cable for Raspberry Pi Zero
* Micro USB charger. For higher specced Raspberry Pi models (3 upwards) the official chargers are recommended due to better power stability
* Micro SD card (>= 4GB)
* HDMI monitor + cable. Some Raspberry Pi models work with analog TVs as well, but this hasn't been tested
* Some input device. The easiest way is a USB (cable) mouse just for the buttons, but a numerical keyboard is also possible, or you can even solder physical push buttons to the GPIO
* Material for the mount. Let your creativity flow, or follow these examples
  * [Lamp setup](docs/magni-lamp-mount.md) (basic and simple)
  * [Flexible arm](docs/magni-flexible-arm-mount.md) with one push-button
  * [Box setup](docs/magni-box-mount.md) with 2 push-buttons
  * [3d print for Pi Zero](docs/magni-3d-zero.md)

A slightly more in-depth description of the first 2 hardware setups is given at http://www.fhack.org/2018/12/19/raspberry-pi-video-magnifier-2018/

If you use the optional push buttons instead of a USB mouse or numerical keyboard, the script expects them at GPIO 4 (physical 7) for the scale button and GPIO 18 (physical 12) for the colour-invert button, using BCM numbering (4 being the 4th pin on the left, 18 being the 6th pin on the right of the GPIO). Each button needs to be connected with GND, e.g. at pins 9 and 14.
While physical buttons are nice, this involves soldering and they may be susceptible to electro-magnetic noise (e.g. getting triggered from switching some device on/off, or even from static charges from my Ikea Markus chair).

## Setup
**2021's Raspberry Pi OS "Bullseye" introduced some incompatible changes for the camera module. The following steps assume you use the latest OS, but the older "Buster" OS is still available as "Legacy OS", and Bullseye also allows to set the camera as Legacy camera in raspi-config (Interface options -> (Legacy) Camera -> Enable)**
* Download [Raspberry Pi OS **Lite**](https://www.raspberrypi.org/software/operating-systems/) and install on SD card, e.g. with Raspberry Pi Imager. The 32 bit version is usually fine
* [Connect camera](https://www.raspberrypi.com/documentation/accessories/camera.html#connecting-the-camera)
* Login with default user “pi”, password “raspberry” (if on desktop, open a terminal). Using the default credentials is not secure, so change it if you will connect the device to the internet or have it accessible to strangers
* Run `sudo raspi-config`
  * System options -> Boot / Autologin -> Console Autologin
  * System options -> Wireless LAN (if you want to connect from another computer by wifi)
  * Interface options -> SSH -> Enable (only if you want to connect from another computer)
  * Finish and reboot (<Yes> or `sudo reboot`)
* If you have an older camera than the v3 with its autofocus, you have to setup the camera focus manually. Run `libcamera-hello --rotation 180 -t 0`
  * If you see the current camera view, and it's at the same angle that you have from above (e.g. it’s not upside down), you’re good, otherwise try different values for rotation (0, 180) and adapt the ROTATION value in magni.py accordingly
  * If the image is blurry you should adjust the focus, simply turning the lens with the plastic “wheel” that comes with the Pi camera v2
  * Use Ctrl-c to get out of the camera view
* Run the following commands in the terminal:
```
sudo apt update && sudo apt -y upgrade
sudo apt install -y python3-picamera2 python3-gpiozero python3-evdev
wget https://github.com/ctrlw/magni/raw/master/magni.py
chmod +x magni.py
echo "clear" >> .bashrc
echo "./magni.py" >> .bashrc
```
* To have a lower-quality fallback when the monitor / TV is switched on *after* the magnifier, edit /boot/config.txt:
 `sudo nano /boot/config.txt`
  * Move to the line "#hdmi_force_hotplug=1" and delete the first character (#)
  * Leave nano with Ctrl-x, press “y” to save and enter to update the given file

* To hide the messages during startup, edit /boot/cmdline.txt:
`sudo nano /boot/cmdline.txt`
  * Append the following at the end of the line and save the file:
` logo.nologo quiet splash`
  * Leave nano with Ctrl-x, press “y” to save and enter to update the given file

### Support hard shut-down
This step allows to simply unplug the Raspberry Pi without possible damage to the SD card. This should be the last step, as the system will be made read-only (but it can be undone if needed).
This feature is now supported out of the box on Raspberry Pi OS, so no extra script is needed anymore.

Run `sudo raspi-config`
* Performance options -> Overlay File System
  * Enable overlay file system: Yes
  * Write-protect boot partition: Yes
  * Reboot? Yes

Now you can still create and modify files locally, but they will not be written to the SD card and disappear on the next reboot.
If you want to make the system writable again, you can do it in 2 steps with raspi-config:
* Disable the Overlay File System, so you can write to the file-system
* If you also want to modify the boot partition, you have to do it in a second step after rebooting

## Camera focus
**If you use the camera v3 with its autofocus you can skip this step as it doesn't need manual setup.**

When everything is in place, adjust the focus till a letter under the camera looks sharp. Then try a book and maybe adjust. Not all objects are flat. The  Raspberry Pi camera v2 usually comes with a white ring tool to easily adjust focus. On the older camera model or cheap alternatives, the lens may be glued and can still be adapted, but you risk breaking the camera.

![Adjust camera focus](docs/camera-focus-300x225.jpg)

## Modifications
You can easily adapt magni.py to your own setup and needs:
* `SCALE_FACTORS`: Modify this line to specify the scale factors
* `PIN_NUMBER_SCALE`: Set the (BCM) GPIO pin number where you connect the optional scale push-button
* `PIN_NUMBER_COLOR`: Set the (BCM) GPIO pin number where you connect the optional colour-mode push-button
* `ROTATION`: Change the value to the camera rotation in your setup if the camera is not placed behind the object (supports 0, 180; picamera on legacy OS also allowed 90 and 270 but this isn't the case on newer OS versions)

## Limitations
* Magnification is done in software, so scale factors above 10 tend to be noisy
* On older cameras the camera focus is fixed, so it cannot adapt to objects that are much closer or further away. However, v3 supports autofocus
* It may take a minute from power on till the picture is shown (depending on model and SD card)
