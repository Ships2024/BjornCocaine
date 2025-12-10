# display.py - FIXED VERSION (v2 + wrap_text/throttle optimizations)
# - Un seul thread d’update EPD à la fois (pas d’accumulation)
# - Full refresh déplacé dans le worker
# - Circuit breaker : désactive temporairement l’EPD après échecs répétés
# - Timeouts & logs conservés / améliorés
# - Reste compatible avec le code appelant
# - NEW: comment layout cache + throttling to reduce wrap_text calls

import threading
import time
import os
import signal
import logging
import random
import sys
import traceback
import json
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from init_shared import shared_data
from comment import CommentAI
from logger import Logger

logger = Logger(name="display.py", level=logging.DEBUG)


class Display:
    """Optimized display manager with robust error handling and recovery"""

    # CRITICAL: Timeout constants
    SEMAPHORE_TIMEOUT = 5.0          # Max time to wait for semaphore
    EPD_OPERATION_TIMEOUT = 10.0     # Max time for EPD operation (indicative)
    LOOP_ITERATION_TIMEOUT = 30.0    # Max time for one display loop
    RECOVERY_COOLDOWN = 60.0         # Min time between hard resets

    # Circuit breaker
    MAX_CONSECUTIVE_FAILURES = 6     # Après N échecs, on coupe l’EPD
    STUCK_RECOVERY_S = 120.0         # Si bloqué > 120s, on tente recovery

    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.config = self.shared_data.config
        self.comment_ai = CommentAI()
        self.epd_enabled = self.config.get("epd_enabled", True)

        self.epd = self.shared_data.epd if self.epd_enabled else None

        if self.config.get("epd_type") == "epd2in13_V2":
            self.shared_data.width = 120
        else:
            self.shared_data.width = self.shared_data.width

        self.semaphore = threading.Semaphore(self.shared_data.semaphore_slots)

        # Recovery tracking
        self.last_successful_update = time.time()
        self.last_recovery_attempt = 0
        self.consecutive_failures = 0
        self.total_updates = 0
        self.failed_updates = 0

        # Update worker (évite l’empilement)
        self._upd_lock = threading.Lock()
        self._upd_thread: Optional[threading.Thread] = None
        self._upd_stuck_since: Optional[float] = None
        self._last_full_refresh = time.time()

        # Screen configuration
        self.screen_reversed = self.shared_data.screen_reversed
        self.web_screen_reversed = self.shared_data.web_screen_reversed

        # Network status with caching
        self.ssid = ""
        self.current_ip = ""
        self.show_ip_on_screen = False
        self.show_ssid_on_screen = False
        self._network_cache = {'ip': None, 'ssid': None, 'timestamp': 0}
        self._network_cache_ttl = 30

        self._connection_cache = {'data': None, 'timestamp': 0}
        self._connection_cache_ttl = 10

        self._data_count_cache = {'count': 0, 'timestamp': 0}
        self._data_count_cache_ttl = 60

        # Display name
        self.bjorn_name = self.shared_data.bjorn_name
        self.previous_bjorn_name = None
        self.calculate_font_to_fit()

        # Full refresh settings
        self.fullrefresh_activated = self.shared_data.fullrefresh_activated
        self.fullrefresh_delay = self.shared_data.fullrefresh_delay

        # Cache for expensive operations
        self._stats_cache = {'data': None, 'timestamp': 0}
        self._stats_cache_ttl = 5.0

        # NEW: comment wrap/layout cache + throttle
        self._comment_layout_cache = {"key": None, "lines": [], "ts": 0.0}
        # Recompute at most once per this interval unless the key changes
        self._comment_layout_min_interval = max(0.8, float(self.shared_data.screen_delay))

        # Initialize display
        try:
            if self.epd_enabled:
                self.shared_data.epd.init_full_update()
                logger.info("EPD display initialization complete")

                if self.shared_data.showstartupipssid:
                    ip_address, ssid = self.get_network_info()
                    self.display_startup_ip(ip_address, ssid)
                    time.sleep(self.shared_data.startup_splash_duration)
            else:
                logger.info("EPD display disabled - running in web-only mode")

        except Exception as e:
            logger.error(f"Error during display initialization: {e}")
            if self.epd_enabled:
                # On remonte si EPD était censé être actif (cohérent avec l’existant)
                raise
            else:
                logger.warning("EPD initialization failed but continuing in web-only mode")

        self.shared_data.bjorn_status_text2 = "Awakening..."

        # Start background threads
        self._start_background_threads()

    def _start_background_threads(self):
        """Start all background update threads"""
        self.main_image_thread = threading.Thread(
            target=self.update_main_image, daemon=True, name="DisplayImageUpdater"
        )
        self.main_image_thread.start()

        self.stats_update_thread = threading.Thread(
            target=self.schedule_stats_update, daemon=True, name="DisplayStatsUpdater"
        )
        self.stats_update_thread.start()

    # ---- Positioning helpers ----

    def px(self, x_ref: int) -> int:
        return int(x_ref * self.shared_data.width / self.shared_data.ref_width)

    def py(self, y_ref: int) -> int:
        return int(y_ref * self.shared_data.height / self.shared_data.ref_height)

    # ---- Font management ----

    def calculate_font_to_fit(self):
        default_font_size = 13
        default_font_path = self.shared_data.font_viking_path
        default_font = ImageFont.truetype(default_font_path, default_font_size)
        max_text_width, _ = default_font.getsize("BJORN")

        self.font_to_use = self.get_font_to_fit(
            self.bjorn_name, default_font_path, max_text_width, default_font_size
        )

    def get_font_to_fit(self, text: str, font_path: str, max_width: int, max_font_size: int):
        font_size = max_font_size
        font = ImageFont.truetype(font_path, font_size)
        text_width, _ = font.getsize(text)

        while text_width > max_width and font_size > 5:
            font_size -= 1
            font = ImageFont.truetype(font_path, font_size)
            text_width, _ = font.getsize(text)

        return font

    def _pad_for_v2(self, img: Image.Image) -> Image.Image:
        if self.config.get("epd_type") == "epd2in13_V2" and img.size == (120, 250):
            padded = Image.new('1', (122, 250), 1)
            padded.paste(img, (1, 0))
            return padded
        return img

    # ---- Network status with caching ----

    def get_network_info(self) -> Tuple[str, str]:
        now = time.time()
        if self._network_cache['timestamp'] + self._network_cache_ttl > now:
            return self._network_cache['ip'], self._network_cache['ssid']

        ip = self.get_ip_address()
        ssid = self.get_ssids()
        self._network_cache = {'ip': ip, 'ssid': ssid, 'timestamp': now}
        return ip, ssid

    def get_ip_address(self) -> str:
        try:
            iface_list = self._as_list(
                getattr(self.shared_data, "ip_iface_priority", ["wlan0", "eth0"]),
                default=["wlan0", "eth0"]
            )

            for iface in iface_list:
                result = subprocess.run(
                    ['ip', 'addr', 'show', iface],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'inet ' in line:
                            return line.split()[1].split('/')[0]

            return "No IP"

        except Exception as e:
            logger.error(f"Error getting IP address: {e}")
            return "Error"

    def get_ssids(self) -> str:
        try:
            result = subprocess.run(
                ['iwgetid', '-r'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout.strip() or "No Wi-Fi"
            return "No Wi-Fi"

        except Exception as e:
            logger.error(f"Error getting SSID: {e}")
            return "Error"

    def check_all_connections(self) -> Dict[str, bool]:
        now = time.time()

        if self._connection_cache['data'] and (now - self._connection_cache['timestamp']) < self._connection_cache_ttl:
            return self._connection_cache['data']

        results = {}

        try:
            ip_neigh = subprocess.run(['ip', 'neigh', 'show'],
                                      capture_output=True, text=True, timeout=2)
            neigh_output = ip_neigh.stdout if ip_neigh.returncode == 0 else ""

            iwgetid = subprocess.run(['iwgetid', '-r'],
                                     capture_output=True, text=True, timeout=1)
            results['wifi'] = bool(iwgetid.returncode == 0 and iwgetid.stdout.strip())

            bt_ifaces = self._as_list(
                getattr(self.shared_data, "neigh_bluetooth_ifaces", ["pan0", "bnep0"]),
                default=["pan0", "bnep0"]
            )
            results['bluetooth'] = any(f'dev {iface}' in neigh_output for iface in bt_ifaces)

            eth_iface = self._as_str(
                getattr(self.shared_data, "neigh_ethernet_iface", "eth0"), "eth0"
            )
            results['ethernet'] = f'dev {eth_iface}' in neigh_output

            usb_iface = self._as_str(
                getattr(self.shared_data, "neigh_usb_iface", "usb0"), "usb0"
            )
            results['usb'] = f'dev {usb_iface}' in neigh_output

        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            results = {'wifi': False, 'bluetooth': False, 'ethernet': False, 'usb': False}

        self._connection_cache = {'data': results, 'timestamp': now}
        return results

    def is_manual_mode(self) -> bool:
        return self.shared_data.manual_mode

    def get_data_count(self) -> int:
        now = time.time()

        if (now - self._data_count_cache['timestamp']) < self._data_count_cache_ttl:
            return self._data_count_cache['count']

        try:
            total = sum(
                len(files) for r, d, files in os.walk(self.shared_data.data_stolen_dir)
            )
            self._data_count_cache = {'count': total, 'timestamp': now}
            return total
        except Exception as e:
            logger.error(f"Error counting data files: {e}")
            return self._data_count_cache.get('count', 0)

    def display_startup_ip(self, ip_address: str, ssid: str):
        if not self.epd_enabled:
            logger.debug("Skipping EPD startup display (EPD disabled)")
            return

        try:
            image = Image.new('1', (self.shared_data.width, self.shared_data.height), 255)
            draw = ImageDraw.Draw(image)

            draw.text((self.px(37), self.py(5)), "BJORN", font=self.shared_data.font_viking, fill=0)

            message = f"Awakening...\nIP: {ip_address}"
            draw.text(
                (self.px(10), int(self.shared_data.height / 2)),
                message, font=self.shared_data.font_arial14, fill=0
            )

            draw.text(
                (self.px(10), int(self.shared_data.height / 2) + 40),
                f"SSID: {ssid}", font=self.shared_data.font_arial9, fill=0
            )

            draw.rectangle((0, 1, self.shared_data.width - 1, self.shared_data.height - 1), outline=0)

            if self.screen_reversed:
                image = image.transpose(Image.ROTATE_180)

            image = self._pad_for_v2(image)

            self.shared_data.epd.display_partial(image)
            if self.shared_data.double_partial_refresh:
                self.shared_data.epd.display_partial(image)

            logger.info(f"Displayed startup IP: {ip_address}, SSID: {ssid}")

        except Exception as e:
            logger.error(f"Error displaying startup IP: {e}")

    def schedule_stats_update(self):
        while not self.shared_data.display_should_exit:
            try:
                self.update_stats_from_db()
                time.sleep(self.shared_data.shared_update_interval)
            except Exception as e:
                logger.error(f"Error in stats update: {e}")
                time.sleep(self.shared_data.shared_update_interval)
                continue

    def update_stats_from_db(self):
        """Update statistics with timeout protection"""
        acquired = self.semaphore.acquire(timeout=self.SEMAPHORE_TIMEOUT)
        if not acquired:
            logger.warning("Failed to acquire semaphore for stats update - skipping")
            return

        try:
            stats = self.shared_data.db.get_display_stats()

            self.shared_data.port_count = stats.get('total_open_ports', 0)
            self.shared_data.target_count = stats.get('alive_hosts_count', 0)
            self.shared_data.network_kb_count = stats.get('all_known_hosts_count', 0)
            self.shared_data.vuln_count = stats.get('vulnerabilities_count', 0)
            self.shared_data.cred_count = stats.get('credentials_count', 0)
            self.shared_data.attacks_count = stats.get('actions_count', 0)
            self.shared_data.zombie_count = stats.get('zombie_count', 0)

            self.current_ip, self.ssid = self.get_network_info()
            self.shared_data.data_count = self.get_data_count()
            self.shared_data.update_stats()

            connections = self.check_all_connections()
            self.shared_data.wifi_connected = connections['wifi']
            self.shared_data.usb_active = connections['usb']
            self.shared_data.bluetooth_active = connections['bluetooth']
            self.shared_data.ethernet_active = connections['ethernet']

            self.shared_data.manual_mode = self.is_manual_mode()
            self.manual_mode_txt = "M" if self.shared_data.manual_mode else "A"

            self.show_ip_on_screen = self.shared_data.showiponscreen
            self.show_ssid_on_screen = self.shared_data.showssidonscreen
            self.bjorn_name = self.shared_data.bjorn_name

            if self.bjorn_name != self.previous_bjorn_name:
                self.calculate_font_to_fit()
                self.previous_bjorn_name = self.bjorn_name

        except Exception as e:
            logger.error(f"Error updating stats from DB: {e}")
        finally:
            self.semaphore.release()

    def update_main_image(self):
        while not self.shared_data.display_should_exit:
            try:
                self.shared_data.update_image_randomizer()
                if self.shared_data.imagegen:
                    self.main_image = self.shared_data.imagegen
                else:
                    logger.debug("No image generated for current status")

                time.sleep(
                    random.uniform(
                        self.shared_data.image_display_delaymin,
                        self.shared_data.image_display_delaymax
                    )
                )

            except Exception as e:
                logger.error(f"Error in update_main_image: {e}")
                time.sleep(5)

    def _as_list(self, value: Any, default: Optional[List] = None) -> List:
        if default is None:
            default = []

        try:
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    obj = json.loads(value)
                    if isinstance(obj, list):
                        return obj
                except:
                    pass
                return [x.strip() for x in value.split(",") if x.strip()]
            return list(value) if value is not None else default
        except:
            return default

    def _as_str(self, value: Any, default: str = "") -> str:
        if isinstance(value, str):
            return value
        try:
            return str(value) if value is not None else default
        except:
            return default

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except:
            return default

    def get_frise_position(self) -> Tuple[int, int]:
        display_type = self.config.get("epd_type", "default")

        if display_type == "epd2in7":
            x = self._as_int(getattr(self.shared_data, "frise_epd2in7_x", 50), 50)
            y = self._as_int(getattr(self.shared_data, "frise_epd2in7_y", 160), 160)
        else:
            x = self._as_int(getattr(self.shared_data, "frise_default_x", 0), 0)
            y = self._as_int(getattr(self.shared_data, "frise_default_y", 160), 160)

        return self.px(x), self.py(y)

    def display_comment(self, status: str):
        params = getattr(self.shared_data, "comment_params", {}) or {}
        comment = self.comment_ai.get_comment(status, params=params)
        if comment:
            self.shared_data.bjorn_says = comment
            self.shared_data.bjorn_status_text = self.shared_data.bjorn_orch_status

    def clear_screen(self):
        if self.epd_enabled:
            try:
                self.shared_data.epd.clear()
            except Exception as e:
                logger.error(f"Error clearing EPD: {e}")
        else:
            logger.debug("Skipping EPD clear (EPD disabled)")

    # ========================================================================
    # MAIN DISPLAY LOOP WITH ROBUST ERROR HANDLING
    # ========================================================================

    def run(self):
        """Main display rendering loop with active watchdog and recovery"""
        self.manual_mode_txt = ""

        try:
            while not self.shared_data.display_should_exit:
                iteration_start = time.time()

                try:
                    success = self._execute_display_update_with_timeout()

                    if success:
                        self.last_successful_update = time.time()
                        self.consecutive_failures = 0
                        self.total_updates += 1
                    else:
                        self.consecutive_failures += 1
                        self.failed_updates += 1
                        logger.warning(f"Display update failed ({self.consecutive_failures} consecutive failures)")

                    # Watchdog & recovery
                    time_since_success = time.time() - self.last_successful_update
                    if (self._upd_stuck_since and (time.time() - self._upd_stuck_since) > self.STUCK_RECOVERY_S) \
                       or self.consecutive_failures >= 3:
                        logger.error("Watchdog: EPD appears stuck or repeated failures - attempting recovery")
                        self._attempt_recovery()

                    # Circuit breaker: disable EPD after many failures
                    if self.epd_enabled and self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        logger.error("Too many consecutive display failures - disabling EPD (graceful degradation)")
                        self.epd_enabled = False  # web-only mode until next recovery success
                        # Do not reference self.shared_data.epd when disabled

                    # Health logs (légers)
                    if self.total_updates % 100 == 0 and self.total_updates > 0:
                        success_rate = ((self.total_updates - self.failed_updates) / self.total_updates) * 100
                        try:
                            fds = len(os.listdir(f"/proc/{os.getpid()}/fd"))
                        except Exception:
                            fds = -1
                        # logger.info(f"Display stats: {self.total_updates} updates, {success_rate:.1f}% success "
                        #             f"(threads={threading.active_count()}, fds={fds})")

                    # Delay before next update
                    time.sleep(self.shared_data.screen_delay)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error in display loop: {e}")
                    logger.error(traceback.format_exc())
                    time.sleep(5)

        finally:
            self._cleanup_display()

    def _execute_display_update_with_timeout(self) -> bool:
        """
        Lance au plus un worker d’update. Si un précédent est encore vivant,
        on ne relance pas (évite l’empilement).
        """
        with self._upd_lock:
            if self._upd_thread and self._upd_thread.is_alive():
                logger.warning("Previous EPD update still running; skipping this cycle")
                # marquer comme potentiellement bloqué
                if self._upd_stuck_since is None:
                    self._upd_stuck_since = time.time()
                return False

            # démarrer un nouveau worker
            self._upd_thread = threading.Thread(
                target=self._do_display_update, daemon=True, name="EPDUpdate"
            )
            self._upd_thread.start()

        # Attente bornée
        self._upd_thread.join(timeout=self.LOOP_ITERATION_TIMEOUT)
        if self._upd_thread.is_alive():
            logger.error(f"Display update timed out after {self.LOOP_ITERATION_TIMEOUT}s")
            if self._upd_stuck_since is None:
                self._upd_stuck_since = time.time()
            return False

        # terminé
        self._upd_stuck_since = None
        return True

    def _do_display_update(self):
        """Perform the actual display update (single worker)"""
        try:
            # Full refresh (si activé) AVANT rendu
            if self.epd_enabled and self.fullrefresh_activated:
                now = time.time()
                if now - self._last_full_refresh >= self.fullrefresh_delay:
                    try:
                        self.shared_data.epd.clear()
                        logger.info("Display cleared for full refresh (in worker)")
                        self._last_full_refresh = now
                    except Exception as e:
                        logger.error(f"Full refresh failed: {e}")
                        # On continue en essayant l’update partiel

            if self.epd_enabled:
                # Init du mode partiel
                try:
                    self.shared_data.epd.init_partial_update()
                except Exception as e:
                    logger.error(f"EPD init_partial_update failed: {e}")
                    raise

            self.display_comment(self.shared_data.bjorn_orch_status)

            image = self._render_display()

            if self.screen_reversed:
                image = image.transpose(Image.ROTATE_180)

            image = self._pad_for_v2(image)

            if self.epd_enabled:
                try:
                    self.shared_data.epd.display_partial(image)
                    if self.shared_data.double_partial_refresh:
                        self.shared_data.epd.display_partial(image)
                except Exception as e:
                    logger.error(f"EPD display_partial failed: {e}")
                    raise

            # Toujours sauver le screenshot (web)
            self._save_screenshot(image)

            # logger.debug("Display update completed successfully")

        except Exception as e:
            logger.error(f"Error in display update: {e}")
            logger.error(traceback.format_exc())
            # laisser l’exception remonter pour le comptage des échecs
            raise

    def _attempt_recovery(self):
        """Attempt to recover from display failures"""
        current_time = time.time()

        # Enforce cooldown between recovery attempts
        if current_time - self.last_recovery_attempt < self.RECOVERY_COOLDOWN:
            time_remaining = self.RECOVERY_COOLDOWN - (current_time - self.last_recovery_attempt)
            logger.warning(f"Recovery cooldown active ({time_remaining:.1f}s remaining)")
            return

        self.last_recovery_attempt = current_time
        logger.warning("=== Attempting display recovery ===")

        try:
            if self.epd_enabled:
                # Try hard reset with timeout
                logger.info("Performing EPD hard reset...")
                reset_thread = threading.Thread(
                    target=self.shared_data.epd.hard_reset,
                    daemon=True
                )
                reset_thread.start()
                reset_thread.join(timeout=15.0)

                if reset_thread.is_alive():
                    logger.error("Hard reset timed out - recovery failed")
                else:
                    logger.info("Hard reset completed")
                    self.consecutive_failures = 0
                    time.sleep(2)  # Let hardware stabilize
            else:
                # Si EPD désactivé, tenter une réactivation soft
                try:
                    self.shared_data.epd.init_full_update()
                    self.epd_enabled = True
                    logger.info("EPD re-enabled after recovery attempt")
                    self.consecutive_failures = 0
                except Exception as e:
                    logger.error(f"Re-enable EPD failed: {e}")

        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            logger.error(traceback.format_exc())

    def _render_display(self) -> Image.Image:
        """Render complete display image"""
        image = Image.new('1', (self.shared_data.width, self.shared_data.height), 255)
        draw = ImageDraw.Draw(image)

        draw.text((self.px(37), self.py(5)), self.bjorn_name, font=self.font_to_use, fill=0)
        draw.text((self.px(105), self.py(171)), self.manual_mode_txt, font=self.shared_data.font_arial14, fill=0)

        self._draw_connection_icons(image)
        self._draw_battery_status(image)
        self._draw_statistics(image, draw)

        self.shared_data.update_bjorn_status()
        image.paste(self.shared_data.bjorn_status_image, (self.px(3), self.py(60)))

        self._draw_status_text(draw)
        self._draw_decorations(image, draw)
        self._draw_comment_text(draw)

        if hasattr(self, "main_image") and self.main_image is not None:
            self.shared_data.bjorn_character = self.main_image
            image.paste(self.main_image, (self.shared_data.x_center1, self.shared_data.y_bottom1 - 1))

        return image

    def _draw_connection_icons(self, image: Image.Image):
        wifi_width = self.px(16)
        bluetooth_width = self.px(9)
        usb_width = self.px(9)
        ethernet_width = self.px(12)

        start_x = self.px(3)
        spacing = self.px(6)

        active_icons = []
        if self.shared_data.wifi_connected:
            active_icons.append(('wifi', self.shared_data.wifi, wifi_width))
        if self.shared_data.bluetooth_active:
            active_icons.append(('bluetooth', self.shared_data.bluetooth, bluetooth_width))
        if self.shared_data.usb_active:
            active_icons.append(('usb', self.shared_data.usb, usb_width))
        if self.shared_data.ethernet_active:
            active_icons.append(('ethernet', self.shared_data.ethernet, ethernet_width))

        current_x = start_x
        for i, (name, icon, width) in enumerate(active_icons):
            if len(active_icons) == 4 and i == 3:
                image.paste(icon, (self.px(92), self.py(4)))
            else:
                y_pos = self.py(3) if name == 'wifi' else self.py(4)
                image.paste(icon, (int(current_x), y_pos))
                current_x += width + spacing

    def _draw_battery_status(self, image: Image.Image):
        battery_pos = (self.px(110), self.py(3))
        battery_status = self.shared_data.battery_status

        if battery_status == 101:
            image.paste(self.shared_data.battery_charging, battery_pos)
        else:
            battery_icons = {
                (0, 24): self.shared_data.battery0,
                (25, 49): self.shared_data.battery25,
                (50, 74): self.shared_data.battery50,
                (75, 89): self.shared_data.battery75,
                (90, 100): self.shared_data.battery100,
            }

            for (lower, upper), icon in battery_icons.items():
                if lower <= battery_status <= upper:
                    image.paste(icon, battery_pos)
                    break

    def _draw_statistics(self, image: Image.Image, draw: ImageDraw.Draw):
        stats = [
            (self.shared_data.target, (self.px(8), self.py(22)),
             (self.px(28), self.py(22)), str(self.shared_data.target_count)),
            (self.shared_data.port, (self.px(47), self.py(22)),
             (self.px(67), self.py(22)), str(self.shared_data.port_count)),
            (self.shared_data.vuln, (self.px(86), self.py(22)),
             (self.px(106), self.py(22)), str(self.shared_data.vuln_count)),
            (self.shared_data.cred, (self.px(8), self.py(41)),
             (self.px(28), self.py(41)), str(self.shared_data.cred_count)),
            (self.shared_data.money, (self.px(3), self.py(172)),
             (self.px(3), self.py(192)), str(self.shared_data.coin_count)),
            (self.shared_data.level, (self.px(2), self.py(217)),
             (self.px(4), self.py(237)), str(self.shared_data.level_count)),
            (self.shared_data.zombie, (self.px(47), self.py(41)),
             (self.px(67), self.py(41)), str(self.shared_data.zombie_count)),
            (self.shared_data.networkkb, (self.px(102), self.py(190)),
             (self.px(102), self.py(208)), str(self.shared_data.network_kb_count)),
            (self.shared_data.data, (self.px(86), self.py(41)),
             (self.px(106), self.py(41)), str(self.shared_data.data_count)),
            (self.shared_data.attacks, (self.px(100), self.py(218)),
             (self.px(102), self.py(237)), str(self.shared_data.attacks_count)),
        ]

        for img, img_pos, text_pos, text in stats:
            if img is not None:
                image.paste(img, img_pos)
            draw.text(text_pos, text, font=self.shared_data.font_arial9, fill=0)

    def _draw_status_text(self, draw: ImageDraw.Draw):
        if self.show_ip_on_screen:
            draw.text((self.px(35), self.py(60)), self.current_ip,
                      font=self.shared_data.font_arial9, fill=0)
            draw.text((self.px(35), self.py(69)), self.shared_data.bjorn_status_text,
                      font=self.shared_data.font_arial9, fill=0)
            draw.text((self.px(35), self.py(78)), self.shared_data.bjorn_status_text2,
                      font=self.shared_data.font_arial9, fill=0)
            draw.text((self.px(102), self.py(78)), self.shared_data.bjorn_progress,
                      font=self.shared_data.font_arial9, fill=0)
            draw.line((1, self.py(89), self.shared_data.width - 1, self.py(89)), fill=0)
        else:
            draw.text((self.px(35), self.py(65)), self.shared_data.bjorn_status_text,
                      font=self.shared_data.font_arial9, fill=0)
            draw.text((self.px(35), self.py(75)), self.shared_data.bjorn_status_text2,
                      font=self.shared_data.font_arial9, fill=0)
            draw.text((self.px(102), self.py(75)), self.shared_data.bjorn_progress,
                      font=self.shared_data.font_arial9, fill=0)
            draw.line((1, self.py(87), self.shared_data.width - 1, self.py(87)), fill=0)

    def _draw_decorations(self, image: Image.Image, draw: ImageDraw.Draw):
        if self.show_ssid_on_screen:
            draw.text((self.px(3), self.py(160)), self.ssid,
                      font=self.shared_data.font_arial9, fill=0)
            draw.line((0, self.py(170), self.shared_data.width, self.py(170)), fill=0)
        else:
            frise_x, frise_y = self.get_frise_position()
            if self.shared_data.frise is not None:
                image.paste(self.shared_data.frise, (frise_x, frise_y))

        draw.rectangle((0, 0, self.shared_data.width - 1, self.shared_data.height - 1), outline=0)
        draw.line((0, self.py(20), self.shared_data.width, self.py(20)), fill=0)
        draw.line((0, self.py(59), self.shared_data.width, self.py(59)), fill=0)

    def _draw_comment_text(self, draw: ImageDraw.Draw):
        # Cache key for the layout
        key = (self.shared_data.bjorn_says, self.shared_data.width, id(self.shared_data.font_arialbold))
        now = time.time()
        if (
            self._comment_layout_cache["key"] != key or
            (now - self._comment_layout_cache["ts"]) >= self._comment_layout_min_interval
        ):
            lines = self.shared_data.wrap_text(
                self.shared_data.bjorn_says,
                self.shared_data.font_arialbold,
                self.shared_data.width - 4
            )
            self._comment_layout_cache = {"key": key, "lines": lines, "ts": now}
        else:
            lines = self._comment_layout_cache["lines"]

        y_text = self.py(92)
        font = self.shared_data.font_arialbold
        bbox = font.getbbox('Aj')
        font_height = (bbox[3] - bbox[1]) if bbox else font.size

        for line in lines:
            draw.text((self.px(4), y_text), line,
                      font=font, fill=0)
            y_text += font_height + self.shared_data.line_spacing

    def _save_screenshot(self, image: Image.Image):
        try:
            out_img = image
            if self.web_screen_reversed:
                out_img = out_img.transpose(Image.ROTATE_180)

            screenshot_path = os.path.join(self.shared_data.web_dir, "screen.png")
            with open(screenshot_path, 'wb') as img_file:
                out_img.save(img_file)
                img_file.flush()
                os.fsync(img_file.fileno())

        except Exception as e:
            logger.error(f"Error saving screenshot: {e}")

    def _cleanup_display(self):
        try:
            if self.epd_enabled:
                self.shared_data.epd.init_full_update()
                blank_image = Image.new('1', (self.shared_data.width, self.shared_data.height), 255)
                blank_image = self._pad_for_v2(blank_image)
                self.shared_data.epd.display_partial(blank_image)
                if self.shared_data.double_partial_refresh:
                    self.shared_data.epd.display_partial(blank_image)
                logger.info("EPD display cleared and device exited")
                try:
                    self.shared_data.epd.sleep()
                except Exception:
                    pass
            else:
                logger.info("Display thread exited (EPD was disabled)")
        except Exception as e:
            logger.error(f"Error clearing display: {e}")


def handle_exit_display(signum, frame, display_thread=None):
    """Signal handler to cleanly exit display threads"""
    shared_data.display_should_exit = True
    logger.info(f"Exit signal {signum} received, shutting down display...")

    try:
        if display_thread:
            display_thread.join(timeout=10.0)
            if display_thread.is_alive():
                logger.warning("Display thread did not exit cleanly")
            else:
                logger.info("Display thread finished cleanly.")
    except Exception as e:
        logger.error(f"Error while closing the display: {e}")

    sys.exit(0)