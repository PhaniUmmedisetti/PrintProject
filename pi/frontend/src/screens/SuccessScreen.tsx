import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

const AUTO_RETURN_SECS = 30
const COUNTDOWN_START  = 10

interface Props {
  onDone: () => void
}

export default function SuccessScreen({ onDone }: Props) {
  const [secondsLeft, setSecondsLeft] = useState(AUTO_RETURN_SECS)

  useEffect(() => {
    const id = setInterval(() => {
      setSecondsLeft(s => {
        if (s <= 1) {
          clearInterval(id)
          onDone()
          return 0
        }
        return s - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [onDone])

  const showCountdown = secondsLeft <= COUNTDOWN_START

  return (
    <motion.div
      key="success"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="w-full h-full flex flex-col items-center justify-center gap-4 bg-surface px-4"
    >
      {/* Animated checkmark */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 220, damping: 14, delay: 0.1 }}
        className="w-24 h-24 rounded-full bg-emerald-500/20 flex items-center justify-center"
      >
        <motion.svg
          viewBox="0 0 52 52"
          className="w-14 h-14"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.5, delay: 0.3, ease: 'easeOut' }}
        >
          <motion.path
            fill="none"
            stroke="#10b981"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14 27 L22 35 L38 18"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          />
        </motion.svg>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="flex flex-col items-center gap-3"
      >
        <h1 className="text-kiosk-xl font-black text-slate-100 text-center">
          Your print is ready!
        </h1>
        <p className="text-kiosk-md text-slate-400 text-center">
          Please collect your print from the tray.
        </p>
      </motion.div>

      <motion.button
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45 }}
        whileTap={{ scale: 0.96 }}
        onClick={onDone}
        className="
          bg-emerald-500 hover:bg-emerald-400
          text-slate-950 font-black
          text-kiosk-lg px-10 py-3 rounded-xl
          shadow-lg shadow-emerald-500/30
          transition-all duration-150 touch-target
        "
      >
        Done
      </motion.button>

      {showCountdown && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-kiosk-sm text-slate-600"
        >
          Returning to home in {secondsLeft}s…
        </motion.p>
      )}
    </motion.div>
  )
}
