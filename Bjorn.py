# bjorn.py
import threading
import signal
import logging
import time
import sys
import subprocess
import re
from init_shared import shared_data
from display import Display, handle_exit_display
from comment import Commentaireia
from webapp import web_thread, handle_exit_web
from orchestrator import Orchestrator
from logger import Logger

logger = Logger(name="Bjorn.py", level=logging.DEBUG)

class Bjorn:
    """Main class for Bjorn. Manages the primary operations of the application."""
    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.commentaire_ia = Commentaireia()
        self.orchestrator_thread = None
        self.orchestrator = None
        self.network_connected = False
        self.wifi_connected = False
        self.previous_network_connected = None  # Pour garder une trace de l'état précédent

    def run(self):
        """Main loop for Bjorn. Waits for Wi-Fi connection and starts Orchestrator."""
        # Wait for startup delay if configured in shared data
        if hasattr(self.shared_data, 'startup_delay') and self.shared_data.startup_delay > 0:
            logger.info(f"Waiting for startup delay: {self.shared_data.startup_delay} seconds")
            time.sleep(self.shared_data.startup_delay)

        # Main loop to keep Bjorn running
        while not self.shared_data.should_exit:
            if not self.shared_data.manual_mode:
                self.check_and_start_orchestrator()
            time.sleep(10)  # Main loop idle waiting

    def check_and_start_orchestrator(self):
        """Check Wi-Fi and start the orchestrator if connected."""
        if self.is_network_connected():
            self.wifi_connected = True
            if self.orchestrator_thread is None or not self.orchestrator_thread.is_alive():
                self.start_orchestrator()
        else:
            self.wifi_connected = False
            logger.info("Waiting for Wi-Fi connection to start Orchestrator...")

    def start_orchestrator(self):
        """Start the orchestrator thread."""
        self.is_network_connected() # reCheck if Wi-Fi is connected before starting the orchestrator
        # time.sleep(10)  # Wait for network to stabilize
        if self.wifi_connected:  # Check if Wi-Fi is connected before starting the orchestrator
            if self.orchestrator_thread is None or not self.orchestrator_thread.is_alive():
                logger.info("Starting Orchestrator thread...")
                self.shared_data.orchestrator_should_exit = False
                self.shared_data.manual_mode = False
                self.orchestrator = Orchestrator()
                self.orchestrator_thread = threading.Thread(target=self.orchestrator.run)
                self.orchestrator_thread.start()
                logger.info("Orchestrator thread started, automatic mode activated.")
            else:
                logger.info("Orchestrator thread is already running.")
        else:
            pass
            
    def stop_orchestrator(self):
        """Stop the orchestrator thread."""
        self.shared_data.manual_mode = True
        logger.info("Stop button pressed. Manual mode activated & Stopping Orchestrator...")
        if self.orchestrator_thread is not None and self.orchestrator_thread.is_alive():
            logger.info("Stopping Orchestrator thread...")
            self.shared_data.orchestrator_should_exit = True
            self.orchestrator_thread.join()
            logger.info("Orchestrator thread stopped.")
            self.shared_data.bjorn_orch_status = "IDLE"
            self.shared_data.bjorn_status_text2 = ""
            self.shared_data.manual_mode = True
        else:
            logger.info("Orchestrator thread is not running.")

    
    def is_network_connected(self):
        """Checks for network connectivity on eth0 or wlan0 using ip command (replacing deprecated ifconfig)."""
        logger = logging.getLogger("Bjorn.py")

        def interface_has_ip(interface_name):
            try:
                # Use 'ip -4 addr show <interface>' to check for IPv4 address
                result = subprocess.run(
                    ['ip', '-4', 'addr', 'show', interface_name], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True
                )
                if result.returncode != 0:
                    return False
                # Check if output contains "inet" which indicates an IP address
                return 'inet' in result.stdout
            except Exception:
                return False

        eth_connected = interface_has_ip('eth0')
        wifi_connected = interface_has_ip('wlan0')

        self.network_connected = eth_connected or wifi_connected

        if self.network_connected != self.previous_network_connected:
            if self.network_connected:
                logger.info(f"Network is connected (eth0={eth_connected}, wlan0={wifi_connected}).")
            else:
                logger.warning("No active network connections found.")
            
            self.previous_network_connected = self.network_connected

        return self.network_connected

    
    @staticmethod
    def start_display():
        """Start the display thread"""
        display = Display(shared_data)
        display_thread = threading.Thread(target=display.run)
        display_thread.start()
        return display_thread

def handle_exit(sig, frame, display_thread, bjorn_thread, web_thread):
    """Handles the termination of the main, display, and web threads."""
    shared_data.should_exit = True
    shared_data.orchestrator_should_exit = True  # Ensure orchestrator stops
    shared_data.display_should_exit = True  # Ensure display stops
    shared_data.webapp_should_exit = True  # Ensure web server stops
    handle_exit_display(sig, frame, display_thread)
    if display_thread.is_alive():
        display_thread.join()
    if bjorn_thread.is_alive():
        bjorn_thread.join()
    if web_thread.is_alive():
        web_thread.join()
    logger.info("Main loop finished. Clean exit.")
    sys.exit(0)

if __name__ == "__main__":
    logger.info("Starting threads")

    try:
        logger.info("Loading shared data config...")
        shared_data.load_config()

        logger.info("Starting display thread...")
        shared_data.display_should_exit = False  # Initialize display should_exit
        display_thread = Bjorn.start_display()

        logger.info("Starting Bjorn thread...")
        bjorn = Bjorn(shared_data)
        shared_data.bjorn_instance = bjorn  # Assigner l'instance de Bjorn à shared_data
        bjorn_thread = threading.Thread(target=bjorn.run)
        bjorn_thread.start()

        if shared_data.config["websrv"]:
            logger.info("Starting the web server...")
            web_thread.start()

        signal.signal(signal.SIGINT, lambda sig, frame: handle_exit(sig, frame, display_thread, bjorn_thread, web_thread))
        signal.signal(signal.SIGTERM, lambda sig, frame: handle_exit(sig, frame, display_thread, bjorn_thread, web_thread))

    except Exception as e:
        logger.error(f"An exception occurred during thread start: {e}")
        handle_exit_display(signal.SIGINT, None)
        exit(1)