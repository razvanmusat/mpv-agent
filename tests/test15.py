import sys, os, tempfile
sys.path.insert(0, ".."); import agent
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)
FULL = """# comentariu
SSH_TARGET=u@h
SSH_KEY=/k/key
SSH_KNOWN_HOSTS="/k/known hosts"
REMOTE_PROGRAM=p.json
REMOTE_CLIPS_DIR=.
VPS_BIND=127.0.0.1
VPS_PORT=18080
AGENT_PORT=8765
CACHE_DIR=/c
MPV_SOCKET=/s.sock
MPV_ARGS=--drm-mode=1280x720 --x=1
"""
def load(text):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, ".env"); open(p, "w").write(text)
        try:
            agent.load_env(p); return None
        except ValueError as e:
            return str(e)
ok(load(FULL) is None, "un .env complet se incarca")
ok(agent.cfg["ssh_target"] == "u@h" and agent.cfg["port_vps"] == 18080 and agent.cfg["port_agent"] == 8765, "valorile si porturile (int) sunt corecte")
ok(agent.cfg["ssh_known_hosts"] == "/k/known hosts" and agent.cfg["mpv_args"] == ["--drm-mode=1280x720", "--x=1"], "ghilimele si MPV_ARGS pe spatii")
o = agent.ssh_options()
ok("/k/key" in o and "UserKnownHostsFile=/k/known hosts" in o and o[:2] == ["-F", "/dev/null"] and "StrictHostKeyChecking=yes" in o, "optiunile ssh vin din .env, fara fisier ssh_config")
e = load(FULL.replace("SSH_KEY=/k/key\n", "").replace("VPS_PORT=18080", "VPS_PORT=abc"))
ok(e and "lipseste SSH_KEY" in e and "VPS_PORT" in e, "lipsuri si port gresit raportate deodata: %s" % e)
ok("cheie necunoscuta FOO" in (load(FULL + "FOO=1\n") or ""), "cheie necunoscuta respinsa")
ok(load(FULL + "ceva fara egal\n") is not None, "linie gresita respinsa")
print("GATA" if not bad else "ESUATE"); sys.exit(1 if bad else 0)
