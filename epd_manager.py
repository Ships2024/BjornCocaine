"""
EPD Manager - Singleton manager for e-Paper display
FIXED VERSION: Added operation timeouts, better error recovery, thread safety
"""

import threading
import importlib
import logging
import time
from PIL import Image
from logger import Logger

logger = Logger(name="epd_manager.py", level=logging.DEBUG)

# ============================================================================
# DEBUG CONFIGURATION
# ============================================================================
DEBUG_MANAGER = False  # Set to True to enable EPD Manager debugging


def debug_log(message, level='debug'):
    """Conditional debug logging for manager"""
    if DEBUG_MANAGER:
        if level == 'info':
            logger.info(f"[EPD_MANAGER] {message}")
        elif level == 'warning':
            logger.warning(f"[EPD_MANAGER] {message}")
        elif level == 'error':
            logger.error(f"[EPD_MANAGER] {message}")
        else:
            logger.debug(f"[EPD_MANAGER] {message}")


class EPDManager:
    """
    Singleton EPD Manager with robust timeout handling and error recovery
    """
    _instance = None
    _lock = threading.Lock()  # Global lock for all SPI access
    
    # Error handling configuration
    MAX_CONSECUTIVE_ERRORS = 3
    RESET_COOLDOWN = 5.0  # seconds between hard resets
    OPERATION_TIMEOUT = 15.0  # CRITICAL: max seconds for any EPD operation
    INIT_TIMEOUT = 20.0  # Longer timeout for initialization
    
    def __new__(cls, epd_type: str):
        if cls._instance is None:
            debug_log("Creating new EPDManager instance", 'info')
            cls._instance = super().__new__(cls)
            cls._instance._init_driver(epd_type)
        else:
            debug_log("Returning existing EPDManager instance", 'info')
        return cls._instance

    def _init_driver(self, epd_type: str):
        """Initialize EPD driver"""
        debug_log(f"Initializing driver: {epd_type}", 'info')
        
        self.epd_type = epd_type
        self.last_reset = time.time()
        self.error_count = 0
        self.last_error_time = 0
        self.operation_start_time = 0
        self.total_operations = 0
        self.successful_operations = 0
        self.timeout_count = 0
        
        try:
            epd_module_name = f"resources.waveshare_epd.{self.epd_type}"
            epd_module = importlib.import_module(epd_module_name)
            self.epd = epd_module.EPD()
            debug_log(f"EPD driver {self.epd_type} loaded successfully", 'info')
        except Exception as e:
            logger.error(f"Failed to load EPD driver {self.epd_type}: {e}")
            raise

    def _safe_call(self, func, *args, timeout=None, **kwargs):
        """
        Execute EPD function with timeout and error handling
        CRITICAL: Uses threading to implement timeout
        """
        if timeout is None:
            timeout = self.OPERATION_TIMEOUT
            
        with EPDManager._lock:
            self.total_operations += 1
            self.operation_start_time = time.time()
            
            debug_log(f"Executing operation #{self.total_operations}: {func.__name__} (timeout={timeout}s)")
            
            # Execute in separate thread to allow timeout
            result_container = {'result': None, 'error': None, 'completed': False}
            
            def execute_operation():
                try:
                    result_container['result'] = func(*args, **kwargs)
                    result_container['completed'] = True
                except Exception as e:
                    result_container['error'] = e
                    result_container['completed'] = True
            
            operation_thread = threading.Thread(target=execute_operation, daemon=True)
            operation_thread.start()
            operation_thread.join(timeout=timeout)
            
            operation_time = time.time() - self.operation_start_time
            
            # Check if operation completed
            if not result_container['completed']:
                # TIMEOUT occurred
                self.timeout_count += 1
                self.error_count += 1
                logger.error(f"EPD operation TIMEOUT after {timeout}s (timeout #{self.timeout_count})")
                
                # Perform recovery if too many timeouts
                if self.error_count >= self.MAX_CONSECUTIVE_ERRORS:
                    return self._perform_recovery(func, args, kwargs, 
                                                 TimeoutError(f"Operation timed out after {timeout}s"))
                else:
                    raise TimeoutError(f"EPD operation timed out after {timeout}s")
            
            # Check if operation had an error
            if result_container['error'] is not None:
                self.error_count += 1
                logger.error(f"EPD operation failed (error #{self.error_count}): {result_container['error']}")
                debug_log(f"Failed operation took {operation_time:.3f}s", 'error')
                
                # Check if we need to perform recovery
                if self.error_count >= self.MAX_CONSECUTIVE_ERRORS:
                    return self._perform_recovery(func, args, kwargs, result_container['error'])
                else:
                    # Simple retry without full reset
                    return self._simple_retry(func, args, kwargs, result_container['error'])
            
            # Operation successful
            self.successful_operations += 1
            self.error_count = 0
            
            debug_log(f"Operation completed successfully in {operation_time:.3f}s", 'info')
            return result_container['result']

    def _simple_retry(self, func, args, kwargs, original_error):
        """Attempt simple retry without full reset"""
        debug_log("Attempting simple retry after error", 'warning')
        
        try:
            time.sleep(0.5)  # Brief delay before retry
            
            # Use shorter timeout for retry
            result_container = {'result': None, 'error': None, 'completed': False}
            
            def execute_retry():
                try:
                    result_container['result'] = func(*args, **kwargs)
                    result_container['completed'] = True
                except Exception as e:
                    result_container['error'] = e
                    result_container['completed'] = True
            
            retry_thread = threading.Thread(target=execute_retry, daemon=True)
            retry_thread.start()
            retry_thread.join(timeout=self.OPERATION_TIMEOUT)
            
            if result_container['completed'] and result_container['error'] is None:
                debug_log("Simple retry successful", 'info')
                self.error_count = 0
                self.successful_operations += 1
                return result_container['result']
            
            # Retry failed
            logger.error(f"Simple retry failed: {result_container.get('error', 'timeout')}")
            raise original_error
            
        except Exception as e:
            logger.error(f"Simple retry failed: {e}")
            raise original_error

    def _perform_recovery(self, func, args, kwargs, original_error):
        """Perform full recovery with hard reset"""
        current_time = time.time()
        time_since_last_reset = current_time - self.last_reset
        
        debug_log(f"Too many errors ({self.error_count}), initiating recovery", 'warning')
        
        # Enforce cooldown between resets
        if time_since_last_reset < self.RESET_COOLDOWN:
            wait_time = self.RESET_COOLDOWN - time_since_last_reset
            logger.warning(f"Reset cooldown active, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        
        # Attempt hard reset
        try:
            debug_log("Performing hard reset...", 'warning')
            self.hard_reset()
            self.error_count = 0
            
            # Retry operation after reset with timeout
            debug_log("Retrying operation after hard reset")
            
            result_container = {'result': None, 'error': None, 'completed': False}
            
            def execute_after_reset():
                try:
                    result_container['result'] = func(*args, **kwargs)
                    result_container['completed'] = True
                except Exception as e:
                    result_container['error'] = e
                    result_container['completed'] = True
            
            reset_retry_thread = threading.Thread(target=execute_after_reset, daemon=True)
            reset_retry_thread.start()
            reset_retry_thread.join(timeout=self.OPERATION_TIMEOUT)
            
            if result_container['completed'] and result_container['error'] is None:
                debug_log("Recovery successful", 'info')
                self.successful_operations += 1
                return result_container['result']
            
            # Recovery failed
            logger.critical(f"Recovery failed: {result_container.get('error', 'timeout')}")
            
        except Exception as e:
            logger.critical(f"Recovery failed catastrophically: {e}")
        
        # Calculate success rate
        if self.total_operations > 0:
            success_rate = (self.successful_operations / self.total_operations) * 100
            logger.error(f"EPD success rate: {success_rate:.1f}% "
                       f"({self.successful_operations}/{self.total_operations}), "
                       f"timeouts: {self.timeout_count}")
        
        self.error_count = 0  # Reset to prevent infinite recovery attempts
        raise original_error

    def hard_reset(self):
        """
        Perform complete hardware and software reset with timeout protection
        """
        debug_log("Starting hard reset sequence", 'warning')
        
        reset_start = time.time()
        
        try:
            # Step 1: Clean shutdown of existing SPI connection
            debug_log("Step 1: Closing existing SPI connection")
            try:
                if hasattr(self.epd, 'epdconfig'):
                    self.epd.epdconfig.module_exit()
                    time.sleep(0.5)
            except Exception as e:
                debug_log(f"Error during SPI shutdown: {e}", 'warning')
            
            # Step 2: Hardware reset
            debug_log("Step 2: Hardware reset")
            try:
                self.epd.reset()
                time.sleep(0.2)
            except Exception as e:
                debug_log(f"Error during hardware reset: {e}", 'warning')
            
            # Step 3: Reset initialization flags
            debug_log("Step 3: Resetting initialization flags")
            self.epd.is_initialized = False
            if hasattr(self.epd, 'is_partial_configured'):
                self.epd.is_partial_configured = False
            
            # Step 4: Reinitialize SPI with timeout
            debug_log("Step 4: Reinitializing SPI")
            if hasattr(self.epd, 'epdconfig'):
                def reinit_spi():
                    ret = self.epd.epdconfig.module_init()
                    if ret != 0:
                        raise RuntimeError("SPI reinitialization failed")
                    time.sleep(0.5)
                
                reinit_thread = threading.Thread(target=reinit_spi, daemon=True)
                reinit_thread.start()
                reinit_thread.join(timeout=5.0)
                
                if reinit_thread.is_alive():
                    raise TimeoutError("SPI reinitialization timed out")
            
            # Step 5: Reinitialize EPD with timeout
            debug_log("Step 5: Reinitializing EPD")
            
            def reinit_epd():
                self.epd.init()
            
            epd_init_thread = threading.Thread(target=reinit_epd, daemon=True)
            epd_init_thread.start()
            epd_init_thread.join(timeout=self.INIT_TIMEOUT)
            
            if epd_init_thread.is_alive():
                raise TimeoutError("EPD reinitialization timed out")
            
            # Update reset timestamp
            self.last_reset = time.time()
            reset_duration = self.last_reset - reset_start
            
            logger.warning(f"EPD hard reset completed successfully in {reset_duration:.2f}s")
            debug_log("Hard reset sequence complete", 'info')
            
        except Exception as e:
            logger.critical(f"Hard reset failed catastrophically: {e}")
            raise

    def check_health(self):
        """
        Check EPD manager health status
        Returns: dict with health metrics
        """
        current_time = time.time()
        uptime = current_time - self.last_reset
        
        if self.total_operations > 0:
            success_rate = (self.successful_operations / self.total_operations) * 100
        else:
            success_rate = 100.0
        
        health = {
            'uptime_seconds': uptime,
            'total_operations': self.total_operations,
            'successful_operations': self.successful_operations,
            'success_rate': success_rate,
            'consecutive_errors': self.error_count,
            'timeout_count': self.timeout_count,
            'last_reset': self.last_reset,
            'is_healthy': self.error_count == 0 and success_rate > 95.0
        }
        
        debug_log(f"Health check: {health}", 'info')
        return health

    # ========================================================================
    # Public API Methods with Timeout Protection
    # ========================================================================

    def init_full_update(self):
        """Initialize EPD for full update mode"""
        debug_log("API: init_full_update", 'info')
        return self._safe_call(self._init_full, timeout=self.INIT_TIMEOUT)

    def init_partial_update(self):
        """Initialize EPD for partial update mode"""
        debug_log("API: init_partial_update")
        return self._safe_call(self._init_partial, timeout=self.INIT_TIMEOUT)

    def display_partial(self, image):
        """Display image using partial update"""
        debug_log("API: display_partial")
        return self._safe_call(self._display_partial, image)

    def display_full(self, image):
        """Display image using full update"""
        debug_log("API: display_full", 'info')
        return self._safe_call(self._display_full, image)

    def clear(self):
        """Clear display"""
        debug_log("API: clear", 'info')
        return self._safe_call(self._clear)

    def sleep(self):
        """Put display to sleep"""
        debug_log("API: sleep", 'info')
        return self._safe_call(self._sleep, timeout=5.0)

    # ========================================================================
    # Protected Implementation Methods
    # ========================================================================

    def _init_full(self):
        """Initialize for full update (protected)"""
        debug_log("Initializing full update mode")
        
        if hasattr(self.epd, "FULL_UPDATE"):
            self.epd.init(self.epd.FULL_UPDATE)
        elif hasattr(self.epd, "lut_full_update"):
            self.epd.init(self.epd.lut_full_update)
        else:
            self.epd.init()
        
        debug_log("Full update mode initialized")

    def _init_partial(self):
        """Initialize for partial update (protected)"""
        debug_log("Initializing partial update mode")
        
        if hasattr(self.epd, "PART_UPDATE"):
            self.epd.init(self.epd.PART_UPDATE)
        elif hasattr(self.epd, "lut_partial_update"):
            self.epd.init(self.epd.lut_partial_update)
        else:
            self.epd.init()
        
        debug_log("Partial update mode initialized")

    def _display_partial(self, image):
        """Display using partial update (protected)"""
        debug_log("Executing partial display")
        
        if hasattr(self.epd, "displayPartial"):
            self.epd.displayPartial(self.epd.getbuffer(image))
        else:
            debug_log("No displayPartial method, using standard display", 'warning')
            self.epd.display(self.epd.getbuffer(image))

    def _display_full(self, image):
        """Display using full update (protected)"""
        debug_log("Executing full display")
        self.epd.display(self.epd.getbuffer(image))

    def _clear(self):
        """Clear display (protected)"""
        debug_log("Clearing display")
        
        if hasattr(self.epd, "Clear"):
            self.epd.Clear()
        else:
            debug_log("No Clear method, displaying white image", 'warning')
            w, h = self.epd.width, self.epd.height
            blank = Image.new("1", (w, h), 255)
            self._display_partial(blank)

    def _sleep(self):
        """Put display to sleep (protected)"""
        debug_log("Putting display to sleep")
        
        if hasattr(self.epd, "sleep"):
            self.epd.sleep()
        else:
            debug_log("No sleep method available", 'warning')


### END OF FILE ###