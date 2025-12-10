# web_utils/network_utils.py
"""
Network utilities for WiFi/network operations.
Handles WiFi scanning, connection, known networks management.
"""
from __future__ import annotations
import json
import subprocess
import logging
import re
import os
from typing import Any, Dict, Optional, List
import logging
from logger import Logger
logger = Logger(name="network_utils.py", level=logging.DEBUG)

class NetworkUtils:
    """Utilities for network and WiFi management."""

    def __init__(self, shared_data):
        self.logger = logger
        self.shared_data = shared_data

    def get_known_wifi(self, handler):
        """List known WiFi networks with priorities."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,TYPE,AUTOCONNECT-PRIORITY', 'connection', 'show'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout = result.stdout
            self.logger.debug(f"nmcli connection show output:\n{stdout}")

            known_networks = []
            lines = stdout.strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(':')
                if len(parts) == 3:
                    name, conn_type, priority = parts
                elif len(parts) == 2:
                    name, conn_type = parts
                    priority = '0'
                    self.logger.warning(f"Missing priority for connection {name}. Assigning priority 0.")
                else:
                    self.logger.warning(f"Unexpected line format: {line}")
                    continue

                if conn_type.lower() in ['802-11-wireless', 'wireless', 'wifi']:
                    try:
                        priority_int = int(priority) if priority.isdigit() else 0
                    except ValueError:
                        priority_int = 0
                        self.logger.warning(f"Non-numeric priority for {name}. Assigning priority 0.")
                    known_networks.append({
                        'ssid': name,
                        'priority': priority_int
                    })

            self.logger.debug(f"Extracted known networks: {known_networks}")
            known_networks.sort(key=lambda x: x['priority'], reverse=True)

            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"known_networks": known_networks}).encode('utf-8'))
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error getting known Wi-Fi networks: {e.stderr.strip()}")
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": e.stderr.strip()}).encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Error getting known Wi-Fi networks: {e}")
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def delete_known_wifi(self, data):
        """Delete a known WiFi connection."""
        ssid = None
        try:
            ssid = data['ssid']
            result = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'delete', ssid],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.logger.info(f"Deleted Wi-Fi connection: {ssid}")
            return {"status": "success", "message": f"Network {ssid} deleted"}
        except subprocess.CalledProcessError as e:
            error_message = f"Error deleting Wi-Fi connection {ssid if ssid else 'unknown'}: {e.stderr.strip()}"
            self.logger.error(error_message)
            return {"status": "error", "message": e.stderr.strip()}
        except Exception as e:
            error_message = f"Unexpected error deleting Wi-Fi connection {ssid if ssid else 'unknown'}: {e}"
            self.logger.error(error_message)
            return {"status": "error", "message": str(e)}

    def connect_known_wifi(self, data):
        """Connect to a known WiFi network."""
        try:
            ssid = data['ssid']
            if not self.validate_network_configuration(ssid):
                raise Exception(f"Invalid or non-existent configuration for network '{ssid}'.")

            result = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'up', ssid],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.logger.info(f"Connected to known Wi-Fi network: {ssid}")
            return {"status": "success", "message": f"Connected to {ssid}"}
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error connecting to known Wi-Fi network {ssid}: {e.stderr.strip()}")
            return {"status": "error", "message": e.stderr.strip()}
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to known Wi-Fi network {ssid}: {e}")
            return {"status": "error", "message": str(e)}

    def update_wifi_priority(self, data):
        """Update WiFi connection priority."""
        try:
            ssid = data['ssid']
            priority = int(data['priority'])
            result = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'modify', ssid, 'connection.autoconnect-priority', str(priority)],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.logger.info(f"Priority updated for {ssid} to {priority}")
            return {"status": "success", "message": "Priority updated"}
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error updating Wi-Fi priority: {e.stderr.strip()}")
            return {"status": "error", "message": e.stderr.strip()}
        except Exception as e:
            self.logger.error(f"Unexpected error updating Wi-Fi priority: {e}")
            return {"status": "error", "message": str(e)}

    def scan_wifi(self, handler):
        """Scan for available WiFi networks."""
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'device', 'wifi', 'list'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout = result.stdout
            networks = self.parse_scan_result(stdout)
            self.logger.info(f"Found {len(networks)} networks")

            current_ssid = self.get_current_ssid()
            self.logger.info(f"Current SSID: {current_ssid}")

            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"networks": networks, "current_ssid": current_ssid}).encode('utf-8'))
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error scanning Wi-Fi networks: {e.stderr.strip()}")
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": e.stderr.strip()}).encode('utf-8'))

    def parse_scan_result(self, scan_output):
        """Parse nmcli scan output."""
        networks = []
        lines = scan_output.split('\n')
        headers = []
        for idx, line in enumerate(lines):
            if line.startswith("IN-USE"):
                headers = re.split(r'\s{2,}', line)
                continue
            if headers and line.strip():
                fields = re.split(r'\s{2,}', line)
                if len(fields) >= len(headers):
                    network = dict(zip(headers, fields))
                    ssid = network.get('SSID', '')
                    signal_level = int(network.get('SIGNAL', '0'))
                    security = network.get('SECURITY', '')
                    networks.append({
                        'ssid': ssid,
                        'signal_level': signal_level,
                        'security': security
                    })
        return networks

    def get_current_ssid(self):
        """Get currently connected SSID."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                active, ssid = line.split(':', 1)
                if active == 'yes':
                    return ssid
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error getting current SSID: {e.stderr.strip()}")
            return None

    def connect_wifi(self, data):
        """Connect to WiFi network (new or existing)."""
        try:
            ssid = data['ssid']
            password = data.get('password', '')

            if self.check_connection_exists(ssid):
                result = subprocess.run(
                    ['sudo', 'nmcli', 'connection', 'up', ssid],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                return {"status": "success", "message": f"Connected to {ssid}"}
            else:
                if password:
                    result = subprocess.run(
                        ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )
                else:
                    result = subprocess.run(
                        ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )
                return {"status": "success", "message": f"Connected to {ssid}"}
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error connecting to network {ssid}: {e.stderr.strip()}")
            return {"status": "error", "message": e.stderr.strip()}
        except Exception as e:
            self.logger.error(f"Error in connect_wifi: {e}")
            return {"status": "error", "message": str(e)}

    def check_connection_exists(self, ssid):
        """Check if a WiFi connection already exists."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME', 'connection', 'show'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            connections = result.stdout.strip().split('\n')
            return ssid in connections
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking existing connections: {e.stderr.strip()}")
            return False

    def validate_network_configuration(self, ssid):
        """Validate network configuration in NetworkManager."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,UUID,TYPE,AUTOCONNECT', 'connection', 'show'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            connections = result.stdout.strip().split('\n')
            for conn in connections:
                if ssid in conn:
                    self.logger.info(f"Network {ssid} validated in NetworkManager.")
                    return True
            self.logger.warning(f"Network {ssid} not found in NetworkManager.")
            return False
        except Exception as e:
            self.logger.error(f"Error validating network {ssid}: {e}")
            return False

    def import_potfiles(self, data=None):
        """Import WiFi credentials from .pot/.potfile files."""
        try:
            potfiles_folder = self.shared_data.potfiles_dir
            import glob
            potfile_paths = glob.glob(f"{potfiles_folder}/*.pot") + glob.glob(f"{potfiles_folder}/*.potfile")

            networks_added = []
            DEFAULT_PRIORITY = 5

            for potfile_path in potfile_paths:
                with open(potfile_path, 'r') as potfile:
                    for line in potfile:
                        line = line.strip()
                        if ':' not in line:
                            self.logger.warning(f"Ignoring malformed line in {potfile_path}: {line}")
                            continue

                        if line.startswith('$WPAPSK$') and '#' in line:
                            try:
                                ssid_hash_part, password = line.split(':', 1)
                                ssid = ssid_hash_part.split('#')[0].replace('$WPAPSK$', '')
                            except ValueError:
                                self.logger.warning(f"Failed to parse WPAPSK line in {potfile_path}: {line}")
                                continue
                        elif len(line.split(':')) == 4:
                            try:
                                _, _, ssid, password = line.split(':')
                            except ValueError:
                                self.logger.warning(f"Failed to parse custom line in {potfile_path}: {line}")
                                continue
                        else:
                            self.logger.warning(f"Unknown format in {potfile_path}: {line}")
                            continue

                        if ssid and password:
                            if not self.check_connection_exists(ssid):
                                try:
                                    subprocess.run(
                                        ['sudo', 'nmcli', 'connection', 'add', 'type', 'wifi',
                                         'con-name', ssid, 'ifname', '*', 'ssid', ssid,
                                         'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password,
                                         'connection.autoconnect', 'yes',
                                         'connection.autoconnect-priority', str(DEFAULT_PRIORITY)],
                                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                                    )
                                    networks_added.append(ssid)
                                    self.logger.info(f"Imported network {ssid} from {potfile_path}")
                                except subprocess.CalledProcessError as e:
                                    self.logger.error(f"Failed to add network {ssid}: {e.stderr.strip()}")
                            else:
                                self.logger.info(f"Network {ssid} already exists. Skipping.")
                        else:
                            self.logger.warning(f"Incomplete data in {potfile_path}: {line}")

            return {"status": "success", "networks_added": networks_added}
        except Exception as e:
            self.logger.error(f"Unexpected error importing potfiles: {e}")
            return {"status": "error", "message": str(e)}



    def delete_preconfigured_file(self, handler):
        try:
            os.remove('/etc/NetworkManager/system-connections/preconfigured.nmconnection')
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
        except FileNotFoundError:
            handler.send_response(404)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": "Fichier introuvable"}).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def create_preconfigured_file(self, handler):
        try:
            with open('/etc/NetworkManager/system-connections/preconfigured.nmconnection', 'w') as f:
                f.write('Exemple de contenu')  # Ajoutez le contenu par défaut
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))