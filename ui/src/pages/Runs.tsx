import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

const color: Record<string, string> = { done: 'text-good', running: 'text-accent', queued: 'text-mute',
  failed: 'text-bad', interrupted: 'text-warn' }

export default function Runs() {
  const [runs, setRuns] = useState<any[]>([]); const [sweeps, setSweeps] = useState<any[]>([])
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [r, s] = await Promise.all([api('/api/runs'), api('/api/sweeps')])
        if (alive) { setRuns(r); setSweeps(s) }
      } catch (e: any) { setErr(e.message) }
    }
    load(); const h = setInterval(load, 2000)
    return () => { alive = false; clearInterval(h) }
  }, [])
  return (
    <div className="space-y-6 max-w-6xl">
      {err && <div className="text-bad text-sm">{err}</div>}
      <section>
        <h2 className="text-lg font-semibold mb-2">Sweeps</h2>
        <div className="card overflow-x-auto"><table className="w-full">
          <thead><tr><th className="th">Sweep</th><th className="th">State</th><th className="th">Progress</th><th className="th">Variants</th></tr></thead>
          <tbody>
            {sweeps.map(s => (
              <tr key={s.id}>
                <td className="td"><Link className="text-accent hover:underline" to={`/sweeps/${s.id}`}>{s.name} · {s.id}</Link></td>
                <td className={`td ${color[s.state]}`}>{s.state}</td>
                <td className="td">{s.done ?? 0}/{s.total ?? '?'}</td>
                <td className="td text-mute">{(s.variants || []).join(', ')}</td>
              </tr>))}
            {!sweeps.length && <tr><td className="td text-mute" colSpan={4}>No sweeps yet.</td></tr>}
          </tbody></table></div>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-2">Single runs (with replay)</h2>
        <div className="card overflow-x-auto"><table className="w-full">
          <thead><tr><th className="th">Run</th><th className="th">State</th><th className="th">Variant</th><th className="th">Seed</th>
            <th className="th">Agents</th><th className="th">On-time %</th><th className="th">Conflicts</th><th className="th">Violations</th></tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id}>
                <td className="td"><Link className="text-accent hover:underline" to={`/runs/${r.id}`}>{r.id}</Link></td>
                <td className={`td ${color[r.state]}`}>{r.state}</td>
                <td className="td">{r.variant}</td><td className="td">{r.seed}</td><td className="td">{r.n_agents}</td>
                <td className="td">{r.headline ? Number(r.headline.tcr_on_time).toFixed(1) : '—'}</td>
                <td className="td">{r.headline?.conflicts ?? '—'}</td>
                <td className={`td ${r.headline?.violations ? 'text-bad font-semibold' : ''}`}>{r.headline?.violations ?? '—'}</td>
              </tr>))}
            {!runs.length && <tr><td className="td text-mute" colSpan={8}>No runs yet. Start one from Scenarios.</td></tr>}
          </tbody></table></div>
      </section>
    </div>
  )
}
