# magni
Software for a simple video magnifier running on Raspberry Pi

## Description
This project aims to build a video magnifier based on Raspberry Pi and its camera. It can be used to see printed text or images at a larger scale, or to identify small parts like SMD electronics. The device has to be connected to a monitor which will display the image from the camera at a specific magnification level. The user can step through predefined scale factors with a push-button or the Enter key, and switch to colour-inversion with a second push button or the "/" key.
After the initial setup, the device works fully offline and does not need an internet connection.

## Hardware
To build the magnifier, you need at least the following
* Raspberry Pi
  * any model will do (Raspberry Pi Zero is nice for its size, but needs specific cables/adapters for camera and USB)
* Raspberry Pi camera
  * Strongly recommended is an official Raspberry Pi camera v2, due to better image quality and flexible focus
* Raspberry Pi camera cable
  * only if the standard 15cm cable is too short or you need the smaller cable for Raspberry Pi Zero
* Micro USB charger
* Micro SD card (>= 4GB)
* HDMI monitor + cable
* Material for the mount

A more in-depth description of 2 hardware setups is given at http://www.fhack.org/2018/12/19/raspberry-pi-video-magnifier-2018/

If you use the optional push buttons, the script expects them at Pin 7 for the scale button and Pin 12 for the colour-switch button, using physical numbering (7 being the 4th pin on the left, 12 being the 6th pin on the right of the GPIO). Each button needs to be connected with GND, e.g. at pins 9 and 14.

## Setup
* Download [Raspberry Pi OS Lite](https://www.raspberrypi.org/software/operating-systems/) and install on SD card
* Connect camera
* Login with default user “pi”, password “raspberry” (if on desktop, open a terminal)
* Run `sudo raspi-config`
  * System options -> Boot / Autologin -> Console Autologin
  * Interface options -> Camera -> Enable
  * System options -> Wireless LAN (if you want to connect from another computer by wifi)
  * Interface options -> SSH -> Enable (only if you want to connect from another computer)
  * Save and `sudo reboot`
* After reboot, adapt the camera focus to your setup: `raspivid -f -rot 180 -t 0`
  * If you see the current camera view, and it's at the same angle that you have from above (e.g. it’s not upside down), you’re good, otherwise try different values for rot (0, 90, 180, 270) and adapt them later in magni.py
  * If the image is blurry you should adjust the focus, simply turning the lens with the plastic “wheel” that comes with the Pi camera v2
  * Use Ctrl-c to get out of the camera view
* Run the following commands in the terminal:
```
sudo apt-get -y update
sudo apt-get -y upgrade
sudo apt-get install -y python3-rpi.gpio python3-picamera
wget https://github.com/ctrlw/magni/raw/master/magni.py
chmod +x magni.py
echo "clear" >> .bashrc
echo "./magni.py" >> .bashrc
```
* To hide the messages during startup, edit /boot/cmdline.txt:
`sudo nano /boot/cmdline.txt`
  * Append the following at the end of the line and save the file:
` logo.nologo quiet splash`
  * Leave nano with Ctrl-x, press “y” to save and enter to update the given file

### Support hard shut-down
This step allows to simply unplug the Raspberry Pi without possible damage to the SD card. This should be the last step, as the system will be made read-only.
```
wget https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/raw/master/read-only-fs.sh
sudo bash read-only-fs.sh
```
The script asks a couple of questions:
* Continue? y
* Enable boot-time read/write jumper? N
* Install GPIO-halt utility? N
* Enable kernel panic watchdog? N
* CONTINUE? y

If you want to do changes after running the script, run the following commands:
* to enable writing again: `mount -o remount,rw /`
* to make it read-only again: `mount -o remount,ro /`

You can use them to change files like magni.py later, but they will not undo all the changes from the read-only-fs.sh script.

## Modifications
You can easily adapt magni.py to your own setup and needs:
* `DISTANCE_TO_SURFACE_CM`: Distance between the camera lens and the surface, adapt it to your setup
* `WIDTHS_CM`: Defines the approximate widths you can iterate through with the scale button. You can change the values, e.g. to the column widths of expected reading material, add more values or remove some
* `SCALE_FACTORS`: Uncomment and modify this line if you rather want to specify scale factors directly instead of line widths
* `PIN_NUMBER_SCALE`: Set the (physical) GPIO pin number where you connect the optional scale push-button
* `PIN_NUMBER_COLOR`: Set the (physical) GPIO pin number where you connect the optional colour-mode push-button
* `KEY_NUMBER_SCALE`: Set the keyboard key you want to use to switch through scale factors
* `KEY_NUMBER_COLOR`: Set the keyboard key you want to use to toggle the colour-mode
* `KEY_NUMBER_ESCAPE`: Set the keyboard key you want to use to get back to command line
* `ROTATION`: Change the value to the camera rotation in your setup if the camera is not placed behind the object (supports 0, 90, 180 and 270)

## Limitations
* Magnification is done in software, so scale factors above 10 tend to be noisy (with Raspberry Pi camera v2)
* The camera focus is fixed, so it cannot adapt to objects that are much closer or further
* It may take 1 minute from power on till the picture is shown (depending on model and SD card)
