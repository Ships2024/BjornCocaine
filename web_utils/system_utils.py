# web_utils/system_utils.py
"""
System utilities for management operations.
Handles system commands, service management, configuration.
"""
from __future__ import annotations
import json
import subprocess
import logging
import os
import time
from typing import Any, Dict, Optional
from logger import Logger


logger = Logger(name="system_utils.py", level=logging.DEBUG)

class SystemUtils:
    """Utilities for system-level operations."""

    def __init__(self, shared_data):
        self.logger = logger
        self.shared_data = shared_data

    def reboot_system(self, handler):
        """Reboot the system."""
        try:
            command = "sudo reboot"
            subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "System is rebooting"}).encode('utf-8'))
        except subprocess.CalledProcessError as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def shutdown_system(self, handler):
        """Shutdown the system."""
        try:
            command = "sudo shutdown now"
            subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "System is shutting down"}).encode('utf-8'))
        except subprocess.CalledProcessError as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def restart_bjorn_service(self, handler):
        """Restart the Bjorn service."""
        if not hasattr(handler, 'send_response'):
            raise TypeError("Invalid handler passed. Expected an HTTP handler.")
        
        try:
            command = "sudo systemctl restart bjorn.service"
            subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Bjorn service restarted successfully"}).encode('utf-8'))
        except subprocess.CalledProcessError as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def clear_logs(self, handler):
        """Clear logs directory contents."""
        try:
            command = "sudo rm -rf data/logs/*"
            subprocess.Popen(command, shell=True)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Logs cleared successfully"}).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def initialize_db(self, handler):
        """Initialize or prepare database schema."""
        try:
            self.shared_data.sync_actions_to_database()
            self.shared_data.initialize_database()
            self.shared_data.initialize_statistics()
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Database initialized successfully"}).encode("utf-8"))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def erase_bjorn_memories(self, handler):
        """Erase all Bjorn-related memories and restart service."""
        try:
            # Import file_utils for clear operations
            from web_utils.file_utils import FileUtils
            file_utils = FileUtils(self.logger, self.shared_data)
            
            # Clear various components
            file_utils.clear_output_folder(handler)
            self.clear_netkb(handler, restart=False)
            self.clear_livestatus(handler, restart=False)
            self.clear_actions_file(handler, restart=False)
            self.clear_shared_config_json(handler, restart=False)
            self.clear_logs(handler)

            # Restart service once at the end
            self.logger.debug("Restarting Bjorn service after clearing memories...")
            self.restart_bjorn_service(handler)

            self.logger.info("Bjorn memories erased and service restarted successfully.")
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                "status": "success",
                "message": "Bjorn memories erased and service restarted successfully."
            }).encode('utf-8'))

        except Exception as e:
            self.logger.error(f"Error erasing Bjorn memories: {str(e)}")
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                "status": "error",
                "message": f"Error erasing Bjorn memories: {str(e)}"
            }).encode('utf-8'))

    def clear_netkb(self, handler, restart=True):
        """Clear network knowledge base in database."""
        try:
            db = self.shared_data.db
            db.execute("DELETE FROM action_results;")
            db.execute("DELETE FROM hosts;")
            db.update_livestats(0, 0, 0, 0)
            if restart:
                self.restart_bjorn_service(handler)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "NetKB cleared in database"}).encode("utf-8"))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def clear_livestatus(self, handler, restart=True):
        """Clear live status counters."""
        try:
            self.shared_data.db.update_livestats(0, 0, 0, 0)
            if restart:
                self.restart_bjorn_service(handler)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Livestatus counters reset"}).encode("utf-8"))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def clear_actions_file(self, handler, restart=True):
        """Clear actions table and resynchronize from modules."""
        try:
            self.shared_data.db.execute("DELETE FROM actions;")
            self.shared_data.generate_actions_json()
            if restart:
                self.restart_bjorn_service(handler)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Actions table refreshed"}).encode("utf-8"))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def clear_shared_config_json(self, handler, restart=True):
        """Reset configuration to defaults."""
        try:
            self.shared_data.config = self.shared_data.get_default_config()
            self.shared_data.save_config()
            if restart:
                self.restart_bjorn_service(handler)
            handler.send_response(200)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "success", "message": "Configuration reset to defaults"}).encode("utf-8"))
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def save_configuration(self, data):
        """Save configuration to database."""
        try:
            if not isinstance(data, dict):
                return {"status": "error", "message": "Invalid data format: expected dictionary"}

            cfg = dict(self.shared_data.config)
            for k, v in data.items():
                if isinstance(v, bool):
                    cfg[k] = v
                elif isinstance(v, str) and v.lower() in ('true', 'false'):
                    cfg[k] = (v.lower() == 'true')
                elif isinstance(v, (int, float)):
                    cfg[k] = v
                elif isinstance(v, list) or v is None:
                    cfg[k] = [] if v is None else [x for x in v if x != ""]
                elif isinstance(v, str):
                    cfg[k] = float(v) if v.replace('.', '', 1).isdigit() and '.' in v else (int(v) if v.isdigit() else v)
                else:
                    cfg[k] = v

            self.shared_data.config = cfg
            self.shared_data.save_config()
            self.shared_data.load_config()
            return {"status": "success", "message": "Configuration saved"}
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            return {"status": "error", "message": str(e)}

    def serve_current_config(self, handler):
        """Serve current configuration as JSON."""
        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(self.shared_data.config).encode('utf-8'))

    def restore_default_config(self, handler):
        """Restore default configuration."""
        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        self.shared_data.config = self.shared_data.default_config.copy()
        self.shared_data.save_config()
        handler.wfile.write(json.dumps(self.shared_data.config).encode('utf-8'))

    def serve_logs(self, handler):
        """Serve logs for web console."""
        try:
            log_file_path = self.shared_data.webconsolelog
            if not os.path.exists(log_file_path):
                subprocess.Popen(f"sudo tail -f /home/bjorn/Bjorn/data/logs/* > {log_file_path}", shell=True)

            with open(log_file_path, 'r') as log_file:
                log_lines = log_file.readlines()

            max_lines = 2000
            if len(log_lines) > max_lines:
                log_lines = log_lines[-max_lines:]
                with open(log_file_path, 'w') as log_file:
                    log_file.writelines(log_lines)

            log_data = ''.join(log_lines)

            handler.send_response(200)
            handler.send_header("Content-type", "text/plain")
            handler.end_headers()
            handler.wfile.write(log_data.encode('utf-8'))
        except BrokenPipeError:
            pass
        except Exception as e:
            handler.send_response(500)
            handler.send_header("Content-type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def sse_log_stream(self, handler):
        """Stream logs using Server-Sent Events (SSE)."""
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "keep-alive")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()

            log_file_path = self.shared_data.log_file

            handler.wfile.write(b"data: Connected\n\n")
            handler.wfile.flush()

            with open(log_file_path, 'r') as log_file:
                log_file.seek(0, os.SEEK_END)
                while True:
                    line = log_file.readline()
                    if line:
                        message = f"data: {line.strip()}\n\n"
                        handler.wfile.write(message.encode('utf-8'))
                        handler.wfile.flush()
                    else:
                        handler.wfile.write(b": heartbeat\n\n")
                        handler.wfile.flush()
                        time.sleep(1)

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
            self.logger.info("Client disconnected from SSE stream")
        except Exception as e:
            self.logger.error(f"SSE Error: {e}")
        finally:
            self.logger.info("SSE stream closed")

    def serve_bjorn_status(self, handler):
        """Serve Bjorn status information."""
        try:
            status_data = {
                "status": self.shared_data.bjorn_orch_status,
                "status2": self.shared_data.bjorn_status_text2,
                "image_path": "/bjorn_status_image?t=" + str(int(time.time()))
            }
            
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps(status_data).encode('utf-8'))
        except BrokenPipeError:
            pass
        except Exception as e:
            self.logger.error(f"Error in serve_bjorn_status: {str(e)}")

    def check_manual_mode(self, handler):
        """Check if manual mode is enabled."""
        try:
            handler.send_response(200)
            handler.send_header("Content-type", "text/plain")
            handler.end_headers()
            handler.wfile.write(str(self.shared_data.manual_mode).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.end_headers()

    def check_console_autostart(self, handler):
        """Check console autostart setting."""
        try:
            handler.send_response(200)
            handler.send_header("Content-type", "text/plain")
            handler.end_headers()
            handler.wfile.write(str(self.shared_data.consoleonwebstart).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.end_headers()