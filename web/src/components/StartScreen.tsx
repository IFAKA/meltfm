/**
 * Full-screen "tap to start" — required for browser autoplay policy.
 */
type Props = {
  onStart: () => void;
  isFirstRun: boolean;
  onFirstVibe?: (text: string) => void;
};

import { useState } from "react";

export default function StartScreen({ onStart, isFirstRun, onFirstVibe }: Props) {
  const [vibe, setVibe] = useState("");

  const handleStart = () => {
    if (isFirstRun && vibe.trim() && onFirstVibe) {
      onFirstVibe(vibe.trim());
    }
    onStart();
  };

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="text-6xl mb-6">&#9835;</div>
      <h1 className="text-2xl font-bold mb-2">Personal Radio</h1>
      <p className="text-neutral-400 mb-8 max-w-xs">
        AI-generated music that learns your taste
      </p>

      {isFirstRun && (
        <input
          type="text"
          value={vibe}
          onChange={(e) => setVibe(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleStart()}
          placeholder="What's your vibe? (e.g., lo-fi beats, dark ambient)"
          className="w-full max-w-sm mb-6 px-4 py-3 rounded-xl bg-surface-2 border border-neutral-700 text-white placeholder-neutral-500 focus:outline-none focus:border-accent"
        />
      )}

      <button
        onClick={handleStart}
        className="px-8 py-4 rounded-2xl bg-accent text-black font-semibold text-lg active:scale-95 transition-transform"
      >
        Start listening
      </button>
    </div>
  );
}
