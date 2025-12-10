# web_utils/bluetooth_utils.py
"""
Bluetooth device management utilities.
Handles Bluetooth scanning, pairing, connection, and device management.
"""
from __future__ import annotations
import json
import subprocess
import time
import os
import dbus
import dbus.mainloop.glib
import dbus.exceptions
from typing import Any, Dict, Optional
import logging
from logger import Logger
logger = Logger(name="bluetooth_utils.py", level=logging.DEBUG)

class BluetoothUtils:
    """Utilities for Bluetooth device management."""

    def __init__(self, shared_data):
        self.logger = logger
        self.shared_data = shared_data
        self.bluetooth_initialized = False
        self.bus = None
        self.manager_interface = None
        self.adapter_path = None
        self.adapter = None
        self.adapter_props = None
        self.adapter_methods = None

    def _ensure_bluetooth_service(self):
        """Check if bluetooth service is running, if not start and enable it."""
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "bluetooth"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if "active" not in res.stdout:
                self.logger.info("Bluetooth service not active. Starting and enabling it...")
                start_res = subprocess.run(
                    ["sudo", "systemctl", "start", "bluetooth"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                if start_res.returncode != 0:
                    self.logger.error(f"Failed to start bluetooth service: {start_res.stderr}")
                    raise Exception("Failed to start bluetooth service.")

                enable_res = subprocess.run(
                    ["sudo", "systemctl", "enable", "bluetooth"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                if enable_res.returncode != 0:
                    self.logger.error(f"Failed to enable bluetooth service: {enable_res.stderr}")
                else:
                    self.logger.info("Bluetooth service enabled successfully.")
            else:
                self.logger.info("Bluetooth service is already active.")
        except Exception as e:
            self.logger.error(f"Error ensuring bluetooth service: {e}")
            raise

    def _init_bluetooth(self):
        """Initialize Bluetooth DBus connection."""
        if self.bluetooth_initialized:
            return

        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._ensure_bluetooth_service()

            self.bus = dbus.SystemBus()
            manager = self.bus.get_object("org.bluez", "/")
            self.manager_interface = dbus.Interface(manager, "org.freedesktop.DBus.ObjectManager")

            objects = self.manager_interface.GetManagedObjects()
            self.adapter_path = None
            for path, ifaces in objects.items():
                if "org.bluez.Adapter1" in ifaces:
                    self.adapter_path = path
                    break

            if not self.adapter_path:
                self.logger.error("No Bluetooth adapter found.")
                raise Exception("No Bluetooth adapter found.")

            self.adapter = self.bus.get_object("org.bluez", self.adapter_path)
            self.adapter_props = dbus.Interface(self.adapter, "org.freedesktop.DBus.Properties")
            self.adapter_methods = dbus.Interface(self.adapter, "org.bluez.Adapter1")

            self.bluetooth_initialized = True
        except Exception as e:
            self.logger.error(f"Failed to initialize Bluetooth: {e}")
            raise

    def _get_device_object(self, address):
        """Get DBus device object by MAC address."""
        self._init_bluetooth()
        objects = self.manager_interface.GetManagedObjects()
        for path, ifaces in objects.items():
            if "org.bluez.Device1" in ifaces:
                dev = ifaces["org.bluez.Device1"]
                if dev.get("Address") == address:
                    return self.bus.get_object("org.bluez", path)
        return None

    def scan_bluetooth(self, handler):
        """Scan for Bluetooth devices."""
        try:
            self._init_bluetooth()
            self.adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
            self.adapter_props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
            self.adapter_props.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(180))

            self.adapter_methods.StartDiscovery()
            time.sleep(3)
            objects = self.manager_interface.GetManagedObjects()
            devices = []
            for path, ifaces in objects.items():
                if "org.bluez.Device1" in ifaces:
                    dev = ifaces["org.bluez.Device1"]
                    addr = dev.get("Address", "")
                    name = dev.get("Name", "Unknown")
                    paired = bool(dev.get("Paired", False))
                    trusted = bool(dev.get("Trusted", False))
                    connected = bool(dev.get("Connected", False))

                    devices.append({
                        "name": name,
                        "address": addr,
                        "paired": paired,
                        "trusted": trusted,
                        "connected": connected
                    })

            self.adapter_methods.StopDiscovery()
            response = {"devices": devices}
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps(response).encode('utf-8'))

        except Exception as e:
            self.logger.error(f"Error scanning Bluetooth: {e}")
            handler.send_response(500)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def pair_bluetooth(self, address, pin=None):
        """Pair with a Bluetooth device."""
        try:
            device = self._get_device_object(address)
            if device is None:
                self.logger.error(f"Device {address} not found")
                return {"status": "error", "message": f"Device {address} not found"}

            device_methods = dbus.Interface(device, "org.bluez.Device1")
            device_props = dbus.Interface(device, "org.freedesktop.DBus.Properties")

            bt_process = subprocess.Popen(
                ['bluetoothctl'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            try:
                self.logger.info(f"Attempting to pair with {address}")
                bt_process.stdin.write(f"pair {address}\n")
                bt_process.stdin.flush()
                
                timeout = 60
                start_time = time.time()
                
                while (time.time() - start_time) < timeout:
                    line = bt_process.stdout.readline()
                    if not line:
                        continue
                        
                    self.logger.info(f"Bluetoothctl output: {line.strip()}")
                    
                    if "Confirm passkey" in line or "Request confirmation" in line:
                        self.logger.info("Sending confirmation...")
                        bt_process.stdin.write("yes\n")
                        bt_process.stdin.flush()
                    
                    try:
                        paired = device_props.Get("org.bluez.Device1", "Paired")
                        if paired:
                            self.logger.info("Device successfully paired!")
                            device_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
                            
                            time.sleep(2)
                            
                            config_path = "/home/bjorn/.settings_bjorn/bt.json"
                            current_mac = None
                            if os.path.exists(config_path):
                                try:
                                    with open(config_path, "r") as f:
                                        data = json.load(f)
                                        current_mac = data.get("device_mac")
                                except (json.JSONDecodeError, IOError):
                                    pass

                            if current_mac != address:
                                self.logger.info(f"Updating config with new MAC: {address}")
                                new_data = {"device_mac": address}
                                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                                with open(config_path, "w") as f:
                                    json.dump(new_data, f)
                                self.logger.info("Updated bt.json with new device MAC.")

                            try:
                                subprocess.run(["sudo", "systemctl", "restart", "auto_bt_connect"], check=True)
                                self.logger.info("auto_bt_connect service restarted successfully")
                            except subprocess.CalledProcessError as e:
                                self.logger.error(f"Failed to restart auto_bt_connect service: {e}")
                            
                            return {"status": "success", "message": "Device successfully paired and trusted"}
                    except:
                        pass
                        
                    if "Failed" in line or "Error" in line:
                        self.logger.error(f"Bluetoothctl error: {line}")
                        return {"status": "error", "message": f"Pairing failed: {line.strip()}"}

                return {"status": "error", "message": "Pairing timed out - please try again"}

            except Exception as e:
                self.logger.error(f"Error during pairing process: {str(e)}")
                return {"status": "error", "message": f"Error during pairing: {str(e)}"}

        finally:
            if 'bt_process' in locals():
                bt_process.stdin.write("quit\n")
                bt_process.stdin.flush()
                time.sleep(1)
                bt_process.terminate()

    def forget_bluetooth(self, address):
        """Remove/forget a Bluetooth device."""
        try:
            device = self._get_device_object(address)
            if device is None:
                return {"status": "error", "message": f"Device {address} not found"}

            device_methods = dbus.Interface(device, "org.bluez.Device1")
            adapter_methods = dbus.Interface(self.adapter, "org.bluez.Adapter1")

            try:
                try:
                    device_methods.Disconnect()
                except:
                    pass

                adapter_methods.RemoveDevice(device)
                self.logger.info(f"Successfully removed device {address}")
                return {"status": "success", "message": "Device forgotten successfully"}

            except Exception as e:
                self.logger.error(f"Failed to forget device: {e}")
                return {"status": "error", "message": f"Failed to forget device: {str(e)}"}

        except Exception as e:
            self.logger.error(f"Error in forget_bluetooth: {str(e)}")
            return {"status": "error", "message": f"Error forgetting device: {str(e)}"}

    def trust_bluetooth(self, address):
        """Trust a Bluetooth device."""
        device = self._get_device_object(address)
        if device is None:
            return {"status": "error", "message": f"Device {address} not found"}
        device_props = dbus.Interface(device, "org.freedesktop.DBus.Properties")
        try:
            device_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
            return {"status": "success", "message": f"Trusted {address}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to trust {address}: {e}"}

    def connect_bluetooth(self, address):
        """Connect to a Bluetooth device and set up networking."""
        device = self._get_device_object(address)
        if device is None:
            return {"status": "error", "message": f"Device {address} not found"}

        device_methods = dbus.Interface(device, "org.bluez.Device1")
        try:
            device_methods.Connect()
            self.logger.info(f"Device {address} connected. Setting up PAN and obtaining IP...")

            bt_net_process = subprocess.Popen(
                ["sudo", "bt-network", "-c", address, "nap"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            time.sleep(2)

            if bt_net_process.poll() is not None:
                if bt_net_process.returncode != 0:
                    stderr_output = bt_net_process.stderr.read() if bt_net_process.stderr else ""
                    self.logger.error(f"Failed to run bt-network: {stderr_output}")
                    return {"status": "error", "message": f"Connected to {address}, but failed to set up bt-network: {stderr_output}"}
                else:
                    self.logger.warning("bt-network ended. PAN might not remain established.")
            else:
                self.logger.info("bt-network process started successfully and is running in background.")

            dhclient_res = subprocess.run(
                ["sudo", "dhclient", "-4", "bnep0"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if dhclient_res.returncode != 0:
                self.logger.error(f"Failed to run dhclient: {dhclient_res.stderr}")
                return {"status": "error", "message": f"Connected to {address}, bt-network ok, but dhclient failed: {dhclient_res.stderr}"}

            self.logger.info("Successfully obtained IP via dhclient on bnep0.")

            config_path = "/home/bjorn/.settings_bjorn/bt.json"
            current_mac = None
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        data = json.load(f)
                        current_mac = data.get("device_mac")
                except (json.JSONDecodeError, IOError):
                    pass

            if current_mac != address:
                self.logger.info(f"Updating config with new MAC: {address}")
                new_data = {"device_mac": address}
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w") as f:
                    json.dump(new_data, f)
                self.logger.info("Updated bt.json with new device MAC.")

            return {"status": "success", "message": f"Connected to {address} and network interface set up."}
        except dbus.exceptions.DBusException as e:
            return {"status": "error", "message": f"Failed to connect to {address}: {e}"}

    def disconnect_bluetooth(self, address):
        """Disconnect from a Bluetooth device."""
        device = self._get_device_object(address)
        if device is None:
            return {"status": "error", "message": f"Device {address} not found"}
        device_methods = dbus.Interface(device, "org.bluez.Device1")
        try:
            device_methods.Disconnect()
            return {"status": "success", "message": f"Disconnected from {address}"}
        except dbus.exceptions.DBusException as e:
            return {"status": "error", "message": f"Failed to disconnect from {address}: {e}"}
