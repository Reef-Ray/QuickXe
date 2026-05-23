"""
QuickXe - retro game launcher (PySide6/Qt edition).

UI is HTML/CSS/JS in a QWebEngineView; Python handles file scanning,
exe launching, cover storage, and folder deletion.

Communication: QWebChannel exposes a Python QObject (Bridge) to JS as
`window.quickxe`. All bridge methods take JSON strings and return JSON
strings to avoid type-conversion gotchas across the channel.
"""

import os
import re
import sys
import json
import shutil
import hashlib
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel



def get_app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    folder = base / "QuickXe"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "covers").mkdir(parents=True, exist_ok=True)
    return folder


def get_config_path() -> Path:
    return get_app_dir() / "config.json"


def get_covers_dir() -> Path:
    return get_app_dir() / "covers"


def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


DEFAULT_CONFIG = {
    "libraries": [],
    "active_library": None,
    "covers": {},
}


def load_config() -> dict:
    p = get_config_path()
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return {k: (v.copy() if isinstance(v, (dict, list)) else v)
            for k, v in DEFAULT_CONFIG.items()}


def save_config(cfg: dict) -> None:
    p = get_config_path()
    try:
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"save_config failed: {e}")



SCENE_TAGS = [
    "fitgirl", "fitgirl repack", "fitgirl-repack",
    "dodi", "dodi repack",
    "elamigos", "razor1911", "razor", "codex", "skidrow",
    "plaza", "hoodlum", "reloaded", "rune", "tenoke",
    "empress", "rng", "tinyiso", "gog", "goldberg",
    "repack", "rip", "scene", "p2p", "deluxe", "edition",
    "definitive", "ultimate", "complete", "directors cut",
    "remastered", "anniversary", "goty", "game of the year",
    "steamunlocked", "steam unlocked", "fix",
    "english", "multi", "multi-lang", "multilang",
    "x64", "x86", "win", "windows", "pc",
    "incl", "inclupdate", "incl update", "incl all dlcs",
    "all dlcs", "all dlc", "dlc", "dlcs",
    "crack", "cracked", "no-cd", "nocd",
]

BAD_EXE_KEYWORDS = (
    "unins", "setup", "install", "redist", "vcredist", "dxsetup",
    "dxwebsetup", "crashreport", "crashpad", "config", "settings",
    "launcher_helper", "cefprocess", "ue4prereqsetup", "dotnet",
    "directx", "_helper", "patcher", "updater",
)


def clean_name(raw: str) -> str:
    name = raw

    name = re.sub(r"[\[\(\{][^\]\)\}]*[\]\)\}]", " ", name)

    name = name.replace("_", " ").replace(".", " ").replace("-", " ")

    name = re.sub(r"\bv\s*\d+(\s*\d+)*[a-z]?\b", " ", name, flags=re.I)
    name = re.sub(r"\bbuild\s+\d+(\s+\d+)*\b", " ", name, flags=re.I)
    name = re.sub(r"\br\d{3,}\b", " ", name)
    name = re.sub(r"\b\d{4}\s+\d{2}\s+\d{2}\b", " ", name)
    name = re.sub(r"\b(64bit|32bit|x64|x86)\b", " ", name, flags=re.I)

    for tag in sorted(SCENE_TAGS, key=len, reverse=True):
        name = re.sub(r"\b" + re.escape(tag) + r"\b", " ", name, flags=re.I)

    name = re.sub(r"\b(by|from)\b\s*\w+\s*$", " ", name, flags=re.I)
    name = re.sub(r"(?:\s+\d+){2,}\s*$", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        return raw.strip()

    if name == name.lower() or (name == name.upper() and len(name) > 3):
        small = {"of", "the", "a", "an", "and", "in", "on", "at", "to", "for", "vs"}
        out = []
        for i, w in enumerate(name.split()):
            wl = w.lower()
            if i > 0 and wl in small:
                out.append(wl)
            elif wl in ("ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii"):
                out.append(wl.upper())
            else:
                out.append(w.capitalize())
        name = " ".join(out)

    return name


def game_id(library_path: str, top_folder_name: str) -> str:
    h = hashlib.md5(f"{library_path}|{top_folder_name}".encode("utf-8")).hexdigest()
    return h[:16]



def _exe_score(exe: Path, top: Path):
    rel = exe.relative_to(top)
    depth = len(rel.parts)
    name_match = 0 if exe.stem.lower() == top.name.lower() else 1
    bad = 1 if any(k in exe.name.lower() for k in BAD_EXE_KEYWORDS) else 0
    return (bad, name_match, depth, len(exe.name))


def scan_library(library_path: str) -> list:
    root = Path(library_path)
    if not root.exists() or not root.is_dir():
        return []

    games = []
    seen = set()

    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and entry.suffix.lower() == ".exe":
            gid = game_id(library_path, entry.stem)
            if gid in seen:
                continue
            seen.add(gid)
            games.append({
                "id": gid,
                "name": clean_name(entry.stem),
                "raw_name": entry.stem,
                "exe_path": str(entry.resolve()),
                "folder_path": str(entry.parent.resolve()),
            })
            continue

        if not entry.is_dir():
            continue

        try:
            all_exes = [p for p in entry.rglob("*")
                        if p.is_file() and p.suffix.lower() == ".exe"]
        except (PermissionError, OSError):
            continue
        if not all_exes:
            continue

        all_exes.sort(key=lambda p: _exe_score(p, entry))
        if _exe_score(all_exes[0], entry)[0] == 1:
            continue

        chosen = all_exes[0]
        gid = game_id(library_path, entry.name)
        if gid in seen:
            continue
        seen.add(gid)
        games.append({
            "id": gid,
            "name": clean_name(entry.name),
            "raw_name": entry.name,
            "exe_path": str(chosen.resolve()),
            "folder_path": str(entry.resolve()),
        })

    return games



class Bridge(QObject):
    """Exposed to JS as window.quickxe via QWebChannel.

    All slots accept a single JSON string argument (or none) and return a
    JSON string. This avoids subtle type-conversion issues across the bridge.
    """

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.cfg = load_config()

    def _ok(self, **extra):
        return json.dumps({"ok": True, **extra})

    def _err(self, msg, **extra):
        return json.dumps({"ok": False, "error": msg, **extra})

    def _find_lib(self, lib_id):
        return next((l for l in self.cfg["libraries"] if l["id"] == lib_id), None)

    @Slot(result=str)
    def get_state(self):
        return json.dumps({
            "libraries": self.cfg.get("libraries", []),
            "active_library": self.cfg.get("active_library"),
        })

    @Slot(result=str)
    def add_library(self):
        path = QFileDialog.getExistingDirectory(
            self._window, "Choose a library folder",
            "", QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not path:
            return self._err("cancelled")
        path = str(Path(path))
        for lib in self.cfg["libraries"]:
            if str(Path(lib["path"])) == path:
                self.cfg["active_library"] = lib["id"]
                save_config(self.cfg)
                return self._ok(library=lib, duplicate=True)
        lib_id = hashlib.md5(path.encode("utf-8")).hexdigest()[:12]
        lib = {
            "id": lib_id,
            "name": Path(path).name or "Library",
            "path": path,
        }
        self.cfg["libraries"].append(lib)
        self.cfg["active_library"] = lib_id
        save_config(self.cfg)
        return self._ok(library=lib)

    @Slot(str, result=str)
    def rename_library(self, payload):
        try:
            data = json.loads(payload)
        except Exception:
            return self._err("bad payload")
        lib_id = data.get("id")
        new_name = (data.get("name") or "").strip()
        if not new_name:
            return self._err("empty name")
        lib = self._find_lib(lib_id)
        if not lib:
            return self._err("not found")
        lib["name"] = new_name[:40]
        save_config(self.cfg)
        return self._ok()

    @Slot(str, result=str)
    def remove_library(self, lib_id):
        self.cfg["libraries"] = [l for l in self.cfg["libraries"] if l["id"] != lib_id]
        if self.cfg.get("active_library") == lib_id:
            self.cfg["active_library"] = (
                self.cfg["libraries"][0]["id"] if self.cfg["libraries"] else None
            )
        save_config(self.cfg)
        return self._ok()

    @Slot(str, result=str)
    def set_active_library(self, lib_id):
        if not self._find_lib(lib_id):
            return self._err("not found")
        self.cfg["active_library"] = lib_id
        save_config(self.cfg)
        return self._ok()

    @Slot(result=str)
    def scan_active(self):
        lib_id = self.cfg.get("active_library")
        if not lib_id:
            return json.dumps({"ok": True, "games": [], "library": None})
        lib = self._find_lib(lib_id)
        if not lib:
            return json.dumps({"ok": True, "games": [], "library": None})
        games = scan_library(lib["path"])
        covers = self.cfg.get("covers", {})
        cdir = get_covers_dir()
        for g in games:
            name = covers.get(g["id"])
            if name and (cdir / name).exists():
                g["cover_url"] = QUrl.fromLocalFile(str(cdir / name)).toString()
            else:
                g["cover_url"] = None
        return json.dumps({"ok": True, "games": games, "library": lib})

    @Slot(str, result=str)
    def launch_game(self, exe_path):
        p = Path(exe_path)
        if not p.exists():
            return self._err(f"Not found: {exe_path}")
        try:
            if sys.platform == "win32":
                # os.startfile is the Windows shell launcher - identical to a
                # user double-clicking the file in Explorer. It:
                #   - inherits the current user's token (no auto-elevation)
                #   - only triggers UAC if the exe's manifest *itself* says
                #     requireAdministrator (then Windows handles UAC for us)
                #   - lets the game's own sub-processes prompt for UAC
                #     individually if they need it (e.g. an OpenAL installer)
                # This is exactly what happens when you double-click the .exe.
                try:
                    os.startfile(str(p), cwd=str(p.parent))  
                except TypeError:
                    old_cwd = os.getcwd()
                    try:
                        os.chdir(str(p.parent))
                        os.startfile(str(p))  
                    finally:
                        os.chdir(old_cwd)
            else:
                subprocess.Popen([str(p)], cwd=str(p.parent))
            return self._ok()
        except OSError as e:
            if sys.platform == "win32" and getattr(e, "winerror", None) == 1223:
                return self._err("Launch cancelled at UAC prompt")
            return self._err(str(e))
        except Exception as e:
            return self._err(str(e))

    @Slot(str, result=str)
    def open_in_explorer(self, folder_path):
        p = Path(folder_path)
        if not p.exists():
            return self._err("Folder not found")
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return self._ok()
        except Exception as e:
            return self._err(str(e))

    @Slot(str, result=str)
    def set_cover(self, game_id_str):
        path, _ = QFileDialog.getOpenFileName(
            self._window, "Choose a cover image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not path:
            return self._err("cancelled")
        src = Path(path)
        if not src.exists():
            return self._err("file not found")
        ext = src.suffix.lower() or ".png"
        dest_name = f"{game_id_str}{ext}"
        dest = get_covers_dir() / dest_name
        for old in get_covers_dir().glob(f"{game_id_str}.*"):
            try:
                old.unlink()
            except OSError:
                pass
        try:
            shutil.copyfile(src, dest)
        except Exception as e:
            return self._err(str(e))
        self.cfg.setdefault("covers", {})[game_id_str] = dest_name
        save_config(self.cfg)
        return self._ok(cover_url=QUrl.fromLocalFile(str(dest)).toString())

    @Slot(str, result=str)
    def remove_cover(self, game_id_str):
        covers = self.cfg.setdefault("covers", {})
        name = covers.pop(game_id_str, None)
        if name:
            try:
                (get_covers_dir() / name).unlink()
            except (OSError, FileNotFoundError):
                pass
        save_config(self.cfg)
        return self._ok()

    @Slot(str, result=str)
    def delete_game_folder(self, payload):
        try:
            data = json.loads(payload)
        except Exception:
            return self._err("bad payload")
        folder_path = data.get("folder_path", "")
        game_id_str = data.get("game_id")
        confirm_text = data.get("confirm", "")
        if confirm_text != "DELETE":
            return self._err("confirmation required")

        p = Path(folder_path)
        if not p.exists():
            return self._err("Folder not found")

        lib_paths = [Path(l["path"]).resolve() for l in self.cfg["libraries"]]
        p_resolved = p.resolve()
        if p_resolved in lib_paths:
            return self._err("Refusing to delete a library root")
        inside_any = any(
            str(p_resolved).lower().startswith(str(lp).lower() + os.sep)
            for lp in lib_paths
        )
        if not inside_any:
            return self._err("Folder not inside any library")

        try:
            if p_resolved.is_dir():
                shutil.rmtree(p_resolved)
            else:
                p_resolved.unlink()
        except Exception as e:
            return self._err(str(e))

        if game_id_str:
            self.remove_cover(game_id_str)
        return self._ok()



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuickXe")
        self.resize(1200, 800)
        self.setMinimumSize(820, 560)

        ico = get_resource_dir() / "quickxe.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))

        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.view.setContextMenuPolicy(Qt.PreventContextMenu)

        self.bridge = Bridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("quickxe", self.bridge)
        self.view.page().setWebChannel(self.channel)

        html_path = get_resource_dir() / "index.html"
        if not html_path.exists():
            alt = get_app_dir() / "index.html"
            if alt.exists():
                html_path = alt
        self.view.load(QUrl.fromLocalFile(str(html_path)))



def main():
    if sys.platform == "win32":
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("QuickXe")
    app.setOrganizationName("QuickXe")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
