/**
 * Always-visible text input for natural language reactions.
 */
import { useState } from "react";

type Props = {
  onSubmit: (text: string) => void;
};

export default function ReactionInput({ onSubmit }: Props) {
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (trimmed) {
      onSubmit(trimmed);
      setText("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="px-6 py-3">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="What should it sound like?"
        className="w-full px-4 py-2.5 rounded-xl bg-surface-2 border border-neutral-700 text-white placeholder-neutral-500 focus:outline-none focus:border-accent text-sm"
      />
    </form>
  );
}
