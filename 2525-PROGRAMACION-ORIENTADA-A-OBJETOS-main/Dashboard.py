# Dashboard.py
import os
import sys
import json
import shlex
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

CONFIG_FILE = "dashboard_config.json"
STATE_FILE = "dashboard_state.json"


# ----------------------------
# Utilidades
# ----------------------------
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg="\nPresiona Enter para continuar..."):
    input(msg)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_python_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() == ".py" and not p.name.startswith("__")


def relpath_str(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return str(path)


# ----------------------------
# Configuración
# ----------------------------
def default_config(base_dir: Path) -> dict:
    """
    Config por defecto: organiza tus proyectos en carpetas "Unidad 1", "Unidad 2", etc.
    """
    return {
        "app_name": "Dashboard de Proyectos",
        "base_dir": str(base_dir),
        "units": {
            "1": "Unidad 1",
            "2": "Unidad 2"
        },
        "show_hidden_folders": False,
        "preferred_editor": "code -n",  # soporta argumentos (ej: "code -n", "notepad", "nano")
        "log_file": "dashboard.log",
        "confirm_before_run": True,
        "code_preview_lines": 200,

        # NUEVO: calidad de vida
        "ignore_dirs": [".venv", "venv", "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".idea", ".vscode"],
        "recent_limit": 15,
        "favorites_enabled": True,
        "ask_args_before_run": True,
        "open_unit_folder_shortcut": True
    }


def load_or_create_config() -> dict:
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / CONFIG_FILE

    if not config_path.exists():
        cfg = default_config(script_dir)
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        return cfg

    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = default_config(script_dir)
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        return cfg

    # Normaliza base_dir a absoluto
    if "base_dir" in cfg:
        cfg["base_dir"] = str(Path(cfg["base_dir"]).expanduser().resolve())

    # Migra claves faltantes (sin romper configs viejas)
    defaults = default_config(Path(cfg.get("base_dir", script_dir)))
    for k, v in defaults.items():
        cfg.setdefault(k, v)

    # Guarda si hubo migración
    try:
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return cfg


# ----------------------------
# Estado persistente (recientes + favoritos)
# ----------------------------
def state_path() -> Path:
    return Path(__file__).resolve().parent / STATE_FILE


def load_state() -> dict:
    p = state_path()
    if not p.exists():
        return {"recent": [], "favorites": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"recent": [], "favorites": []}
        data.setdefault("recent", [])
        data.setdefault("favorites", [])
        return data
    except Exception:
        return {"recent": [], "favorites": []}


def save_state(state: dict):
    try:
        state_path().write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def add_recent(cfg: dict, script_path: Path):
    state = load_state()
    p = str(script_path.resolve())
    recent = [x for x in state.get("recent", []) if x != p]
    recent.insert(0, p)
    state["recent"] = recent[: int(cfg.get("recent_limit", 15))]
    save_state(state)


def toggle_favorite(script_path: Path) -> bool:
    state = load_state()
    p = str(script_path.resolve())
    favs = state.get("favorites", [])
    if p in favs:
        favs = [x for x in favs if x != p]
        state["favorites"] = favs
        save_state(state)
        return False
    else:
        favs.append(p)
        state["favorites"] = favs
        save_state(state)
        return True


def is_favorite(script_path: Path) -> bool:
    state = load_state()
    return str(script_path.resolve()) in set(state.get("favorites", []))


# ----------------------------
# Logging simple (append)
# ----------------------------
def log_event(cfg: dict, message: str):
    try:
        log_path = (Path(__file__).resolve().parent / cfg.get("log_file", "dashboard.log")).resolve()
        line = f"[{now_str()}] {message}\n"
        with log_path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line)
    except Exception:
        pass


# ----------------------------
# Mostrar código (preview)
# ----------------------------
def show_code_preview(cfg: dict, script_path: Path):
    clear_screen()
    print(f"--- Código: {script_path.name} ---")
    print(f"Ruta: {script_path}")
    print("-" * 60)

    try:
        text = safe_read_text(script_path)
        lines = text.splitlines()
        limit = int(cfg.get("code_preview_lines", 200))

        if len(lines) <= limit:
            print(text)
        else:
            start = 0
            page = 60
            while start < len(lines):
                chunk = lines[start:start + page]
                print("\n".join(chunk))
                start += page
                if start >= len(lines):
                    break
                resp = input("\n(Enter para seguir / 'q' para salir) > ").strip().lower()
                if resp == "q":
                    break

        print("\n" + "-" * 60)
    except FileNotFoundError:
        print("El archivo no se encontró.")
    except Exception as e:
        print(f"Ocurrió un error al leer el archivo: {e}")

    pause()


# ----------------------------
# Ejecutar script
# ----------------------------
def run_script(cfg: dict, script_path: Path):
    if cfg.get("confirm_before_run", True):
        ans = input(f"¿Ejecutar '{script_path.name}'? (s/n) > ").strip().lower()
        if ans != "s":
            print("Ejecución cancelada.")
            pause()
            return

    args: list[str] = []
    if cfg.get("ask_args_before_run", True):
        raw = input("Argumentos (opcional, Enter para ninguno) > ").strip()
        if raw:
            try:
                args = shlex.split(raw)
            except Exception:
                # fallback básico
                args = raw.split()

    clear_screen()
    print(f"Ejecutando: {script_path.name}")
    print(f"Ruta: {script_path}")
    if args:
        print(f"Args: {args}")
    print("-" * 60)

    log_event(cfg, f"RUN {script_path} args={args!r}")
    add_recent(cfg, script_path)

    try:
        cmd = [sys.executable, str(script_path), *args]
        completed = subprocess.run(cmd, cwd=str(script_path.parent))
        print("\n" + "-" * 60)
        print(f"Finalizó con código: {completed.returncode}")
    except Exception as e:
        print(f"Error al ejecutar: {e}")

    pause()


# ----------------------------
# Abrir en editor
# ----------------------------
def open_in_editor(cfg: dict, script_path: Path):
    editor = (cfg.get("preferred_editor") or "").strip()
    log_event(cfg, f"OPEN_EDITOR {script_path}")

    try:
        if not editor:
            if os.name == "nt":
                os.startfile(str(script_path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(script_path)])
            return

        parts = shlex.split(editor)
        subprocess.Popen([*parts, str(script_path)])
    except Exception as e:
        print(f"No se pudo abrir el editor: {e}")
        pause()


# ----------------------------
# Exploración de carpetas
# ----------------------------
def list_subfolders(cfg: dict, unit_path: Path) -> list[Path]:
    show_hidden = bool(cfg.get("show_hidden_folders", False))
    folders = []
    try:
        for p in unit_path.iterdir():
            if p.is_dir():
                if not show_hidden and p.name.startswith("."):
                    continue
                folders.append(p)
    except (FileNotFoundError, PermissionError):
        return []
    return sorted(folders, key=lambda x: x.name.lower())


def list_scripts(folder: Path) -> list[Path]:
    try:
        scripts = [p for p in folder.iterdir() if is_python_file(p)]
    except (FileNotFoundError, PermissionError):
        return []
    return sorted(scripts, key=lambda x: x.name.lower())


def search_scripts(cfg: dict, unit_path: Path, query: str) -> list[Path]:
    """
    Busca recursivamente scripts .py por nombre dentro de la unidad, ignorando carpetas ruidosas.
    """
    query = query.lower().strip()
    ignore_dirs = set(cfg.get("ignore_dirs", []))

    hits = []
    try:
        for p in unit_path.rglob("*.py"):
            if not p.is_file():
                continue
            if p.name.startswith("__"):
                continue
            # ignora carpetas por nombre
            if any(part in ignore_dirs for part in p.parts):
                continue
            if query in p.name.lower():
                hits.append(p)
    except Exception:
        return []

    return sorted(hits, key=lambda x: x.name.lower())


# ----------------------------
# Acciones rápidas: recientes y favoritos
# ----------------------------
def get_recent_scripts(cfg: dict) -> list[Path]:
    state = load_state()
    out = []
    for p in state.get("recent", []):
        pp = Path(p)
        if pp.exists() and is_python_file(pp):
            out.append(pp)
    return out[: int(cfg.get("recent_limit", 15))]


def get_favorite_scripts() -> list[Path]:
    state = load_state()
    out = []
    for p in state.get("favorites", []):
        pp = Path(p)
        if pp.exists() and is_python_file(pp):
            out.append(pp)
    return sorted(out, key=lambda x: x.name.lower())


# ----------------------------
# UI Menús
# ----------------------------
def main_menu(cfg: dict):
    base_dir = Path(cfg["base_dir"])
    units: dict[str, str] = cfg.get("units", {})

    while True:
        clear_screen()
        print(f"=== {cfg.get('app_name', 'Dashboard')} ===")
        print(f"Base: {base_dir}")
        print("\nUnidades:")
        for k in sorted(units.keys()):
            print(f"  {k}) {units[k]}")

        print("\nAcciones:")
        print("  r) Recientes")
        if cfg.get("favorites_enabled", True):
            print("  f) Favoritos")
        print("  s) Buscar script por nombre (en una unidad)")
        print("  c) Abrir/editar configuración (dashboard_config.json)")
        print("  0) Salir")

        choice = input("\nElige una opción > ").strip().lower()

        if choice == "0":
            print("Saliendo...")
            return

        if choice == "c":
            config_path = Path(__file__).resolve().parent / CONFIG_FILE
            open_in_editor(cfg, config_path)
            cfg.update(load_or_create_config())
            continue

        if choice == "r":
            recents = get_recent_scripts(cfg)
            if not recents:
                print("No hay recientes todavía.")
                pause()
                continue
            scripts_actions_menu(cfg, recents, title="Recientes")
            continue

        if choice == "f" and cfg.get("favorites_enabled", True):
            favs = get_favorite_scripts()
            if not favs:
                print("No hay favoritos aún. Marca uno con ⭐ desde el menú del script.")
                pause()
                continue
            scripts_actions_menu(cfg, favs, title="Favoritos")
            continue

        if choice == "s":
            unit_key = input("Unidad (ej: 1, 2) > ").strip()
            if unit_key not in units:
                print("Unidad inválida.")
                pause()
                continue
            unit_path = base_dir / units[unit_key]
            q = input("Buscar (parte del nombre del .py) > ").strip()
            if not q:
                continue
            hits = search_scripts(cfg, unit_path, q)
            if not hits:
                print("No se encontraron scripts.")
                pause()
                continue
            scripts_actions_menu(cfg, hits, title=f"Resultados de búsqueda en {units[unit_key]}")
            continue

        if choice in units:
            unit_path = base_dir / units[choice]
            unit_menu(cfg, unit_path, units[choice])
        else:
            print("Opción no válida.")
            pause()


def unit_menu(cfg: dict, unit_path: Path, unit_name: str):
    while True:
        clear_screen()
        print(f"=== {cfg.get('app_name', 'Dashboard')} > {unit_name} ===")
        print(f"Ruta: {unit_path}\n")

        folders = list_subfolders(cfg, unit_path)
        if not folders:
            print("No hay subcarpetas (o la ruta no existe).")
            print("\nOpciones:")
            print("  b) Volver")
            print("  o) Abrir carpeta en explorador")
            choice = input("\n> ").strip().lower()
            if choice == "b":
                return
            if choice == "o":
                open_folder(unit_path)
                continue
            continue

        for i, f in enumerate(folders, start=1):
            print(f"  {i}) {f.name}")

        print("\nOpciones:")
        print("  o) Abrir carpeta en explorador")
        print("  b) Volver")

        choice = input("\nElige subcarpeta > ").strip().lower()

        if choice == "b":
            return
        if choice == "o":
            open_folder(unit_path)
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                folder_menu(cfg, folders[idx], unit_name)
            else:
                print("Opción inválida.")
                pause()
        except ValueError:
            print("Opción inválida.")
            pause()


def folder_menu(cfg: dict, folder: Path, unit_name: str):
    base_dir = Path(cfg["base_dir"])

    while True:
        clear_screen()
        print(f"=== {cfg.get('app_name', 'Dashboard')} > {unit_name} > {folder.name} ===")
        print(f"Ruta: {folder}\n")

        scripts = list_scripts(folder)
        if not scripts:
            print("No hay scripts .py en esta carpeta.")
            print("\nOpciones:")
            print("  o) Abrir carpeta en explorador")
            print("  b) Volver")
            choice = input("\n> ").strip().lower()
            if choice == "b":
                return
            if choice == "o":
                open_folder(folder)
                continue
            continue

        for i, s in enumerate(scripts, start=1):
            star = "⭐ " if is_favorite(s) else "   "
            print(f"  {i}) {star}{s.name}")

        print("\nAcciones:")
        print("  o) Abrir carpeta en explorador")
        print("  b) Volver")

        choice = input("\nSelecciona un script > ").strip().lower()

        if choice == "b":
            return
        if choice == "o":
            open_folder(folder)
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(scripts):
                script_actions_menu(cfg, scripts[idx], base_dir=base_dir)
            else:
                print("Opción inválida.")
                pause()
        except ValueError:
            print("Opción inválida.")
            pause()


def script_actions_menu(cfg: dict, script_path: Path, base_dir: Path | None = None):
    base_dir = base_dir or Path(cfg["base_dir"])

    while True:
        clear_screen()
        print(f"=== Script: {script_path.name} ===")
        print(f"Ruta: {relpath_str(script_path, base_dir)}")
        print(f"Absoluta: {script_path}\n")

        fav_enabled = cfg.get("favorites_enabled", True)
        fav = is_favorite(script_path) if fav_enabled else False

        print("Acciones:")
        print("  1) Ver código")
        print("  2) Ejecutar")
        print("  3) Ejecutar (sin confirmar)" if cfg.get("confirm_before_run", True) else "  3) Ejecutar (confirmar)")
        print("  4) Abrir en editor")
        print("  5) Abrir carpeta contenedora")
        if fav_enabled:
            print(f"  6) {'Quitar de favoritos' if fav else 'Marcar favorito'} (⭐)")
        print("  0) Volver")

        choice = input("\n> ").strip().lower()

        if choice == "0":
            return
        elif choice == "1":
            show_code_preview(cfg, script_path)
        elif choice == "2":
            run_script(cfg, script_path)
        elif choice == "3":
            # Ejecutar invirtiendo temporalmente confirm_before_run
            old = cfg.get("confirm_before_run", True)
            cfg["confirm_before_run"] = not old
            try:
                run_script(cfg, script_path)
            finally:
                cfg["confirm_before_run"] = old
        elif choice == "4":
            open_in_editor(cfg, script_path)
        elif choice == "5":
            open_folder(script_path.parent)
        elif choice == "6" and fav_enabled:
            new_state = toggle_favorite(script_path)
            print("✅ Marcado como favorito." if new_state else "✅ Quitado de favoritos.")
            pause()
        else:
            print("Opción inválida.")
            pause()


def scripts_actions_menu(cfg: dict, scripts: list[Path], title: str = "Scripts"):
    base_dir = Path(cfg["base_dir"])

    while True:
        clear_screen()
        print(f"=== {title} ===\n")
        for i, s in enumerate(scripts, start=1):
            star = "⭐ " if is_favorite(s) else "   "
            print(f"  {i}) {star}{s.name}   ({relpath_str(s.parent, base_dir)})")

        print("\nOpciones:")
        print("  b) Volver")

        choice = input("\nSelecciona un script > ").strip().lower()
        if choice == "b":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(scripts):
                script_actions_menu(cfg, scripts[idx], base_dir=base_dir)
            else:
                print("Opción inválida.")
                pause()
        except ValueError:
            print("Opción inválida.")
            pause()


def open_folder(path: Path):
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# ----------------------------
# Entry point
# ----------------------------
def main():
    cfg = load_or_create_config()

    # Asegura base_dir válido
    base_dir = Path(cfg["base_dir"])
    if not base_dir.exists():
        cfg["base_dir"] = str(Path(__file__).resolve().parent)
        try:
            (Path(__file__).resolve().parent / CONFIG_FILE).write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    main_menu(cfg)


if __name__ == "__main__":
    main()
