#!/usr/bin/env python3
"""Agent Sellbit pentru Pi4: tunel SSH catre VPS, comenzi instant si webhook de sync,
redare cu mpv dupa programul JSON. Toata configurarea (adrese, porturi, cai, cheia SSH) e in fisierul
.env de langa acest script; vezi env.example."""
import json
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
# Nicio valoare de deploy nu e scrisa in cod: toate vin din .env (cheie din .env -> cheie in cfg).
ENV_KEYS = {
    "SSH_TARGET": "ssh_target",                # utilizator@adresa VPS
    "SSH_KEY": "ssh_key",                      # cheia privata a tunelului
    "SSH_KNOWN_HOSTS": "ssh_known_hosts",      # fisierul known_hosts (verificare stricta a serverului)
    "REMOTE_PROGRAM": "remote_program",        # program.json pe VPS
    "REMOTE_CLIPS_DIR": "remote_clips_dir",    # folderul cu fisiere pe VPS
    "VPS_BIND": "vps_bind",                    # adresa pe care asculta tunelul pe VPS
    "VPS_PORT": "port_vps",                    # portul tunelului pe VPS
    "AGENT_PORT": "port_agent",                # portul HTTP local al agentului (doar 127.0.0.1)
    "CACHE_DIR": "cache_dir",
    "MPV_SOCKET": "mpv_socket",
    "MPV_ARGS": "mpv_args",                    # argumente mpv, separate prin spatiu (ex. --drm-mode=1280x720)
    "DRM_CONNECTOR": "drm_connector",          # optional
}
OPTIONAL_KEYS = {"DRM_CONNECTOR", "MPV_ARGS"}
INT_KEYS = {"port_vps", "port_agent"}
cfg = {"drm_connector": "", "mpv_args": [], "ssh_target": "", "ssh_key": "", "ssh_known_hosts": "",
       "remote_program": "", "remote_clips_dir": ""}   # completate din .env de load_env()


def parse_env(text):
    """Citeste linii CHEIE=valoare (fara export, comentarii cu #, ghilimele optionale)."""
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("linia %d din .env nu are forma CHEIE=valoare" % n)
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def load_env(path=ENV_PATH):
    """Pune valorile din .env in cfg. Ridica ValueError cu lista tuturor problemelor."""
    with open(path, encoding="utf-8") as f:
        env = parse_env(f.read())
    problems = ["lipseste %s" % k for k in ENV_KEYS if k not in OPTIONAL_KEYS and not env.get(k)]
    unknown = [k for k in env if k not in ENV_KEYS]
    problems += ["cheie necunoscuta %s" % k for k in unknown]
    new = {}
    for k, name in ENV_KEYS.items():
        v = env.get(k, "")
        if k == "MPV_ARGS":
            new[name] = shlex.split(v)
        elif name in INT_KEYS and v:
            try:
                new[name] = int(v)
                if not 1 <= new[name] <= 65535:
                    raise ValueError
            except ValueError:
                problems.append("%s trebuie sa fie un port 1-65535" % k)
        elif v or k in OPTIONAL_KEYS:
            new[name] = v
    if problems:
        raise ValueError("; ".join(problems))
    cfg.update(new)


def ssh_options():
    """Optiunile ssh comune tunelului si rsync (fara fisier ssh_config): doar cheia dedicata, server verificat strict."""
    return ["-F", "/dev/null", "-i", cfg["ssh_key"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + cfg["ssh_known_hosts"]]


COMMANDS = {"play", "pause", "stop", "next", "party", "quick"}
QUICK_MAX_FILES = 50
TICK_SECONDS = 5
RETRY_SECONDS = 5
IDLE_RETRY_SECONDS = 30       # mpv idle cu playlist ne-gol: reia redarea cel mult odata la atat
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
DEFAULT_IMAGE_SECONDS = 10     # pentru poze fara imageSeconds (mpv ar tine poza doar 1s)
CONNECT_SECONDS = 5
log = logging.getLogger("sellbit")


# ---------------------------------------------------------------- program
def hhmm(value):
    return datetime.strptime(value, "%H:%M").strftime("%H:%M")


def parse_entry(e):
    name = e["file"]
    if not isinstance(name, str) or not name or name != os.path.basename(name) or name.startswith("."):
        raise ValueError("nume de fisier invalid: %r" % (name,))
    secs = e.get("imageSeconds")
    if secs is not None and not (isinstance(secs, (int, float)) and secs > 0):
        raise ValueError("imageSeconds invalid pentru %s" % name)
    return {"file": name, "order": int(e.get("order", 0)), "secs": secs}


def parse_schedule(raw):
    """Programul de lucru: {zi ISO 1..7: (deschidere, inchidere)}. Zilele care lipsesc sunt inchise.
    Forma noua: "schedule": [{"day": 1, "open": "10:00", "close": "18:00"}, ...] (inchiderea mai mica decat
    deschiderea = trece peste miezul noptii). Forma veche (fara "schedule"): "open"/"close" unice, valabile in toate zilele."""
    if raw.get("schedule") is None:
        hours = (hhmm(raw["open"]), hhmm(raw["close"]))
        return {day: hours for day in range(1, 8)}
    if not isinstance(raw["schedule"], list):
        raise ValueError("schedule invalid")
    schedule = {}
    for e in raw["schedule"]:
        day = e["day"]
        if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 7 or day in schedule:
            raise ValueError("zi invalida in schedule: %r" % (day,))
        schedule[day] = (hhmm(e["open"]), hhmm(e["close"]))
    return schedule


def parse_program(raw):
    """Valideaza programul JSON. Ridica ValueError/KeyError/TypeError daca e gresit."""
    prog = {"schedule": parse_schedule(raw), "default": [], "parties": [], "stop_images": []}
    # pozele de fundal: lista stopImages [{file, imageSeconds?}] sau, in forma veche, o singura poza stopImage
    if raw.get("stopImages"):
        prog["stop_images"] = [parse_entry(e) for e in raw["stopImages"]]
    elif raw.get("stopImage"):
        prog["stop_images"] = [parse_entry({"file": raw["stopImage"]})]
    for e in raw.get("default", []):
        item = parse_entry(e)
        if "days" in e:       # forma veche: zilele clipului; in forma noua clipurile ruleaza in toate zilele deschise
            item["days"] = e["days"]
            if not item["days"] or not all(isinstance(d, int) and 1 <= d <= 7 for d in item["days"]):
                raise ValueError("days invalid pentru %s" % item["file"])
        prog["default"].append(item)
    manual_counts = {}      # petreceri fara ora: numarate pe zi, pentru id-ul "YYYY-MM-DD #N"
    for p in raw.get("parties", []):
        party_files = [parse_entry(e) for e in p["files"]]
        if p.get("start") is None and p.get("durationMinutes") is None:
            # fara ora de inceput si de sfarsit: nu porneste singura, doar manual (comanda "party")
            datetime.strptime(p["date"], "%Y-%m-%d")
            n = manual_counts.get(p["date"], 0) + 1
            manual_counts[p["date"]] = n
            prog["parties"].append({"id": "%s #%d" % (p["date"], n), "start": None, "end": None,
                                    "files": party_files})
            continue
        start = datetime.strptime(p["date"] + " " + hhmm(p["start"]), "%Y-%m-%d %H:%M")
        minutes = int(p["durationMinutes"])
        if minutes <= 0:
            raise ValueError("durationMinutes invalid")
        prog["parties"].append({"id": start.strftime("%Y-%m-%d %H:%M"), "start": start,
                                "end": start + timedelta(minutes=minutes), "files": party_files})
    return prog


def name_is_image(name):
    return name.lower().endswith(IMAGE_EXTENSIONS)


def by_order(items):
    return sorted(items, key=lambda i: i["order"])


def default_items(prog, now):
    return by_order([i for i in prog["default"] if "days" not in i or now.isoweekday() in i["days"]])


def is_open(prog, now):
    """Deschis dupa programul zilei de azi; sau, dupa miezul noptii, dupa programul de ieri daca acela trecea peste miezul noptii."""
    t = now.strftime("%H:%M")
    today = prog["schedule"].get(now.isoweekday())
    if today:
        opens, closes = today
        if opens < closes and opens <= t < closes:
            return True
        if opens > closes and t >= opens:               # program peste miezul noptii: partea de dinainte de 24:00
            return True
    yesterday = prog["schedule"].get((now - timedelta(days=1)).isoweekday())
    return bool(yesterday) and yesterday[0] > yesterday[1] and t < yesterday[1]   # partea de dupa miezul noptii


def compute_target(prog, now):
    """(cheie, fisiere): petrecere activa > default in orele de functionare > nimic."""
    active = [p for p in prog["parties"] if p["start"] is not None and p["start"] <= now < p["end"]]
    if active:
        p = max(active, key=lambda x: x["start"])
        return "party:" + p["id"], by_order(p["files"])
    if is_open(prog, now):
        return "default", default_items(prog, now)
    return "none", []


def parse_quick_files(raw):
    """Fisierele pentru rularea rapida: [{"file": nume, "imageSeconds": n?}, ...] (1..QUICK_MAX_FILES), in ordinea data.
    Ridica ValueError/TypeError daca lista e gresita."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= QUICK_MAX_FILES:
        raise ValueError("lista de fisiere invalida")
    items = []
    for e in raw:
        if not isinstance(e, dict):
            raise ValueError("fisier invalid")
        items.append(parse_entry({"file": e.get("file"), "imageSeconds": e.get("imageSeconds")}))
    return items


def referenced_files(prog):
    names = {i["file"] for i in prog["default"]}
    names.update(i["file"] for i in prog["stop_images"])
    for p in prog["parties"]:
        names.update(i["file"] for i in p["files"])
    return names


# ---------------------------------------------------------------- mpv
class Player:
    def __init__(self):
        self.proc = None
        self.entry_files = {}       # playlist_entry_id mpv -> numele fisierului (pentru erorile de redare)
        self.error_seq = 0          # creste la fiecare eroare de redare raportata
        self.last_error = None      # {"id", "file", "message"}: ultima eroare de redare, vizibila in /status

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def ipc(self, *command):
        """Trimite o comanda mpv pe socketul IPC si intoarce raspunsul ei."""
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3)
            s.connect(cfg["mpv_socket"])
            s.sendall((json.dumps({"command": list(command), "request_id": 1}) + "\n").encode())
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    raise OSError("socket mpv inchis")
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("request_id") == 1 and "error" in msg:  # sare peste evenimente
                        return msg

    def idle(self):
        """mpv ruleaza, dar nu mai reda nimic (ex. toate fisierele din playlist au dat eroare: mpv nu reia bucla)."""
        return self.running() and self.prop("idle-active") is True

    def prop(self, name):
        try:
            return self.ipc("get_property", name).get("data")
        except OSError:
            return None

    def start(self):
        sock = cfg["mpv_socket"]
        if os.path.exists(sock):
            os.unlink(sock)
        cmd = ["mpv", "--no-config", "--idle=yes", "--vo=drm", "--no-audio", "--loop-playlist=inf",
               "--no-terminal", "--input-ipc-server=" + sock]
        if cfg["drm_connector"]:
            cmd.append("--drm-connector=" + cfg["drm_connector"])
        cmd += cfg["mpv_args"]
        log.info("pornesc mpv: %s", " ".join(cmd))
        self.proc = subprocess.Popen(cmd)
        self.entry_files = {}
        for _ in range(50):
            if os.path.exists(sock) or not self.running():
                break
            time.sleep(0.1)
        if os.path.exists(sock):
            # conectarea se face aici, inainte sa se incarce primul fisier, ca prima eroare sa nu se piarda
            try:
                watcher = socket.socket(socket.AF_UNIX)
                watcher.connect(sock)
                threading.Thread(target=self.watch, args=(watcher,), daemon=True).start()
            except OSError as e:
                log.warning("nu pot urmari evenimentele mpv: %s", e)

    def watch(self, s):
        """Conexiunea permanenta la mpv (ruleaza in fir propriu, pana se inchide mpv): la evenimentul end-file cu
        reason=error retine eroarea de redare, ca sa apara in /status."""
        try:
            with s:
                for line in s.makefile("rb"):
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("event") == "end-file" and msg.get("reason") == "error":
                        self.report_error(msg)
        except OSError as e:
            log.warning("urmarirea evenimentelor mpv s-a oprit: %s", e)

    def refresh_entries(self):
        """Retine, pentru fiecare intrare din playlist-ul mpv, id-ul ei -> numele fisierului."""
        count = self.prop("playlist/count")
        if not isinstance(count, int):
            return
        for n in range(count):
            entry_id = self.prop("playlist/%d/id" % n)
            filename = self.prop("playlist/%d/filename" % n)
            if isinstance(entry_id, int) and isinstance(filename, str):
                self.entry_files[entry_id] = os.path.basename(filename)

    def report_error(self, msg):
        """Eroare de redare a unui fisier (end-file, reason=error). Fiecare aparitie primeste un id nou, chiar daca
        e aceeasi eroare, ca Sellbit sa o poata afisa din nou dupa ce utilizatorul a apasat OK."""
        entry_id = msg.get("playlist_entry_id")
        if entry_id not in self.entry_files:
            self.refresh_entries()
        name = self.entry_files.get(entry_id)
        text = msg.get("file_error") or "eroare necunoscuta"
        if "no audio or video data played" in text:   # zgomot de la mpv: nu se retine, nu apare in /status si nu se logheaza
            return
        self.error_seq += 1
        self.last_error = {"id": self.error_seq, "file": name, "message": text}
        log.error("eroare de redare (%s): %s", name or "fisier necunoscut", text)

    def stop(self):
        if not self.running():
            return
        try:
            self.ipc("quit")
            self.proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            self.proc.wait()

    def load(self, playlist):
        """playlist: [(cale, imageSeconds|None)]. Inlocuieste ce ruleaza."""
        if not self.running():
            self.start()
        for n, (path, secs) in enumerate(playlist):
            args = ["loadfile", path, "replace" if n == 0 else "append"]
            if secs:
                args.append("image-display-duration=%s" % secs)
            self.ipc(*args)
        self.refresh_entries()
        self.ipc("set_property", "pause", False)


# ---------------------------------------------------------------- agent
class Agent:
    def __init__(self):
        self.lock = threading.RLock()
        self.sync_state = threading.Lock()
        self.sync_busy = False
        self.sync_again = False
        self.last_sync = None   # rezultatul ultimului sync, vizibil in /status
        self.player = Player()
        self.ssh = None
        self.manual = None      # None | "stop" | "pause" | "play" | "party"
        self.party_session = None   # id-ul petrecerii pornite manual ("YYYY-MM-DD HH:MM" sau "YYYY-MM-DD #N") (se pastreaza peste pauza)
        self.party_items = []       # fisierele ei: ultima versiune cunoscuta, ca sesiunea sa nu depinda de program
        self.adhoc_loading = False  # rularea rapida: se descarca fisiere care nu erau pe player
        self.adhoc_error = None     # motivul ultimului esec la descarcare
        self.last_idle_retry = 0.0  # momentul ultimei reluari automate (time.monotonic)
        self.key = None         # tinta curenta: "none" | "default" | "party:..."
        self.playlist = []      # ce ruleaza acum, [(cale, secs)]
        self.program_path = os.path.join(cfg["cache_dir"], "program.json")
        self.clips_dir = os.path.join(cfg["cache_dir"], "clips")
        os.makedirs(self.clips_dir, exist_ok=True)

    # ---- program / playlist
    def load_program(self):
        try:
            with open(self.program_path) as f:
                return parse_program(json.load(f))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.error("program invalid in cache: %s", e)
            return None

    def to_playlist(self, items):
        """Pastreaza doar fisierele care exista local."""
        out = []
        for i in items:
            path = os.path.join(self.clips_dir, i["file"])
            if os.path.isfile(path):
                secs = i["secs"]
                if secs is None and name_is_image(i["file"]):
                    secs = DEFAULT_IMAGE_SECONDS
                out.append((path, secs))
            else:
                log.warning("lipseste local: %s", i["file"])
        return out

    # ---- redare
    def apply(self, playlist):
        try:
            if playlist:
                self.player.load(playlist)
                if self.manual == "pause":
                    self.player.ipc("set_property", "pause", True)
            else:
                self.player.stop()
            self.playlist = playlist
        except OSError as e:
            log.error("eroare mpv, il repornesc la urmatorul ciclu: %s", e)
            self.playlist = None                 # nu e aplicat: tick-ul reincearca
            self.player.stop()                   # pornire curata data viitoare

    def enforce(self, playlist):
        if playlist != self.playlist or (playlist and not self.player.running()):
            self.apply(playlist)
        elif not playlist and self.player.running():
            self.player.stop()

    def find_party(self, prog, party_id):
        """Petrecerea din program cu id-ul dat, sau None. Id: 'YYYY-MM-DD HH:MM' (data si ora de inceput) sau,
        pentru petrecerea fara ore, 'YYYY-MM-DD #N' (N = a cata petrecere fara ore din acea zi, in ordinea din program)."""
        for party in prog["parties"] if prog else []:
            if party["id"] == party_id:
                return party
        return None

    def adhoc_names(self):
        """Fisierele rularii rapide active: nu se sterg la sync chiar daca nu sunt in program."""
        return {item["file"] for item in self.party_items} if self.party_session == "adhoc" else set()

    def fetch_adhoc(self, names):
        """Descarca (in fundal) fisierele rularii rapide care lipsesc de pe player."""
        errors = []
        try:
            if not (cfg["ssh_target"] and cfg["remote_clips_dir"]):
                raise RuntimeError("lipseste configuratia de sync")
            for name in names:
                try:
                    self.rsync(os.path.join(cfg["remote_clips_dir"], name), os.path.join(self.clips_dir, name))
                except Exception as e:  # noqa: BLE001 - un fisier esuat nu opreste restul
                    errors.append("%s: %s" % (name, str(e)[-120:]))
        except RuntimeError as e:
            errors.append(str(e))
        finally:
            self.adhoc_error = "; ".join(errors) if errors else None
            self.adhoc_loading = False
            if errors:
                log.error("rulare rapida: descarcare esuata: %s", self.adhoc_error)
            else:
                log.info("rulare rapida: %d fisiere descarcate", len(names))

    def manual_party_continues(self, new_key):
        """Petrecerea pornita manual continua cand se schimba tinta doar daca schimbarea tine de ea sau de
        programul implicit: incepe sau se termina propria ei petrecere programata (ora ei e ignorata).
        Se opreste cand incepe alta petrecere programata, cand programul se inchide (tinta "none")
        sau cand se deschide programul (preia programul, ca la orice comanda manuala din afara orelor)."""
        if new_key == "party:" + self.party_session:
            return True
        return new_key == "default" and self.key != "none"

    def party_playlist(self, prog):
        """Fisierele petrecerii pornite manual. Daca petrecerea e inca in program, urmeaza modificarile (sync);
        daca a disparut din program, ruleaza mai departe ultima versiune cunoscuta."""
        party = self.find_party(prog, self.party_session) if self.party_session else None
        if party:
            self.party_items = by_order(party["files"])
        return self.to_playlist(self.party_items)

    def stop_playlist(self, prog):
        """Pozele de fundal din program (stopImages), afisate dupa `stop` sau cand nu e nimic de rulat.
        O singura poza ramane pe ecran permanent; mai multe se schimba la secundele lor (implicit 10 s), in bucla."""
        if not prog or not prog["stop_images"]:
            return []
        if len(prog["stop_images"]) == 1:
            return self.to_playlist([{"file": prog["stop_images"][0]["file"], "secs": "inf"}])
        return self.to_playlist(prog["stop_images"])

    def tick(self):
        """Reevalueaza ce trebuie sa ruleze acum (ora, zi, petrecere) si aduce mpv in starea aceea."""
        now = datetime.now()
        prog = self.load_program()
        key, items = compute_target(prog, now) if prog else ("none", [])
        playlist = self.to_playlist(items)
        if not playlist and prog and is_open(prog, now):   # in program, fara clip de rulat: poza de oprire
            playlist = self.stop_playlist(prog)
        with self.lock:
            manual_party = bool(self.party_session) and self.manual in ("party", "pause")
            if key != self.key and manual_party and self.manual_party_continues(key):
                # petrecerea pornita manual se comporta ca un clip implicit: ii ignora doar propria ora de inceput
                # si de sfarsit; orice altceva din program (alta petrecere, inchiderea programului) se aplica normal
                log.info("tinta noua: %s (petrecerea pornita manual continua)", key)
                self.key = key
            if key != self.key:                      # s-a schimbat tinta: comanda manuala se anuleaza
                log.info("tinta noua: %s (%d fisiere)", key, len(playlist))
                self.key, self.manual, self.party_session, self.party_items = key, None, None, []
                self.apply(playlist)
            elif self.manual == "stop":
                self.enforce(self.stop_playlist(prog))
            elif manual_party:
                party_playlist = self.party_playlist(prog)
                if party_playlist:                   # ruleaza ca un clip implicit, pana la Stop sau alta petrecere programata
                    self.enforce(party_playlist)
                elif self.adhoc_loading and self.party_session == "adhoc":
                    pass                             # inca se descarca fisierele: ruleaza mai departe ce rula
                else:                                # nu mai are niciun fisier pe player: sesiunea se termina
                    self.party_session, self.party_items, self.manual = None, [], None
                    self.enforce(playlist)
            elif self.manual == "play" or (self.manual == "pause" and not playlist):
                # sesiune manuala in afara programului (play, sau pauza dupa play): clipurile default de azi
                manual_playlist = self.to_playlist(default_items(prog, now)) if prog else []
                if not manual_playlist and prog and is_open(prog, now):
                    manual_playlist = self.stop_playlist(prog)       # in program, fara clipuri: poza
                self.enforce(manual_playlist)
            else:
                self.enforce(playlist)
        self.recover_idle()

    def recover_idle(self):
        """mpv ruleaza dar e idle cu playlist ne-gol = nu a putut reda nimic (ex. TV oprit la pornire: fara EDID, deci
        fara modul DRM cerut). Reia redarea la cel mult IDLE_RETRY_SECONDS, ca sa porneasca singura cand ecranul revine."""
        if not self.playlist or self.adhoc_loading or not self.player.running():
            return
        if time.monotonic() - self.last_idle_retry < IDLE_RETRY_SECONDS:
            return
        if self.player.idle():
            self.last_idle_retry = time.monotonic()
            log.warning("mpv e idle cu playlist ne-gol, reiau redarea")
            with self.lock:
                self.player.stop()                 # repornire curata: modul DRM se alege la initializare
                self.apply(self.playlist)

    def manual_after_resume(self, prog, now):
        """Dupa iesirea din pauza: in program/cu tinta activa nu mai e nimic manual; in afara programului
        ramane sesiune manuala ("play"), ca tick-ul sa nu opreasca playerul."""
        if self.party_session:
            return "party"
        _, items = compute_target(prog, now) if prog else ("none", [])
        in_program = bool(prog) and is_open(prog, now)
        return None if (self.to_playlist(items) or in_program) else "play"

    def command(self, name, arg=None):
        try:
            return self._command(name, arg)
        except OSError as e:
            log.error("comanda %s esuata: %s", name, e)
            return False, "eroare mpv: %s" % e

    def _command(self, name, arg=None):
        with self.lock:
            prog = self.load_program()
            now = datetime.now()
            if name == "stop":
                if not self.player.running():
                    return False, "nu ruleaza nimic"
                self.manual = "stop"
                self.party_session = None
                self.apply(self.stop_playlist(prog))
            elif name == "party":
                party = self.find_party(prog, arg or "")
                if party is None:
                    return False, "petrecerea nu e in programul de pe player (salveaza programul)"
                playlist = self.to_playlist(by_order(party["files"]))
                if not playlist:
                    return False, "fisierele petrecerii nu sunt pe player"
                self.party_session, self.party_items, self.manual = arg, by_order(party["files"]), "party"
                if playlist != self.playlist or not self.player.running() or self.player.idle():
                    self.apply(playlist)
                else:
                    self.player.ipc("set_property", "pause", False)
            elif name == "quick":
                # rulare rapida: fisiere alese acum, fara sa fie in program; se comporta ca o petrecere pornita manual
                self.party_session, self.party_items, self.manual = "adhoc", arg, "party"
                self.adhoc_error = None
                missing = [item["file"] for item in arg if not os.path.isfile(os.path.join(self.clips_dir, item["file"]))]
                if missing:
                    self.adhoc_loading = True
                    threading.Thread(target=self.fetch_adhoc, args=(missing,), daemon=True).start()
                    return True, "se descarca %d fisiere; porneste cand sunt gata" % len(missing)
                playlist = self.to_playlist(arg)
                if playlist != self.playlist or not self.player.running() or self.player.idle():
                    self.apply(playlist)
                else:
                    self.player.ipc("set_property", "pause", False)
            elif name in ("pause", "next") and self.manual == "stop":
                return False, "playerul e oprit, da play"
            elif name == "pause":
                if not self.player.running():
                    return False, "nu ruleaza nimic"
                self.manual = "pause"
                self.player.ipc("set_property", "pause", True)
            elif name == "next":
                if not self.player.running():
                    return False, "nu ruleaza nimic"
                was_paused = self.manual == "pause"
                if was_paused:                        # next din pauza: porneste urmatorul clip
                    self.manual = self.manual_after_resume(prog, now)
                self.player.ipc("playlist-next", "force")
                time.sleep(0.3)
                if self.player.prop("idle-active"):   # playlistul s-a terminat: reia de la capat
                    self.apply(self.playlist)
                if was_paused:
                    self.player.ipc("set_property", "pause", False)
            elif name == "play":
                if self.manual == "pause" and self.player.running():
                    self.manual = self.manual_after_resume(prog, now)
                    self.player.ipc("set_property", "pause", False)
                elif self.manual == "party":
                    return True, "ok"                  # petrecerea pornita manual ruleaza deja
                else:
                    self.party_session = None
                    _, items = compute_target(prog, now) if prog else ("none", [])
                    playlist = self.to_playlist(items)
                    if playlist:
                        self.manual = None
                    else:                              # nimic de rulat acum: clipurile default de azi
                        playlist = self.to_playlist(default_items(prog, now)) if prog else []
                        self.manual = "play" if playlist else None
                    if not playlist:
                        return False, "nu exista clipuri de rulat"
                    if playlist != self.playlist or not self.player.running() or self.player.idle():
                        self.apply(playlist)             # daca ruleaza deja exact asta, nu o reiau de la zero
        return True, "ok"

    # ---- tunel: reconectare la 5 secunde, la nesfarsit, fara backoff
    def tunnel_loop(self):
        cmd = ["ssh"] + ssh_options() + ["-N", "-T",
               "-o", "ExitOnForwardFailure=yes",
               "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=%d" % CONNECT_SECONDS,
               "-R", "%s:%d:127.0.0.1:%d" % (cfg["vps_bind"], cfg["port_vps"], cfg["port_agent"]),
               cfg["ssh_target"]]
        while True:
            try:
                log.info("deschid tunelul")
                self.ssh = subprocess.Popen(cmd)
                try:
                    code = self.ssh.wait(timeout=CONNECT_SECONDS + 1)
                except subprocess.TimeoutExpired:    # a trecut de ConnectTimeout si traieste: tunelul e activ
                    log.info("tunel activ, sincronizez")
                    threading.Thread(target=self.sync, daemon=True).start()
                    code = self.ssh.wait()
                log.warning("tunel cazut (cod %s), reincerc in %ss", code, RETRY_SECONDS)
            except Exception as e:  # noqa: BLE001 - tunelul trebuie sa reinceapa orice s-ar intampla
                log.error("eroare tunel: %s", e)
            time.sleep(RETRY_SECONDS)

    # ---- sincronizare (la pornire si la POST /sync)
    def rsync(self, remote, local):
        cmd = ["rsync", "-t", "--timeout=60", "-e", " ".join(["ssh"] + [shlex.quote(o) for o in ssh_options()]),
               "%s:%s" % (cfg["ssh_target"], remote), local]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            raise RuntimeError("rsync a depasit 15 minute pentru %s" % remote)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip().replace("\n", " | ") or "rsync cod %d" % r.returncode)

    def sync(self):
        """Trage programul si clipurile. Un apel venit in timpul unui sync face sa mai ruleze unul dupa el."""
        with self.sync_state:
            if self.sync_busy:
                self.sync_again = True
                return
            self.sync_busy = True
        while True:
            try:
                result = self.sync_once()
            except Exception as e:  # noqa: BLE001
                log.error("sync esuat: %s", e)
                result = {"ok": False, "message": str(e), "failed": []}
            result["time"] = datetime.now().isoformat(timespec="seconds")
            self.last_sync = result
            with self.sync_state:
                if not self.sync_again:
                    self.sync_busy = False
                    return
                self.sync_again = False

    def sync_once(self):
        """rsync scrie fisierul nou si il muta abia cand e complet."""
        if not (cfg["ssh_target"] and cfg["remote_program"] and cfg["remote_clips_dir"]):
            log.warning("sync dezactivat: lipsesc ssh_target/remote_program/remote_clips_dir din config")
            return {"ok": False, "message": "sync dezactivat: lipseste configuratia", "failed": []}
        tmp = self.program_path + ".tmp"
        self.rsync(cfg["remote_program"], tmp)
        try:
            with open(tmp) as f:
                prog = parse_program(json.load(f))
        except (OSError, ValueError, KeyError, TypeError) as e:
            os.unlink(tmp)
            raise RuntimeError("program primit invalid, il pastrez pe cel vechi: %s" % e)
        os.replace(tmp, self.program_path)
        keep = referenced_files(prog)
        failed = []
        for name in sorted(keep):
            try:
                self.rsync(os.path.join(cfg["remote_clips_dir"], name), os.path.join(self.clips_dir, name))
            except RuntimeError as e:
                log.error("nu pot trage %s: %s", name, e)
                failed.append(name)
        protected = keep | self.adhoc_names()
        for name in ([] if self.adhoc_loading else os.listdir(self.clips_dir)):  # sterge ce nu mai apare in program
            if name not in protected:                # (nu cat se descarca fisiere pentru rularea rapida)
                os.unlink(os.path.join(self.clips_dir, name))
                log.info("sters: %s", name)
        log.info("sync gata (%d fisiere in program, %d netrase)", len(keep), len(failed))
        self.tick()                              # aplica noul program imediat
        return {"ok": not failed, "failed": failed, "files": len(keep),
                "message": "ok" if not failed else "programul e aplicat, dar nu s-au tras: " + ", ".join(failed)}

    def status(self):
        with self.lock:
            key, manual, party = self.key, self.manual, self.party_session
        running = self.player.running()
        playing = self.player.prop("path") if running else None
        try:
            version = datetime.fromtimestamp(os.stat(self.program_path).st_mtime).isoformat(timespec="seconds")
        except OSError:
            version = None
        vfs = os.statvfs(cfg["cache_dir"])
        return {"target": key, "manual": manual, "party": party, "party_loading": self.adhoc_loading,
                "quick_error": self.adhoc_error, "mpv_running": running,
                "paused": self.player.prop("pause") if running else None,
                "playing": os.path.basename(playing) if isinstance(playing, str) else None,
                "program_version": version, "free_mb": vfs.f_bavail * vfs.f_frsize // 2**20,
                "syncing": self.sync_busy, "last_sync": self.last_sync,
                "playback_error": self.player.last_error}


# ---------------------------------------------------------------- HTTP (doar loopback, prin tunel)
def make_handler(agent):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/status":
                self.reply(200, agent.status())
            else:
                self.reply(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/command":
                try:
                    length = max(0, min(int(self.headers.get("Content-Length", 0)), 65536))
                    body = json.loads(self.rfile.read(length))
                    name, arg = body["command"], body.get("party")
                    if not isinstance(name, str) or (name == "party" and not isinstance(arg, str)):
                        raise TypeError
                    if name == "quick":
                        arg = parse_quick_files(body.get("files"))
                except (ValueError, KeyError, TypeError):
                    return self.reply(400, {"error": 'corp asteptat: {"command":"play|pause|stop|next"} sau {"command":"party","party":"YYYY-MM-DD HH:MM"} sau {"command":"quick","files":[{"file":"nume"}]}'})
                if name not in COMMANDS:
                    return self.reply(400, {"error": "comanda necunoscuta", "allowed": sorted(COMMANDS)})
                ok, msg = agent.command(name, arg)
                self.reply(200 if ok else 409, {"ok": ok, "message": msg})
            elif self.path == "/sync":
                threading.Thread(target=agent.sync, daemon=True).start()
                self.reply(202, {"started": True})
            else:
                self.reply(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            log.info("http %s", fmt % args)

    return Handler


# ---------------------------------------------------------------- main
def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        load_env()
    except (OSError, ValueError) as e:
        log.error("configurare invalida (%s): %s", ENV_PATH, e)
        return 1
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    agent = Agent()
    server = ThreadingHTTPServer(("127.0.0.1", cfg["port_agent"]), make_handler(agent))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=agent.tunnel_loop, daemon=True).start()
    threading.Thread(target=agent.sync, daemon=True).start()   # o data la pornire
    try:
        while True:                     # redarea nu depinde de tunel: foloseste cache-ul local
            try:
                agent.tick()
            except Exception:  # noqa: BLE001
                log.exception("eroare in tick")
            time.sleep(TICK_SECONDS)
    finally:
        if agent.ssh and agent.ssh.poll() is None:
            agent.ssh.terminate()
        agent.player.stop()


if __name__ == "__main__":
    sys.exit(main())
