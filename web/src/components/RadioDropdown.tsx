/**
 * Radio switcher — dropdown to switch/create/delete radios.
 */
import { useEffect, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ChevronDown, Plus, Trash2 } from "lucide-react";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newVibe, setNewVibe] = useState("");

  useEffect(() => {
    if (open) {
      fetch("/api/radios")
        .then((r) => r.json())
        .then((data: { radios?: RadioInfo[] }) => setRadios(data.radios || []))
        .catch(() => {});
    }
  }, [open]);

  const handleCreate = () => {
    if (newName.trim()) {
      onCreate(newName.trim(), newVibe.trim());
      setNewName("");
      setNewVibe("");
      setCreateOpen(false);
    }
  };

  const handleDelete = () => {
    if (deleteTarget) {
      onDelete(deleteTarget);
      setRadios((prev) => prev.filter((r) => r.name !== deleteTarget));
      setDeleteTarget(null);
    }
  };

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="text-lg font-bold px-0 hover:bg-transparent gap-1">
            {currentRadio}
            <ChevronDown className="size-4 text-neutral-500" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent className="w-64 bg-surface-2 border-neutral-700">
          {radios.map((r) => (
            <DropdownMenuItem
              key={r.name}
              className="flex items-center justify-between cursor-pointer"
              onSelect={(e) => {
                if (!r.is_current) {
                  e.preventDefault();
                  onSwitch(r.name);
                  setOpen(false);
                } else {
                  e.preventDefault();
                }
              }}
            >
              <div className="flex flex-col flex-1 min-w-0">
                <span className={r.is_current ? "text-radio-accent font-medium" : ""}>{r.name}</span>
                <span className="text-xs text-neutral-500">{r.track_count} tracks</span>
              </div>
              {!r.is_current && (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteTarget(r.name);
                    setOpen(false);
                  }}
                  className="text-neutral-600 hover:text-dislike hover:bg-transparent shrink-0"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </DropdownMenuItem>
          ))}

          <DropdownMenuSeparator className="bg-neutral-700" />

          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              setCreateOpen(true);
              setOpen(false);
            }}
            className="text-radio-accent cursor-pointer"
          >
            <Plus className="size-4" />
            New radio
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Create radio dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="bg-surface-2 border-neutral-700 sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>New radio</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Radio name"
              className="bg-surface-3! border-neutral-600 text-white placeholder:text-neutral-500"
              autoFocus
            />
            <Input
              value={newVibe}
              onChange={(e) => setNewVibe(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="What's the vibe?"
              className="bg-surface-3! border-neutral-600 text-white placeholder:text-neutral-500"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" className="border-neutral-600" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!newName.trim()}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <AlertDialogContent className="bg-surface-2 border-neutral-700">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete radio?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete &ldquo;{deleteTarget}&rdquo;? All tracks and taste data will be removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-neutral-600">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-white hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
