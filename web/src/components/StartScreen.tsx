/**
 * Full-screen "tap to start" — required for browser autoplay policy.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = {
  onStart: () => void;
  isFirstRun: boolean;
  onFirstVibe?: (text: string) => void;
};

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
        <Input
          value={vibe}
          onChange={(e) => setVibe(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleStart()}
          placeholder="What's your vibe? (e.g., lo-fi beats, dark ambient)"
          className="w-full max-w-sm mb-6 bg-surface-2! border-neutral-700 text-white placeholder:text-neutral-500 focus-visible:ring-radio-accent"
        />
      )}

      <Button
        onClick={handleStart}
        size="lg"
        className="px-8 rounded-2xl text-lg font-semibold active:scale-95"
      >
        Start listening
      </Button>
    </div>
  );
}
