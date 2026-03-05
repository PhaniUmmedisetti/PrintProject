import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

import PrinterAnimation from "../components/PrinterAnimation";
import { getJobStatus } from "../api/piBackend";

interface Props {
  jobId: string;
  onDone: () => void;
  onError: (msg: string) => void;
}

export default function PrintingScreen({ jobId, onDone, onError }: Props) {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId);
        if (status.status === "DONE") {
          clearInterval(intervalRef.current!);
          onDone();
        } else if (status.status === "FAILED") {
          clearInterval(intervalRef.current!);
          onError(
            status.error_msg
              ? `Printing failed: ${status.error_msg}`
              : "Printing failed. Please contact staff."
          );
        }
      } catch {
        // Keep polling through transient local failures.
      }
    }, 2000);

    return () => clearInterval(intervalRef.current!);
  }, [jobId, onDone, onError]);

  return (
    <motion.div
      key="printing"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="w-full h-full flex flex-col items-center justify-center gap-4 bg-surface px-4"
    >
      <PrinterAnimation />

      <motion.p
        className="text-kiosk-xl font-bold text-slate-100 text-center px-8"
        animate={{ opacity: [1, 0.5, 1] }}
        transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
      >
        Printing your document...
      </motion.p>

      <p className="text-kiosk-md text-slate-500 text-center px-8">
        Please wait. Collect your print from the tray.
      </p>
    </motion.div>
  );
}
