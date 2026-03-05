import { motion } from "framer-motion";

const NUM_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
const CODE_LENGTH = 6;

interface Props {
  value: string;
  onChange: (val: string) => void;
  shaking: boolean;
  errorMsg: string;
}

export default function CodeKeypad({ value, onChange, shaking, errorMsg }: Props) {
  const append = (ch: string) => {
    if (value.length < CODE_LENGTH) onChange(value + ch);
  };
  const del = () => onChange(value.slice(0, -1));
  const clear = () => onChange("");

  return (
    <div className="flex flex-col items-center gap-2 w-full max-w-lg mx-auto">
      <motion.div
        animate={shaking ? { x: [0, -12, 12, -8, 8, 0] } : {}}
        transition={{ duration: 0.45 }}
        className="flex gap-2"
      >
        {Array.from({ length: CODE_LENGTH }).map((_, i) => (
          <div
            key={i}
            className={`
              w-12 h-14 rounded-lg flex items-center justify-center
              text-kiosk-xl font-black tracking-widest
              border-2 transition-colors duration-200
              ${
                i < value.length
                  ? "border-accent bg-surface-card text-accent"
                  : "border-slate-700 bg-surface-card text-slate-600"
              }
            `}
          >
            {value[i] ?? ""}
          </div>
        ))}
      </motion.div>

      <div className="h-5 flex items-center">
        {errorMsg && (
          <motion.p
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-kiosk-sm text-red-400 font-semibold"
          >
            {errorMsg}
          </motion.p>
        )}
      </div>

      <div className="flex flex-col gap-2 w-full">
        {[0, 3, 6].map((start) => (
          <div key={start} className="flex gap-2 justify-center">
            {NUM_KEYS.slice(start, start + 3).map((k) => (
              <Key key={k} label={k} onPress={append} />
            ))}
          </div>
        ))}
        <div className="flex gap-2 justify-center">
          <Key label="0" onPress={append} wide />
        </div>

        <div className="flex gap-2 justify-center mt-1">
          <Key label="Del" onPress={del} accent />
          <Key label="Clear" onPress={clear} accent wide />
        </div>
      </div>
    </div>
  );
}

function Key({
  label,
  onPress,
  accent = false,
  wide = false,
}: {
  label: string;
  onPress: (v: string) => void;
  accent?: boolean;
  wide?: boolean;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.88 }}
      onClick={() => onPress(label)}
      className={`
        ${wide ? "w-28" : "w-[3.7rem]"} h-12 rounded-lg
        text-kiosk-md font-bold
        transition-colors duration-100
        touch-target
        ${
          accent
            ? "bg-slate-700 hover:bg-slate-600 text-slate-200"
            : "bg-surface-raised hover:bg-slate-600 text-slate-100 active:bg-accent active:text-slate-950"
        }
      `}
    >
      {label}
    </motion.button>
  );
}
