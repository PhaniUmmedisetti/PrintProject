import { motion } from 'framer-motion'

interface Props {
  message: string
  onRetry: () => void
  onCancel: () => void
}

export default function ErrorScreen({ message, onRetry, onCancel }: Props) {
  return (
    <motion.div
      key="error"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="w-full h-full flex flex-col items-center justify-center gap-8 bg-surface"
    >
      {/* Error icon */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 220, damping: 14 }}
        className="w-36 h-36 rounded-full bg-red-500/20 flex items-center justify-center"
      >
        <span className="text-[4rem] leading-none">✕</span>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="flex flex-col items-center gap-3 px-8 max-w-xl text-center"
      >
        <h1 className="text-kiosk-xl font-black text-slate-100">Something went wrong</h1>
        <p className="text-kiosk-md text-slate-400">{message}</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="flex gap-5"
      >
        <button
          onClick={onCancel}
          className="
            border-2 border-slate-600 hover:border-slate-400
            text-slate-300 font-bold
            text-kiosk-md px-10 py-5 rounded-2xl
            transition-all duration-150 touch-target
          "
        >
          Cancel
        </button>
        <button
          onClick={onRetry}
          className="
            bg-accent hover:bg-accent-hover
            text-slate-950 font-black
            text-kiosk-md px-10 py-5 rounded-2xl
            shadow-lg shadow-accent/30
            transition-all duration-150 touch-target
          "
        >
          Try Again
        </button>
      </motion.div>
    </motion.div>
  )
}
