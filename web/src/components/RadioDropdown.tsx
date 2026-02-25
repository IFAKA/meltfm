/**
 * Radio switcher — dropdown to switch/create/delete radios.
 */
import { useEffect, useState, useRef } from "react";

type RadioInfo = {
  name: string;
  track_count: number;
  is_current: boolean;
};

type Props = {
  currentRadio: string;
  onSwitch: (name: string) => void;
  onCreate: (name: string, vibe: string) => void;
  onDelete: (name: string) => void;
};

export default function RadioDropdown({ currentRadio, onSwitch, onCreate, onDelete }: Props) {
  const [open, setOpen] = useState(false);
  const [radios, setRadios] = useState<RadioInfo[]>([]);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newVibe, setNewVibe] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      fetch("/api/radios")
        .then((r) => r.json())
        .then((data) => setRadios(data.radios || []))
        .catch(() => {});
    }
  }, [open]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleCreate = () => {
    if (newName.trim()) {
      onCreate(newName.trim(), newVibe.trim());
      setNewName("");
      setNewVibe("");
      setCreating(false);
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-lg font-bold"
      >
        {currentRadio}
        <span className="text-neutral-500 text-sm">&#9662;</span>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-2 w-64 bg-surface-2 border border-neutral-700 rounded-xl shadow-lg z-50 overflow-hidden">
          {radios.map((r) => (
            <div
              key={r.name}
              className={`flex items-center justify-between px-4 py-3 hover:bg-surface-3 cursor-pointer ${
                r.is_current ? "text-accent" : ""
              }`}
            >
              <button
                className="flex-1 text-left"
                onClick={() => {
                  onSwitch(r.name);
                  setOpen(false);
                }}
              >
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-neutral-500">{r.track_count} tracks</div>
              </button>
              {!r.is_current && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete radio "${r.name}"?`)) {
                      onDelete(r.name);
                      setRadios((prev) => prev.filter((x) => x.name !== r.name));
                    }
                  }}
                  className="text-neutral-600 hover:text-dislike text-sm ml-2"
                >
                  &#10007;
                </button>
              )}
            </div>
          ))}

          <div className="border-t border-neutral-700">
            {creating ? (
              <div className="p-3 space-y-2">
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Radio name"
                  className="w-full px-3 py-1.5 rounded-lg bg-surface-3 border border-neutral-600 text-sm text-white placeholder-neutral-500 focus:outline-none"
                  autoFocus
                />
                <input
                  type="text"
                  value={newVibe}
                  onChange={(e) => setNewVibe(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="What's the vibe?"
                  className="w-full px-3 py-1.5 rounded-lg bg-surface-3 border border-neutral-600 text-sm text-white placeholder-neutral-500 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleCreate}
                    className="flex-1 py-1.5 rounded-lg bg-accent text-black text-sm font-medium"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => setCreating(false)}
                    className="flex-1 py-1.5 rounded-lg bg-surface-3 text-neutral-400 text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="w-full px-4 py-3 text-left text-sm text-accent hover:bg-surface-3"
              >
                + New radio
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
