import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

import { confirmPrint, getJobStatus } from "../api/piBackend";
import type { StartPrintResponse } from "../api/piBackend";

interface Props {
  job: StartPrintResponse;
  onConfirm: () => void;
  onError: (msg: string) => void;
}

export default function PreviewScreen({ job, onConfirm, onError }: Props) {
  const [ready, setReady] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const summary = job.job_summary;

  useEffect(() => {
    intervalRef.current = setInterval(async () => {
      try {
        const status = await getJobStatus(job.job_id);
        if (status.status === "READY") {
          clearInterval(intervalRef.current!);
          setReady(true);
        } else if (status.status === "FAILED") {
          clearInterval(intervalRef.current!);
          onError(
            status.error_msg
              ? `Failed to prepare file: ${status.error_msg}`
              : "Failed to prepare your file. Please try again or contact staff."
          );
        }
      } catch {
        // Keep polling through transient local failures.
      }
    }, 2000);

    return () => clearInterval(intervalRef.current!);
  }, [job.job_id, onError]);

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await confirmPrint(job.job_id);
      onConfirm();
    } catch {
      onError("Failed to start printing. Please contact staff.");
    }
  };

  return (
    <motion.div
      key="preview"
      initial={{ opacity: 0, x: 60 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -60 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="w-full h-full flex flex-col bg-surface"
    >
      <div className="px-4 pt-3 pb-1">
        <h1 className="text-center text-kiosk-xl font-bold text-slate-100">Your Print Job</h1>
        <p className="text-center text-kiosk-sm text-slate-400 mt-1">
          {ready ? "Ready to print." : "Preparing your file..."}
        </p>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-3">
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="w-full max-w-xl bg-surface-card rounded-2xl p-4 shadow-xl border border-slate-700/50"
        >
          <div className="mb-3">
            <p className="text-kiosk-md font-bold text-slate-100 text-center">Confirm the print details below.</p>
          </div>

          <div className="h-px bg-slate-700 mb-3" />

          <div className="grid grid-cols-2 gap-2">
            <InfoRow label="Copies" value={String(summary?.copies ?? 1)} />
            <InfoRow label="Color" value={String(summary?.color ?? "BW")} />
            <InfoRow
              label="Price"
              value={`${summary?.currency ?? "INR"} ${formatPrice(summary?.priceCents ?? 0)}`}
            />
            <InfoRow label="Privacy" value="No file preview" />
          </div>
        </motion.div>

        {!ready ? (
          <div className="flex items-center gap-4 text-kiosk-md text-slate-400">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              className="w-8 h-8 border-4 border-slate-600 border-t-accent rounded-full"
            />
            Downloading your file...
          </div>
        ) : (
          <motion.button
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            whileTap={{ scale: 0.96 }}
            onClick={handleConfirm}
            disabled={confirming}
            className="
              w-full max-w-xl
              bg-accent hover:bg-accent-hover
              text-slate-950 font-black
              text-kiosk-lg py-3 rounded-xl
              transition-all duration-150
              shadow-lg shadow-accent/30
              touch-target
            "
          >
            {confirming ? "Starting..." : "Start Printing"}
          </motion.button>
        )}
      </div>
    </motion.div>
  );
}

function formatPrice(priceCents: number): string {
  return (priceCents / 100).toFixed(2);
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface rounded-lg px-3 py-2">
      <p className="text-kiosk-sm text-slate-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-kiosk-md font-bold text-slate-100 truncate">{value}</p>
    </div>
  );
}
