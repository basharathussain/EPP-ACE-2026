import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import Scenarios from './pages/Scenarios'
import Runs from './pages/Runs'
import Replay from './pages/Replay'
import Results from './pages/Results'

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded text-sm ${isActive ? 'bg-accent text-bg font-semibold' : 'text-mute hover:text-ink'}`

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line px-6 py-3 flex items-center gap-6">
        <div className="flex items-center gap-2"><span className="w-3 h-3 bg-accent" />
          <b className="tracking-wide">EPP-ACE Lab</b>
          <span className="text-xs text-mute">deterministic reference implementation</span></div>
        <nav className="flex gap-1">
          <NavLink to="/scenarios" className={link}>Scenarios</NavLink>
          <NavLink to="/runs" className={link}>Runs</NavLink>
        </nav>
      </header>
      <main className="flex-1 p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/scenarios" replace />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:id" element={<Replay />} />
          <Route path="/sweeps/:id" element={<Results />} />
        </Routes>
      </main>
    </div>
  )
}
