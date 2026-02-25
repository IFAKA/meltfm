/**
 * Brief toast notification — auto-dismisses.
 */

type Props = {
  message: string | null;
};

export default function Toast({ message }: Props) {
  if (!message) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full bg-surface-2 border border-neutral-700 text-sm text-neutral-300 shadow-lg z-40 animate-[fadeIn_0.2s_ease-out]">
      {message}
    </div>
  );
}
