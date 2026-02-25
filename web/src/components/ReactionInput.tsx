/**
 * Always-visible text input for natural language reactions.
 */
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

type Props = {
  onSubmit: (text: string) => void;
};

export default function ReactionInput({ onSubmit }: Props) {
  const [text, setText] = useState("");

  const handleSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (trimmed) {
      onSubmit(trimmed);
      setText("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="px-6 py-3 flex gap-2 shrink-0">
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="What should it sound like?"
        className="flex-1 bg-surface-2! border-neutral-700 text-white placeholder:text-neutral-500"
      />
      <Button
        type="submit"
        variant="ghost"
        size="icon"
        disabled={!text.trim()}
        className="text-neutral-400 hover:text-radio-accent"
      >
        <ArrowRight className="size-4" />
      </Button>
    </form>
  );
}
