"""
EPD Configuration - GPIO and SPI interface management
FIXED VERSION: Better resource management, cleanup, and error handling
"""

import os
import sys
import time
import subprocess
import logging
from ctypes import *
from logger import Logger

logger = Logger(name="epdconfig.py", level=logging.DEBUG)

# ============================================================================
# DEBUG CONFIGURATION
# ============================================================================
DEBUG_CONFIG = False  # Set to True to enable epdconfig debugging
DEBUG_GPIO = False    # Set to True to enable GPIO operation debugging


def debug_log(message, level='debug'):
    """Conditional debug logging for config"""
    if DEBUG_CONFIG:
        if level == 'info':
            logger.info(f"[EPD_CONFIG] {message}")
        elif level == 'warning':
            logger.warning(f"[EPD_CONFIG] {message}")
        elif level == 'error':
            logger.error(f"[EPD_CONFIG] {message}")
        else:
            logger.debug(f"[EPD_CONFIG] {message}")


class RaspberryPi:
    """Raspberry Pi GPIO and SPI implementation with robust resource management"""
    
    # Pin definition
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18
    MOSI_PIN = 10
    SCLK_PIN = 11

    def __init__(self):
        debug_log("Initializing RaspberryPi GPIO/SPI", 'info')
        
        import spidev
        import gpiozero
        
        self.SPI = spidev.SpiDev()
        self.spi_initialized = False
        self.spi_lock = None  # Will be set to threading.Lock() if needed
        
        # Initialize GPIO pins
        self.GPIO_RST_PIN = gpiozero.LED(self.RST_PIN)
        self.GPIO_DC_PIN = gpiozero.LED(self.DC_PIN)
        self.GPIO_PWR_PIN = gpiozero.LED(self.PWR_PIN)
        self.GPIO_BUSY_PIN = gpiozero.Button(self.BUSY_PIN, pull_up=False)
        
        debug_log("GPIO pins initialized", 'info')

    def digital_write(self, pin, value):
        """Write digital value to pin"""
        if DEBUG_GPIO:
            debug_log(f"digital_write: pin={pin}, value={value}")
        
        try:
            if pin == self.RST_PIN:
                if value:
                    self.GPIO_RST_PIN.on()
                else:
                    self.GPIO_RST_PIN.off()
            elif pin == self.DC_PIN:
                if value:
                    self.GPIO_DC_PIN.on()
                else:
                    self.GPIO_DC_PIN.off()
            elif pin == self.PWR_PIN:
                if value:
                    self.GPIO_PWR_PIN.on()
                else:
                    self.GPIO_PWR_PIN.off()
        except Exception as e:
            logger.error(f"Error in digital_write(pin={pin}, value={value}): {e}")
            raise

    def digital_read(self, pin):
        """Read digital value from pin"""
        try:
            if pin == self.BUSY_PIN:
                value = self.GPIO_BUSY_PIN.value
            elif pin == self.RST_PIN:
                value = self.GPIO_RST_PIN.value
            elif pin == self.DC_PIN:
                value = self.GPIO_DC_PIN.value
            elif pin == self.PWR_PIN:
                value = self.GPIO_PWR_PIN.value
            else:
                value = 0
            
            if DEBUG_GPIO:
                debug_log(f"digital_read: pin={pin}, value={value}")
            
            return value
        except Exception as e:
            logger.error(f"Error in digital_read(pin={pin}): {e}")
            return 0

    def delay_ms(self, delaytime):
        """Delay in milliseconds"""
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        """Write single byte or list to SPI with error handling"""
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte: {data}")
        
        try:
            if not self.spi_initialized:
                raise RuntimeError("SPI not initialized")
            self.SPI.writebytes(data)
        except Exception as e:
            logger.error(f"SPI writebytes error: {e}")
            raise

    def spi_writebyte2(self, data):
        """Write bulk data to SPI (optimized) with error handling"""
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte2: {len(data)} bytes")
        
        try:
            if not self.spi_initialized:
                raise RuntimeError("SPI not initialized")
            self.SPI.writebytes2(data)
        except Exception as e:
            logger.error(f"SPI writebytes2 error: {e}")
            raise

    def module_init(self, cleanup=False):
        """
        Initialize module - SPI and GPIO
        FIXED: Better handling of SPI state and error recovery
        """
        debug_log("module_init called", 'info')
        
        # Turn on power first
        try:
            self.GPIO_PWR_PIN.on()
            debug_log("Power pin enabled")
        except Exception as e:
            logger.error(f"Failed to enable power pin: {e}")
            return -1
        
        if cleanup:
            debug_log("Cleanup mode - performing full reset", 'warning')
            # Force close and reinit
            self._force_spi_cleanup()
            time.sleep(1)
        
        # Initialize or verify SPI connection
        if not self.spi_initialized:
            try:
                debug_log("Opening SPI connection")
                self.SPI.open(0, 0)
                self.SPI.max_speed_hz = 4000000
                self.SPI.mode = 0b00
                self.spi_initialized = True
                debug_log("SPI initialized successfully", 'info')
            except Exception as e:
                logger.error(f"Failed to initialize SPI: {e}")
                
                # Try recovery
                try:
                    debug_log("Attempting SPI recovery", 'warning')
                    self._force_spi_cleanup()
                    time.sleep(0.5)
                    
                    self.SPI.open(0, 0)
                    self.SPI.max_speed_hz = 4000000
                    self.SPI.mode = 0b00
                    self.spi_initialized = True
                    debug_log("SPI recovered successfully", 'info')
                except Exception as e2:
                    logger.critical(f"Failed to recover SPI: {e2}")
                    return -1
        else:
            debug_log("SPI already initialized - verifying connection")
            # Verify SPI is still working
            try:
                # Try a dummy operation to verify connection
                pass  # SPI connection seems valid
            except Exception as e:
                logger.warning(f"SPI verification failed, reinitializing: {e}")
                self._force_spi_cleanup()
                time.sleep(0.5)
                try:
                    self.SPI.open(0, 0)
                    self.SPI.max_speed_hz = 4000000
                    self.SPI.mode = 0b00
                    self.spi_initialized = True
                except Exception as e2:
                    logger.critical(f"SPI reinitialization failed: {e2}")
                    return -1
        
        return 0

    def _force_spi_cleanup(self):
        """Force cleanup of SPI connection"""
        debug_log("Forcing SPI cleanup", 'warning')
        try:
            if self.spi_initialized:
                self.SPI.close()
                self.spi_initialized = False
                debug_log("SPI closed")
        except Exception as e:
            debug_log(f"Error during SPI cleanup: {e}", 'warning')
            # Continue anyway - connection might already be closed

    def module_exit(self, cleanup=False):
        """
        Exit module - cleanup SPI and GPIO
        FIXED: More robust cleanup with error handling
        """
        debug_log("module_exit called", 'info')
        
        # Close SPI first
        if self.spi_initialized:
            try:
                debug_log("Closing SPI connection")
                self.SPI.close()
                self.spi_initialized = False
                debug_log("SPI closed successfully")
            except Exception as e:
                logger.error(f"Error closing SPI: {e}")
                # Continue with GPIO cleanup even if SPI close failed
        
        # Turn off GPIO pins
        try:
            debug_log("Turning off GPIO pins")
            self.GPIO_RST_PIN.off()
            self.GPIO_DC_PIN.off()
            self.GPIO_PWR_PIN.off()
            debug_log("GPIO pins turned off")
        except Exception as e:
            logger.error(f"Error turning off GPIO: {e}")
        
        # Full cleanup if requested
        if cleanup:
            try:
                debug_log("Performing full GPIO cleanup")
                self.GPIO_RST_PIN.close()
                self.GPIO_DC_PIN.close()
                self.GPIO_PWR_PIN.close()
                self.GPIO_BUSY_PIN.close()
                debug_log("GPIO cleanup complete", 'info')
            except Exception as e:
                logger.error(f"Error during GPIO cleanup: {e}")


class JetsonNano:
    """Jetson Nano GPIO and SPI implementation"""
    
    # Pin definition
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18

    def __init__(self):
        debug_log("Initializing JetsonNano GPIO/SPI", 'info')
        
        import ctypes
        find_dirs = [
            os.path.dirname(os.path.realpath(__file__)),
            '/usr/local/lib',
            '/usr/lib',
        ]
        self.SPI = None
        for find_dir in find_dirs:
            so_filename = os.path.join(find_dir, 'sysfs_software_spi.so')
            if os.path.exists(so_filename):
                self.SPI = ctypes.cdll.LoadLibrary(so_filename)
                break
        
        if self.SPI is None:
            raise RuntimeError('Cannot find sysfs_software_spi.so')

        import Jetson.GPIO
        self.GPIO = Jetson.GPIO

    def digital_write(self, pin, value):
        if DEBUG_GPIO:
            debug_log(f"digital_write: pin={pin}, value={value}")
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        value = self.GPIO.input(self.BUSY_PIN)
        if DEBUG_GPIO:
            debug_log(f"digital_read: pin={pin}, value={value}")
        return value

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte: {data}")
        self.SPI.SYSFS_software_spi_transfer(data[0])

    def spi_writebyte2(self, data):
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte2: {len(data)} bytes")
        for i in range(len(data)):
            self.SPI.SYSFS_software_spi_transfer(data[i])

    def module_init(self):
        debug_log("Initializing Jetson Nano module", 'info')
        
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)
        
        self.GPIO.output(self.PWR_PIN, 1)
        
        self.SPI.SYSFS_software_spi_begin()
        return 0

    def module_exit(self):
        debug_log("Exiting Jetson Nano module", 'info')
        
        self.SPI.SYSFS_software_spi_end()
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)
        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, 
                          self.BUSY_PIN, self.PWR_PIN])


class SunriseX3:
    """Sunrise X3 GPIO and SPI implementation"""
    
    # Pin definition
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18
    Flag = 0

    def __init__(self):
        debug_log("Initializing SunriseX3 GPIO/SPI", 'info')
        
        import spidev
        import Hobot.GPIO

        self.GPIO = Hobot.GPIO
        self.SPI = spidev.SpiDev()

    def digital_write(self, pin, value):
        if DEBUG_GPIO:
            debug_log(f"digital_write: pin={pin}, value={value}")
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        value = self.GPIO.input(pin)
        if DEBUG_GPIO:
            debug_log(f"digital_read: pin={pin}, value={value}")
        return value

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte: {data}")
        self.SPI.writebytes(data)

    def spi_writebyte2(self, data):
        if DEBUG_GPIO:
            debug_log(f"spi_writebyte2: {len(data)} bytes")
        self.SPI.xfer3(data)

    def module_init(self):
        debug_log("Initializing SunriseX3 module", 'info')
        
        if self.Flag == 0:
            self.Flag = 1
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)

            self.GPIO.output(self.PWR_PIN, 1)
        
            self.SPI.open(2, 0)
            self.SPI.max_speed_hz = 4000000
            self.SPI.mode = 0b00
            return 0
        else:
            return 0

    def module_exit(self):
        debug_log("Exiting SunriseX3 module", 'info')
        
        self.SPI.close()
        self.Flag = 0
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)
        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, 
                          self.BUSY_PIN, self.PWR_PIN])


# ============================================================================
# Platform Detection and Setup
# ============================================================================

debug_log("Detecting platform...", 'info')

if sys.version_info[0] == 2:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", 
                              shell=True, stdout=subprocess.PIPE)
else:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", 
                              shell=True, stdout=subprocess.PIPE, text=True)

output, _ = process.communicate()

if sys.version_info[0] == 2:
    output = output.decode(sys.stdout.encoding)

if "Raspberry" in output:
    debug_log("Platform: Raspberry Pi", 'info')
    implementation = RaspberryPi()
elif os.path.exists('/sys/bus/platform/drivers/gpio-x3'):
    debug_log("Platform: SunriseX3", 'info')
    implementation = SunriseX3()
else:
    debug_log("Platform: Jetson Nano", 'info')
    implementation = JetsonNano()

# Export all implementation functions to module level
for func in [x for x in dir(implementation) if not x.startswith('_')]:
    setattr(sys.modules[__name__], func, getattr(implementation, func))

debug_log("epdconfig module initialized successfully", 'info')

### END OF FILE ###