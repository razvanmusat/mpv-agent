import sys, os, json, shutil, time
sys.path.insert(0, ".."); import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache16"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
open(T + "/run/fake-mpv.log", "w").close()
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv16.sock", mpv_args=[])
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)

# eroare de redare a unui clip: end-file (reason=error) de la mpv ajunge in /status ca playback_error
prog = {"open": "00:00", "close": "23:59", "parties": [],
        "default": [{"file": "a.mp4", "days": [1,2,3,4,5,6,7], "order": 1}, {"file": "corrupt.mp4", "days": [1,2,3,4,5,6,7], "order": 2}]}
json.dump(prog, open(d + "/program.json", "w"))
for n in ("a.mp4", "corrupt.mp4"): open(d + "/clips/" + n, "wb").write(b"x")
a = agent.Agent()
ok(a.status()["playback_error"] is None, "fara erori: playback_error e null")
a.tick()
for _ in range(30):
    if a.player.last_error: break
    time.sleep(0.1)
err = a.status()["playback_error"]
ok(err is not None and err["file"] == "corrupt.mp4" and err["message"] == "unrecognized file format", "eroarea apare in /status cu fisierul si mesajul: %s" % err)
first_id = err["id"]
a.player.report_error({"event": "end-file", "reason": "error", "playlist_entry_id": 2, "file_error": "unrecognized file format"})
err_same = a.status()["playback_error"]
ok(err_same["id"] == first_id + 1 and err_same["file"] == "corrupt.mp4" and err_same["message"] == "unrecognized file format", "aceeasi eroare repetata imediat primeste id nou (se poate afisa din nou): %s" % err_same)
a.player.report_error({"event": "end-file", "reason": "error", "playlist_entry_id": 1, "file_error": "loading failed"})
err2 = a.status()["playback_error"]
ok(err2["id"] == first_id + 2 and err2["file"] == "a.mp4" and err2["message"] == "loading failed", "alta eroare primeste id nou: %s" % err2)
a.player.report_error({"event": "end-file", "reason": "error", "playlist_entry_id": 99})
err3 = a.status()["playback_error"]
ok(err3["id"] == first_id + 3 and err3["file"] is None and err3["message"] == "eroare necunoscuta", "intrare necunoscuta si fara file_error: fisier null, mesaj implicit: %s" % err3)
a.player.stop()
print("GATA" if not bad else "ESUATE"); sys.exit(1 if bad else 0)
