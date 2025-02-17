import logging
import os
from PIL import Image

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
        # No hardware reset needed for framebuffer
        pass

    def send_command(self, command):
        # Not applicable for framebuffer
        pass

    def send_data(self, data):
        # Not applicable for framebuffer
        pass

    def send_data2(self, data):
        # Not applicable for framebuffer
        pass

    def ReadBusy(self):
        # Not applicable for framebuffer
        pass

    def TurnOnDisplay(self):
        # Not applicable for framebuffer
        pass

    def TurnOnDisplay_Fast(self):
        # Not applicable for framebuffer
        pass

    def TurnOnDisplayPart(self):
        # Not applicable for framebuffer
        pass

    def SetWindow(self, x_start, y_start, x_end, y_end):
        # Not applicable for framebuffer
        pass

    def SetCursor(self, x, y):
        # Not applicable for framebuffer
        pass

    def init(self):
        if not self.is_initialized:
            self.is_initialized = True
        return 0

    def init_fast(self):
        return 0

    def getbuffer(self, image):
        img = image
        imwidth, imheight = img.size

        if imwidth == self.width and imheight == self.height:
            img = img.convert('RGB') # Convert to RGB for fbi
        elif imwidth == self.height and imheight == self.width:
            img = img.rotate(90, expand=True).convert('RGB')
        else:
            logger.warning("Wrong image dimensions: must be " + str(self.width) + "x" + str(self.height))
            # Create a blank image if dimensions are wrong
            img = Image.new("RGB", (self.width, self.height), "white") # White background

        return img

    def display(self, image):
        # create a copy to temp so we don't deal with clearing this
        temp_filename = "/tmp/temp.png"
        image.save(temp_filename)

        try:
            os.system(f"fbi -d /dev/fb0 -noverbose -T 1 -a {temp_filename}") # -T 1 to disable console output
        except FileNotFoundError:
            pass  # Or, if you want to do *something* in case of an error, put it here.
        #finally:
        #    # Some might try this but this will cause flicker on LCD, hence a copy on tmp to let OS GC
        #    os.remove(temp_filename)

    def display_fast(self, image):
        #self.display(image) # Same as regular display for framebuffer
        pass

    def displayPartial(self, image):
        self.display(image) # Same as regular display for framebuffer

    def displayPartBaseImage(self, image):
        #self.display(image) # Same as regular display for framebuffer
        pass

    def Clear(self, color=0xFF):
        # Create a blank image and display it
        if color == 0xFF: #default is white
            img = Image.new("RGB", (self.width, self.height), "white")
        else:
            # Assuming color is an integer representing a grayscale value (0-255)
            img = Image.new("RGB", (self.width, self.height), (color, color, color))
        self.display(img)

    def sleep(self):
        # Not applicable for framebuffer
        pass
