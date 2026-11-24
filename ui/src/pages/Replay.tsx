import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, b64bytes, num } from '../lib/api'

// Perceptual-ish dark->bright scale (viridis stops). Not a rainbow: order is readable in greyscale.
const STOPS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]]
function viridis(v: number): string {
  const x = Math.min(1, Math.max(0, v)) * (STOPS.length - 1), i = Math.min(STOPS.length - 2, Math.floor(x)), f = x - i
  const c = STOPS[i].map((s, k) => Math.round(s + (STOPS[i + 1][k] - s) * f))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
const MODULE: Record<string, string> = { assign: 'PMF', plan: 'DPPE', arb: 'Coordination', failure: 'Adaptation',
  weights: 'Adaptation', agent_failure: 'Adaptation', done: 'Evaluator' }

type Trace = { T: number; N: number; H: number; W: number; pos: Int16Array; status: Int8Array; walls: Uint8Array;
  cong: Uint8Array; cong_t: number[]; obstacles: number[][][]; tasks: any[]; assigns: number[][]; dones: number[][] }

export default function Replay() {
  const { id } = useParams()
  const [run, setRun] = useState<any>(null); const [tr, setTr] = useState<Trace | null>(null)
  const [plans, setPlans] = useState<any[]>([]); const [arbs, setArbs] = useState<any[]>([])
  const [t, setT] = useState(0); const [playing, setPlaying] = useState(false); const [speed, setSpeed] = useState(8)
  const [sel, setSel] = useState<number | null>(null)
  const [layers, setLayers] = useState({ agents: true, cong: true, paths: false, goals: true })
  const [stepEvents, setStepEvents] = useState<any[]>([]); const [err, setErr] = useState('')
  const [tab, setTab] = useState<'state' | 'inspector'>('state')
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const r = await api(`/api/runs/${id}`)
        if (!alive) return
        setRun(r)
        if (r.status.state === 'done') {
          const [x, p, a] = await Promise.all([api(`/api/runs/${id}/trace`),
            api(`/api/runs/${id}/events?kind=plan&limit=5000`), api(`/api/runs/${id}/events?kind=arb&limit=5000`)])
          if (!alive) return
          setTr({ ...x, pos: new Int16Array(b64bytes(x.pos).buffer), status: new Int8Array(b64bytes(x.status).buffer),
            walls: b64bytes(x.walls), cong: b64bytes(x.cong) })
          setPlans(p); setArbs(a)
        } else if (['queued', 'running'].includes(r.status.state)) setTimeout(tick, 1000)
      } catch (e: any) { setErr(e.message) }
    }
    tick(); return () => { alive = false }
  }, [id])

  // playback
  useEffect(() => {
    if (!playing || !tr) return
    const h = setInterval(() => setT(x => { if (x + 1 >= tr.T) { setPlaying(false); return x } return x + 1 }), 1000 / speed)
    return () => clearInterval(h)
  }, [playing, speed, tr])

  useEffect(() => {
    if (!tr) return
    api(`/api/runs/${id}/events?t=${t}&limit=500`).then(setStepEvents).catch(() => {})
  }, [t, id, tr])

  // latest plan per agent at or before t (for path overlays and the inspector)
  const planByAgent = useMemo(() => {
    const m = new Map<number, any[]>()
    for (const p of plans) { if (!m.has(p.agent)) m.set(p.agent, []); m.get(p.agent)!.push(p) }
    return m
  }, [plans])
  const planAt = (a: number) => {
    const L = planByAgent.get(a) || []; let best = null
    for (const p of L) { if (p.t <= t && p.status === 'ok') best = p; else if (p.t > t) break }
    return best
  }
  const timeline = useMemo(() => {
    if (!tr) return null
    const pl = new Array(tr.T).fill(0), cf = new Array(tr.T).fill(0)
    for (const p of plans) if (p.t < tr.T) pl[p.t]++
    for (const a of arbs) if (a.t < tr.T && a.kind !== 'obstacle' && a.kind !== 'yield') cf[a.t]++
    return { pl, cf, maxp: Math.max(1, ...pl), maxc: Math.max(1, ...cf) }
  }, [tr, plans, arbs])

  const cell = tr ? Math.max(4, Math.min(24, Math.floor(820 / Math.max(tr.W, tr.H)))) : 10

  // draw
  useEffect(() => {
    if (!tr || !canvas.current) return
    const c = canvas.current, g = c.getContext('2d')!
    const { H, W, N } = tr
    c.width = W * cell; c.height = H * cell
    g.fillStyle = '#0b1220'; g.fillRect(0, 0, c.width, c.height)
    for (let r = 0; r < H; r++) for (let q = 0; q < W; q++)
      if (tr.walls[r * W + q]) { g.fillStyle = '#2a3550'; g.fillRect(q * cell, r * cell, cell, cell) }
    if (layers.cong && tr.cong_t.length) {
      let f = 0; for (let i = 0; i < tr.cong_t.length; i++) if (tr.cong_t[i] <= t) f = i
      for (let r = 0; r < H; r++) for (let q = 0; q < W; q++) {
        const v = tr.cong[f * H * W + r * W + q]
        if (v > 12) { g.globalAlpha = 0.25 + 0.55 * (v / 255); g.fillStyle = viridis(v / 255); g.fillRect(q * cell, r * cell, cell, cell) }
      }
      g.globalAlpha = 1
    }
    g.strokeStyle = 'rgba(138,160,196,0.08)'; g.lineWidth = 1
    if (cell >= 8) for (let r = 0; r <= H; r++) { g.beginPath(); g.moveTo(0, r * cell); g.lineTo(W * cell, r * cell); g.stroke() }
    if (cell >= 8) for (let q = 0; q <= W; q++) { g.beginPath(); g.moveTo(q * cell, 0); g.lineTo(q * cell, H * cell); g.stroke() }
    // moving obstacles
    g.fillStyle = '#f5b942'
    for (const [r, q] of tr.obstacles[t] || []) if (r >= 0) g.fillRect(q * cell + 1, r * cell + 1, cell - 2, cell - 2)
    // goals of busy agents
    const task = new Map<number, number>(), doneT = new Map<number, number>()
    for (const [dt, tk] of tr.dones) doneT.set(tk, dt)
    for (const [at, tk, a] of tr.assigns) if (at <= t) task.set(a, tk)
    const goalOf = (a: number) => { const tk = task.get(a); if (tk === undefined) return null
      const d = doneT.get(tk); if (d !== undefined && d <= t) return null; return tr.tasks[tk] }
    const P = (a: number) => [tr.pos[(t * N + a) * 2], tr.pos[(t * N + a) * 2 + 1]]
    if (layers.paths || sel !== null) {
      g.lineWidth = 1.5
      for (let a = 0; a < N; a++) {
        if (!layers.paths && a !== sel) continue
        if (tr.status[t * N + a] !== 1) continue
        const p = planAt(a); if (!p) continue
        const path: number[][] = p.path || []
        g.strokeStyle = a === sel ? '#ffffff' : 'rgba(74,163,255,0.45)'; g.beginPath()
        const [r0, c0] = P(a); g.moveTo(c0 * cell + cell / 2, r0 * cell + cell / 2)
        for (const [r, q] of path.slice(Math.max(0, t - p.t + 1))) g.lineTo(q * cell + cell / 2, r * cell + cell / 2)
        g.stroke()
      }
    }
    if (layers.goals) for (let a = 0; a < N; a++) {
      if (sel !== null && a !== sel && N > 60) continue
      const tk = goalOf(a); if (!tk) continue
      g.strokeStyle = a === sel ? '#ffffff' : '#3ecf8e'; g.lineWidth = 1.5
      g.strokeRect(tk.goal[1] * cell + 2, tk.goal[0] * cell + 2, cell - 4, cell - 4)
    }
    if (layers.agents) for (let a = 0; a < N; a++) {
      const [r, q] = P(a), s = tr.status[t * N + a]
      g.fillStyle = s === 2 ? '#ff5d5d' : s === 1 ? '#4aa3ff' : '#8aa0c4'
      g.beginPath(); g.arc(q * cell + cell / 2, r * cell + cell / 2, Math.max(2, cell * 0.36), 0, 7); g.fill()
      if (a === sel) { g.strokeStyle = '#fff'; g.lineWidth = 2; g.beginPath(); g.arc(q * cell + cell / 2, r * cell + cell / 2, cell * 0.6, 0, 7); g.stroke() }
    }
  }, [tr, t, layers, sel, cell, planByAgent])

  function pick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!tr) return
    const b = e.currentTarget.getBoundingClientRect()
    const x = (e.clientX - b.left) * (e.currentTarget.width / b.width) / cell, y = (e.clientY - b.top) * (e.currentTarget.height / b.height) / cell
    let best = -1, bd = 1.5
    for (let a = 0; a < tr.N; a++) {
      const d = Math.hypot(tr.pos[(t * tr.N + a) * 2 + 1] + 0.5 - x, tr.pos[(t * tr.N + a) * 2] + 0.5 - y)
      if (d < bd) { bd = d; best = a }
    }
    setSel(best >= 0 ? best : null)
  }

  if (err) return <div className="text-bad">{err}</div>
  if (!run) return <div className="text-mute">Loading…</div>
  if (run.status.state !== 'done' || !tr) return (
    <div className="card p-4 max-w-xl">Run {id}: <b>{run.status.state}</b>
      {run.status.error && <pre className="text-bad text-xs mt-2 whitespace-pre-wrap">{run.status.error}</pre>}</div>)

  const m = run.metrics, cfg = run.manifest.config
  const counts = [0, 0, 0]; for (let a = 0; a < tr.N; a++) counts[tr.status[t * tr.N + a]]++
  const created = tr.tasks.filter(k => k.created <= t).length, completed = tr.dones.filter(d => d[0] <= t).length
  const selPlan = sel !== null ? planAt(sel) : null
  const selTask = sel !== null ? (() => { let tk: number | undefined; for (const [at, k, a] of tr.assigns) if (a === sel && at <= t) tk = k
    return tk !== undefined ? tr.tasks[tk] : null })() : null
  const grouped: Record<string, any[]> = {}
  for (const e of stepEvents) (grouped[MODULE[e.event] || e.event] ||= []).push(e)

  return (
    <div className="space-y-4 max-w-[1400px]">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div><h1 className="text-xl font-semibold">{cfg.variant} <span className="text-mute text-sm">· seed {cfg.seed} · {cfg.height}×{cfg.width} · {cfg.n_agents} agents · {id}</span></h1>
          <p className="text-xs text-mute">Replay of a recorded trace. Final metrics below come from the independent evaluator.</p></div>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-center">
          {[['On-time %', num(m.tcr_on_time, 1)], ['Throughput', num(m.throughput, 3)], ['Conflicts', m.conflicts],
            ['Mean density', num(m.mean_density, 3)], ['Path eff.', num(m.path_efficiency, 3)], ['Violations', m.violations]].map(([k, v]) => (
            <div key={k as string} className={`card px-3 py-1.5 ${k === 'Violations' && m.violations ? 'border-bad' : ''}`}>
              <div className="lbl">{k}</div><div className={`text-lg font-semibold ${k === 'Violations' && m.violations ? 'text-bad' : ''}`}>{v}</div></div>))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[170px_1fr_340px]">
        <div className="card p-3 space-y-2 h-fit">
          <div className="lbl">Layers</div>
          {([['agents', 'Agents'], ['goals', 'Goals'], ['paths', `Planned paths${tr.N > 100 ? ' (busy, heavy)' : ''}`], ['cong', 'Congestion']] as const).map(([k, l]) => (
            <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={layers[k]} onChange={e => setLayers({ ...layers, [k]: e.target.checked })} />{l}</label>))}
          <div className="lbl pt-2">Legend</div>
          <div className="text-xs space-y-1 text-mute">
            <div><span className="inline-block w-2.5 h-2.5 rounded-full bg-accent mr-2" />busy agent</div>
            <div><span className="inline-block w-2.5 h-2.5 rounded-full bg-mute mr-2" />idle agent</div>
            <div><span className="inline-block w-2.5 h-2.5 rounded-full bg-bad mr-2" />failed agent</div>
            <div><span className="inline-block w-2.5 h-2.5 bg-warn mr-2" />moving obstacle</div>
            <div><span className="inline-block w-2.5 h-2.5 border border-good mr-2" />goal</div>
            <div className="pt-1 h-2 rounded" style={{ background: `linear-gradient(90deg,${viridis(0.05)},${viridis(0.5)},${viridis(1)})` }} />
            <div className="flex justify-between"><span>low</span><span>congestion</span><span>high</span></div>
          </div>
          <div className="text-[11px] text-mute pt-2">Click an agent to inspect it.</div>
        </div>

        <div className="space-y-3 min-w-0">
          <div className="card p-2 overflow-auto flex justify-center"><canvas ref={canvas} onClick={pick} className="cursor-crosshair max-w-full" style={{ imageRendering: 'pixelated' }} /></div>
          <div className="card p-3 space-y-2">
            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn2" onClick={() => setT(0)}>⏮</button>
              <button className="btn2" onClick={() => setT(Math.max(0, t - 1))}>◀</button>
              <button className="btn w-20" onClick={() => { if (t >= tr.T - 1) setT(0); setPlaying(!playing) }}>{playing ? 'Pause' : 'Play'}</button>
              <button className="btn2" onClick={() => setT(Math.min(tr.T - 1, t + 1))}>▶</button>
              <label className="text-xs text-mute flex items-center gap-2">speed
                <select className="inp w-20" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[2, 4, 8, 16, 32, 64].map(s => <option key={s} value={s}>{s}/s</option>)}</select></label>
              <span className="ml-auto font-mono text-sm">t = {t} / {tr.T - 1}</span>
            </div>
            {timeline && (
              <svg viewBox={`0 0 ${tr.T} 30`} preserveAspectRatio="none" className="w-full h-10" role="img" aria-label="events per step">
                {timeline.pl.map((v, i) => <rect key={`p${i}`} x={i} y={15 - 14 * v / timeline.maxp} width={1} height={14 * v / timeline.maxp} fill="#4aa3ff" />)}
                {timeline.cf.map((v, i) => <rect key={`c${i}`} x={i} y={16} width={1} height={14 * v / timeline.maxc} fill="#f5b942" />)}
                <rect x={t} y={0} width={Math.max(1, tr.T / 300)} height={30} fill="#fff" />
              </svg>)}
            <input type="range" min={0} max={tr.T - 1} value={t} onChange={e => setT(Number(e.target.value))} className="w-full" aria-label="time step" />
            <div className="text-[11px] text-mute">Above the slider: <span className="text-accent">replans per step</span> (up) and <span className="text-warn">conflicts left to the arbiter</span> (down).</div>
          </div>
        </div>

        <div className="card h-fit">
          <div className="flex border-b border-line">
            {(['state', 'inspector'] as const).map(k => (
              <button key={k} onClick={() => setTab(k)} className={`flex-1 py-2 text-sm ${tab === k ? 'text-accent border-b-2 border-accent' : 'text-mute'}`}>{k === 'state' ? 'State' : 'Inspector'}</button>))}
          </div>
          <div className="p-3 space-y-3 text-sm max-h-[620px] overflow-auto">
            {tab === 'state' ? (<>
              <div className="grid grid-cols-2 gap-2">
                {[['Busy agents', counts[1]], ['Idle agents', counts[0]], ['Failed agents', counts[2]],
                  ['Tasks created', created], ['Tasks completed', completed], ['Open tasks', created - completed]].map(([k, v]) => (
                  <div key={k as string} className="bg-bg rounded p-2"><div className="lbl">{k}</div><div className="text-base font-semibold">{v}</div></div>))}
              </div>
              {sel !== null ? (
                <div className="bg-bg rounded p-2 space-y-1">
                  <div className="lbl">Agent {sel}</div>
                  <div>cell ({tr.pos[(t * tr.N + sel) * 2]}, {tr.pos[(t * tr.N + sel) * 2 + 1]}) · {['idle', 'busy', 'failed'][tr.status[t * tr.N + sel]]}</div>
                  {selTask && <div className="text-mute">task {selTask.id} · {selTask.cls} · priority {num(selTask.priority, 2)} · deadline {selTask.deadline}</div>}
                  {selPlan && <div className="text-mute">plan v{selPlan.version} made at t={selPlan.t} ({selPlan.reason}) · cost {selPlan.cost} · {selPlan.steps} steps</div>}
                </div>) : <div className="text-mute text-xs">No agent selected.</div>}
            </>) : (<>
              <div className="text-xs text-mute">What each module did at step {t}. Cost split is the planner’s own accounting.</div>
              {Object.keys(grouped).length === 0 && <div className="text-mute">No module events at this step.</div>}
              {['PMF', 'DPPE', 'Coordination', 'Adaptation', 'Evaluator'].filter(k => grouped[k]).map(k => (
                <div key={k} className="bg-bg rounded p-2">
                  <div className="lbl mb-1">{k} · {grouped[k].length}</div>
                  <ul className="space-y-1 text-xs font-mono">
                    {grouped[k].slice(0, 25).map((e, i) => (
                      <li key={i} className={e.agent === sel ? 'text-white' : 'text-mute'}>
                        {e.event === 'plan' && <>agent {e.agent}: {e.status} · {e.reason} · cost {e.cost} · {e.steps} steps · congestion {e.congestion} · expanded {e.expanded} · weights v{e.weights_v}</>}
                        {e.event === 'assign' && <>task {e.task} → agent {e.agent}</>}
                        {e.event === 'arb' && <>{e.kind}: agent {e.agent}{e.by !== undefined ? ` (by ${e.by})` : ''}</>}
                        {e.event === 'weights' && <>weights v{e.version}: α {num(e.alpha, 2)} β {num(e.beta, 2)} ε {num(e.eps, 2)} (hot {num(e.frac_hot, 3)})</>}
                        {['failure', 'agent_failure'].includes(e.event) && <>agent {e.agent} failed</>}
                        {e.event === 'done' && <>task {e.task} done by agent {e.agent} · {e.on_time ? 'on time' : 'late'}</>}
                      </li>))}
                    {grouped[k].length > 25 && <li className="text-mute">… {grouped[k].length - 25} more</li>}
                  </ul>
                </div>))}
              <div className="text-[11px] text-mute">CDS inputs are not stored per step; its output is the congestion layer.</div>
            </>)}
          </div>
        </div>
      </div>
    </div>)
}
