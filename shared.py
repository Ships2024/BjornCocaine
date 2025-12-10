# shared.py
# Core component for managing shared resources and data for Bjorn project
# Handles initialization, configuration, logging, fonts, images, and database management

import os
import re
import importlib
import random
import time
import ast
import logging
import subprocess
import threading
from typing import Dict, List, Optional, Any
from PIL import Image, ImageFont 
from logger import Logger
# from epd_helper import EPDHelper
from epd_manager import EPDManager

from database import BjornDatabase

logger = Logger(name="shared.py", level=logging.DEBUG)


class SharedData:
    """Centralized shared data manager for all Bjorn modules"""
    
    def __init__(self):
        # Initialize core paths first
        self.initialize_paths()
        
        # Initialize status tracking
        self.status_list = []
        self.last_comment_time = time.time()
        
        # Event for orchestrator wake-up (Avoids CPU busy-waiting)
        self.queue_event = threading.Event()
        
        # Load default configuration
        self.default_config = self.get_default_config()
        self.config = self.default_config.copy()
        
        # Initialize database (single source of truth)
        self.db = BjornDatabase()
        
        # Load existing configuration from database
        self.load_config()
        
        # Update security blacklists
        self.update_security_blacklists()
        
        # Setup environment and resources
        self.setup_environment()
        self.initialize_runtime_variables()
        self.initialize_statistics()
        self.load_fonts()
        self.load_images()
        
        logger.info("SharedData initialization complete")

    def initialize_paths(self):
        """Initialize all application paths and create necessary directories"""
        # Base directories
        self.bjorn_user_dir = '/home/bjorn/'
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Main application directories
        self.data_dir = os.path.join(self.current_dir, 'data')
        self.actions_dir = os.path.join(self.current_dir, 'actions')
        self.web_dir = os.path.join(self.current_dir, 'web')
        self.resources_dir = os.path.join(self.current_dir, 'resources')
        
        # User directories
        self.backup_dir = '/home/bjorn/.backups_bjorn'
        self.settings_dir = '/home/bjorn/.settings_bjorn'
        
        # Data subdirectories
        self.logs_dir = os.path.join(self.data_dir, 'logs')
        self.output_dir = os.path.join(self.data_dir, 'output')
        self.input_dir = os.path.join(self.data_dir, 'input')

        
        # Output subdirectories
        self.data_stolen_dir = os.path.join(self.output_dir, 'data_stolen')
        
        # Resources subdirectories
        self.images_dir = os.path.join(self.resources_dir, 'images')
        self.fonts_dir = os.path.join(self.resources_dir, 'fonts')
        self.default_config_dir = os.path.join(self.resources_dir, 'default_config')
        self.default_comments_dir = os.path.join(self.default_config_dir, 'comments')

        # Default config subdirectories
        self.default_comments_file = os.path.join(self.default_comments_dir, 'comments.en.json')
        self.default_images_dir = os.path.join(self.default_config_dir, 'images')
        self.default_actions_dir = os.path.join(self.default_config_dir, 'actions')
        
        # Images subdirectories
        self.status_images_dir = os.path.join(self.images_dir, 'status')
        self.static_images_dir = os.path.join(self.images_dir, 'static')
        
        # Input subdirectories
        self.dictionary_dir = os.path.join(self.input_dir, "dictionary")
        self.potfiles_dir = os.path.join(self.input_dir, "potfiles")
        self.wordlists_dir = os.path.join(self.input_dir, "wordlists")
        self.nmap_prefixes_dir = os.path.join(self.input_dir, "prefixes")
        
        # Actions subdirectory
        self.actions_icons_dir = os.path.join(self.actions_dir, 'actions_icons')
        
        # Important files
        self.version_file = os.path.join(self.current_dir, 'version.txt')
        self.backups_json = os.path.join(self.backup_dir, 'backups.json')
        self.webapp_json = os.path.join(self.settings_dir, 'webapp.json')
        self.nmap_prefixes_file = os.path.join(self.nmap_prefixes_dir, "nmap-mac-prefixes.txt")
        self.common_wordlist = os.path.join(self.wordlists_dir, "common.txt")
        self.users_file = os.path.join(self.dictionary_dir, "users.txt")
        self.passwords_file = os.path.join(self.dictionary_dir, "passwords.txt")
        self.log_file = os.path.join(self.logs_dir, 'Bjorn.log')
        self.web_console_log = os.path.join(self.logs_dir, 'web_console_log.txt')
        
        # Create all necessary directories
        self._create_directories()

    def _create_directories(self):
        """Create all necessary directories if they don't exist"""
        directories = [
            self.data_dir, self.actions_dir, self.web_dir, self.resources_dir,
            self.logs_dir, self.output_dir, self.input_dir, 
            self.data_stolen_dir, self.images_dir, self.fonts_dir, 
            self.fonts_dir, self.default_config_dir, self.default_comments_dir,
            self.status_images_dir, self.static_images_dir, self.dictionary_dir,
            self.potfiles_dir, self.wordlists_dir, self.nmap_prefixes_dir,
            self.backup_dir, self.settings_dir
        ]
        
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                logger.error(f"Cannot create directory {directory}: {e}")

    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration settings"""
        return {
            # General Settings
            "__title_Bjorn__": "Settings",
            "bjorn_name": "Bjorn",
            "current_character": "BJORN",
            "manual_mode": False,
            "debug_mode": True,
            "lang_priority":["en", "fr", "es"] ,
            "lang": "en",
            
            # Web Server Settings
            "websrv": True,
            "webauth": False,
            "retry_success_actions": False,
            "retry_failed_actions": True,
            "blacklistcheck": True,
            "consoleonwebstart": True,
            
            # Timing Settings
            "startup_delay": 5,
            "web_delay": 2,
            "screen_delay": 1,
            "comment_delaymin": 15,
            "comment_delaymax": 30,
            "livestatus_delay": 8,
            
            # Display Settings
            "epd_enabled": True,
            "screen_reversed": True,
            "web_screen_reversed": True,
            "showstartupipssid": False,
            "showiponscreen": True,
            "showssidonscreen": True,
            "shared_update_interval": 10,
            "vuln_update_interval": 20,
            "semaphore_slots": 5,
            "double_partial_refresh": True,
            "startup_splash_duration": 3,
            "fullrefresh_activated": True,
            "fullrefresh_delay": 600,
            "image_display_delaymin": 2,
            "image_display_delaymax": 8,
            
            # EPD Display Settings
            "ref_width": 122,
            "ref_height": 250,
            "epd_type": "epd2in13_V4",
            "defaultfonttitle": "Viking.TTF",
            "defaultfont": "Arial.ttf",
            "line_spacing": 1,
            
            # Display Positions
            "frise_default_x": 0,
            "frise_default_y": 160,
            "frise_epd2in7_x": 50,
            "frise_epd2in7_y": 160,
            
            # Network Interface Settings
            "ip_iface_priority": ["wlan0", "eth0"],
            "neigh_wifi_iface": "wlan0",
            "neigh_ethernet_iface": "eth0",
            "neigh_usb_iface": "usb0",
            "neigh_bluetooth_ifaces": ["pan0", "bnep0"],
            
            # Security Lists
            "__title_lists__": "List Settings",
            "portlist": [20, 21, 22, 23, 25, 53, 69, 80, 110, 111, 135, 137, 139, 143, 
                        161, 162, 389, 443, 445, 512, 513, 514, 587, 636, 993, 995, 
                        1080, 1433, 1521, 2049, 3306, 3389, 5000, 5001, 5432, 5900, 
                        8080, 8443, 9090, 10000],
            "mac_scan_blacklist": [],
            "ip_scan_blacklist": [],
            "hostname_scan_blacklist": ["bjorn.home"],
            "steal_file_names": ["ssh.csv", "hack.txt"],
            "steal_file_extensions": [".bjorn", ".hack", ".flag"],
            "ignored_smb_shares": ["print$", "ADMIN$", "IPC$"],
            
            # Network Scanning Settings
            "__title_network__": "Network",
            "nmap_scan_aggressivity": "-T2",
            "portstart": 1,
            "portend": 2,
            "use_custom_network": False,
            "custom_network": "192.168.1.0/24",
            "default_network_interface": "wlan0",

            # Vulnerability Scanning Settings
            "vuln_fast": True,
            "nse_vulners": True,
            "vuln_max_ports": 25,
            "vuln_rescan_on_change_only": False,   # (facultatif: force un rescan)
            "vuln_rescan_ttl_seconds": 0,
            "scan_cpe": True,
            "nvd_api_key": "",                 
            "exploitdb_repo_dir": "/home/bjorn/exploitdb",
            "exploitdb_enabled": True,
            "searchsploit_path": "/home/bjorn/exploitdb/searchsploit",   
            "exploitdb_root": "/home/bjorn/exploitdb",                   # si cloné
            "kev_feed_url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            "epss_api": "https://api.first.org/data/v1/epss?cve=",

            #Actions Studio Settings
            "__title_actions_studio__": "Actions Studio",
            "use_actions_studio": True,


            # Action Timing Settings
            "__title_timewaits__": "Time Wait Settings",
            "timewait_smb": 0,
            "timewait_ssh": 0,
            "timewait_telnet": 0,
            "timewait_ftp": 0,
            "timewait_sql": 0,
        }

    def get_actions_config(self) -> List[Dict[str, Any]]:
        """Return actions configuration from database"""
        try:
            return self.db.list_actions()
        except Exception as e:
            logger.error(f"Failed to get actions config from DB: {e}")
            return []

    def update_security_blacklists(self):
        """Update MAC and hostname blacklists for security"""
        # Get local MAC address
        mac_address = self.get_raspberry_mac()
        if mac_address:
            self._add_to_blacklist('mac_scan_blacklist', mac_address, 'MAC address')
        else:
            logger.warning("Could not add local MAC to blacklist: MAC address not found")
        
        # Add local hostname to blacklist
        bjorn_hostname = "bjorn.home"
        self._add_to_blacklist('hostname_scan_blacklist', bjorn_hostname, 'hostname')

    def _add_to_blacklist(self, blacklist_key: str, value: str, value_type: str):
        """Add value to specified blacklist"""
        if blacklist_key not in self.config:
            self.config[blacklist_key] = []
        
        if value not in self.config[blacklist_key]:
            self.config[blacklist_key].append(value)
            logger.info(f"Added {value_type} {value} to blacklist")
        else:
            logger.info(f"{value_type} {value} already in blacklist")

    def get_raspberry_mac(self) -> Optional[str]:
        """Get MAC address of primary network interface"""
        try:
            # Try wireless interface first
            result = subprocess.run(['cat', '/sys/class/net/wlan0/address'], 
                                 capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().lower()
            
            # Fallback to ethernet interface
            result = subprocess.run(['cat', '/sys/class/net/eth0/address'], 
                                 capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().lower()
            
            logger.warning("Could not find MAC address for wlan0 or eth0")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Raspberry Pi MAC address: {e}")
            return None

    def setup_environment(self):
        """Setup application environment"""
        os.system('cls' if os.name == 'nt' else 'clear')
        self.save_config()
        self.sync_actions_to_database()
        self.delete_web_console_log()
        self.initialize_database()
        self.initialize_epd_display()

    def initialize_epd_display(self):
        """Initialize e-paper display"""
        try:
            logger.info("Initializing EPD display...")
            time.sleep(1)

            # Utiliser le manager au lieu de l’ancien helper
            self.epd = EPDManager(self.config["epd_type"])

            # Config orientation
            epd_configs = {
                "epd2in7": (False, False),
                "epd2in13_V2": (True, True),
                "epd2in13_V3": (True, True),
                "epd2in13_V4": (True, True)
            }
            if self.config["epd_type"] in epd_configs:
                self.screen_reversed, self.web_screen_reversed = epd_configs[self.config["epd_type"]]
                logger.info(f"EPD type: {self.config['epd_type']} - reversed: {self.screen_reversed}")

            # Init hardware une fois
            self.epd.init_full_update()
            self.width, self.height = self.epd.epd.width, self.epd.epd.height

            # Scaling
            self.ref_width = self.config.get('ref_width', 122)
            self.ref_height = self.config.get('ref_height', 250)
            self.scale_factor_x = self.width / self.ref_width
            self.scale_factor_y = self.height / self.ref_height

            logger.info(f"EPD {self.config['epd_type']} initialized: {self.width}x{self.height}")

        except Exception as e:
            logger.error(f"Error initializing EPD display: {e}")
            raise


    def initialize_runtime_variables(self):
        """Initialize runtime variables"""
        # System state flags
        self.should_exit = False
        self.display_should_exit = False
        self.orchestrator_should_exit = False
        self.webapp_should_exit = False
        
        # Instance tracking
        self.bjorn_instance = None
        
        # Network state
        self.wifi_connected = False
        self.wifi_changed = False
        self.bluetooth_active = False
        self.ethernet_active = False
        self.pan_connected = False
        self.usb_active = False
        
        # Display state
        self.bjorn_character = None
        self.current_path = []
        self.comment_params = {}
        self.bjorn_says = "Hacking away..."
        self.bjorn_orch_status = "IDLE"
        self.bjorn_status_text = "IDLE"
        self.bjorn_status_text2 = "Awakening..."
        self.bjorn_progress = ""
        
        # UI positioning
        self.text_frame_top = int(88 * self.scale_factor_x)
        self.text_frame_bottom = int(159 * self.scale_factor_y)
        self.y_text = self.text_frame_top + 2
        
        # Statistics
        self.battery_status = 26
        self.target_count = 0
        self.port_count = 0
        self.vuln_count = 0
        self.cred_count = 0
        self.data_count = 0
        self.zombie_count = 0
        self.coin_count = 0
        self.level_count = 0
        self.network_kb_count = 0
        self.attacks_count = 0
        
        # Display control
        self.show_first_image = True
        
        # Threading
        self.scripts_lock = threading.Lock()
        self.running_scripts = {}
        self.output_lock = threading.Lock()
        
        # URLs
        self.github_version_url = "https://raw.githubusercontent.com/infinition/Bjorn/main/version.txt"

    def initialize_statistics(self):
        """Initialize statistics in database"""
        try:
            self.db.ensure_stats_initialized()
            self.db.update_livestats(
                total_open_ports=0,
                alive_hosts_count=0,
                all_known_hosts_count=0,
                vulnerabilities_count=0
            )
            logger.info("Statistics initialized in database")
        except Exception as e:
            logger.error(f"Error initializing statistics: {e}")

    def delete_web_console_log(self):
        """Delete and recreate web console log file"""
        try:
            if os.path.exists(self.web_console_log):
                os.remove(self.web_console_log)
                logger.info(f"Deleted web console log: {self.web_console_log}")
            
            # Recreate empty file
            open(self.web_console_log, 'a').close()
            
        except Exception as e:
            logger.error(f"Error managing web console log: {e}")

    def sync_actions_to_database(self):
        """Sync action definitions from files to database (and keep actions_studio in sync non-destructively)."""
        actions_config = []

        try:
            for filename in os.listdir(self.actions_dir):
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue

                meta = self._extract_action_metadata(os.path.join(self.actions_dir, filename))
                if not meta:
                    continue

                # Defaults
                meta.setdefault("b_action", "normal")
                meta.setdefault("b_priority", 50)
                meta.setdefault("b_timeout", 300)
                meta.setdefault("b_max_retries", 3)
                meta.setdefault("b_cooldown", 0)
                meta.setdefault("b_stealth_level", 5)
                meta.setdefault("b_risk_level", "medium")
                meta.setdefault("b_enabled", 1)

                actions_config.append(meta)

                # Status tracking
                if meta["b_class"] not in self.status_list:
                    self.status_list.append(meta["b_class"])

            if actions_config:
                self.db.sync_actions(actions_config)
                logger.info(f"Synchronized {len(actions_config)} actions to database")

            # Garde actions_studio alignée
            try:
                self.db._sync_actions_studio_schema_and_rows()
                logger.info("actions_studio schema/rows synced (non-destructive)")
            except Exception as e:
                logger.error(f"actions_studio sync failed: {e}")

        except Exception as e:
            logger.error(f"Error syncing actions to database: {e}")


    def _extract_action_metadata(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Extract action metadata from Python file using AST parsing (Safe)"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)
            
            meta = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    if isinstance(node.targets[0], ast.Name):
                        key = node.targets[0].id
                        if key.startswith("b_"):
                            try:
                                val = ast.literal_eval(node.value)
                                meta[key] = val
                            except (ValueError, SyntaxError):
                                logger.warning(f"Could not safe-eval variable {key} in {filepath}. Use literals only.")
                                pass
            
            # Set default module name if not specified
            if "b_module" not in meta:
                meta["b_module"] = os.path.splitext(os.path.basename(filepath))[0]
            
            return meta if meta.get("b_class") else None
            
        except Exception as e:
            logger.error(f"Failed to parse {filepath}: {e}")
            return None

    # ... (le reste des méthodes initialize_database, load_config, etc. reste inchangé) ...
    # Assurez-vous d'inclure les autres méthodes existantes de la classe SharedData ici.
    # Pour la brièveté de la réponse, je ne répète pas les méthodes non modifiées si elles sont identiques au fichier original.
    # [INCLURE LE RESTE DU FICHIER SHARED.PY ORIGINAL ICI]
    def initialize_database(self):
        """Initialize database schema"""
        logger.info("Initializing database schema")
        try:
            self.db.ensure_schema()
            
            # Update status list from database if empty
            if not self.status_list:
                actions = self.db.list_actions()
                for action in actions:
                    if action.get("b_class"):
                        self.status_list.append(action["b_class"])
                        
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    def load_config(self):
        """Load configuration from database"""
        try:
            logger.info("Loading configuration from database")
            cfg = self.db.get_config()
            
            if not cfg:
                # Seed with defaults
                self.db.save_config(self.default_config.copy())
                cfg = self.db.get_config() or {}
            
            # Merge with current config
            self.config.update(cfg)
            
            # Expose config as attributes for backward compatibility
            for key, value in self.config.items():
                setattr(self, key, value)
                
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            # Fallback to defaults
            for key, value in self.config.items():
                setattr(self, key, value)

    def save_config(self):
        """Save configuration to database"""
        logger.info("Saving configuration to database")
        try:
            self.db.save_config(self.config)
            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def load_fonts(self):
        """Load font resources"""
        try:
            logger.info("Loading fonts")
            
            # Font paths
            self.default_font_path = os.path.join(self.fonts_dir, self.defaultfont)
            self.default_font_title_path = os.path.join(self.fonts_dir, self.defaultfonttitle)
            
            # Load font sizes
            self.font_arial14 = self._load_font(self.default_font_path, 14)
            self.font_arial11 = self._load_font(self.default_font_path, 11)
            self.font_arial9 = self._load_font(self.default_font_path, 9)
            self.font_arialbold = self._load_font(self.default_font_path, 12)
            
            # Viking font for title
            self.font_viking_path = self.default_font_title_path
            self.font_viking = self._load_font(self.default_font_title_path, 13)
            
            logger.info("Fonts loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            raise

    def _load_font(self, font_path: str, size: int):
        """Load a single font with specified size"""
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.error(f"Error loading font {font_path}: {e}")
            raise

    def load_images(self):
        """Load image resources for display"""
        try:
            logger.info("Loading images")
            
            # Initialize status image
            self.bjorn_status_image = None
            
            # Load static images
            self._load_static_images()
            
            # Load status images
            self._load_status_images()
            
            # Calculate display positions
            self._calculate_image_positions()
            
            logger.info("Images loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading images: {e}")
            raise

    def _load_static_images(self):
        """Load static UI images"""
        static_images = {
            'bjorn1': 'bjorn1.bmp',
            'port': 'port.bmp',
            'frise': 'frise.bmp',
            'target': 'target.bmp',
            'vuln': 'vuln.bmp',
            'connected': 'connected.bmp',
            'bluetooth': 'bluetooth.bmp',
            'wifi': 'wifi.bmp',
            'ethernet': 'ethernet.bmp',
            'usb': 'usb.bmp',
            'level': 'level.bmp',
            'cred': 'cred.bmp',
            'attack': 'attack.bmp',
            'attacks': 'attacks.bmp',
            'gold': 'gold.bmp',
            'networkkb': 'networkkb.bmp',
            'zombie': 'zombie.bmp',
            'data': 'data.bmp',
            'money': 'money.bmp',
            'zombie_status': 'zombie.bmp',
            'battery0': '0.bmp',
            'battery25': '25.bmp',
            'battery50': '50.bmp',
            'battery75': '75.bmp',
            'battery100': '100.bmp',
            'battery_charging': 'charging1.bmp'
        }
        
        for attr_name, filename in static_images.items():
            image_path = os.path.join(self.static_images_dir, filename)
            setattr(self, attr_name, self._load_image(image_path))

    def _load_status_images(self):
        """Load status-specific images and image series"""
        self.image_series = {}
        
        try:
            # Load images from database actions
            actions = self.db.list_actions()
            for action in actions:
                b_class = action.get('b_class')
                if b_class:
                    # Load individual status image
                    status_dir = os.path.join(self.status_images_dir, b_class)
                    image_path = os.path.join(status_dir, f'{b_class}.bmp')
                    image = self._load_image(image_path)
                    setattr(self, b_class, image)
                    
                    if b_class not in self.status_list:
                        self.status_list.append(b_class)
                    
                    # Load image series for animations
                    self.image_series[b_class] = []
                    if not os.path.isdir(status_dir):
                        os.makedirs(status_dir, exist_ok=True)
                        logger.warning(f"Created missing directory: {status_dir}")
                    
                    # Load numbered images for animation
                    for image_name in os.listdir(status_dir):
                        if image_name.endswith('.bmp') and re.search(r'\d', image_name):
                            series_image = self._load_image(os.path.join(status_dir, image_name))
                            if series_image:
                                self.image_series[b_class].append(series_image)
                    
                    logger.info(f"Loaded {len(self.image_series.get(b_class, []))} images for {b_class}")
                    
        except Exception as e:
            logger.error(f"Error loading status images: {e}")
        
        # Ensure IDLE images exist as fallback
        if not self.image_series:
            logger.error("No image series loaded")
        else:
            for status, images in self.image_series.items():
                logger.info(f"Status {status}: {len(images)} animation frames")

    def _load_image(self, image_path: str) -> Optional[Image.Image]:
        """Load a single image file"""
        try:
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}")
                return None
            return Image.open(image_path)
        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            return None

    def _calculate_image_positions(self):
        """Calculate image positions for display centering"""
        if self.bjorn1:
            self.x_center1 = (self.width - self.bjorn1.width) // 2
            self.y_bottom1 = self.height - self.bjorn1.height

    def update_bjorn_status(self):
        """Update current status image"""
        try:
            self.bjorn_status_image = getattr(self, self.bjorn_orch_status, None)
            if self.bjorn_status_image is None:
                logger.warning(f"Image for status {self.bjorn_orch_status} not available, using default")
                self.bjorn_status_image = self.attack
        except AttributeError:
            logger.warning(f"Status {self.bjorn_orch_status} not found, using IDLE")
            self.bjorn_status_image = self.attack
        
        self.bjorn_status_text = self.bjorn_orch_status

    def update_image_randomizer(self):
        """Select random image from current status series"""
        try:
            status = self.bjorn_status_text
            
            # Try to get images for current status
            if status in self.image_series and self.image_series[status]:
                images = self.image_series[status]
            # Fallback to IDLE images
            elif "IDLE" in self.image_series and self.image_series["IDLE"]:
                logger.warning(f"No images for {status}, using IDLE")
                images = self.image_series["IDLE"]
            else:
                logger.error("No images available")
                self.imagegen = None
                return
            
            # Select random image
            random_index = random.randint(0, len(images) - 1)
            self.imagegen = images[random_index]
            
            # Calculate centering
            self.x_center = (self.width - self.imagegen.width) // 2
            self.y_bottom = self.height - self.imagegen.height
            
        except Exception as e:
            logger.error(f"Error updating image randomizer: {e}")
            self.imagegen = None

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """Wrap text to fit within specified width"""
        try:
            lines = []
            words = text.split()
            
            while words:
                line = []
                while words and font.getlength(' '.join(line + [words[0]])) <= max_width:
                    line.append(words.pop(0))
                lines.append(' '.join(line).strip())
            
            return lines
            
        except Exception as e:
            logger.error(f"Error wrapping text: {e}")
            return [text]

    def update_stats(self):
        """Update calculated statistics based on formulas"""
        self.coin_count = int(
            self.network_kb_count * 5 + 
            self.cred_count * 5 + 
            self.data_count * 5 + 
            self.zombie_count * 10 + 
            self.attacks_count * 5 + 
            self.vuln_count * 2
        )
        
        self.level_count = int(
            self.network_kb_count * 0.1 + 
            self.cred_count * 0.2 + 
            self.data_count * 0.1 + 
            self.zombie_count * 0.5 + 
            self.attacks_count + 
            self.vuln_count * 0.01
        )

    def debug_print(self, message: str):
        """Print debug message if debug mode is enabled"""
        if self.config.get('debug_mode', False):
            logger.debug(message)