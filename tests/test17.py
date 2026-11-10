import sys, os, json, shutil, time
sys.path.insert(0, ".."); import agent
from datetime import datetime
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache17"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv17.sock", mpv_args=[])
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)

# toate fisierele petrecerii sunt stricate: mpv ramane idle dupa eroare; la „Porneste acum” repetat eroarea trebuie sa apara din nou
today = datetime.now().strftime("%Y-%m-%d")
prog = {"open": "00:00", "close": "23:59", "default": [],
        "parties": [{"date": today, "files": [{"file": "corrupt.mp4", "order": 1}]}]}
json.dump(prog, open(d + "/program.json", "w"))
open(d + "/clips/corrupt.mp4", "wb").write(b"x")
a = agent.Agent()
def wait_for(seq):
    for _ in range(40):
        if a.player.last_error and a.player.last_error["id"] >= seq: return True
        time.sleep(0.1)
    return False
pid = today + " #1"
ok(a.command("party", pid)[0], "party pornit")
ok(wait_for(1), "prima eroare raportata")
ok(a.player.idle(), "mpv ramane pornit dar idle dupa ce toate fisierele au esuat")
ok(a.command("party", pid)[0], "party pornit a doua oara (aceleasi fisiere, mpv idle)")
ok(wait_for(2), "a doua eroare raportata dupa repornire: %s" % a.player.last_error)
ok(a.command("party", pid)[0] and wait_for(3), "si a treia oara")
a.player.stop()
print("GATA" if not bad else "ESUATE"); sys.exit(1 if bad else 0)
