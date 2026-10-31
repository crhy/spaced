import time
from pathlib import Path
from evdev import UInput, ecodes as e
caps={e.EV_KEY:[e.BTN_LEFT,e.BTN_RIGHT,e.BTN_MIDDLE], e.EV_REL:[e.REL_X,e.REL_Y,e.REL_WHEEL,e.REL_WHEEL_HI_RES]}
with UInput(caps, name='Release high-resolution wheel probe') as dev:
    Path('/tmp/wheel-device-ready').touch()
    for i in range(3600):
        if Path('/tmp/wheel-trigger').exists():
            Path('/tmp/wheel-trigger').unlink()
            for step in range(8):
                dev.write(e.EV_REL,e.REL_WHEEL_HI_RES,15)
                if step==7: dev.write(e.EV_REL,e.REL_WHEEL,1)
                dev.syn()
                time.sleep(.05)
        time.sleep(.5)
