#!/usr/bin/env python3
"""
SWAP File Manager — GTK3 (PyGObject)
No pip installation required:
  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0
  Fedora:        sudo dnf install python3-gobject gtk3
  Arch:          sudo pacman -S python-gobject gtk3
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

import json
import locale
import os
import subprocess
import threading
from pathlib import Path

CONFIG_DIR  = Path.home() / ".config" / "swap-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
I18N_DIR    = Path(__file__).parent / "i18n"

SUPPORTED_LANGUAGES = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "tr": "Türkçe",
    "zh": "中文",
    "ja": "日本語",
}


DEFAULT_CONFIG = {"lang": "system"}


# ── Config & i18n ─────────────────────────────────────────────────────────────

def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def detect_system_lang():
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    if not loc:
        loc = os.environ.get("LANG", "")
    code = loc.lower().split("_")[0].split(".")[0]
    if code in SUPPORTED_LANGUAGES and (I18N_DIR / f"{code}.json").exists():
        return code
    return "de" if code == "de" else "en"


def resolve_lang(setting):
    if setting == "system":
        return detect_system_lang()
    return setting


def load_i18n(lang):
    en = {}
    en_path = I18N_DIR / "en.json"
    if en_path.exists():
        with open(en_path) as f:
            en = json.load(f)
    if lang == "en":
        return en
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return en
    with open(path) as f:
        strings = json.load(f)
    for k, v in en.items():
        strings.setdefault(k, v)
    return strings

def build_lang_options(strings):
    """Liste (code, label) fuer das Sprachmenue. Sprachen ohne eigene
    i18n-Datei werden mit "(EN)" markiert (Fallback auf Englisch)."""
    opts = [("system", t(strings, "lang_system")),
            ("de", t(strings, "lang_de")),
            ("en", t(strings, "lang_en"))]
    for code, name in SUPPORTED_LANGUAGES.items():
        if code in ("de", "en"):
            continue
        label = name if (I18N_DIR / f"{code}.json").exists() else f"{name} (EN)"
        opts.append((code, label))
    return opts


def build_lang_lists(strings):
    """Wie build_lang_options, aber als getrennte Listen (codes, labels)."""
    codes, items = [], []
    for code, label in build_lang_options(strings):
        codes.append(code)
        items.append(label)
    return codes, items



def t(strings, key, **kwargs):
    s = strings.get(key, key)
    for k, v in kwargs.items():
        s = s.replace("{" + k + "}", str(v))
    return s


# ── MenuButton helper ─────────────────────────────────────────────────────────

def make_menu_button(items, on_select, min_width=150):
    btn = Gtk.MenuButton()
    btn.set_size_request(min_width, -1)
    lbl = Gtk.Label(label=items[0] if items else "")
    btn.add(lbl)
    menu = Gtk.Menu()

    def build_menu(items, current=None):
        for child in menu.get_children():
            menu.remove(child)
        group = []
        active = current if current in items else (items[0] if items else None)
        for text in items:
            item = Gtk.RadioMenuItem.new_with_label(group, text)
            group = item.get_group()
            if text == active:
                item.set_active(True)
            def _on_activate(i, tx=text):
                if i.get_active():
                    lbl.set_text(tx)
                    on_select(tx)
            item.connect("activate", _on_activate)
            menu.append(item)
        menu.show_all()
        if active:
            lbl.set_text(active)

    build_menu(items)
    btn.set_popup(menu)

    def update(new_items, current=None):
        build_menu(new_items, current)

    return btn, lbl, update


# ── Helper functions ──────────────────────────────────────────────────────────

def run_cmd(cmd, use_sudo=False, timeout_msg="Timeout"):
    if use_sudo:
        cmd = ["sudo"] + cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, timeout_msg
    except FileNotFoundError as e:
        return False, str(e)


def get_swappiness():
    try:
        with open("/proc/sys/vm/swappiness") as f:
            return int(f.read().strip())
    except Exception:
        return -1


def get_swap_list():
    result = []
    ok, out = run_cmd(["swapon", "--raw", "--bytes"])
    if not ok or not out:
        return result
    lines = out.strip().split("\n")[1:]
    for line in lines:
        parts = line.split()
        if len(parts) >= 5 and parts[1] == "file":
            size = int(parts[2])
            used = int(parts[3])
            result.append({
                "path":     parts[0],
                "size_mb":  size / 1024 / 1024,
                "used_mb":  used / 1024 / 1024,
                "percent":  (used / size * 100) if size > 0 else 0,
                "prio":     parts[4],
            })
    return result


def get_mem_info(strings):
    ok,  out  = run_cmd(["free", "-h"])
    ok2, out2 = run_cmd(["swapon", "--show"])
    text  = t(strings, "mem_overview") + "\n"
    text += (out if ok else "n/a") + "\n"
    text += "\n" + t(strings, "active_swaps_header") + "\n"
    text += (out2 if ok2 and out2 else t(strings, "no_swaps_active"))
    return text


def msg(strings, parent, kind, title_key, text):
    icons = {
        "error":    Gtk.MessageType.ERROR,
        "question": Gtk.MessageType.QUESTION,
        "info":     Gtk.MessageType.INFO,
        "warning":  Gtk.MessageType.WARNING,
    }
    btns = Gtk.ButtonsType.YES_NO if kind == "question" else Gtk.ButtonsType.OK
    d = Gtk.MessageDialog(
        transient_for=parent, modal=True,
        message_type=icons.get(kind, Gtk.MessageType.INFO),
        buttons=btns,
        text=t(strings, title_key),
    )
    d.format_secondary_text(text)
    resp = d.run()
    d.destroy()
    return resp == Gtk.ResponseType.YES


# ── Dialog: Create swapfile ───────────────────────────────────────────────────

class CreateSwapDialog(Gtk.Dialog):
    def __init__(self, parent, strings):
        super().__init__(title=t(strings, "dlg_create_title"),
                         transient_for=parent, modal=True)
        self.strings = strings
        self.set_default_size(560, -1)
        self.add_buttons(t(strings, "btn_cancel"), Gtk.ResponseType.CANCEL)
        self._create_btn = self.add_button(t(strings, "btn_create"),
                                           Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self._pulse_timer = None

        grid = Gtk.Grid(column_spacing=10, row_spacing=10,
                        margin_top=16, margin_bottom=8,
                        margin_start=16, margin_end=16)
        self.get_content_area().add(grid)

        def lbl(k): return Gtk.Label(label=t(strings, k), xalign=1)

        # Path
        grid.attach(lbl("lbl_location"), 0, 0, 1, 1)
        path_box = Gtk.Box(spacing=4)
        self.path_entry = Gtk.Entry(text="/swapfile", hexpand=True)
        browse = Gtk.Button(label="…")
        browse.connect("clicked", self._browse)
        path_box.pack_start(self.path_entry, True, True, 0)
        path_box.pack_start(browse, False, False, 0)
        grid.attach(path_box, 1, 0, 1, 1)

        # Size
        grid.attach(lbl("lbl_size"), 0, 1, 1, 1)
        size_box = Gtk.Box(spacing=4)
        self.size_spin = Gtk.SpinButton.new_with_range(0.25, 128, 0.25)
        self.size_spin.set_value(4)
        self.size_spin.set_digits(2)
        size_box.pack_start(self.size_spin, True, True, 0)
        size_box.pack_start(Gtk.Label(label="GB"), False, False, 0)
        grid.attach(size_box, 1, 1, 1, 1)

        # Quick select
        grid.attach(lbl("lbl_quick"), 0, 2, 1, 1)
        quick_box = Gtk.Box(spacing=4)
        for gb in [1, 2, 4, 8, 16, 32]:
            b = Gtk.Button(label=f"{gb} GB")
            b.connect("clicked", lambda _, g=gb: self.size_spin.set_value(g))
            quick_box.pack_start(b, False, False, 0)
        grid.attach(quick_box, 1, 2, 1, 1)

        # Priority
        grid.attach(lbl("lbl_priority"), 0, 3, 1, 1)
        prio_box = Gtk.Box(spacing=4)
        self.prio_spin = Gtk.SpinButton.new_with_range(-1, 32767, 1)
        self.prio_spin.set_value(-1)
        prio_box.pack_start(self.prio_spin, False, False, 0)
        prio_box.pack_start(Gtk.Label(label=t(strings, "prio_default")),
                            False, False, 0)
        grid.attach(prio_box, 1, 3, 1, 1)

        # fstab
        self.fstab_check = Gtk.CheckButton(
            label=t(strings, "chk_fstab_autostart"))
        self.fstab_check.set_active(True)
        grid.attach(self.fstab_check, 0, 4, 2, 1)

        # Progress
        self.progress = Gtk.ProgressBar()
        self.progress.set_no_show_all(True)
        self.status_lbl = Gtk.Label(label="", xalign=0)
        self.status_lbl.set_no_show_all(True)
        grid.attach(self.progress, 0, 5, 2, 1)
        grid.attach(self.status_lbl, 0, 6, 2, 1)

        self.show_all()
        self._create_btn.connect("clicked", self._on_create)

    def _browse(self, _):
        fc = Gtk.FileChooserDialog(
            title=t(self.strings, "dlg_pick_location"),
            transient_for=self, modal=True,
            action=Gtk.FileChooserAction.SAVE)
        fc.add_buttons(t(self.strings, "btn_cancel"), Gtk.ResponseType.CANCEL,
                       t(self.strings, "btn_choose"), Gtk.ResponseType.OK)
        fc.set_current_folder("/")
        fc.set_current_name("swapfile")
        if fc.run() == Gtk.ResponseType.OK:
            self.path_entry.set_text(fc.get_filename())
        fc.destroy()

    def _set_busy(self, busy, status=""):
        self._create_btn.set_sensitive(not busy)
        self.progress.set_visible(busy)
        self.status_lbl.set_visible(busy)
        if busy:
            self.status_lbl.set_text(status)

    def _on_create(self, _):
        s = self.strings
        path = self.path_entry.get_text().strip()
        if not path:
            msg(s, self, "error", "error", t(s, "err_no_path")); return
        if os.path.exists(path):
            msg(s, self, "error", "error", t(s, "err_exists", path=path)); return

        size_mb = int(self.size_spin.get_value() * 1024)
        prio    = int(self.prio_spin.get_value())
        fstab   = self.fstab_check.get_active()

        self._set_busy(True, t(s, "status_creating_file"))
        self._pulse_timer = GLib.timeout_add(
            200, lambda: (self.progress.pulse(), True)[1])

        def worker():
            steps = [
                (["dd", "if=/dev/zero", f"of={path}", "bs=1M",
                  f"count={size_mb}", "status=none"], True,
                 t(s, "status_setting_perms")),
                (["chmod", "600", path], True, t(s, "status_formatting")),
                (["mkswap", path], True, t(s, "status_activating")),
            ]
            for cmd, sudo, next_msg in steps:
                ok, err = run_cmd(cmd, use_sudo=sudo)
                if not ok:
                    GLib.idle_add(self._done, False, t(s, "error") + f": {err}")
                    return
                GLib.idle_add(self.status_lbl.set_text, next_msg)

            swapon = (["swapon", path] if prio == -1
                      else ["swapon", "-p", str(prio), path])
            ok, err = run_cmd(swapon, use_sudo=True)
            if not ok:
                GLib.idle_add(self._done, False,
                              t(s, "err_swapon", err=err)); return

            if fstab:
                try:
                    with open("/etc/fstab") as f:
                        content = f.read()
                    if path not in content:
                        prio_str = f",pri={prio}" if prio != -1 else ""
                        with open("/etc/fstab", "a") as f:
                            f.write(f"{path} none swap sw{prio_str} 0 0\n")
                except Exception as e:
                    GLib.idle_add(self._done, False,
                                  t(s, "err_fstab", e=e)); return

            GLib.idle_add(self._done, True, "")

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, success, err):
        if self._pulse_timer:
            GLib.source_remove(self._pulse_timer)
            self._pulse_timer = None
        self._set_busy(False)
        s = self.strings
        if success:
            msg(s, self, "info", "success",
                t(s, "msg_created", path=self.path_entry.get_text()))
            self.response(Gtk.ResponseType.OK)
        else:
            msg(s, self, "error", "error", err)


# ── Dialog: Activate swapfile ─────────────────────────────────────────────────

class ActivateSwapDialog(Gtk.Dialog):
    def __init__(self, parent, strings):
        super().__init__(title=t(strings, "dlg_activate_title"),
                         transient_for=parent, modal=True)
        self.strings = strings
        self.set_default_size(480, -1)
        self.add_buttons(t(strings, "btn_cancel"), Gtk.ResponseType.CANCEL,
                         t(strings, "btn_activate"), Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10,
                        margin_top=16, margin_bottom=8,
                        margin_start=16, margin_end=16)
        self.get_content_area().add(grid)

        def lbl(k): return Gtk.Label(label=t(strings, k), xalign=1)

        grid.attach(lbl("lbl_swapfile"), 0, 0, 1, 1)
        path_box = Gtk.Box(spacing=4)
        self.path_entry = Gtk.Entry(hexpand=True)
        browse = Gtk.Button(label="…")
        browse.connect("clicked", self._browse)
        path_box.pack_start(self.path_entry, True, True, 0)
        path_box.pack_start(browse, False, False, 0)
        grid.attach(path_box, 1, 0, 1, 1)

        candidates = [p for p in ["/swapfile", "/swapfile1", "/swap.img",
                                   "/swapfile2"] if os.path.exists(p)]
        row = 1
        if candidates:
            grid.attach(lbl("lbl_quick"), 0, 1, 1, 1)
            q_box = Gtk.Box(spacing=4)
            for p in candidates:
                b = Gtk.Button(label=p)
                b.connect("clicked", lambda _, p=p: self.path_entry.set_text(p))
                q_box.pack_start(b, False, False, 0)
            grid.attach(q_box, 1, 1, 1, 1)
            row = 2

        grid.attach(lbl("lbl_priority"), 0, row, 1, 1)
        prio_box = Gtk.Box(spacing=4)
        self.prio_spin = Gtk.SpinButton.new_with_range(-1, 32767, 1)
        self.prio_spin.set_value(-1)
        prio_box.pack_start(self.prio_spin, False, False, 0)
        prio_box.pack_start(Gtk.Label(label=t(strings, "prio_default")),
                            False, False, 0)
        grid.attach(prio_box, 1, row, 1, 1)

        self.fstab_check = Gtk.CheckButton(label=t(strings, "chk_fstab_add"))
        self.fstab_check.set_active(True)
        grid.attach(self.fstab_check, 0, row + 1, 2, 1)

        self.show_all()

    def _browse(self, _):
        fc = Gtk.FileChooserDialog(
            title=t(self.strings, "dlg_pick_swapfile"),
            transient_for=self, modal=True,
            action=Gtk.FileChooserAction.OPEN)
        fc.add_buttons(t(self.strings, "btn_cancel"), Gtk.ResponseType.CANCEL,
                       t(self.strings, "btn_choose"), Gtk.ResponseType.OK)
        fc.set_current_folder("/")
        if fc.run() == Gtk.ResponseType.OK:
            self.path_entry.set_text(fc.get_filename())
        fc.destroy()

    def get_values(self):
        return {
            "path":  self.path_entry.get_text().strip(),
            "prio":  int(self.prio_spin.get_value()),
            "fstab": self.fstab_check.get_active(),
        }


# ── Dialog: Resize swapfile ───────────────────────────────────────────────────

class ResizeSwapDialog(Gtk.Dialog):
    """
    Swap cannot be resized live — the dialog deactivates the swapfile,
    creates a new one, and reactivates it.
    """
    def __init__(self, parent, strings, swap):
        super().__init__(title=t(strings, "dlg_resize_title"),
                         transient_for=parent, modal=True)
        self.strings = strings
        self.set_default_size(520, -1)
        self.add_buttons(t(strings, "btn_cancel"), Gtk.ResponseType.CANCEL)
        self._ok_btn = self.add_button(t(strings, "btn_apply"),
                                       Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self._swap = swap
        self._pulse_timer = None

        grid = Gtk.Grid(column_spacing=10, row_spacing=10,
                        margin_top=16, margin_bottom=8,
                        margin_start=16, margin_end=16)
        self.get_content_area().add(grid)

        def lbl(k): return Gtk.Label(label=t(strings, k), xalign=1)

        # Info
        info = Gtk.Label(xalign=0)
        info.set_markup(
            f'<b>{GLib.markup_escape_text(swap["path"])}</b>\n'
            f'<i>{GLib.markup_escape_text(t(strings, "resize_warning"))}</i>'
        )
        info.set_line_wrap(True)
        grid.attach(info, 0, 0, 2, 1)

        # Current size
        grid.attach(lbl("lbl_current_size"), 0, 1, 1, 1)
        grid.attach(Gtk.Label(
            label=f"{swap['size_mb']:.0f} MB  ({swap['size_mb']/1024:.2f} GB)",
            xalign=0), 1, 1, 1, 1)

        # New size
        grid.attach(lbl("lbl_new_size"), 0, 2, 1, 1)
        size_box = Gtk.Box(spacing=4)
        self.size_spin = Gtk.SpinButton.new_with_range(0.25, 128, 0.25)
        self.size_spin.set_value(round(swap["size_mb"] / 1024, 2))
        self.size_spin.set_digits(2)
        size_box.pack_start(self.size_spin, False, False, 0)
        size_box.pack_start(Gtk.Label(label="GB"), False, False, 0)
        grid.attach(size_box, 1, 2, 1, 1)

        # Quick select
        grid.attach(lbl("lbl_quick"), 0, 3, 1, 1)
        quick_box = Gtk.Box(spacing=4)
        for gb in [1, 2, 4, 8, 16, 32]:
            b = Gtk.Button(label=f"{gb} GB")
            b.connect("clicked", lambda _, g=gb: self.size_spin.set_value(g))
            quick_box.pack_start(b, False, False, 0)
        grid.attach(quick_box, 1, 3, 1, 1)

        # Progress
        self.progress = Gtk.ProgressBar()
        self.progress.set_no_show_all(True)
        self.status_lbl = Gtk.Label(label="", xalign=0)
        self.status_lbl.set_no_show_all(True)
        grid.attach(self.progress, 0, 4, 2, 1)
        grid.attach(self.status_lbl, 0, 5, 2, 1)

        self.show_all()
        self._ok_btn.connect("clicked", self._on_apply)

    def _set_busy(self, busy, status=""):
        self._ok_btn.set_sensitive(not busy)
        self.progress.set_visible(busy)
        self.status_lbl.set_visible(busy)
        if busy:
            self.status_lbl.set_text(status)

    def _on_apply(self, _):
        s    = self.strings
        path = self._swap["path"]
        size_mb = int(self.size_spin.get_value() * 1024)
        prio    = self._swap["prio"]

        self._set_busy(True, t(s, "status_deactivating"))
        self._pulse_timer = GLib.timeout_add(
            200, lambda: (self.progress.pulse(), True)[1])

        def worker():
            ok, err = run_cmd(["swapoff", path], use_sudo=True)
            if not ok:
                GLib.idle_add(self._done, False,
                              t(s, "err_swapoff", err=err)); return

            GLib.idle_add(self.status_lbl.set_text, t(s, "status_creating_new"))
            ok, err = run_cmd(
                ["dd", "if=/dev/zero", f"of={path}", "bs=1M",
                 f"count={size_mb}", "status=none"], use_sudo=True)
            if not ok:
                GLib.idle_add(self._done, False,
                              t(s, "err_dd", err=err)); return

            GLib.idle_add(self.status_lbl.set_text, t(s, "status_setting_perms"))
            run_cmd(["chmod", "600", path], use_sudo=True)

            GLib.idle_add(self.status_lbl.set_text, t(s, "status_formatting"))
            ok, err = run_cmd(["mkswap", path], use_sudo=True)
            if not ok:
                GLib.idle_add(self._done, False,
                              t(s, "err_mkswap", err=err)); return

            GLib.idle_add(self.status_lbl.set_text, t(s, "status_activating"))
            swapon = (["swapon", path] if prio == "-1"
                      else ["swapon", "-p", prio, path])
            ok, err = run_cmd(swapon, use_sudo=True)
            if not ok:
                GLib.idle_add(self._done, False,
                              t(s, "err_swapon", err=err)); return

            GLib.idle_add(self._done, True, "")

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, success, err):
        if self._pulse_timer:
            GLib.source_remove(self._pulse_timer)
            self._pulse_timer = None
        self._set_busy(False)
        s = self.strings
        if success:
            msg(s, self, "info", "success",
                t(s, "msg_resized", gb=self.size_spin.get_value(),
                  path=self._swap["path"]))
            self.response(Gtk.ResponseType.OK)
        else:
            msg(s, self, "error", "error", err)


# ── Main window ───────────────────────────────────────────────────────────────

class SwapManagerWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_default_size(900, 700)
        self._swaps = []

        self.cfg = load_config()
        self.strings = load_i18n(resolve_lang(self.cfg.get("lang", "system")))
        s = self.strings

        self.set_title(t(s, "app_title"))

        # HeaderBar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = t(s, "app_title")
        self.set_titlebar(header)

        about_btn = Gtk.Button()
        about_btn.set_image(Gtk.Image.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON))
        about_btn.set_tooltip_text(t(self.strings, "tooltip_about"))
        about_btn.connect("clicked", self._on_about)
        header.pack_end(about_btn)

        self._lang_options = build_lang_options(self.strings)
        self.lang_menu_btn = Gtk.MenuButton()
        self.lang_menu_btn.set_size_request(170, -1)
        self._lang_label = Gtk.Label()
        self.lang_menu_btn.add(self._lang_label)
        lang_menu = Gtk.Menu()
        group = []
        current_lang = self.cfg.get("lang", "system")
        for code, key in self._lang_options:
            item = Gtk.RadioMenuItem.new_with_label(group, t(s, key))
            group = item.get_group()
            if code == current_lang:
                item.set_active(True)
                self._lang_label.set_text(t(s, key))
            item.connect("activate", self._on_lang_menu_item, code)
            lang_menu.append(item)
        lang_menu.show_all()
        self.lang_menu_btn.set_popup(lang_menu)
        header.pack_end(self.lang_menu_btn)

        # Outer scrolled window
        outer_scroll = Gtk.ScrolledWindow()
        outer_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add(outer_scroll)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        outer_scroll.add(vbox)

        # System status
        status_frame = Gtk.Frame(label=f" {t(s, 'frame_system_status')} ")
        vbox.pack_start(status_frame, False, False, 0)

        status_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                               margin_top=6, margin_bottom=6,
                               margin_start=8, margin_end=8)
        status_frame.add(status_inner)

        self.status_tv = Gtk.TextView()
        self.status_tv.set_editable(False)
        self.status_tv.set_monospace(True)
        sw_status = Gtk.ScrolledWindow()
        sw_status.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw_status.set_size_request(-1, 140)
        sw_status.add(self.status_tv)
        status_inner.pack_start(sw_status, True, True, 0)

        refresh_btn = Gtk.Button(label=t(s, "btn_refresh"))
        refresh_btn.connect("clicked", lambda _: self._refresh())
        status_inner.pack_start(refresh_btn, False, False, 0)

        # Active swapfiles list
        list_frame = Gtk.Frame(label=f" {t(s, 'frame_active_swaps')} ")
        vbox.pack_start(list_frame, True, True, 0)

        list_inner = Gtk.Box(margin_top=6, margin_bottom=6,
                             margin_start=8, margin_end=8)
        list_frame.add(list_inner)

        self.store = Gtk.ListStore(str, str, str, str, str)
        self.tv = Gtk.TreeView(model=self.store)
        self.tv.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        for key, idx, expand in [
            ("col_path", 0, True), ("col_size", 1, False),
            ("col_used", 2, False), ("col_percent", 3, False),
            ("col_prio", 4, False),
        ]:
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(t(s, key), r, text=idx)
            c.set_expand(expand)
            c.set_resizable(True)
            self.tv.append_column(c)
        sw_list = Gtk.ScrolledWindow()
        sw_list.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw_list.set_size_request(-1, 120)
        sw_list.add(self.tv)
        list_inner.pack_start(sw_list, True, True, 0)

        # Actions
        action_frame = Gtk.Frame(label=f" {t(s, 'frame_actions')} ")
        vbox.pack_start(action_frame, False, False, 0)

        action_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                               margin_top=6, margin_bottom=6,
                               margin_start=8, margin_end=8)
        action_frame.add(action_inner)

        row1 = Gtk.Box(spacing=6)
        row2 = Gtk.Box(spacing=6)
        action_inner.pack_start(row1, False, False, 0)
        action_inner.pack_start(row2, False, False, 0)

        for key, cb, row in [
            ("btn_activate_action", self._activate,       row1),
            ("btn_deactivate",      self._deactivate,     row1),
            ("btn_deactivate_all",  self._deactivate_all, row1),
            ("btn_new_swap",        self._create,         row2),
            ("btn_resize",          self._resize,         row2),
            ("btn_delete",          self._delete,         row2),
        ]:
            b = Gtk.Button(label=t(s, key))
            b.connect("clicked", lambda _, f=cb: f())
            row.pack_start(b, False, False, 0)

        # Swappiness
        swap_frame = Gtk.Frame(label=f" {t(s, 'frame_swappiness')} ")
        vbox.pack_start(swap_frame, False, False, 0)

        swap_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                             margin_top=6, margin_bottom=6,
                             margin_start=8, margin_end=8)
        swap_frame.add(swap_inner)

        cur_row = Gtk.Box(spacing=8)
        cur_row.pack_start(Gtk.Label(label=t(s, "lbl_current_value")),
                           False, False, 0)
        self.swappiness_lbl = Gtk.Label(label="?")
        self.swappiness_lbl.set_markup("<b>?</b>")
        cur_row.pack_start(self.swappiness_lbl, False, False, 0)
        swap_inner.pack_start(cur_row, False, False, 0)

        slider_row = Gtk.Box(spacing=8)
        slider_row.pack_start(Gtk.Label(label=t(s, "lbl_new_value")),
                              False, False, 0)
        self.slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.slider.set_value(60)
        self.slider.set_hexpand(True)
        self.slider.set_draw_value(True)
        slider_row.pack_start(self.slider, True, True, 0)
        apply_btn = Gtk.Button(label=t(s, "btn_apply"))
        apply_btn.connect("clicked", lambda _: self._apply_swappiness())
        slider_row.pack_start(apply_btn, False, False, 0)
        swap_inner.pack_start(slider_row, False, False, 0)

        hint = Gtk.Label(label=t(s, "swappiness_hint"))
        hint.set_xalign(0)
        swap_inner.pack_start(hint, False, False, 0)

        # Statusbar
        self.statusbar = Gtk.Statusbar()
        self.ctx = self.statusbar.get_context_id("main")
        vbox.pack_start(self.statusbar, False, False, 0)

        self._refresh()
        GLib.timeout_add_seconds(10, self._auto_refresh)

    # ── Internal methods ──────────────────────────────────────────────────────

    def _set_status(self, text):
        self.statusbar.pop(self.ctx)
        self.statusbar.push(self.ctx, text)

    def _refresh(self):
        s = self.strings
        buf = self.status_tv.get_buffer()
        buf.set_text(get_mem_info(s))

        self.store.clear()
        self._swaps = get_swap_list()
        for sw in self._swaps:
            self.store.append([
                sw["path"],
                f"{sw['size_mb']:.0f} MB",
                f"{sw['used_mb']:.0f} MB",
                f"{sw['percent']:.1f}%",
                sw["prio"],
            ])

        v = get_swappiness()
        self.swappiness_lbl.set_markup(f"<b>{v}</b>" if v >= 0 else "<b>?</b>")
        if v >= 0:
            self.slider.set_value(v)

        self._set_status(t(s, "status_swapfiles", n=len(self._swaps)))

    def _auto_refresh(self):
        self._refresh()
        return True

    def _selected_swap(self):
        s = self.strings
        model, it = self.tv.get_selection().get_selected()
        if it is None:
            msg(s, self, "error", "no_selection", t(s, "err_no_selection"))
            return None
        idx = model.get_path(it).get_indices()[0]
        return self._swaps[idx]

    def _apply_swappiness(self):
        s = self.strings
        v = int(self.slider.get_value())
        ok, err = run_cmd(["sysctl", f"vm.swappiness={v}"], use_sudo=True)
        if ok:
            msg(s, self, "info", "swappiness_set",
                t(s, "swappiness_msg", v=v))
            self._refresh()
        else:
            msg(s, self, "error", "error", err)

    def _activate(self):
        s = self.strings
        dlg = ActivateSwapDialog(self, s)
        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy(); return
        v = dlg.get_values()
        dlg.destroy()

        path, prio, fstab = v["path"], v["prio"], v["fstab"]
        if not path:
            msg(s, self, "error", "error", t(s, "err_no_path")); return
        if not os.path.exists(path):
            msg(s, self, "error", "error", t(s, "err_not_exists", path=path))
            return

        ok, out = run_cmd(["file", path])
        if ok and "swap" not in out.lower():
            if not msg(s, self, "question", "warning",
                       t(s, "warn_not_swapfile", path=path)):
                return

        cmd = (["swapon", path] if prio == -1
               else ["swapon", "-p", str(prio), path])
        ok, err = run_cmd(cmd, use_sudo=True)
        if not ok:
            msg(s, self, "error", "err_swapon_failed",
                t(s, "err_swapon", err=err)); return

        if fstab:
            try:
                with open("/etc/fstab") as f:
                    content = f.read()
                if path not in content:
                    prio_str = f",pri={prio}" if prio != -1 else ""
                    with open("/etc/fstab", "a") as f:
                        f.write(f"{path} none swap sw{prio_str} 0 0\n")
            except Exception as e:
                msg(s, self, "warning", "warning", t(s, "err_fstab", e=e))

        self._set_status(t(s, "status_activated", path=path))
        self._refresh()

    def _deactivate(self):
        s = self.strings
        sw = self._selected_swap()
        if not sw: return
        if not msg(s, self, "question", "confirm",
                   t(s, "confirm_deactivate", path=sw["path"])): return
        ok, err = run_cmd(["swapoff", sw["path"]], use_sudo=True)
        if ok:
            self._set_status(t(s, "status_deactivated", path=sw["path"]))
            self._refresh()
        else:
            msg(s, self, "error", "error", t(s, "err_swapoff", err=err))

    def _deactivate_all(self):
        s = self.strings
        if not self._swaps:
            msg(s, self, "info", "info", t(s, "no_active_swaps")); return
        if not msg(s, self, "question", "confirm",
                   t(s, "confirm_deactivate_all")): return
        errors = []
        for sw in self._swaps:
            ok, err = run_cmd(["swapoff", sw["path"]], use_sudo=True)
            if not ok:
                errors.append(f"{sw['path']}: {err}")
        if errors:
            msg(s, self, "error", "err_partial", "\n".join(errors))
        else:
            self._set_status(t(s, "status_deactivated_all"))
        self._refresh()

    def _create(self):
        dlg = CreateSwapDialog(self, self.strings)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK:
            self._refresh()

    def _resize(self):
        sw = self._selected_swap()
        if not sw: return
        dlg = ResizeSwapDialog(self, self.strings, sw)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.OK:
            self._refresh()

    def _delete(self):
        s = self.strings
        sw = self._selected_swap()
        if not sw: return
        if not msg(s, self, "question", "confirm_delete_title",
                   t(s, "confirm_delete", path=sw["path"])): return
        ok, err = run_cmd(["swapoff", sw["path"]], use_sudo=True)
        if not ok:
            msg(s, self, "error", "error", t(s, "err_swapoff", err=err)); return
        ok, err = run_cmd(["rm", "-f", sw["path"]], use_sudo=True)
        if ok:
            self._set_status(t(s, "status_deleted", path=sw["path"]))
            self._refresh()
        else:
            msg(s, self, "error", "error", err)

    def _on_about(self, _btn):
        dlg = Gtk.AboutDialog(transient_for=self, modal=True)
        dlg.set_program_name(t(self.strings, "app_title"))
        dlg.set_version("1.0")
        dlg.set_comments(t(self.strings, "about_comments"))
        dlg.set_license_type(Gtk.License.MIT_X11)
        dlg.run()
        dlg.destroy()

    def _on_lang_menu_item(self, item, code):
        if not item.get_active():
            return
        if code == self.cfg.get("lang"):
            return
        self.cfg["lang"] = code
        save_config(self.cfg)
        for c, key in self._lang_options:
            if c == code:
                self._lang_label.set_text(t(self.strings, key))
                break
        new_strings = load_i18n(resolve_lang(code))
        dlg = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=t(new_strings, "restart_hint"),
        )
        dlg.run()
        dlg.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    win = SwapManagerWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
