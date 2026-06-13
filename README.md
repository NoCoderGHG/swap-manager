# SWAP File Manager

A GTK3 desktop app for managing Linux swap files — create, activate, deactivate, resize and delete swap files, and adjust swappiness, all without touching the terminal.

![Status: Linux-only](https://img.shields.io/badge/platform-Linux-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Swap file management** — create, activate, deactivate, resize and delete swap files
- **fstab integration** — optionally add or remove entries from `/etc/fstab` automatically
- **Swappiness control** — adjust the kernel's swap tendency via a slider (0–100)
- **System overview** — live memory and swap usage via `free` and `swapon`
- **Multi-language** — English and German, switchable in the app with system language auto-detection

## Requirements

System packages (Debian/Ubuntu/Mint):

```
sudo apt install python3-gi gir1.2-gtk-3.0
```

Fedora:
```
sudo dnf install python3-gobject gtk3
```

Arch:
```
sudo pacman -S python-gobject gtk3
```

`sudo` access is required for swap operations (`swapon`, `swapoff`, `mkswap`, `dd`).

## Installation

```
git clone https://github.com/NoCoderGHG/swap-manager.git
cd swap-manager
python3 swap_manager.py
```

No pip dependencies. No virtual environment needed.

## Configuration

Language preference is stored in `~/.config/swap-manager/config.json`.

## License

MIT — see [LICENSE](LICENSE).
