import { motion } from 'framer-motion'
import SlideShow from '../components/SlideShow'

interface Props {
  onPrintNow: () => void
}

export default function LandingScreen({ onPrintNow }: Props) {
  return (
    <motion.div
      key="landing"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="w-full h-full flex flex-col bg-surface"
    >
      {/* Top bar */}
      <div className="flex items-center justify-end px-4 pt-3 pb-2">
        <button
          onClick={onPrintNow}
          className="
            bg-accent hover:bg-accent-hover active:scale-95
            text-slate-950 font-black tracking-wide
            text-kiosk-lg
            px-6 py-3 rounded-xl
            transition-all duration-150
            shadow-lg shadow-accent/30
            touch-target
          "
        >
          Print Now →
        </button>
      </div>

      {/* Hero slideshow — vertically centered in remaining space */}
      <div className="flex-1 flex items-center justify-center px-4">
        <SlideShow />
      </div>

      {/* Subtle bottom brand line */}
      <p className="text-center text-slate-600 text-kiosk-sm pb-3 tracking-widest uppercase">
        Self Service · Secure · Instant
      </p>
    </motion.div>
  )
}
