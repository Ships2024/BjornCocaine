import logging
import os

# Display resolution
EPD_WIDTH = 166
EPD_HEIGHT = 250

logger = logging.getLogger(__name__)

class EPD:
    def __init__(self):
        self.is_initialized = False
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    def reset(self):
        # No hardware reset needed for none
        pass

    def send_command(self, command):
        # Not applicable for none
        pass

    def send_data(self, data):
        # Not applicable for none
        pass

    def send_data2(self, data):
        # Not applicable for none
        pass

    def ReadBusy(self):
        # Not applicable for none
        pass

    def TurnOnDisplay(self):
        # Not applicable for none
        pass

    def TurnOnDisplay_Fast(self):
        # Not applicable for none
        pass

    def TurnOnDisplayPart(self):
        # Not applicable for none
        pass

    def SetWindow(self, x_start, y_start, x_end, y_end):
        # Not applicable for none
        pass

    def SetCursor(self, x, y):
        # Not applicable for none
        pass

    def init(self):
        if not self.is_initialized:
            self.is_initialized = True
        return 0

    def init_fast(self):
        return 0

    def getbuffer(self, image):
        return

    def display(self, image):
        # very important to implement! but none has nothing
        pass

    def display_fast(self, image):
        # very important to implement! but none has nothing
        pass

    def displayPartial(self, image):
        # very important to implement! but none has nothing
        pass

    def displayPartBaseImage(self, image):
        # important! but none has nothing
        pass

    def Clear(self, color=0xFF):
        # nothing to clear
        pass

    def sleep(self):
        # Not applicable for none
        pass
