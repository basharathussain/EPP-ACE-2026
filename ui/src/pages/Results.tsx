import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, num } from '../lib/api'

const METRICS: [string, string, number, boolean][] = [   // key, label, digits, higherIsBetter
  ['tcr_on_time', 'On-time completion %', 1, true], ['completion_rate', 'Completion %', 1, true],
  ['throughput', 'Throughput (tasks/step)', 3, true], ['path_efficiency', 'Path efficiency', 3, true],
  ['mean_task_latency', 'Task latency (steps)', 1, false], ['mean_density', 'Mean density (evaluator)', 3, false],
  ['conflicts', 'Conflicts left to arbiter', 0, false], ['mean_wait_per_task', 'Wait steps per task', 1, false],
  ['adaptation_time', 'Adaptation time (steps)', 1, false],
]

function Bars({ rows, metric, digits }: { rows: any[]; metric: string; digits: number }) {
  const vals = rows.map(r => r[metric]?.mean ?? 0)
  const max = Math.max(...rows.map(r => (r[metric]?.mean ?? 0) + (r[metric]?.ci ?? 0)), 1e-9)
  const W = 520, rowH = 28, pad = 150
  return (
    <svg width={W + pad + 60} height={rows.length * rowH + 8} role="img" aria-label={`${metric} by variant`}>
      {rows.map((r, i) => {
        const m = r[metric]?.mean, ci = r[metric]?.ci ?? 0
        const x = (v: number) => pad + (v / max) * W
        return (
          <g key={r.variant} transform={`translate(0,${i * rowH + 4})`}>
            <text x={pad - 8} y={15} textAnchor="end" fill="#8aa0c4" fontSize="12">{r.variant}</text>
            <rect x={pad} y={3} width={Math.max(0, x(m ?? 0) - pad)} height={16} fill="#4aa3ff" rx={2} />
            {ci > 0 && <g stroke="#e6ecf8" strokeWidth={1.5}>
              <line x1={x(Math.max(0, m - ci))} x2={x(m + ci)} y1={11} y2={11} />
              <line x1={x(Math.max(0, m - ci))} x2={x(Math.max(0, m - ci))} y1={6} y2={16} />
              <line x1={x(m + ci)} x2={x(m + ci)} y1={6} y2={16} /></g>}
            <text x={x((m ?? 0) + ci) + 8} y={15} fill="#e6ecf8" fontSize="12">{num(m, digits)}</text>
          </g>)
      })}
      <title>{vals.join(', ')}</title>
    </svg>)
}

export default function Results() {
  const { id } = useParams()
  const [st, setSt] = useState<any>(null); const [sm, setSm] = useState<any>(null)
  const [baseline, setBaseline] = useState<string>(''); const [metric, setMetric] = useState('tcr_on_time')
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await api(`/api/sweeps/${id}`)
        if (!alive) return
        setSt(s.status)
        if (s.status.state === 'done') {
          setSm(await api(`/api/sweeps/${id}/summary${baseline ? `?baseline=${baseline}` : ''}`))
        } else if (s.status.state === 'running') setTimeout(tick, 1500)
      } catch (e: any) { setErr(e.message) }
    }
    tick(); return () => { alive = false }
  }, [id, baseline])

  if (err) return <div className="text-bad">{err}</div>
  if (!st) return <div className="text-mute">Loading…</div>
  if (st.state !== 'done' || !sm) return (
    <div className="max-w-xl space-y-2">
      <h1 className="text-xl font-semibold">{st.name}</h1>
      <div className="card p-4">State: <b>{st.state}</b>{st.error && <div className="text-bad text-sm mt-2">{st.error}</div>}
        <div className="h-2 bg-bg rounded mt-3 overflow-hidden"><div className="h-full bg-accent" style={{ width: `${100 * (st.done ?? 0) / (st.total || 1)}%` }} /></div>
        <div className="text-xs text-mute mt-1">{st.done ?? 0}/{st.total} runs</div></div></div>)

  const [, label, digits] = METRICS.find(m => m[0] === metric)!
  const paired = sm.paired.filter((p: any) => p.metric === metric)
  return (
    <div className="max-w-6xl space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div><h1 className="text-xl font-semibold">{st.name} <span className="text-mute text-sm">· {id}</span></h1>
          <p className="text-sm text-mute">{sm.runs} runs · {sm.seeds} seeds per variant · paired on identical scenario and seed</p></div>
        <div className="flex gap-2">
          <a className="btn2" href={`/api/sweeps/${id}/export?fmt=csv`} download={`${id}.csv`}>CSV</a>
          <a className="btn2" href={`/api/sweeps/${id}/export?fmt=latex`} target="_blank" rel="noreferrer">LaTeX table</a></div>
      </div>

      <div className="space-y-2">
        {sm.violations > 0 && <div className="card p-3 border-bad text-bad text-sm">Safety violations detected in {sm.violations} step-events. Results are invalid until this is zero.</div>}
        {sm.seeds < 30 && <div className="card p-3 border-warn text-warn text-sm">{sm.seeds} seeds: exploratory. The experimental protocol requires at least 30 per condition before any claim.</div>}
        {sm.censored_tasks > 0 && <div className="card p-3 text-mute text-sm">{sm.censored_tasks} tasks were still open at the end and are excluded from rates (censored), not counted as failures.</div>}
      </div>

      <div className="card overflow-x-auto"><table className="w-full">
        <thead><tr><th className="th">Variant</th>{METRICS.map(m => <th key={m[0]} className="th">{m[1]}</th>)}</tr></thead>
        <tbody>{sm.summary.map((r: any) => (
          <tr key={r.variant}><td className="td font-medium">{r.variant}</td>
            {METRICS.map(([k, , d]) => <td key={k} className="td">{num(r[k].mean, d)}<span className="text-mute text-xs"> ±{num(r[k].sd, d)}</span></td>)}</tr>))}</tbody>
      </table></div>

      <div className="card p-4 space-y-3">
        <div className="flex gap-3 items-center flex-wrap">
          <label className="text-sm text-mute">Metric
            <select className="inp ml-2 w-64 inline-block" value={metric} onChange={e => setMetric(e.target.value)}>
              {METRICS.map(m => <option key={m[0]} value={m[0]}>{m[1]}</option>)}</select></label>
          <label className="text-sm text-mute">Baseline
            <select className="inp ml-2 w-48 inline-block" value={sm.baseline} onChange={e => setBaseline(e.target.value)}>
              {sm.variants.map((v: string) => <option key={v}>{v}</option>)}</select></label>
        </div>
        <div className="overflow-x-auto"><Bars rows={sm.summary} metric={metric} digits={digits} /></div>
        <div className="text-[11px] text-mute">Bars: mean over seeds; whiskers: normal-approximation 95% CI.</div>
      </div>

      <div className="card overflow-x-auto">
        <div className="px-3 pt-3 lbl">{label}: each variant vs {sm.baseline} (paired)</div>
        <table className="w-full"><thead><tr>
          {['Variant', 'n', 'Mean diff', '95% CI (bootstrap)', 'Wilcoxon p', 'Holm p', 'Cliff’s δ'].map(h => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{paired.map((p: any) => (
            <tr key={p.variant}><td className="td font-medium">{p.variant}</td><td className="td">{p.n}</td>
              <td className="td">{num(p.mean_diff, digits + 1)}</td>
              <td className="td">[{num(p.ci_lo, digits + 1)}, {num(p.ci_hi, digits + 1)}]</td>
              <td className="td">{num(p.p, 4)}</td>
              <td className={`td ${p.p_holm < 0.05 ? 'text-good font-semibold' : ''}`}>{num(p.p_holm, 4)}</td>
              <td className="td">{num(p.cliffs_delta, 2)}</td></tr>))}
            {!paired.length && <tr><td className="td text-mute" colSpan={7}>No paired rows (need ≥ 2 shared seeds).</td></tr>}</tbody></table>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card overflow-x-auto"><div className="px-3 pt-3 lbl">On-time completion by priority class (%)</div>
          <table className="w-full"><thead><tr><th className="th">Variant</th>{['critical', 'high', 'medium', 'low'].map(c => <th key={c} className="th">{c}</th>)}</tr></thead>
            <tbody>{Object.entries(sm.by_class).map(([v, c]: any) => (
              <tr key={v}><td className="td font-medium">{v}</td>{['critical', 'high', 'medium', 'low'].map(k => <td key={k} className="td">{num(c[k], 1)}</td>)}</tr>))}</tbody></table></div>
        <div className="card overflow-x-auto"><div className="px-3 pt-3 lbl">Congestion reduction vs {sm.baseline} (evaluator density)</div>
          <table className="w-full"><thead><tr><th className="th">Variant</th><th className="th">Mean density</th><th className="th">Reduction %</th></tr></thead>
            <tbody>{sm.congestion_reduction.map((r: any) => (
              <tr key={r.variant}><td className="td font-medium">{r.variant}</td><td className="td">{num(r.mean_density, 3)}</td><td className="td">{num(r.congestion_reduction_pct, 1)}</td></tr>))}</tbody></table></div>
      </div>
    </div>)
}
