# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Bjorn is an autonomous network security tool designed for Raspberry Pi that performs network scanning, vulnerability assessment, and offensive security operations. It features a "Tamagotchi-like" interface displayed on a 2.13-inch e-Paper HAT and provides a web interface for monitoring and control.

**Target Platform**: Raspberry Pi Zero W/W2 (32-bit or 64-bit)
**Primary Use**: Educational penetration testing and network security assessment
**Language**: Python 3.12+
**Supported OS**: Debian 12 (Bookworm), Debian 13 (Trixie), and newer

## Development Commands

### Running Bjorn

```bash
# Manual start (ensure service is stopped first)
sudo systemctl stop bjorn.service
sudo python Bjorn.py

# Service management
sudo systemctl start bjorn.service
sudo systemctl stop bjorn.service
sudo systemctl status bjorn.service
sudo journalctl -u bjorn.service  # View logs
```

### Linting and Code Quality

```bash
# Run pylint on Python files
pylint Bjorn.py
pylint orchestrator.py
pylint actions/*.py

# The project uses a custom .pylintrc configuration with:
# - snake_case naming for functions/variables
# - PascalCase for classes
# - Max line length: 100 characters
# - Fail-under score: 8.0
```

### Fresh Start / Reset

```bash
# Clean all generated data and caches (use with caution)
sudo rm -rf /home/bjorn/Bjorn/config/*.json \
    /home/bjorn/Bjorn/data/*.csv \
    /home/bjorn/Bjorn/data/*.log \
    /home/bjorn/Bjorn/data/output/data_stolen/* \
    /home/bjorn/Bjorn/data/output/crackedpwd/* \
    /home/bjorn/Bjorn/data/output/scan_results/* \
    /home/bjorn/Bjorn/__pycache__ \
    /home/bjorn/Bjorn/actions/__pycache__ \
    /home/bjorn/Bjorn/data/logs/* \
    /home/bjorn/Bjorn/data/output/vulnerabilities/*
```

## Architecture

### Core Components

**Bjorn.py** - Main entry point and application coordinator
- Initializes all subsystems (display, web server, orchestrator)
- Manages Wi-Fi connectivity checks
- Handles graceful shutdown via signal handlers
- Controls automatic vs manual operation modes

**orchestrator.py** - Heuristic brain of Bjorn
- Loads and executes actions from `actions.json` dynamically
- Manages action dependencies (parent-child relationships)
- Handles retry logic for failed and successful actions
- Uses semaphores to limit concurrent action threads (default: 10)
- Coordinates network scanning → vulnerability scanning → attack → data exfiltration pipeline

**shared.py** - Shared data and configuration manager
- Singleton pattern providing centralized configuration via `SharedData` class
- Manages all filesystem paths (config, data, logs, output directories)
- Loads/saves configuration from `shared_config.json`
- Handles e-Paper display initialization and resources
- Provides utility methods for CSV operations and status updates

**display.py** - e-Paper HAT interface manager
- Updates the 2.13-inch e-Paper display with real-time status
- Displays Bjorn character, comments, network stats, and vulnerabilities
- Supports multiple e-Paper HAT versions (V1-V4)
- Includes ghosting removal optimization

**webapp.py** - Web interface server
- Runs HTTP server on port 8000 (auto-increments if occupied)
- Serves gzipped HTML/CSS/JS for efficiency
- Provides REST API for configuration, network data, logs, and system control
- Enables remote monitoring and manual attack execution

### Data Flow

1. **Network Discovery**: `actions/scanning.py` scans network, identifies live hosts and open ports
2. **Knowledge Base Update**: Results stored in `data/netkb.csv` (network knowledge base)
3. **Orchestration**: `orchestrator.py` reads netkb.csv and determines which actions to execute
4. **Action Execution**: Actions are loaded dynamically from `actions/` directory based on `config/actions.json`
5. **Results Storage**: Credentials → `data/output/crackedpwd/`, Files → `data/output/data_stolen/`, Vulnerabilities → `data/output/vulnerabilities/`
6. **Display Update**: Status reflected on e-Paper display and web interface in real-time

### Action System

Actions are modular Python files in `actions/` directory. Each action must implement:

```python
class ActionName:
    def __init__(self, shared_data):
        # Initialize with shared data
        
    def execute(self, ip, port, row, status_key):
        # Execute action and return 'success' or 'failed'
```

**Action Types**:
- **Scanners**: `scanning.py` (network), `nmap_vuln_scanner.py` (vulnerabilities)
- **Connectors**: `ssh_connector.py`, `ftp_connector.py`, `smb_connector.py`, `rdp_connector.py`, `telnet_connector.py`, `sql_connector.py` (brute-force attacks)
- **Data Exfiltration**: `steal_files_*.py`, `steal_data_sql.py`

**Action Configuration** (`config/actions.json`):
- `b_module`: Python module name
- `b_class`: Class name to instantiate
- `b_port`: Target port (0 for standalone actions)
- `b_parent`: Parent action dependency (null if independent)

### Key Data Files

**data/netkb.csv** - Network knowledge base (central data structure)
- Columns: MAC Address, IPs, Hostnames, Alive (0/1), Ports, [Action Status Columns]
- Action status format: `success_YYYYMMDD_HHMMSS` or `failed_YYYYMMDD_HHMMSS`
- Updated after each scan and action execution

**data/livestatus.csv** - Real-time statistics for display
- Total known hosts, alive hosts, open ports, vulnerabilities count

**config/shared_config.json** - Runtime configuration
- Scan intervals, retry delays, port lists, blacklists
- E-Paper display settings (`epd_type`: epd2in13, epd2in13_V2, epd2in13_V3, epd2in13_V4)
- Manual mode, debug settings, web server options

## Important Patterns

### Threading Model
- Main thread: Bjorn instance, monitors Wi-Fi and coordinates
- Display thread: Continuous e-Paper display updates
- Web server thread: HTTP server for web interface
- Orchestrator thread: Action coordination and execution
- Action threads: Individual attack/scan operations (limited by semaphore)

### Retry Logic
Orchestrator implements time-based retry delays:
- **Failed actions**: Retry after `failed_retry_delay` seconds (default: 600s)
- **Successful actions**: Optionally retry after `success_retry_delay` seconds (default: 900s) if `retry_success_actions` is enabled
- Timestamps are embedded in netkb.csv action status fields

### Configuration Access
Always access configuration through `shared_data` instance:
```python
from init_shared import shared_data
scan_interval = shared_data.scan_interval
shared_data.config['manual_mode'] = True
shared_data.save_config()  # Persist changes
```

### Logging
Use the custom Logger class from `logger.py`:
```python
from logger import Logger
logger = Logger(name="module_name.py", level=logging.DEBUG)
logger.info("Message")
logger.warning("Warning")
logger.error("Error")
```

## Platform-Specific Notes

### Raspberry Pi Assumptions
- Default installation path: `/home/bjorn/Bjorn`
- Username and hostname: `bjorn`
- USB gadget networking on `usb0` interface (172.20.2.1)
- Systemd service: `bjorn.service`
- E-Paper HAT connected to GPIO pins (SPI/I2C enabled)

### Debian Version Compatibility
- **Bookworm (12)**: Fully tested and supported
- **Trixie (13+)**: Supported with OpenBLAS instead of ATLAS
- The installer automatically detects the Debian version and installs appropriate BLAS libraries
- NumPy is not directly required (pandas installs it as a dependency)

### File Descriptor Limits
System is configured with high file descriptor limits (65535) due to concurrent network operations. If adding features that open many files/sockets, be mindful of this constraint.

### Network Operations
- Uses `nmap` for port scanning (command-line tool must be installed)
- Network interfaces accessed via `nmcli` for Wi-Fi status
- MAC address retrieval from `/sys/class/net/wlan0/address` or `/sys/class/net/eth0/address`

## Security Considerations

This is an offensive security tool designed for **educational purposes and authorized testing only**.

When contributing:
- Do not weaken existing credential protections
- Ensure new actions respect blacklist configurations
- Test actions in isolated environments
- Document potential impacts in action docstrings
- Follow responsible disclosure for any discovered vulnerabilities in Bjorn itself

## Adding New Actions

1. Create `actions/your_action.py` with required class structure
2. Define module-level variables: `b_class`, `b_module`, `b_status`, `b_port`, `b_parent`
3. Implement `__init__(self, shared_data)` and `execute(self, ip, port, row, status_key)`
4. Action will be auto-discovered and added to `config/actions.json` on next run
5. Return `'success'` or `'failed'` from execute method to control retry behavior

## Web Interface

Access at `http://[device-ip]:8000`

Key endpoints:
- `/` - Main dashboard
- `/config.html` - Configuration management
- `/netkb.html` - Network knowledge base viewer
- `/credentials.html` - Captured credentials
- `/loot.html` - Exfiltrated files
- `/manual.html` - Manual attack execution

The web interface uses gzip compression for all responses to minimize bandwidth on resource-constrained Raspberry Pi.
