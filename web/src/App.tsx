import { useState, useCallback } from "react";
import { useRadio } from "./hooks/useRadio";
import StartScreen from "./components/StartScreen";
import NowPlaying from "./components/NowPlaying";
import Controls from "./components/Controls";
import ReactionInput from "./components/ReactionInput";
import GenerationBadge from "./components/GenerationBadge";
import History from "./components/History";
import RadioDropdown from "./components/RadioDropdown";
import ShareOverlay from "./components/ShareOverlay";
import Toast from "./components/Toast";

export default function App() {
  const { state, start, send, togglePause, setVolume, seekTo } = useRadio();
  const [showStart, setShowStart] = useState(true);
  const [showShare, setShowShare] = useState(false);

  const handleStart = useCallback(async () => {
    await start();
    setShowStart(false);
  }, [start]);

  const handleFirstVibe = useCallback(
    (text: string) => send("first_vibe", { text }),
    [send]
  );

  if (showStart) {
    return (
      <StartScreen
        onStart={handleStart}
        isFirstRun={state.isFirstRun}
        onFirstVibe={handleFirstVibe}
      />
    );
  }

  // Use local audio time when available (more accurate than server ticks)
  const elapsed = state.localDuration > 0 ? state.localElapsed : state.playback.elapsed;
  const duration = state.localDuration > 0 ? state.localDuration : (state.playback.duration || 0);

  return (
    <div className="flex flex-col h-full max-w-lg mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4">
        <RadioDropdown
          currentRadio={state.radioName}
          onSwitch={(name) => send("switch_radio", { name })}
          onCreate={(name, vibe) => send("create_radio", { name, vibe })}
          onDelete={(name) => send("delete_radio", { name })}
        />
        <div className="flex items-center gap-3">
          {/* Connection indicator */}
          <span
            className={`w-2 h-2 rounded-full ${state.connected ? "bg-like" : "bg-dislike animate-pulse"}`}
            title={state.connected ? "Connected" : "Reconnecting..."}
          />
          {/* Share button */}
          <button
            onClick={() => setShowShare(true)}
            className="text-neutral-500 hover:text-white"
            title="Share"
          >
            &#8942;
          </button>
        </div>
      </header>

      {/* Now playing */}
      <NowPlaying
        track={state.nowPlaying}
        elapsed={elapsed}
        duration={duration}
        onSeek={seekTo}
      />

      {/* Controls */}
      <Controls
        playing={state.playback.playing}
        volume={state.playback.volume}
        onTogglePause={togglePause}
        onSkip={() => send("skip")}
        onLike={() => send("like")}
        onDislike={() => send("dislike")}
        onSave={() => send("save")}
        onVolumeChange={setVolume}
      />

      {/* Reaction input */}
      <ReactionInput onSubmit={(text) => send("reaction", { text })} />

      {/* Generation status */}
      <GenerationBadge
        generating={state.generating}
        elapsed={state.generationElapsed}
        params={state.generationParams}
      />

      {/* Divider */}
      <div className="border-t border-neutral-800 mx-6" />

      {/* History */}
      <div className="flex-1 overflow-y-auto">
        <History radioName={state.radioName} />
      </div>

      {/* Share overlay */}
      <ShareOverlay show={showShare} onClose={() => setShowShare(false)} />

      {/* Toast */}
      <Toast message={state.toast} />

      {/* Error banner */}
      {state.error && (
        <div className="fixed top-0 left-0 right-0 bg-dislike/90 text-white text-sm text-center py-2 z-50">
          {state.error}
        </div>
      )}
    </div>
  );
}
