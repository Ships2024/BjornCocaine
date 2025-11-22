# Debian Trixie (Testing) Migration Guide

## Overview

This document explains the changes made to support Debian Trixie (version 13) and newer versions of Raspberry Pi OS.

## Key Changes

### 1. ATLAS to OpenBLAS Migration

**Problem**: Debian Trixie removed `libatlas-base-dev` package in favor of `libopenblas-dev`.

**Solution**: 
- Removed `libatlas-base-dev` as a hard dependency
- The installer now conditionally installs `libatlas-base-dev` only on Debian Bookworm (12) and older
- Debian Trixie (13+) uses only `libopenblas-dev` which is already in the dependency list

### 2. NumPy Dependency Removed

**Problem**: NumPy was listed in `requirements.txt` but never imported or used in the codebase.

**Solution**: 
- Removed `numpy==2.1.3` from requirements.txt
- Pandas will install its own optimized numpy dependency automatically
- This reduces installation size and complexity

### 3. Updated Version Checks

The installer now recognizes both:
- Debian 12 (Bookworm) - stable, tested
- Debian 13 (Trixie) - testing, supported

## Installation on Debian Trixie

### Automatic Installation

```bash
wget https://raw.githubusercontent.com/infinition/Bjorn/refs/heads/main/install_bjorn.sh
sudo chmod +x install_bjorn.sh && sudo ./install_bjorn.sh
```

The installer will automatically detect Trixie and skip `libatlas-base-dev`.

### Manual Installation on Trixie

If you're following the manual installation guide in INSTALL.md:

```bash
# The libatlas-base-dev line will fail gracefully on Trixie - this is expected
sudo apt install -y libatlas-base-dev 2>/dev/null || echo "libatlas-base-dev not available (OK on Trixie)"
```

The error is handled and won't stop the installation.

## Technical Details

### Why This Change Was Needed

1. **Package availability**: Debian Trixie transitioned from ATLAS to OpenBLAS for BLAS/LAPACK operations
2. **Performance**: OpenBLAS provides better performance on modern ARM processors
3. **Maintenance**: OpenBLAS is actively maintained while ATLAS development has slowed

### Dependencies That Use BLAS Libraries

Only **pandas** in this project requires BLAS libraries for numerical operations:
- On Debian Bookworm: Uses either ATLAS or OpenBLAS
- On Debian Trixie: Uses OpenBLAS only

### Compatibility Matrix

| Debian Version | ATLAS Support | OpenBLAS Support | Bjorn Status |
|---------------|---------------|------------------|--------------|
| 11 (Bullseye) | ✓ | ✓ | Compatible |
| 12 (Bookworm) | ✓ | ✓ | Fully Tested |
| 13 (Trixie)   | ✗ | ✓ | Supported |
| 14+ (Future)  | ✗ | ✓ | Should work |

## Troubleshooting

### Issue: "Package libatlas-base-dev is not available"

**Status**: This is expected on Debian Trixie and newer.

**Solution**: The installer handles this automatically. OpenBLAS provides all needed functionality.

### Issue: Pandas installation fails

**On Trixie**, if pandas fails to install:

```bash
# Ensure OpenBLAS is installed
sudo apt install -y libopenblas-dev libopenblas0

# Reinstall pandas
pip3 install --no-cache-dir pandas --break-system-packages
```

### Issue: Version warnings during installation

If you see warnings about Debian version 13, you can safely proceed. The installer will work correctly.

## Testing on Trixie

To verify the installation works correctly on Trixie:

```bash
# Check Python can import all required modules
python3 -c "import pandas; import PIL; import paramiko; print('All imports successful')"

# Verify OpenBLAS is being used
python3 -c "import numpy; numpy.show_config()"
```

## Future Compatibility

These changes ensure Bjorn will continue to work on:
- Current stable Raspberry Pi OS (Bookworm)
- Future Raspberry Pi OS releases based on Trixie
- Debian-based distributions that have dropped ATLAS support

## For Developers

When adding new numeric computation libraries:
- Do NOT add `libatlas-base-dev` as a dependency
- Use `libopenblas-dev` which works across all supported versions
- Test on both Bookworm and Trixie when possible

## References

- [Debian Trixie Release Notes](https://www.debian.org/releases/testing/)
- [OpenBLAS Project](https://www.openblas.net/)
- [NumPy BLAS/LAPACK Support](https://numpy.org/install/)
