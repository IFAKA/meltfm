/**
 * QR code share overlay — generates QR from current URL.
 * Uses a simple QR code via a public API (no extra deps).
 */
type Props = {
  show: boolean;
  onClose: () => void;
};

export default function ShareOverlay({ show, onClose }: Props) {
  if (!show) return null;

  const url = window.location.href;
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}&bgcolor=0a0a0a&color=ffffff`;

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // fallback
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-surface-2 rounded-2xl p-8 flex flex-col items-center gap-4 max-w-xs"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold">Share your radio</h2>
        <p className="text-sm text-neutral-400 text-center">
          Scan to open on another device
        </p>
        <img src={qrUrl} alt="QR Code" className="w-48 h-48 rounded-lg" />
        <div className="text-xs text-neutral-500 break-all text-center">{url}</div>
        <button
          onClick={copyUrl}
          className="px-4 py-2 rounded-lg bg-surface-3 text-sm text-neutral-300 hover:text-white"
        >
          Copy URL
        </button>
        <button
          onClick={onClose}
          className="text-sm text-neutral-500"
        >
          Close
        </button>
      </div>
    </div>
  );
}
