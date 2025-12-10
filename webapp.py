"""
Web Application Server for Bjorn
Handles HTTP requests with optional authentication, gzip compression, and routing.
"""

import gzip
import http.server
import io
import json
import logging
import os
import signal
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
from http import cookies
from urllib.parse import unquote

from init_shared import shared_data
from logger import Logger
from utils import WebUtils

# ============================================================================
# INITIALIZATION
# ============================================================================

logger = Logger(name="webapp.py", level=logging.DEBUG)
favicon_path = os.path.join(shared_data.web_dir, '/images/favicon.ico')


# ============================================================================
# REQUEST HANDLER
# ============================================================================

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    """
    Custom HTTP request handler with authentication, compression, and routing.
    Refactored to use dynamic routing maps.
    """
    
    # Routes definitions initialized in __init__
    GET_ROUTES = {}
    POST_ROUTES_JSON = {}
    POST_ROUTES_MULTIPART = {}

    def __init__(self, *args, **kwargs):
        self.shared_data = shared_data
        self.web_utils = WebUtils(shared_data)
        self._register_routes()
        super().__init__(*args, **kwargs)

    def _register_routes(self):
        """Register all API routes to dictionaries for dynamic dispatch"""
        
        # --- GET ROUTES ---
        self.GET_ROUTES = {
            # INDEX / DASHBOARD
            '/api/bjorn/stats': self.web_utils.index_utils.dashboard_stats,
            '/apple-touch-icon': self.web_utils.index_utils.serve_apple_touch_icon,
            '/favicon.ico': self.web_utils.index_utils.serve_favicon,
            '/manifest.json': self.web_utils.index_utils.serve_manifest,

            # C2
            '/c2/agents': self.web_utils.c2.c2_agents,
            '/c2/events': self.web_utils.c2.c2_events_sse,
            '/c2/list_clients': self.web_utils.c2.c2_list_clients,
            '/c2/status': self.web_utils.c2.c2_status,

            # WEBENUM
            # Note: '/api/webenum/results' is handled via startswith in do_GET

            # NETWORK
            '/get_known_wifi': self.web_utils.network_utils.get_known_wifi,
            '/scan_wifi': self.web_utils.network_utils.scan_wifi,
            '/get_web_delay': self._serve_web_delay,

            # FILE
            '/list_directories': self.web_utils.file_utils.list_directories,
            '/loot_directories': self.web_utils.file_utils.loot_directories,
            # '/download_file', '/list_files', '/loot_download' handled dynamically

            # BACKUP
            '/check_update': self.web_utils.backup_utils.check_update,
            # '/download_backup' handled dynamically

            # SYSTEM
            '/bjorn_status': self.web_utils.system_utils.serve_bjorn_status,
            '/load_config': self.web_utils.system_utils.serve_current_config,
            '/get_logs': self.web_utils.system_utils.serve_logs,
            '/stream_logs': self.web_utils.system_utils.sse_log_stream,
            '/check_console_autostart': self.web_utils.system_utils.check_console_autostart,
            '/check_manual_mode': self.web_utils.system_utils.check_manual_mode,
            '/restore_default_config': self.web_utils.system_utils.restore_default_config,

            # BLUETOOTH
            '/scan_bluetooth': self.web_utils.bluetooth_utils.scan_bluetooth,

            # SCRIPTS
            '/get_running_scripts': self._serve_running_scripts,
            '/list_scripts': self._serve_list_scripts,
            '/get_action_args_schema': self._serve_action_args_schema,
            # '/get_script_output' handled dynamically

            # ACTION / IMAGES / STUDIO
            '/get_actions': self.web_utils.action_utils.get_actions,
            '/list_static_images': self.web_utils.action_utils.list_static_images_with_dimensions,
            '/list_characters': self.web_utils.action_utils.list_characters,
            '/bjorn_say': getattr(self.web_utils.action_utils, 'serve_bjorn_say', None),
            '/api/vulns/fix': self.web_utils.vuln_utils.fix_vulns_data,
            '/api/vulns/stats': self.web_utils.vuln_utils.serve_vulns_stats,
            '/api/studio/actions_db': self.web_utils.studio_utils.studio_get_actions_db,
            '/api/studio/actions_studio': self.web_utils.studio_utils.studio_get_actions_studio,
            '/api/studio/edges': self.web_utils.studio_utils.studio_get_edges,
            # '/api/studio/hosts' handled dynamically
            
            # DB & NETKB
            '/api/db/catalog': self.web_utils.db_utils.db_catalog_endpoint,
            '/api/db/export_all': self.web_utils.db_utils.db_export_all_endpoint,
            '/api/db/tables': self.web_utils.db_utils.db_list_tables_endpoint,
            '/netkb_data': self.web_utils.netkb_utils.serve_netkb_data,
            '/netkb_data_json': self.web_utils.netkb_utils.serve_netkb_data_json,
            '/network_data': self.web_utils.netkb_utils.serve_network_data,
            '/list_credentials': self.web_utils.orchestrator_utils.serve_credentials_data,
        }

        # --- POST ROUTES (MULTIPART) ---
        self.POST_ROUTES_MULTIPART = {
            '/action/create': self.web_utils.action_utils.create_action,
            '/replace_image': self.web_utils.action_utils.replace_image,
            '/resize_images': self.web_utils.action_utils.resize_images,
            '/restore_default_images': self.web_utils.action_utils.restore_default_images,
            '/delete_images': self.web_utils.action_utils.delete_images,
            '/upload_static_image': self.web_utils.action_utils.upload_static_image,
            '/upload_status_icon': self.web_utils.action_utils.upload_status_image,
            '/upload_status_image': self.web_utils.action_utils.upload_status_image,
            '/upload_character_images': self.web_utils.action_utils.upload_character_images,
            '/upload_files': self.web_utils.file_utils.handle_file_upload,
            '/upload_project': self.web_utils.script_utils.upload_project,
            '/upload_script': self.web_utils.script_utils.upload_script,
            '/clear_actions_file': self.web_utils.system_utils.clear_actions_file,
            '/clear_livestatus': self.web_utils.system_utils.clear_livestatus,
            '/clear_logs': self.web_utils.system_utils.clear_logs,
            '/clear_netkb': self.web_utils.system_utils.clear_netkb,
            '/clear_output_folder': self.web_utils.file_utils.clear_output_folder,
            '/erase_bjorn_memories': self.web_utils.system_utils.erase_bjorn_memories,
            '/create_preconfigured_file': self.web_utils.network_utils.create_preconfigured_file,
            '/delete_preconfigured_file': self.web_utils.network_utils.delete_preconfigured_file,
            '/clear_shared_config_json': self.web_utils.index_utils.clear_shared_config_json,
            '/reload_generate_actions_json': self.web_utils.index_utils.reload_generate_actions_json,
        }

        # --- POST ROUTES (JSON) ---
        # Note: Using lambda wrappers to normalize arguments if needed
        self.POST_ROUTES_JSON = {
            # INDEX
            '/api/bjorn/config': lambda d: self.web_utils.index_utils.set_config(self, d),
            '/api/bjorn/vulns/baseline': lambda d: self.web_utils.index_utils.mark_vuln_scan_baseline(self, d),
            # C2
            '/c2/broadcast': lambda d: self.web_utils.c2.c2_broadcast(self, d),
            '/c2/command': lambda d: self.web_utils.c2.c2_command(self, d),
            '/c2/deploy': lambda d: self.web_utils.c2.c2_deploy(self, d),
            '/c2/generate_client': lambda d: self.web_utils.c2.c2_generate_client(self, d),
            '/c2/purge_agents': lambda d: self.web_utils.c2.c2_purge_agents(self, d),
            '/c2/remove_client': lambda d: self.web_utils.c2.c2_remove_client(self, d),
            '/c2/start': lambda d: self.web_utils.c2.c2_start(self, d),
            '/c2/stop': lambda d: self.web_utils.c2.c2_stop(self, d),
            # WEBENUM
            '/api/webenum/import': self.web_utils.webenum_utils.import_webenum_results,
            # NETWORK
            '/connect_known_wifi': lambda d: (self.web_utils.network_utils.connect_known_wifi(d), setattr(self.shared_data, 'wifichanged', True))[0],
            '/connect_wifi': lambda d: (self.web_utils.network_utils.connect_wifi(d), setattr(self.shared_data, 'wifichanged', True))[0],
            '/delete_known_wifi': self.web_utils.network_utils.delete_known_wifi,
            '/update_wifi_priority': self.web_utils.network_utils.update_wifi_priority,
            '/import_potfiles': self.web_utils.network_utils.import_potfiles,
            # FILE
            '/create_folder': self.web_utils.file_utils.create_folder,
            '/delete_file': self.web_utils.file_utils.delete_file,
            '/duplicate_file': self.web_utils.file_utils.duplicate_file,
            '/move_file': self.web_utils.file_utils.move_file,
            '/rename_file': self.web_utils.file_utils.rename_file,
            # BACKUP
            '/create_backup': self.web_utils.backup_utils.create_backup,
            '/delete_backup': self.web_utils.backup_utils.delete_backup,
            '/list_backups': self.web_utils.backup_utils.list_backups,
            '/restore_backup': self.web_utils.backup_utils.restore_backup,
            '/set_default_backup': self.web_utils.backup_utils.set_default_backup,
            '/update_application': self.web_utils.backup_utils.update_application,
            # SYSTEM
            '/initialize_csv': self.web_utils.system_utils.initialize_db,
            '/restart_bjorn_service': lambda _: self.web_utils.system_utils.restart_bjorn_service(self),
            '/restore_default_config': self.web_utils.system_utils.restore_default_config,
            '/save_config': self.web_utils.system_utils.save_configuration,
            'reboot': self.web_utils.system_utils.reboot_system,
            'shutdown': self.web_utils.system_utils.shutdown_system,
            # BLUETOOTH
            '/connect_bluetooth': lambda d: self.web_utils.bluetooth_utils.connect_bluetooth(d.get('address')),
            '/disconnect_bluetooth': lambda d: self.web_utils.bluetooth_utils.disconnect_bluetooth(d.get('address')),
            '/forget_bluetooth': lambda d: self.web_utils.bluetooth_utils.forget_bluetooth(d.get('address')),
            '/pair_bluetooth': lambda d: self.web_utils.bluetooth_utils.pair_bluetooth(d.get('address'), d.get('pin')),
            '/trust_bluetooth': lambda d: self.web_utils.bluetooth_utils.trust_bluetooth(d.get('address')),
            # SCRIPTS
            '/clear_script_output': self.web_utils.script_utils.clear_script_output,
            '/delete_script': self.web_utils.script_utils.delete_script,
            '/export_script_logs': self.web_utils.script_utils.export_script_logs,
            '/get_script_output': self.web_utils.script_utils.get_script_output,
            '/run_script': self.web_utils.script_utils.run_script,
            '/stop_script': self.web_utils.script_utils.stop_script,
            # CHARACTERS
            '/create_character': self.web_utils.action_utils.create_character,
            '/switch_character': self.web_utils.action_utils.switch_character,
            '/delete_character': self.web_utils.action_utils.delete_character,
            '/reload_fonts': getattr(self.web_utils.action_utils, 'reload_fonts', None),
            '/reload_images': getattr(self.web_utils.action_utils, 'reload_images', None),
            # COMMENTS
            '/delete_comment_section': self.web_utils.action_utils.delete_comment_section,
            '/restore_default_comments': self.web_utils.action_utils.restore_default_comments,
            '/save_comments': self.web_utils.action_utils.save_comments,
            # ATTACKS
            '/add_attack': self.web_utils.action_utils.add_attack,
            '/remove_attack': self.web_utils.action_utils.remove_attack,
            '/restore_attack': self.web_utils.action_utils.restore_attack,
            '/save_attack': self.web_utils.action_utils.save_attack,
            # VULN
            '/api/cve/bulk': lambda d: (self.web_utils.vuln_utils.serve_cve_bulk(self, d) or {"status": "ok"}),
            # STUDIO
            '/api/studio/action/replace': lambda d: self.web_utils.studio_utils.studio_replace_actions_with_db(),
            '/api/studio/action/update': self.web_utils.studio_utils.studio_update_action,
            '/api/studio/actions/sync': lambda d: self.web_utils.studio_utils.studio_sync_actions_studio(),
            '/api/studio/apply': lambda d: self.web_utils.studio_utils.studio_apply_to_runtime(),
            '/api/studio/edge/delete': self.web_utils.studio_utils.studio_delete_edge,
            '/api/studio/edge/upsert': self.web_utils.studio_utils.studio_upsert_edge,
            '/api/studio/host': self.web_utils.studio_utils.studio_upsert_host_flat,
            '/api/studio/host/delete': self.web_utils.studio_utils.studio_delete_host,
            '/api/studio/save': self.web_utils.studio_utils.studio_save_bundle,
            # DB
            '/api/db/add_column': lambda d: self.web_utils.db_utils.db_add_column_endpoint(self, d),
            '/api/db/create_table': lambda d: self.web_utils.db_utils.db_create_table_endpoint(self, d),
            '/api/db/delete': lambda d: self.web_utils.db_utils.db_delete_rows_endpoint(self, d),
            '/api/db/insert': lambda d: self.web_utils.db_utils.db_insert_row_endpoint(self, d),
            '/api/db/rename_table': lambda d: self.web_utils.db_utils.db_rename_table_endpoint(self, d),
            '/api/db/update': lambda d: self.web_utils.db_utils.db_update_cells_endpoint(self, d),
            '/api/db/vacuum': lambda d: self.web_utils.db_utils.db_vacuum_endpoint(self),
            # ACTION
            '/action/delete': self.web_utils.action_utils.delete_action,
            '/actions/restore_defaults': self.web_utils.action_utils.restore_defaults,
            # NETKB
            '/delete_all_actions': self.web_utils.netkb_utils.delete_all_actions,
            '/delete_netkb_action': self.web_utils.netkb_utils.delete_netkb_action,
            # ORCHESTRATOR
            '/manual_attack': self.web_utils.orchestrator_utils.execute_manual_attack,
            '/manual_scan': lambda d: self.web_utils.orchestrator_utils.execute_manual_scan(),
            '/start_orchestrator': lambda _: self.web_utils.orchestrator_utils.start_orchestrator(),
            '/stop_orchestrator': lambda _: self.web_utils.orchestrator_utils.stop_orchestrator(),
        }

    # ------------------------------------------------------------------------
    # HELPER HANDLERS
    # ------------------------------------------------------------------------
    
    def _serve_web_delay(self, handler):
        handler.send_response(200)
        handler.send_header("Content-type", "application/json")
        handler.end_headers()
        response = json.dumps({"web_delay": self.shared_data.web_delay})
        handler.wfile.write(response.encode('utf-8'))

    def _serve_running_scripts(self, handler):
        response = self.web_utils.script_utils.get_running_scripts()
        self._send_json(response, status=200)

    def _serve_list_scripts(self, handler):
        response = self.web_utils.script_utils.list_scripts()
        self._send_json(response, status=200)

    def _serve_action_args_schema(self, handler):
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(self.path).query)
        action_name = query.get('action_name', [''])[0]
        response = self.web_utils.script_utils.get_action_args_schema({"action_name": action_name})
        self._send_json(response, status=200)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    # ... [Authentication helpers same as before] ...
    def delete_cookie(self, key, path='/'):
        """Delete a cookie by setting max-age to 0."""
        self.set_cookie(key, '', path=path, max_age=0)

    def get_cookie(self, key):
        """Retrieve the value of a specific cookie from request headers."""
        if "Cookie" in self.headers:
            cookie = cookies.SimpleCookie(self.headers["Cookie"])
            if key in cookie:
                return cookie[key].value
        return None

    def is_authenticated(self):
        if not self.shared_data.webauth:
            return True
        return self.get_cookie('authenticated') == '1'

    def set_cookie(self, key, value, path='/', max_age=None):
        cookie = cookies.SimpleCookie()
        cookie[key] = value
        cookie[key]['path'] = path
        if max_age is not None:
            cookie[key]['max-age'] = max_age
        self.send_header('Set-Cookie', cookie.output(header='', sep=''))

    # ... [Compression helpers same as before] ...
    def gzip_encode(self, content):
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="w") as f:
            f.write(content)
        return out.getvalue()

    def send_gzipped_response(self, content, content_type):
        gzipped_content = self.gzip_encode(content)
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(gzipped_content)))
        self.end_headers()
        self.wfile.write(gzipped_content)

    def serve_file_gzipped(self, file_path, content_type):
        with open(file_path, 'rb') as file:
            content = file.read()
        self.send_gzipped_response(content, content_type)

    # ... [Login/Logout handlers same as before] ...
    def handle_login(self):
        if not self.shared_data.webauth:
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = urllib.parse.parse_qs(post_data)

        username = params.get('username', [None])[0]
        password = params.get('password', [None])[0]

        try:
            with open(self.shared_data.webapp_json, 'r') as f:
                auth_config = json.load(f)
                expected_user = auth_config['username']
                expected_pass = auth_config['password']
        except Exception as e:
            logger.error(f"Error loading webapp.json: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Server Error')
            return

        if username == expected_user and password == expected_pass:
            always_auth = params.get('alwaysAuth', [None])[0] == 'on'
            try:
                with open(self.shared_data.webapp_json, 'r+') as f:
                    config = json.load(f)
                    config['always_require_auth'] = always_auth
                    f.seek(0)
                    json.dump(config, f, indent=4)
                    f.truncate()
            except Exception as e:
                logger.error(f"Error saving auth preference: {e}")

            if not always_auth:
                self.set_cookie('authenticated', '1', max_age=30*24*60*60)
            else:
                self.set_cookie('authenticated', '1')
                
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.send_response(401)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Unauthorized')

    def handle_logout(self):
        if not self.shared_data.webauth:
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
            return
            
        self.send_response(302)
        self.delete_cookie('authenticated')
        self.send_header('Location', '/login.html')
        self.end_headers()

    def serve_login_page(self):
        try:
            with open(self.shared_data.webapp_json, 'r') as f:
                config = json.load(f)
                always_auth = config.get('always_require_auth', False)
                
            with open(os.path.join(self.shared_data.web_dir, 'login.html'), 'r') as f:
                content = f.read()
            if always_auth:
                content = content.replace('name="alwaysAuth"', 'name="alwaysAuth" checked')
            self.send_gzipped_response(content.encode(), 'text/html')
        except Exception as e:
            logger.error(f"Error handling login page: {e}")
            login_page_path = os.path.join(self.shared_data.web_dir, 'login.html')
            self.serve_file_gzipped(login_page_path, 'text/html')

    def log_message(self, format, *args):
        if 'GET' not in format % args:
            logger.info("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    # ------------------------------------------------------------------------
    # DELETE REQUEST HANDLER
    # ------------------------------------------------------------------------
    def do_DELETE(self):
        if self.shared_data.webauth and not self.is_authenticated():
            self._send_json({"status": "error", "message": "Unauthorized"}, 401)
            return

        try:
            if self.path.startswith('/api/studio/host/'):
                mac = self.path.split('/api/studio/host/')[-1]
            elif self.path.startswith('/studio/host/'):
                mac = self.path.split('/studio/host/')[-1]
            else:
                super().do_GET()
                return

            resp = self.web_utils.studio_utils.studio_delete_host({"mac_address": mac})
            status_code = 400 if resp.get("status") == "error" else 200
            self._send_json(resp, status_code)
        except Exception as e:
            logger.error(f"DELETE error: {e}")
            self._send_json({"status": "error", "message": str(e)}, 500)

    # ------------------------------------------------------------------------
    # GET REQUEST HANDLER
    # ------------------------------------------------------------------------
    def do_GET(self):
        # Public assets
        public_paths = [
            '/apple-touch-icon', '/favicon.ico', '/manifest.json',
            '/static/', '/web/css/', '/web/images/', '/web/js/',
        ]
        if self.shared_data.webauth:
            public_paths.extend(['/login', '/login.html', '/logout'])
        
        # Bypass auth for public paths
        if any(self.path.startswith(p) for p in public_paths):
            if self.shared_data.webauth:
                if self.path in ['/login', '/login.html']:
                    self.serve_login_page()
                    return
                elif self.path == '/logout':
                    self.handle_logout()
                    return
            super().do_GET()
            return
                
        # Enforce auth
        if self.shared_data.webauth and not self.is_authenticated():
            self.send_response(302)
            self.send_header('Location', '/login.html')
            self.end_headers()
            return

        # HTML Pages
        html_pages = {
            '/': 'index.html',
            '/actions.html': 'actions.html',
            '/actions_launcher.html': 'actions_launcher.html',
            '/actions_studio.html': 'actions_studio.html',
            '/backup_update.html': 'backup_update.html',
            '/bjorn.html': 'bjorn.html',
            '/comments.html': 'comments.html',
            '/config.html': 'config.html',
            '/credentials.html': 'credentials.html',
            '/database.html': 'database.html',
            '/files_explorer.html': 'files_explorer.html',
            '/index.html': 'index.html',
            '/loot.html': 'loot.html',
            '/manual.html': 'manual.html',
            '/netkb.html': 'netkb.html',
            '/network.html': 'network.html',
            '/scheduler.html': 'scheduler.html',
            '/status_images.html': 'status_images.html',
            '/web_enum.html': 'web_enum.html',
            '/zombieland.html': 'zombieland.html',
        }
        
        path_clean = self.path.split('?')[0]
        if path_clean in html_pages:
            self.serve_file_gzipped(os.path.join(self.shared_data.web_dir, html_pages[path_clean]), 'text/html')
            return

        if self.path == '/vulnerabilities.html':
            optimized_path = os.path.join(self.shared_data.web_dir, 'vulnerabilities_optimized.html')
            normal_path = os.path.join(self.shared_data.web_dir, 'vulnerabilities.html')
            path_to_serve = optimized_path if os.path.exists(optimized_path) else normal_path
            self.serve_file_gzipped(path_to_serve, 'text/html')
            return

        # --- DYNAMIC ROUTING MATCHING ---
        
        # 1. Exact match
        if path_clean in self.GET_ROUTES:
            # FIX: Pass 'self' (the handler instance) to the function
            self.GET_ROUTES[path_clean](self)
            return

        # 2. Prefix match (for routes with params in path)
        if self.path.startswith('/c2/download_client/'):
            filename = unquote(self.path.split('/c2/download_client/')[-1])
            self.web_utils.c2.c2_download_client(self, filename)
            return
        elif self.path.startswith('/c2/stale_agents'):
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            threshold = int(query.get("threshold", [300])[0])
            self.web_utils.c2.c2_stale_agents(self, threshold)
            return
        elif self.path.startswith('/api/webenum/results'):
            self.web_utils.webenum_utils.serve_webenum_data(self)
            return
        elif self.path.startswith('/download_file'):
            self.web_utils.file_utils.download_file(self)
            return
        elif self.path.startswith('/list_files'):
            self.web_utils.file_utils.list_files_endpoint(self)
            return
        elif self.path.startswith('/loot_download'):
            self.web_utils.file_utils.loot_download(self)
            return
        elif self.path.startswith('/download_backup'):
            self.web_utils.backup_utils.download_backup(self)
            return
        elif self.path.startswith('/get_script_output/'):
            script_name = unquote(self.path.split('/')[-1])
            response = self.web_utils.script_utils.get_script_output({"script_name": script_name})
            self._send_json(response)
            return
        elif self.path.startswith('/get_action_images?'):
            self.web_utils.action_utils.get_action_images(self)
            return
        elif self.path.startswith('/get_status_icon?'):
            self.web_utils.action_utils.get_status_icon(self)
            return
        elif self.path.startswith('/images/status/'):
            self.web_utils.action_utils.serve_status_image(self)
            return
        elif self.path.startswith('/list_static_images_with_dimensions'):
            self.web_utils.action_utils.list_static_images_with_dimensions(self)
            return
        elif self.path.startswith('/screen.png'):
            self.web_utils.action_utils.serve_image(self)
            return
        elif self.path.startswith('/static_images/'):
            self.web_utils.action_utils.serve_static_image(self)
            return
        elif self.path.startswith('/bjorn_status_image'):
            self.web_utils.action_utils.serve_bjorn_status_image(self)
            return
        elif self.path.startswith('/get_character_icon'):
            self.web_utils.action_utils.get_character_icon(self)
            return
        elif self.path.startswith('/get_character_image?'):
            self.web_utils.action_utils.get_character_image(self)
            return
        elif self.path.startswith('/bjorn_character'):
            fn = getattr(self.web_utils.action_utils, 'serve_bjorn_character', self.web_utils.action_utils.serve_bjorn_status_image)
            fn(self)
            return
        elif self.path.startswith('/get_comments?'):
            self.web_utils.action_utils.get_comments(self)
            return
        elif self.path.startswith('/get_attack_content'):
            self.web_utils.action_utils.get_attack_content(self)
            return
        elif self.path.startswith('/get_attacks'):
            self.web_utils.action_utils.get_attacks(self)
            return
        elif self.path.startswith('/actions_icons'):
            self.web_utils.action_utils.serve_actions_icons(self)
            return
        elif self.path.startswith('/list_vulnerabilities'):
            if '?' in self.path and 'page=' in self.path:
                self.web_utils.vuln_utils.serve_vulns_data_optimized(self)
            else:
                self.web_utils.vuln_utils.serve_vulns_data(self)
            return
        elif self.path.startswith('/vulnerabilities/history'):
            self.web_utils.vuln_utils.serve_vuln_history(self)
            return
        elif self.path.startswith('/api/cve/'):
            cve_id = self.path.split('/api/cve/')[-1].split('?')[0]
            self.web_utils.vuln_utils.serve_cve_details(self, cve_id)
            return
        elif self.path.startswith('/api/exploitdb/'):
            cve_id = self.path.split('/api/exploitdb/')[-1].split('?')[0]
            self.web_utils.vuln_utils.serve_exploitdb_by_cve(self, cve_id)
            return
        elif self.path.startswith('/api/studio/hosts'):
            self.web_utils.studio_utils.studio_get_hosts(self)
            return
        elif self.path.startswith('/api/studio/layout'):
            self.web_utils.studio_utils.studio_load_layout(self)
            return
        elif self.path.startswith('/api/db/export/'):
            table_name = unquote(self.path.split('/api/db/export/', 1)[1].split('?', 1)[0])
            self.web_utils.db_utils.db_export_table_endpoint(self, table_name)
            return
        elif self.path.startswith('/api/db/schema/'):
            name = unquote(self.path.split('/api/db/schema/', 1)[1])
            self.web_utils.db_utils.db_schema_endpoint(self, name)
            return
        elif self.path.startswith('/api/db/table/'):
            table_name = unquote(self.path.split('/api/db/table/', 1)[1].split('?', 1)[0])
            self.web_utils.db_utils.db_get_table_endpoint(self, table_name)
            return
        elif self.path.startswith('/attempt_history'):
            self.web_utils.netkb_utils.serve_attempt_history(self)
            return
        elif self.path.startswith('/action_queue'):
            self.web_utils.netkb_utils.serve_action_queue(self)
            return

        super().do_GET()

    # ------------------------------------------------------------------------
    # POST REQUEST HANDLER
    # ------------------------------------------------------------------------
    def do_POST(self):
        # Handle Auth
        if self.path == '/login' and self.shared_data.webauth:
            self.handle_login()
            return
        elif self.path == '/logout' and self.shared_data.webauth:
            self.handle_logout()
            return
        
        if self.shared_data.webauth and not self.is_authenticated():
            self.send_response(401)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Unauthorized')
            return

        # Special Route
        if self.path == '/queue_cmd':
            self.web_utils.netkb_utils.handle_queue_cmd(self)
            return

        try:
            # 1. MULTIPART ROUTES
            if self.path in self.POST_ROUTES_MULTIPART:
                self.POST_ROUTES_MULTIPART[self.path](self)
                return

            # 2. JSON ROUTES
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            
            # Guard
            content_type = self.headers.get('Content-Type', '')
            if content_type.startswith('multipart/form-data'):
                self._send_json({"status": "error", "message": "Unexpected multipart/form-data"}, 400)
                return

            data = json.loads(body)

            # Special case for livestatus
            if self.path == '/clear_livestatus':
                restart = data.get("restart", True)
                self.web_utils.system_utils.clear_livestatus(self, restart=restart)
                return

            # Dynamic Dispatch for JSON
            if self.path in self.POST_ROUTES_JSON:
                handler = self.POST_ROUTES_JSON[self.path]
                if callable(handler):
                    response = handler(data)
                    # Handlers that return response data need sending, those that return None handle sending themselves?
                    # Looking at original code, many util methods return dicts, but some handle self.wfile.
                    # The lambda wrappers in POST_ROUTES_JSON suggest they return data.
                    # Let's standardize: if handler returns data, we send it.
                    if response is not None:
                        status_code = 400 if isinstance(response, dict) and response.get("status") == "error" else 200
                        self._send_json(response, status_code)
                    return

            # Path params routes (DB)
            if self.path.startswith('/api/db/drop/'):
                table_name = unquote(self.path.split('/api/db/drop/', 1)[1])
                self.web_utils.db_utils.db_drop_table_endpoint(self, table_name)
                return
            elif self.path.startswith('/api/db/drop_view/'):
                view_name = unquote(self.path.split('/api/db/drop_view/', 1)[1])
                self.web_utils.db_utils.db_drop_view_endpoint(self, view_name)
                return
            elif self.path.startswith('/api/db/truncate/'):
                table_name = unquote(self.path.split('/api/db/truncate/', 1)[1])
                self.web_utils.db_utils.db_truncate_table_endpoint(self, table_name)
                return

            # 404
            self._send_json({"status": "error", "message": "Route not found"}, 404)

        except json.JSONDecodeError:
            self._send_json({"status": "error", "message": "Invalid JSON format"}, 400)
        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            self._send_json({"status": "error", "message": str(e)}, 500)


# ============================================================================
# WEB SERVER THREAD
# ============================================================================

class WebThread(threading.Thread):
    """
    Threaded web server with automatic port conflict resolution.
    Handles graceful shutdown and server lifecycle.
    """
    
    def __init__(self, handler_class=CustomHandler, port=8000):
        super().__init__()
        self.shared_data = shared_data
        self.initial_port = port
        self.current_port = port
        self.handler_class = handler_class
        self.httpd = None

    def setup_server(self):
        """
        Configure and start server with port error handling.
        Attempts to bind to the port up to 10 times, incrementing port on conflicts.
        """
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                class ThreadedTCPServer(socketserver.ThreadingTCPServer):
                    """
                    Custom TCP server with socket reuse options.
                    Allows address/port reuse to prevent "Address already in use" errors.
                    """
                    allow_reuse_address = True
                    socket_options = [(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)]
                    if hasattr(socket, "SO_REUSEPORT"):  # Linux only
                        socket_options.append((socket.SOL_SOCKET, socket.SO_REUSEPORT, 1))

                server = ThreadedTCPServer(("", self.current_port), self.handler_class)
                
                for opt in server.socket_options:
                    server.socket.setsockopt(*opt)
                
                return server
                
            except OSError as e:
                if e.errno == 98:  # Address already in use
                    retry_count += 1
                    if self.current_port == self.initial_port:
                        time.sleep(1)
                    else:
                        self.current_port += 1
                else:
                    raise

        raise RuntimeError(f"Unable to start server after {max_retries} attempts")

    def run(self):
        while not self.shared_data.webapp_should_exit:
            try:
                self.current_port = self.initial_port
                self.httpd = self.setup_server()
                logger.info(f"Server started on port {self.current_port}")
                self.httpd.serve_forever()
            except Exception as e:
                logger.error(f"Server error: {e}")
                if self.httpd:
                    self.httpd.server_close()
                time.sleep(1)

    def shutdown(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            logger.info("Web server stopped.")


def handle_exit_web(signum, frame):
    shared_data.webapp_should_exit = True
    if web_thread.is_alive():
        web_thread.shutdown()
        web_thread.join()
    logger.info("Server shutting down...")
    sys.exit(0)


web_thread = WebThread(port=8000)
signal.signal(signal.SIGINT, handle_exit_web)
signal.signal(signal.SIGTERM, handle_exit_web)

if __name__ == "__main__":
    try:
        web_thread.start()
        logger.info("Web server thread started.")
    except Exception as e:
        logger.error(f"An exception occurred during web server start: {e}")
        handle_exit_web(signal.SIGINT, None)
        sys.exit(1)