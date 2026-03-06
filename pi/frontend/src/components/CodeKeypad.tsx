import { motion } from "framer-motion";

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

  return (
    <div className="flex flex-col items-center gap-5 w-full max-w-xl mx-auto">
      <motion.div
        animate={shaking ? { x: [0, -12, 12, -8, 8, 0] } : {}}
        transition={{ duration: 0.45 }}
        className="flex gap-4"
      >
        {Array.from({ length: CODE_LENGTH }).map((_, i) => (
          <div
            key={i}
            className={`
              w-[clamp(3.5rem,9vw,4.5rem)] h-[clamp(4.5rem,11vw,5.5rem)] rounded-2xl flex items-center justify-center
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

      <div className="h-8 flex items-center">
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

      <div className="grid grid-cols-4 gap-4 w-fit mx-auto">
        <Key label="1" onPress={append} />
        <Key label="2" onPress={append} />
        <Key label="3" onPress={append} />
        <Key
          label="backspace"
          onPress={del}
          accent
          icon="backspace"
          ariaLabel="Delete last digit"
          disabled={value.length === 0}
        />

        <Key label="4" onPress={append} />
        <Key label="5" onPress={append} />
        <Key label="6" onPress={append} />
        <div />

        <Key label="7" onPress={append} />
        <Key label="8" onPress={append} />
        <Key label="9" onPress={append} />
        <div />

        <Key label="0" onPress={append} wide className="col-span-3" />
        <div />
      </div>
    </div>
  );
}

function Key({
  label,
  onPress,
  accent = false,
  wide = false,
  ariaLabel,
  disabled = false,
  icon,
  className = "",
}: {
  label: string;
  onPress: (v: string) => void;
  accent?: boolean;
  wide?: boolean;
  ariaLabel?: string;
  disabled?: boolean;
  icon?: "backspace";
  className?: string;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.88 }}
      onClick={() => onPress(label)}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      className={`
        ${wide ? "w-[clamp(16.5rem,43vw,20rem)]" : "w-[clamp(5rem,13vw,6.25rem)]"} h-[clamp(5rem,13vw,6.25rem)] rounded-2xl
        flex items-center justify-center
        text-[clamp(2rem,5vw,3rem)] font-black
        transition-colors duration-100
        touch-target
        ${className}
        ${
          disabled
            ? "bg-slate-800 text-slate-600 cursor-not-allowed"
            : accent
              ? "bg-slate-700 hover:bg-slate-600 text-slate-200 active:bg-slate-500"
              : "bg-surface-raised hover:bg-slate-600 text-slate-100 active:bg-accent active:text-slate-950"
        }
      `}
    >
      {icon === "backspace" ? <BackspaceIcon /> : label}
    </motion.button>
  );
}

function BackspaceIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="w-[clamp(2.2rem,5.5vw,3rem)] h-[clamp(2.2rem,5.5vw,3rem)]"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 6H9.2a2 2 0 0 0-1.5.67L3 12l4.7 5.33A2 2 0 0 0 9.2 18H21a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1Z" />
      <path d="m11 9 5 6" />
      <path d="m16 9-5 6" />
    </svg>
  );
}
