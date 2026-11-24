import os
import tempfile
import time

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["EPPACE_WORKERS"] = "2"

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

c = TestClient(app)


def wait(url, key="status", tries=120):
    for _ in range(tries):
        s = c.get(url).json()[key]
        if s["state"] in ("done", "failed"):
            return s
        time.sleep(0.5)
    raise AssertionError("timeout")


def test_meta_and_validation():
    assert c.get("/api/health").json()["ok"]
    m = c.get("/api/meta").json()
    assert "eppace" in m["variants"] and m["defaults"]["n_agents"] > 0
    assert c.post("/api/runs", json={"config": {"variant": "nope"}}).status_code == 422
    assert c.post("/api/runs", json={"config": {"bogus": 1}}).status_code == 422
    assert c.get("/api/runs/does-not-exist").status_code == 404


def test_run_trace_events():
    r = c.post("/api/runs", json={"config": {"variant": "eppace", "steps": 60, "n_agents": 12}}).json()
    s = wait(f"/api/runs/{r['id']}")
    assert s["state"] == "done", s
    t = c.get(f"/api/runs/{r['id']}/trace").json()
    assert t["T"] == 60 and t["N"] == 12 and len(t["pos"]) > 100
    plans = c.get(f"/api/runs/{r['id']}/events", params={"kind": "plan"}).json()
    assert plans and "path" in plans[0]
    assert r["id"] in [x["id"] for x in c.get("/api/runs").json()]


def test_sweep_summary_export():
    exp = {"name": "t", "base": {"steps": 50, "n_agents": 10, "height": 15, "width": 15},
           "variants": ["b1_astar", "eppace"], "seeds": 4}
    sw = c.post("/api/sweeps", json={"experiment": exp, "workers": 2}).json()
    assert sw["runs"] == 8
    assert wait(f"/api/sweeps/{sw['id']}")["state"] == "done"
    sm = c.get(f"/api/sweeps/{sw['id']}/summary").json()
    assert sm["baseline"] == "b1_astar" and sm["violations"] == 0 and sm["paired"]
    assert "\\begin{tabular}" in c.get(f"/api/sweeps/{sw['id']}/export", params={"fmt": "latex"}).text
    assert c.get(f"/api/sweeps/{sw['id']}/export").text.startswith("variant")


def test_spa_fallback_and_api_404(tmp_path, monkeypatch):
    # direct loads of client routes must return the app shell, unknown API paths a real 404
    import importlib
    ui = tmp_path / "dist"; (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<html>shell</html>"); (ui / "assets" / "a.js").write_text("x")
    monkeypatch.setenv("UI_DIR", str(ui))
    import server.app as mod
    mod = importlib.reload(mod)
    cc = TestClient(mod.app)
    assert "shell" in cc.get("/runs/abc").text and cc.get("/assets/a.js").text == "x"
    assert cc.get("/api/nope").status_code == 404


def test_rejects_nonsense_counts():
    for bad in ({"n_agents": -49}, {"n_agents": 0}, {"steps": 0}, {"task_rate": -1}):
        assert c.post("/api/runs", json={"config": bad}).status_code == 422, bad
