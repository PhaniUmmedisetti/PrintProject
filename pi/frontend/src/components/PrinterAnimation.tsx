import { motion } from 'framer-motion'

/**
 * Pure CSS/SVG animated printer — no external assets needed.
 * Shows paper sliding out of a printer body in a loop.
 */
export default function PrinterAnimation() {
  return (
    <div className="flex items-center justify-center" style={{ width: 150, height: 150 }}>
      <svg viewBox="0 0 120 120" width={150} height={150} fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Printer body */}
        <rect x="10" y="44" width="100" height="50" rx="8" fill="#1e293b" stroke="#334155" strokeWidth="2" />

        {/* Paper tray slot */}
        <rect x="28" y="52" width="64" height="6" rx="2" fill="#0f172a" />

        {/* Printer top input */}
        <rect x="30" y="28" width="60" height="18" rx="4" fill="#1e293b" stroke="#334155" strokeWidth="2" />

        {/* Status light */}
        <motion.circle
          cx="88" cy="82" r="5"
          fill="#06b6d4"
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ repeat: Infinity, duration: 1.2, ease: 'easeInOut' }}
        />

        {/* Animated paper coming out */}
        <motion.rect
          x="38" y="55" width="44" height="28" rx="3"
          fill="#f8fafc" stroke="#cbd5e1" strokeWidth="1.5"
          initial={{ y: 55 }}
          animate={{ y: [28, 60] }}
          transition={{ repeat: Infinity, duration: 1.8, ease: 'easeInOut', repeatDelay: 0.4 }}
        />

        {/* Paper lines */}
        <motion.g
          initial={{ y: 55 }}
          animate={{ y: [28, 60] }}
          transition={{ repeat: Infinity, duration: 1.8, ease: 'easeInOut', repeatDelay: 0.4 }}
        >
          <line x1="45" y1="64" x2="75" y2="64" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="45" y1="69" x2="70" y2="69" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="45" y1="74" x2="72" y2="74" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
        </motion.g>

        {/* Wheels on sides */}
        <circle cx="18" cy="69" r="5" fill="#0f172a" stroke="#334155" strokeWidth="2" />
        <circle cx="102" cy="69" r="5" fill="#0f172a" stroke="#334155" strokeWidth="2" />
      </svg>
    </div>
  )
}
