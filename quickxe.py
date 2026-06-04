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


# ===================== Paths / Config =====================

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


# ===================== Name cleanup =====================

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
    # Uninstallers
    "unins", "uninst", "uninstall",
    # Installers
    "setup", "install", "installer", "installhelper",
    # Microsoft / DX / .NET / runtime redistributables
    "redist", "vcredist", "vcruntime", "vc_redist",
    "dxsetup", "dxwebsetup", "directx", "dx9", "dx10", "dx11", "dx12",
    "dotnet", "dotnetfx", "ndp", "netfx",
    "openalinst", "oalinst", "openalsetup", "openal_inst", "openal-soft",
    "physx", "physxloader", "physxlegacy",
    "ue4prereqsetup", "uesetup", "ue5prereqsetup",
    "xnafx", "xna",
    # Crash / telemetry / handlers
    "crashreport", "crashpad", "crashhandler", "errorreport",
    "telemetry", "diagnostic",
    # Helpers / sub-processes
    "helper", "_helper", "cefprocess", "cefsubproc", "webhelper",
    "crashpad_handler", "subprocess", "renderer",
    # Patchers / updaters / configurators
    "patch", "patcher", "updater", "autoupdater", "launcher_helper",
    "config", "configure", "configurator", "settings", "options",
    "register", "unregister", "activation",
    # Misc utilities that ship next to games
    "register", "license", "readme", "report", "diag",
    # ProductActivator nonsense
    "activator", "registrationservice",
    # Common gameplay-unrelated tools
    "modkit", "editor", "leveleditor", "mapeditor", "consolelog",
)

# Things that, if found IN the filename anywhere, strongly suggest "not the game"
# (used as a higher-confidence signal than BAD_EXE_KEYWORDS substring match)
DEFINITELY_NOT_GAME = (
    "unins", "uninstall", "uninst",
    "vcredist", "vc_redist", "vcruntime",
    "dxsetup", "dxwebsetup", "directx_setup",
    "dotnet", "ndp4", "ndp48", "ndp6", "ndp7", "ndp8",
    "openalinst", "oalinst", "openalsetup", "openal-soft-mojo",
    "physxloader", "physx_systemsoftware",
    "ue4prereqsetup", "uesetup", "ue5prereqsetup",
    "redist", "redistributable",
    "crashpad_handler", "crashreport", "crashhandler",
    "ueprereqsetup",
)


def clean_name(raw: str) -> str:
    name = raw

    # Strip bracketed blobs
    name = re.sub(r"[\[\(\{][^\]\)\}]*[\]\)\}]", " ", name)

    # Separators -> spaces
    name = name.replace("_", " ").replace(".", " ").replace("-", " ")

    # Version blobs
    name = re.sub(r"\bv\s*\d+(\s*\d+)*[a-z]?\b", " ", name, flags=re.I)
    name = re.sub(r"\bbuild\s+\d+(\s+\d+)*\b", " ", name, flags=re.I)
    name = re.sub(r"\br\d{3,}\b", " ", name)
    name = re.sub(r"\b\d{4}\s+\d{2}\s+\d{2}\b", " ", name)
    name = re.sub(r"\b(64bit|32bit|x64|x86)\b", " ", name, flags=re.I)

    # Scene tags (longest first)
    for tag in sorted(SCENE_TAGS, key=len, reverse=True):
        name = re.sub(r"\b" + re.escape(tag) + r"\b", " ", name, flags=re.I)

    name = re.sub(r"\b(by|from)\b\s*\w+\s*$", " ", name, flags=re.I)
    # Strip trailing runs of digit-groups (version remnants)
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


# ===================== Scanning =====================

def _is_definitely_not_game(exe_name_lower: str) -> bool:
    """True if the exe is almost certainly an installer / runtime / helper,
    even when no other game-like exe is in the folder. Used to outright
    reject games where the only exe is junk."""
    return any(k in exe_name_lower for k in DEFINITELY_NOT_GAME)


def _exe_score(exe: Path, top: Path):
    """Lower score = better candidate for "the actual game".

    Priorities, in order:
      1. Junk exes (installers / helpers / runtimes) heavily penalized.
      2. Exe whose name matches the folder name wins.
      3. Exe in the folder root (depth 1) wins over deeper ones.
      4. Shorter filename wins as tiebreaker.
    """
    name_lower = exe.name.lower()
    stem_lower = exe.stem.lower()
    top_lower = top.name.lower()
    rel = exe.relative_to(top)
    depth = len(rel.parts)

    # Strong "this is junk" signal
    if _is_definitely_not_game(name_lower):
        junk = 2
    elif any(k in name_lower for k in BAD_EXE_KEYWORDS):
        junk = 1
    else:
        junk = 0

    # Exact folder-name match is the strongest "this is the game" signal
    if stem_lower == top_lower:
        name_match = 0
    elif top_lower.replace(" ", "") == stem_lower.replace(" ", ""):
        name_match = 0
    elif stem_lower in top_lower or top_lower in stem_lower:
        name_match = 1
    else:
        name_match = 2

    # Common game exe names get a small boost
    common_names = ("game", "start", "play", "run", "main")
    if stem_lower in common_names and depth <= 2:
        name_match = min(name_match, 1)

    return (junk, name_match, depth, len(exe.name))


SKIP_SUBDIRS = frozenset({
    "_commonredist", "commonredist", "_redist", "redist",
    "directx", "dotnet", "vcredist", "physx", "openal",
    "support", "supportfiles", "crashpad", "crashreporter",
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", "build",
    "tools", "toolkits", "modkit", "sdk",
    "logs", "log", "saves", "savegames",
    "cache", "tmp", "temp",
})

MAX_SCAN_DEPTH = 4
MAX_EXES_PER_FOLDER = 40


def _walk_exes(top: Path):
    stack = [(top, 0)]
    count = 0
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            if entry.name.lower().endswith(".exe"):
                                yield Path(entry.path)
                                count += 1
                                if count >= MAX_EXES_PER_FOLDER:
                                    return
                        elif entry.is_dir(follow_symlinks=False):
                            if depth >= MAX_SCAN_DEPTH:
                                continue
                            if entry.name.lower() in SKIP_SUBDIRS:
                                continue
                            stack.append((Path(entry.path), depth + 1))
                    except OSError:
                        continue
        except (PermissionError, OSError):
            continue


def scan_library(library_path: str) -> list:
    root = Path(library_path)
    if not root.exists() or not root.is_dir():
        return []

    games = []
    seen = set()

    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and entry.suffix.lower() == ".exe":
            # Skip junk exes even when loose in the library root
            if _is_definitely_not_game(entry.name.lower()):
                continue
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
            all_exes = list(_walk_exes(entry))
        except (PermissionError, OSError):
            continue
        if not all_exes:
            continue

        # Filter out the "definitely not game" exes entirely.
        # If that leaves nothing, the whole folder is junk - skip it.
        non_junk = [e for e in all_exes
                    if not _is_definitely_not_game(e.name.lower())]
        if not non_junk:
            continue

        non_junk.sort(key=lambda p: _exe_score(p, entry))
        chosen = non_junk[0]

        # Final safety check: if even our best pick is "bad" (junk=1), skip it.
        if _exe_score(chosen, entry)[0] >= 1:
            continue

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


# ===================== Bridge (JS <-> Python) =====================

class Bridge(QObject):
    """Exposed to JS as window.quickxe via QWebChannel.

    All slots accept a single JSON string argument (or none) and return a
    JSON string. This avoids subtle type-conversion issues across the bridge.
    """

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.cfg = load_config()
        # Cache: lib_id -> list of game dicts. Invalidated on rename/refresh.
        self._scan_cache = {}

    # --- helpers ---
    def _ok(self, **extra):
        return json.dumps({"ok": True, **extra})

    def _err(self, msg, **extra):
        return json.dumps({"ok": False, "error": msg, **extra})

    def _find_lib(self, lib_id):
        return next((l for l in self.cfg["libraries"] if l["id"] == lib_id), None)

    # --- state ---
    @Slot(result=str)
    def get_state(self):
        return json.dumps({
            "libraries": self.cfg.get("libraries", []),
            "active_library": self.cfg.get("active_library"),
        })

    # --- libraries ---
    @Slot(result=str)
    def add_library(self):
        path = QFileDialog.getExistingDirectory(
            self._window, "Choose a library folder",
            "", QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not path:
            return self._err("cancelled")
        path = str(Path(path))
        # de-dup
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
        self._invalidate_cache(lib_id)
        save_config(self.cfg)
        return self._ok()

    @Slot(str, result=str)
    def set_active_library(self, lib_id):
        if not self._find_lib(lib_id):
            return self._err("not found")
        self.cfg["active_library"] = lib_id
        save_config(self.cfg)
        return self._ok()

    # --- games ---
    @Slot(result=str)
    def scan_active(self):
        return self._scan_internal(force=False)

    @Slot(result=str)
    def rescan_active(self):
        return self._scan_internal(force=True)

    def _scan_internal(self, force=False):
        lib_id = self.cfg.get("active_library")
        if not lib_id:
            return json.dumps({"ok": True, "games": [], "library": None})
        lib = self._find_lib(lib_id)
        if not lib:
            return json.dumps({"ok": True, "games": [], "library": None})

        if not force and lib_id in self._scan_cache:
            games = self._scan_cache[lib_id]
        else:
            games = scan_library(lib["path"])
            self._scan_cache[lib_id] = games

        # Cover URLs aren't cached - they're cheap to look up and can change.
        covers = self.cfg.get("covers", {})
        cdir = get_covers_dir()
        out_games = []
        for g in games:
            g_copy = dict(g)
            name = covers.get(g["id"])
            if name and (cdir / name).exists():
                g_copy["cover_url"] = QUrl.fromLocalFile(str(cdir / name)).toString()
            else:
                g_copy["cover_url"] = None
            out_games.append(g_copy)
        return json.dumps({"ok": True, "games": out_games, "library": lib})

    def _invalidate_cache(self, lib_id=None):
        if lib_id is None:
            self._scan_cache.clear()
        else:
            self._scan_cache.pop(lib_id, None)

    @Slot(str, result=str)
    def launch_game(self, exe_path):
        p = Path(exe_path)
        if not p.exists():
            return self._err(f"Not found: {exe_path}")
        try:
            if sys.platform == "win32":
                # Use ShellExecuteW directly via ctypes. This is exactly what
                # Explorer calls when you double-click an exe:
                #   - lpVerb=NULL  -> default verb ("open")
                #   - lpDirectory  -> working directory (we point at exe's folder
                #                     so the game can find its assets/DLLs)
                #   - nShowCmd=SW_SHOWNORMAL=1
                # Crucially, ShellExecuteW DOES NOT pass any process-creation
                # flags that confuse RPG Maker / OpenAL games the way Python's
                # subprocess does, and DOES NOT block waiting for the child.
                import ctypes
                from ctypes import wintypes
                ShellExecuteW = ctypes.windll.shell32.ShellExecuteW
                ShellExecuteW.argtypes = [
                    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                    wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int,
                ]
                ShellExecuteW.restype = wintypes.HINSTANCE
                rc = ShellExecuteW(
                    None,                # hwnd
                    None,                # verb (None = "open" / default)
                    str(p),              # file
                    None,                # parameters
                    str(p.parent),       # working directory
                    1,                   # SW_SHOWNORMAL
                )
                # ShellExecuteW returns > 32 on success. Common error codes:
                #   SE_ERR_ACCESSDENIED (5)
                #   SE_ERR_NOASSOC (31)
                #   ERROR_CANCELLED (1223) - user clicked No on UAC prompt
                rc_int = int(rc) if rc is not None else 0
                if rc_int <= 32:
                    if rc_int == 1223 or rc_int == 0:
                        return self._err("Launch cancelled at UAC prompt")
                    return self._err(f"Windows refused to launch (code {rc_int})")
            else:
                subprocess.Popen([str(p)], cwd=str(p.parent))
            return self._ok()
        except Exception as e:
            return self._err(str(e))

    @Slot(str, result=str)
    def open_in_explorer(self, folder_path):
        p = Path(folder_path)
        if not p.exists():
            return self._err("Folder not found")
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return self._ok()
        except Exception as e:
            return self._err(str(e))

    # --- covers ---
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
        # Remove any old cover with a different extension
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

    # --- destructive ---
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
        self._invalidate_cache()
        return self._ok()


# ===================== Window =====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuickXe")
        self.resize(1200, 800)
        self.setMinimumSize(820, 560)

        # Window icon
        ico = get_resource_dir() / "quickxe.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))

        # Web view
        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        # Use a fresh, off-the-record profile so devtools menus don't leak
        # Allow local file access from local files (for our index.html -> covers/)
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        # Disable right-click default browser menu; we use our own in JS
        self.view.setContextMenuPolicy(Qt.PreventContextMenu)

        # Bridge
        self.bridge = Bridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("quickxe", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Load HTML
        html_path = get_resource_dir() / "index.html"
        if not html_path.exists():
            # Try app dir as a fallback (in case bundling moved things)
            alt = get_app_dir() / "index.html"
            if alt.exists():
                html_path = alt
        self.view.load(QUrl.fromLocalFile(str(html_path)))


# ===================== Entry =====================

def main():
    # On Windows, ensure subprocesses (launched games) don't inherit our handles
    if sys.platform == "win32":
        # High DPI handling
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("QuickXe")
    app.setOrganizationName("QuickXe")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
