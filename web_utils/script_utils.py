# web_utils/script_utils.py
"""
Script launcher and execution utilities.
Handles script management, execution, monitoring, and output capture.
"""
from __future__ import annotations
import json
import subprocess
import os
import time
import threading
import importlib.util
import ast
import html
import cgi
from pathlib import Path
from typing import Any, Dict, Optional, List
from io import BytesIO
import logging
from logger import Logger
logger = Logger(name="script_utils.py", level=logging.DEBUG)

class ScriptUtils:
    """Utilities for script management and execution."""

    def __init__(self, shared_data):
        self.logger = logger
        self.shared_data = shared_data

    def get_script_description(self, script_path: Path) -> str:
        """Extract description from script comments."""
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()[:10]]
                
            description = []
            for line in lines:
                if line.startswith('#'):
                    clean_line = html.escape(line[1:].strip())
                    description.append(clean_line)
                elif line.startswith('"""') or line.startswith("'''"):
                    break
                elif line and not description:
                    break
                    
            description_text = '\n'.join(description) if description else "No description available"
            return description_text
        except Exception as e:
            self.logger.error(f"Error reading script description: {e}")
            return "Error reading description"

    def list_scripts(self) -> Dict:
        """List all actions with metadata for the launcher."""
        try:
            actions_out: list[dict] = []
            db_actions = self.shared_data.db.list_actions()

            for row in db_actions:
                b_class = (row.get("b_class") or "").strip()
                b_module = (row.get("b_module") or "").strip()
                action_path = os.path.join(self.shared_data.actions_dir, f"{b_module}.py")

                # Load b_args from DB (priority)
                db_args_raw = row.get("b_args")
                if isinstance(db_args_raw, str):
                    db_args_raw_str = db_args_raw.strip()
                    if (db_args_raw_str.startswith("{") and db_args_raw_str.endswith("}")) or \
                       (db_args_raw_str.startswith("[") and db_args_raw_str.endswith("]")):
                        try:
                            b_args = json.loads(db_args_raw_str)
                        except Exception:
                            b_args = {}
                    else:
                        b_args = {}
                elif db_args_raw is None:
                    b_args = {}
                else:
                    b_args = db_args_raw

                # Basic metadata from DB
                b_name = row.get("b_name")
                b_description = row.get("b_description") or row.get("b_status") or "No description available"
                b_author = row.get("b_author")
                b_version = row.get("b_version")
                b_icon = row.get("b_icon")
                b_docs_url = row.get("b_docs_url")

                b_examples = None
                if row.get("b_examples") is not None:
                    try:
                        if isinstance(row["b_examples"], str):
                            b_examples = json.loads(row["b_examples"])
                        else:
                            b_examples = row["b_examples"]
                    except Exception:
                        b_examples = None

                # Enrich from module if available
                try:
                    if os.path.exists(action_path):
                        spec = importlib.util.spec_from_file_location(b_module, action_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Dynamic b_args
                        if hasattr(module, "compute_dynamic_b_args"):
                            try:
                                b_args = module.compute_dynamic_b_args(b_args or {})
                            except Exception as e:
                                self.logger.warning(f"compute_dynamic_b_args failed for {b_module}: {e}")

                        # Enrich fields
                        if getattr(module, "b_name", None): b_name = module.b_name
                        if getattr(module, "b_description", None): b_description = module.b_description
                        if getattr(module, "b_author", None): b_author = module.b_author
                        if getattr(module, "b_version", None): b_version = module.b_version
                        if getattr(module, "b_icon", None): b_icon = module.b_icon
                        if getattr(module, "b_docs_url", None): b_docs_url = module.b_docs_url
                        if getattr(module, "b_examples", None): b_examples = module.b_examples

                except Exception as e:
                    self.logger.warning(f"Could not import {b_module} for dynamic/meta: {e}")

                # Parse tags
                tags_raw = row.get("b_tags")
                if isinstance(tags_raw, str):
                    t = tags_raw.strip()
                    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
                        try:
                            tags = json.loads(t)
                        except Exception:
                            tags = tags_raw
                    else:
                        tags = tags_raw
                else:
                    tags = tags_raw

                # Display name
                display_name = b_name or (f"{b_module}.py" if b_module else (f"{b_class}.py" if b_class else "Unnamed"))

                # Icon URL
                icon_url = self._normalize_icon_url(b_icon, b_class)

                # Build action info
                action_info = {
                    "name": display_name,
                    "path": action_path,
                    "b_module": b_module,
                    "b_class": b_class,
                    "category": row.get("b_action", "normal") or "normal",
                    "type": "action",
                    "description": b_description or "No description available",
                    "b_args": b_args,
                    "enabled": bool(row.get("b_enabled", 1)),
                    "priority": row.get("b_priority", 50),
                    "tags": tags,
                    "b_author": b_author,
                    "b_version": b_version,
                    "b_icon": icon_url,
                    "b_docs_url": b_docs_url,
                    "b_examples": b_examples,
                    "is_running": False,
                    "output": []
                }

                # Runtime state
                with self.shared_data.scripts_lock:
                    if action_path in self.shared_data.running_scripts:
                        runinfo = self.shared_data.running_scripts[action_path]
                        action_info["is_running"] = runinfo.get("is_running", False)
                        action_info["output"] = runinfo.get("output", [])
                        action_info["last_error"] = runinfo.get("last_error", "")

                actions_out.append(action_info)

            actions_out.sort(key=lambda x: x["name"])
            return {"status": "success", "data": actions_out}

        except Exception as e:
            self.logger.error(f"Error listing actions: {e}")
            return {"status": "error", "message": str(e)}

    def _normalize_icon_url(self, raw_icon: str | None, b_class: str) -> str:
        """Normalize icon URL for frontend consumption."""
        def _default_icon_url(b_class: str) -> str | None:
            if not b_class:
                return None
            fname = f"{b_class}.png"
            icon_fs = os.path.join(self.shared_data.actions_icons_dir, fname)
            return f"/actions_icons/{fname}" if os.path.exists(icon_fs) else None

        if raw_icon:
            s = str(raw_icon).strip()
            if s.startswith("http://") or s.startswith("https://"):
                return s
            if "/" not in s and "\\" not in s:
                return f"/actions_icons/{s}"
            url = _default_icon_url(b_class)
            if url:
                return url

        url = _default_icon_url(b_class)
        if url:
            return url

        return "/actions/actions_icons/default.png"

    def run_script(self, data: Dict) -> Dict:
        """Run an action/script with arguments."""
        try:
            script_key = data.get("script_name")
            args = data.get("args", "")
            
            if not script_key:
                return {"status": "error", "message": "Script name is required"}
            
            # Find action in database
            action = None
            for a in self.shared_data.db.list_actions():
                if a["b_class"] == script_key or a["b_module"] == script_key:
                    action = a
                    break
            
            if not action:
                return {"status": "error", "message": f"Action {script_key} not found"}
            
            module_name = action["b_module"]
            script_path = os.path.join(self.shared_data.actions_dir, f"{module_name}.py")
            
            if not os.path.exists(script_path):
                return {"status": "error", "message": f"Script file {script_path} not found"}
            
            # Check if already running
            with self.shared_data.scripts_lock:
                if script_path in self.shared_data.running_scripts and \
                   self.shared_data.running_scripts[script_path].get("is_running", False):
                    return {"status": "error", "message": f"Script {module_name} is already running"}
                
                # Prepare environment
                env = dict(os.environ)
                env["PYTHONUNBUFFERED"] = "1"
                env["BJORN_EMBEDDED"] = "1"
                
                # Start process
                cmd = ["sudo", "python3", "-u", script_path]
                if args:
                    cmd.extend(args.split())
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                    cwd=self.shared_data.actions_dir
                )
                
                # Store process info
                self.shared_data.running_scripts[script_path] = {
                    "process": process,
                    "output": [],
                    "start_time": time.time(),
                    "is_running": True,
                    "last_error": "",
                    "b_class": action["b_class"],
                    "b_module": module_name,
                }
            
            # Start monitoring thread
            threading.Thread(
                target=self.monitor_script_output,
                args=(script_path, process),
                daemon=True
            ).start()
            
            return {
                "status": "success",
                "message": f"Started {module_name}",
                "data": {
                    "is_running": True,
                    "output": [],
                    "script_path": script_path
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error running script: {e}")
            return {"status": "error", "message": str(e)}

    def stop_script(self, data: Dict) -> Dict:
        """Stop a running script."""
        try:
            script_name = data.get('script_name')
            
            if not script_name:
                return {"status": "error", "message": "Script name is required"}
            
            # Handle both paths and names
            if not script_name.startswith('/'):
                for path, info in self.shared_data.running_scripts.items():
                    if info.get("b_module") == script_name or info.get("b_class") == script_name:
                        script_name = path
                        break
            
            with self.shared_data.scripts_lock:
                if script_name not in self.shared_data.running_scripts:
                    return {"status": "error", "message": f"Script {script_name} not found or not running"}
                
                script_info = self.shared_data.running_scripts[script_name]
                if script_info["process"]:
                    script_info["process"].terminate()
                    try:
                        script_info["process"].wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        script_info["process"].kill()
                        script_info["process"].wait()
                    
                    script_info["output"].append("Script stopped by user")
                    script_info["is_running"] = False
                    script_info["process"] = None
            
            return {"status": "success", "message": f"Script {script_name} stopped"}
            
        except Exception as e:
            self.logger.error(f"Error stopping script: {e}")
            return {"status": "error", "message": str(e)}

    def get_script_output(self, data: Dict) -> Dict:
        """Get output for a running or completed script."""
        try:
            script_name = data.get('script_name')
            
            if not script_name:
                return {"status": "error", "message": "Script name is required"}
            
            self.logger.debug(f"Getting output for: {script_name}")
            
            with self.shared_data.scripts_lock:
                # Direct path lookup
                if script_name in self.shared_data.running_scripts:
                    script_info = self.shared_data.running_scripts[script_name]
                    return {
                        "status": "success",
                        "data": {
                            "output": script_info["output"],
                            "is_running": script_info.get("is_running", False),
                            "runtime": time.time() - script_info.get("start_time", time.time()),
                            "last_error": script_info.get("last_error", "")
                        }
                    }
                
                # Try basename lookup
                script_basename = os.path.basename(script_name)
                for key, info in self.shared_data.running_scripts.items():
                    if os.path.basename(key) == script_basename:
                        return {
                            "status": "success",
                            "data": {
                                "output": info["output"],
                                "is_running": info.get("is_running", False),
                                "runtime": time.time() - info.get("start_time", time.time()),
                                "last_error": info.get("last_error", "")
                            }
                        }
                
                # Try module/class name lookup
                for key, info in self.shared_data.running_scripts.items():
                    if info.get("b_module") == script_name or info.get("b_class") == script_name:
                        return {
                            "status": "success",
                            "data": {
                                "output": info["output"],
                                "is_running": info.get("is_running", False),
                                "runtime": time.time() - info.get("start_time", time.time()),
                                "last_error": info.get("last_error", "")
                            }
                        }
            
            # Not found - return empty
            return {
                "status": "success",
                "data": {
                    "output": [],
                    "is_running": False,
                    "runtime": 0,
                    "last_error": ""
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting script output: {e}")
            return {"status": "error", "message": str(e)}

    def monitor_script_output(self, script_path: str, process: subprocess.Popen):
        """Monitor script output in real-time."""
        try:
            self.logger.debug(f"Starting output monitoring for: {script_path}")
            
            while True:
                line = process.stdout.readline()
                
                if not line and process.poll() is not None:
                    break
                
                if line:
                    line = line.rstrip()
                    with self.shared_data.scripts_lock:
                        if script_path in self.shared_data.running_scripts:
                            self.shared_data.running_scripts[script_path]["output"].append(line)
                            self.logger.debug(f"[{os.path.basename(script_path)}] {line}")
            
            # Process ended
            return_code = process.poll()
            with self.shared_data.scripts_lock:
                if script_path in self.shared_data.running_scripts:
                    info = self.shared_data.running_scripts[script_path]
                    info["process"] = None
                    info["is_running"] = False
                    
                    if return_code == 0:
                        info["output"].append("Script completed successfully")
                    else:
                        info["output"].append(f"Script exited with code {return_code}")
                        info["last_error"] = f"Exit code: {return_code}"
            
            self.logger.info(f"Script {script_path} finished with code {return_code}")
            
        except Exception as e:
            self.logger.error(f"Error monitoring output for {script_path}: {e}")
            with self.shared_data.scripts_lock:
                if script_path in self.shared_data.running_scripts:
                    info = self.shared_data.running_scripts[script_path]
                    info["output"].append(f"Monitoring error: {str(e)}")
                    info["last_error"] = str(e)
                    info["process"] = None
                    info["is_running"] = False

    def upload_script(self, handler) -> None:
        """Upload a new script file."""
        try:
            form = cgi.FieldStorage(
                fp=handler.rfile,
                headers=handler.headers,
                environ={'REQUEST_METHOD': 'POST'}
            )
            if 'script_file' not in form:
                resp = {"status": "error", "message": "Missing 'script_file'"}
                handler.send_response(400)
            else:
                file_item = form['script_file']
                if not file_item.filename.endswith('.py'):
                    resp = {"status": "error", "message": "Only .py allowed"}
                    handler.send_response(400)
                else:
                    script_name = os.path.basename(file_item.filename)
                    script_path = Path(self.shared_data.actions_dir) / script_name
                    if script_path.exists():
                        resp = {"status": "error", "message": f"Script '{script_name}' already exists."}
                        handler.send_response(400)
                    else:
                        with open(script_path, 'wb') as f:
                            f.write(file_item.file.read())

                        description = self.get_script_description(script_path)

                        self.shared_data.db.add_script(
                            name=script_name,
                            type_="script",
                            path=str(script_path),
                            category="general",
                            description=description
                        )

                        resp = {"status": "success", "message": f"Script '{script_name}' uploaded."}
                        handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(resp).encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Error uploading script: {e}")
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

    def delete_script(self, data: Dict) -> Dict:
        """Delete a script."""
        try:
            script_name = data.get('script_name')
            if not script_name:
                return {"status": "error", "message": "Missing script_name"}
            
            rows = self.shared_data.db.query("SELECT * FROM scripts WHERE name=?", (script_name,))
            if not rows:
                return {"status": "error", "message": f"Script '{script_name}' not found in DB"}
            row = rows[0]
            is_project = row["type"] == "project"
            path = Path(row["path"])

            if is_project and path.exists():
                import shutil
                shutil.rmtree(path)
            else:
                script_path = Path(self.shared_data.actions_dir) / script_name
                if script_path.exists():
                    with self.shared_data.scripts_lock:
                        if str(script_path) in self.shared_data.running_scripts and \
                           self.shared_data.running_scripts[str(script_path)].get("is_running", False):
                            return {"status": "error", "message": f"Script '{script_name}' is running."}
                    script_path.unlink()

            self.shared_data.db.delete_script(script_name)
            return {"status": "success", "message": f"{'Project' if is_project else 'Script'} '{script_name}' deleted."}
        except Exception as e:
            self.logger.error(f"Error deleting script: {e}")
            return {"status": "error", "message": str(e)}

    def upload_project(self, handler) -> None:
        """Upload a project with multiple files."""
        try:
            form = cgi.FieldStorage(
                fp=handler.rfile,
                headers=handler.headers,
                environ={'REQUEST_METHOD': 'POST'}
            )
            if 'main_file' not in form:
                raise ValueError("Missing main_file")
            main_file_path = form.getvalue('main_file')
            project_name = Path(main_file_path).parts[0]
            project_dir = Path(self.shared_data.actions_dir) / project_name
            project_dir.mkdir(exist_ok=True)

            files = form['project_files[]']
            if not isinstance(files, list):
                files = [files]
            for fileitem in files:
                if fileitem.filename:
                    relative_path = Path(fileitem.filename).relative_to(project_name)
                    file_path = project_dir / relative_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(fileitem.file.read())

            description = self.get_script_description(project_dir / Path(main_file_path).name)

            self.shared_data.db.add_script(
                name=project_name,
                type_="project",
                path=str(project_dir),
                main_file=main_file_path,
                category="projects",
                description=description
            )

            resp = {"status": "success", "message": f"Project '{project_name}' uploaded."}
            handler.send_response(200)
        except Exception as e:
            self.logger.error(f"Error uploading project: {e}")
            resp = {"status": "error", "message": str(e)}
            handler.send_response(400)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(resp).encode('utf-8'))

    def get_action_args_schema(self, data: Dict) -> Dict:
        """Get the arguments schema for a specific action."""
        try:
            action_name = data.get("action_name")
            
            if not action_name:
                return {"status": "error", "message": "Action name is required"}
            
            action = None
            for a in self.shared_data.db.list_actions():
                if a["b_class"] == action_name or a["b_module"] == action_name:
                    action = a
                    break
            
            if not action:
                return {"status": "error", "message": f"Action {action_name} not found"}
            
            module_name = action["b_module"]
            action_path = os.path.join(self.shared_data.actions_dir, f"{module_name}.py")
            
            b_args = {}
            
            if os.path.exists(action_path):
                try:
                    spec = importlib.util.spec_from_file_location(module_name, action_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'b_args'):
                        b_args = module.b_args
                        
                    if hasattr(module, 'compute_dynamic_b_args'):
                        b_args = module.compute_dynamic_b_args(b_args)
                        
                except Exception as e:
                    self.logger.warning(f"Could not load b_args for {module_name}: {e}")
            
            return {
                "status": "success",
                "data": {
                    "action_name": action_name,
                    "module": module_name,
                    "args_schema": b_args,
                    "description": action.get("b_description", ""),
                    "enabled": bool(action.get("b_enabled", 1))
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting action args schema: {e}")
            return {"status": "error", "message": str(e)}

    def get_running_scripts(self) -> Dict:
        """Get list of all currently running scripts."""
        try:
            running = []
            
            with self.shared_data.scripts_lock:
                for path, info in self.shared_data.running_scripts.items():
                    if info.get("is_running", False):
                        running.append({
                            "path": path,
                            "name": os.path.basename(path),
                            "module": info.get("b_module", ""),
                            "class": info.get("b_class", ""),
                            "start_time": info.get("start_time", 0),
                            "runtime": time.time() - info.get("start_time", time.time()),
                            "output_lines": len(info.get("output", []))
                        })
            
            return {"status": "success", "data": running}
            
        except Exception as e:
            self.logger.error(f"Error getting running scripts: {e}")
            return {"status": "error", "message": str(e)}

    def clear_script_output(self, data: Dict) -> Dict:
        """Clear output for a specific script."""
        try:
            script_name = data.get('script_name')
            
            if not script_name:
                return {"status": "error", "message": "Script name is required"}
            
            cleared = False
            with self.shared_data.scripts_lock:
                if script_name in self.shared_data.running_scripts:
                    self.shared_data.running_scripts[script_name]["output"] = []
                    cleared = True
                else:
                    for key, info in self.shared_data.running_scripts.items():
                        if (os.path.basename(key) == script_name or
                            info.get("b_module") == script_name or
                            info.get("b_class") == script_name):
                            info["output"] = []
                            cleared = True
                            break
            
            if cleared:
                return {"status": "success", "message": "Output cleared"}
            else:
                return {"status": "error", "message": "Script not found"}
            
        except Exception as e:
            self.logger.error(f"Error clearing script output: {e}")
            return {"status": "error", "message": str(e)}

    def export_script_logs(self, data: Dict) -> Dict:
        """Export logs for a script to a file."""
        try:
            from datetime import datetime
            import csv
            
            script_name = data.get('script_name')
            format_type = data.get('format', 'txt')
            
            if not script_name:
                return {"status": "error", "message": "Script name is required"}
            
            output = []
            script_info = None
            
            with self.shared_data.scripts_lock:
                if script_name in self.shared_data.running_scripts:
                    script_info = self.shared_data.running_scripts[script_name]
                else:
                    for key, info in self.shared_data.running_scripts.items():
                        if (os.path.basename(key) == script_name or
                            info.get("b_module") == script_name or
                            info.get("b_class") == script_name):
                            script_info = info
                            break
            
            if not script_info:
                return {"status": "error", "message": "Script not found"}
            
            output = script_info.get("output", [])
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{script_name}_{timestamp}.{format_type}"
            filepath = os.path.join(self.shared_data.output_dir, filename)
            
            if format_type == 'json':
                with open(filepath, 'w') as f:
                    json.dump({
                        "script": script_name,
                        "timestamp": timestamp,
                        "logs": output
                    }, f, indent=2)
            elif format_type == 'csv':
                with open(filepath, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Timestamp', 'Message'])
                    for line in output:
                        writer.writerow([datetime.now().isoformat(), line])
            else:
                with open(filepath, 'w') as f:
                    f.write('\n'.join(output))
            
            return {
                "status": "success",
                "message": f"Logs exported to {filename}",
                "data": {
                    "filename": filename,
                    "path": filepath,
                    "lines": len(output)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error exporting logs: {e}")
            return {"status": "error", "message": str(e)}
