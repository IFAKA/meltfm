/**
 * Clean taste data — Sheet (mobile) / AlertDialog (desktop).
 */
import { useEffect, useState } from "react";
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  radioName: string;
};

export default function CleanDataDialog({ open, onClose, onConfirm, radioName }: Props) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const description = `This will clear all liked, disliked, and skipped history for "${radioName}". The radio will start learning your taste from scratch.`;

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
        <SheetContent side="bottom" className="bg-surface-2 border-neutral-700">
          <SheetHeader>
            <SheetTitle>Clean taste data?</SheetTitle>
            <SheetDescription>{description}</SheetDescription>
          </SheetHeader>
          <SheetFooter className="mt-6 flex-row gap-3">
            <Button variant="outline" className="flex-1 border-neutral-600" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="flex-1"
              onClick={() => { onConfirm(); onClose(); }}
            >
              Clear data
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={(v) => !v && onClose()}>
      <AlertDialogContent className="bg-surface-2 border-neutral-700">
        <AlertDialogHeader>
          <AlertDialogTitle>Clean taste data?</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="border-neutral-600">Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-white hover:bg-destructive/90"
          >
            Clear data
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
