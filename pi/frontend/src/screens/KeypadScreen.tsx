import { useState } from "react";
import { motion } from "framer-motion";

import CodeKeypad from "../components/CodeKeypad";
import { InvalidCodeError, PrinterNotReadyError, startPrint } from "../api/piBackend";
import type { StartPrintResponse } from "../api/piBackend";

const CODE_LENGTH = 6;

interface Props {
  onBack: () => void;
  onCodeAccepted: (job: StartPrintResponse) => void;
  onError: (msg: string) => void;
}

export default function KeypadScreen({ onBack, onCodeAccepted, onError }: Props) {
  const [code, setCode] = useState("");
  const [shaking, setShaking] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (code.length !== CODE_LENGTH || loading) return;
    setLoading(true);
    setErrorMsg("");
    try {
      const job = await startPrint(code);
      onCodeAccepted(job);
    } catch (err) {
      if (err instanceof InvalidCodeError) {
        setErrorMsg("Invalid or expired OTP. Please try again.");
        setShaking(true);
        setTimeout(() => setShaking(false), 500);
        setCode("");
      } else if (err instanceof PrinterNotReadyError) {
        onError(err.message);
      } else {
        onError("Could not reach the print server. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      key="keypad"
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
          Enter Your OTP
        </h1>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-4">
        <CodeKeypad value={code} onChange={setCode} shaking={shaking} errorMsg={errorMsg} />

        <motion.button
          onClick={handleSubmit}
          disabled={code.length !== CODE_LENGTH || loading}
          whileTap={{ scale: 0.96 }}
          className={`
            mt-6 w-full max-w-lg
            text-kiosk-lg font-black py-6 rounded-2xl
            transition-all duration-200 touch-target
            ${
              code.length === CODE_LENGTH && !loading
                ? "bg-accent hover:bg-accent-hover text-slate-950 shadow-lg shadow-accent/30"
                : "bg-slate-800 text-slate-600 cursor-not-allowed"
            }
          `}
        >
          {loading ? "Checking..." : "Submit OTP"}
        </motion.button>
      </div>
    </motion.div>
  );
}
