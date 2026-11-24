import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, post } from '../lib/api'

type F = { key: string; label: string; step?: number; hint?: string }
const GROUPS: { title: string; fields: F[] }[] = [
  { title: 'Environment', fields: [
    { key: 'height', label: 'Grid height' }, { key: 'width', label: 'Grid width' },
    { key: 'obstacle_density', label: 'Static obstacle density', step: 0.05, hint: 'fraction of cells; unreachable pockets become walls' },
    { key: 'n_agents', label: 'Agents' }, { key: 'n_moving_obstacles', label: 'Moving obstacles' },
    { key: 'steps', label: 'Simulation steps' } ] },
  { title: 'Tasks', fields: [
    { key: 'task_rate', label: 'New tasks per step', step: 0.1, hint: 'Poisson rate; raise it until agents are mostly busy' } ] },
  { title: 'Disturbances', fields: [
    { key: 'comm_loss', label: 'Communication loss', step: 0.05, hint: 'share of agents planning on a stale congestion map' },
    { key: 'agent_failure', label: 'Agent failure', step: 0.05, hint: 'share of agents that die at a seeded time' } ] },
  { title: 'Planner weights (sum to 1)', fields: [
    { key: 'alpha', label: 'α distance', step: 0.05 }, { key: 'beta', label: 'β congestion', step: 0.05 },
    { key: 'eps', label: 'ε safety', step: 0.05 } ] },
]

export default function Scenarios() {
  const nav = useNavigate()
  const [meta, setMeta] = useState<any>(null)
  const [cfg, setCfg] = useState<any>(null)
  const [mode, setMode] = useState<'run' | 'sweep'>('run')
  const [variants, setVariants] = useState<string[]>(['b1_astar', 'b3_prioritized', 'eppace'])
  const [seeds, setSeeds] = useState(10)
  const [name, setName] = useState('experiment')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('')

  useEffect(() => { api('/api/meta').then(m => { setMeta(m); setCfg(m.defaults) }).catch(e => setErr(e.message)) }, [])
  const wsum = useMemo(() => cfg ? cfg.alpha + cfg.beta + cfg.eps : 1, [cfg])
  if (!cfg || !meta) return <div className="text-mute">{err || 'Loading…'}</div>

  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v })
  const bad = Math.abs(wsum - 1) > 1e-6
  const toggle = (v: string) => setVariants(variants.includes(v) ? variants.filter(x => x !== v) : [...variants, v])
  const names = Object.keys(meta.variants).filter(v => !['a1_astar', 'a6_full'].includes(v))
  const load = cfg.n_agents * cfg.steps

  async function go() {
    setBusy(true); setErr('')
    try {
      if (mode === 'run') {
        const r = await post('/api/runs', { config: cfg })
        nav(`/runs/${r.id}`)
      } else {
        const { variant, seed, name: _n, ...base } = cfg
        const r = await post('/api/sweeps', { experiment: { name, base, variants, seeds } })
        nav(`/sweeps/${r.id}`)
      }
    } catch (e: any) { setErr(e.message); setBusy(false) }
  }

  return (
    <div className="max-w-6xl space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div><h1 className="text-xl font-semibold">Scenario builder</h1>
          <p className="text-sm text-mute">Every run is fully described by this configuration and a seed.</p></div>
        <div className="flex rounded border border-line overflow-hidden">
          {(['run', 'sweep'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`px-4 py-1.5 text-sm ${mode === m ? 'bg-accent text-bg font-semibold' : 'text-mute'}`}>
              {m === 'run' ? 'Single run + replay' : 'Sweep (variants × seeds)'}</button>))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {GROUPS.map(g => (
          <div key={g.title} className="card p-4">
            <div className="lbl mb-3">{g.title}</div>
            <div className="grid grid-cols-2 gap-3">
              {g.fields.map(f => (
                <label key={f.key} className="block">
                  <span className="text-xs text-mute">{f.label}</span>
                  <input className="inp mt-1" type="number" step={f.step ?? 1} value={cfg[f.key]}
                         onChange={e => set(f.key, Number(e.target.value))} />
                  {f.hint && <span className="text-[10px] text-mute">{f.hint}</span>}
                </label>))}
              {g.title === 'Tasks' && (
                <label className="block"><span className="text-xs text-mute">Assignment</span>
                  <select className="inp mt-1" value={cfg.assignment} onChange={e => set('assignment', e.target.value)}>
                    <option value="nearest">nearest idle agent (short trips)</option>
                    <option value="longest_idle">longest-idle agent (long trips)</option>
                  </select></label>)}
            </div>
            {g.title.startsWith('Planner') && bad &&
              <div className="text-bad text-xs mt-2">Weights sum to {wsum.toFixed(2)}; they must sum to 1.</div>}
          </div>))}
      </div>

      <div className="card p-4">
        <div className="lbl mb-3">{mode === 'run' ? 'Variant' : 'Variants to compare'}</div>
        {mode === 'run' ? (
          <div className="flex gap-3 items-center flex-wrap">
            <select className="inp max-w-xs" value={cfg.variant} onChange={e => set('variant', e.target.value)}>
              {names.map(v => <option key={v} value={v}>{v}</option>)}</select>
            <label className="flex items-center gap-2 text-sm">Seed
              <input className="inp w-24" type="number" value={cfg.seed} onChange={e => set('seed', Number(e.target.value))} /></label>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {names.map(v => (
                <button key={v} onClick={() => toggle(v)}
                  className={`px-3 py-1 rounded border text-sm ${variants.includes(v) ? 'border-accent text-accent' : 'border-line text-mute'}`}>{v}</button>))}
            </div>
            <div className="flex gap-3 items-end flex-wrap">
              <label className="text-sm">Seeds per variant
                <input className="inp w-28 mt-1" type="number" min={1} value={seeds} onChange={e => setSeeds(Number(e.target.value))} /></label>
              <label className="text-sm">Name
                <input className="inp w-56 mt-1" value={name} onChange={e => setName(e.target.value)} /></label>
              <div className="text-sm text-mute">{variants.length * seeds} runs. The design calls for ≥ 30 seeds for any claim; fewer is exploratory.</div>
            </div>
          </div>)}
      </div>

      {mode === 'run' && load > 400_000 && <div className="text-warn text-sm">agents × steps above 400k: the server refuses single runs this large; use a sweep.</div>}
      {err && <div className="text-bad text-sm">{err}</div>}
      <button className="btn" disabled={busy || bad || !variants.length || (mode === 'run' && load > 400_000)} onClick={go}>
        {busy ? 'Starting…' : mode === 'run' ? 'Run and open replay' : 'Start sweep'}</button>
    </div>
  )
}
