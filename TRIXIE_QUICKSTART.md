# Debian Trixie - Quick Start Guide

## TL;DR

✅ **Bjorn now works on Debian Trixie (13) out of the box**

The installer automatically detects your Debian version and installs the correct dependencies.

## Installation on Trixie

```bash
wget https://raw.githubusercontent.com/infinition/Bjorn/refs/heads/main/install_bjorn.sh
sudo chmod +x install_bjorn.sh && sudo ./install_bjorn.sh
```

That's it! The installer handles everything.

## What Changed?

| Before | After |
|--------|-------|
| ❌ Failed on Trixie due to missing `libatlas-base-dev` | ✅ Works on both Bookworm and Trixie |
| Required manual intervention | Fully automatic |
| Included unused `numpy` dependency | Streamlined dependencies |

## Key Points

1. **libatlas-base-dev is OPTIONAL**: Only installed on Debian 12 and older
2. **OpenBLAS is used**: Works on all Debian versions
3. **No code changes**: Only build dependencies were updated
4. **Fully backward compatible**: Works on Bookworm exactly as before

## If You See Warnings

During installation on Trixie, you might see:
```
Package libatlas-base-dev is not available
```

**This is EXPECTED and SAFE** - OpenBLAS provides everything needed.

## Verify Installation

```bash
# Check all Python modules work
python3 -c "import pandas; import PIL; import paramiko; print('✓ All imports successful')"

# Check BLAS backend (should show OpenBLAS)
python3 -c "import numpy; numpy.show_config()" | grep -i openblas
```

## Troubleshooting

### Installation fails with Python errors

```bash
# Ensure OpenBLAS is installed
sudo apt install -y libopenblas-dev libopenblas0

# Retry requirements installation
cd /home/bjorn/Bjorn
pip3 install -r requirements.txt --break-system-packages --force-reinstall
```

### Version warning during installation

If you see warnings about Debian version 13, just press `y` to continue. The installer is Trixie-aware.

## More Information

- **Full migration guide**: See [DEBIAN_TRIXIE_MIGRATION.md](DEBIAN_TRIXIE_MIGRATION.md)
- **Complete changes**: See [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)
- **General installation**: See [INSTALL.md](INSTALL.md)

## Support

- Compatible with: Debian 12 (Bookworm), Debian 13 (Trixie), and newer
- Tested on: Raspberry Pi Zero W and W2
- Report issues: GitHub Issues with output of `cat /etc/os-release`
