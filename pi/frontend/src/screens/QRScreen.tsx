import { motion } from "framer-motion";
import QRCode from "react-qr-code";

const WEBAPP_URL: string = import.meta.env.VITE_WEBAPP_URL ?? "https://print.example.com";

interface Props {
  onBack: () => void;
  onEnterCode: () => void;
}

export default function QRScreen({ onBack, onEnterCode }: Props) {
  return (
    <motion.div
      key="qr"
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -60 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="w-full h-full flex flex-col bg-surface"
    >
      <div className="flex items-center px-8 pt-6 pb-2">
        <button
          onClick={onBack}
          className="text-slate-400 hover:text-slate-100 active:scale-95 text-kiosk-md transition-all touch-target px-2"
        >
          Back
        </button>
        <h1 className="flex-1 text-center text-kiosk-xl font-bold text-slate-100 pr-16">
          Upload from your phone
        </h1>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center gap-8 px-8">
        <div className="bg-white p-6 rounded-3xl shadow-2xl shadow-black/50">
          <QRCode value={WEBAPP_URL} size={280} bgColor="#ffffff" fgColor="#0f172a" />
        </div>

        <p className="text-kiosk-md text-slate-300 text-center">Scan with your phone to upload files and pay</p>

        <div className="w-full max-w-md flex items-center gap-4">
          <div className="flex-1 h-px bg-slate-700" />
          <span className="text-kiosk-sm text-slate-500">or</span>
          <div className="flex-1 h-px bg-slate-700" />
        </div>

        <button
          onClick={onEnterCode}
          className="
            w-full max-w-md
            bg-accent hover:bg-accent-hover active:scale-95
            text-slate-950 font-black
            text-kiosk-lg
            py-6 rounded-2xl
            transition-all duration-150
            shadow-lg shadow-accent/30
            touch-target
          "
        >
          Enter OTP
        </button>
      </div>
    </motion.div>
  );
}
