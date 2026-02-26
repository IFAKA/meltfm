import { useState, useCallback, useEffect } from "react";
import { useRadio } from "./hooks/useRadio";
import StartScreen from "./components/StartScreen";
import NowPlaying from "./components/NowPlaying";
import Controls from "./components/Controls";
import ReactionInput from "./components/ReactionInput";
import GenerationBadge from "./components/GenerationBadge";
import History from "./components/History";
import EventLog from "./components/EventLog";
import DevPanel from "./components/DevPanel";
import RadioDropdown from "./components/RadioDropdown";
import AudioVisualizer from "./components/AudioVisualizer";
import ShareOverlay from "./components/ShareOverlay";
import CleanDataDialog from "./components/CleanDataDialog";
import LyricsView from "./components/LyricsView";

export default function App() {
  const { state, start, send, togglePause, setVolume, seekTo, playUrl, getAnalyser } = useRadio();
  const [showStart, setShowStart] = useState(true);
  const [showShare, setShowShare] = useState(false);
  const [showClean, setShowClean] = useState(false);
  const [showLyrics, setShowLyrics] = useState(false);

  // Close lyrics view when track changes to one without lyrics
  useEffect(() => {
    if (showLyrics && !state.nowPlaying?.lyrics) {
      setShowLyrics(false);
    }
  }, [state.nowPlaying?.id]);

  const handleStart = useCallback(async () => {
    await start();
    setShowStart(false);
  }, [start]);

  if (showStart) {
    return (
      <StartScreen
        onStart={handleStart}
        isFirstRun={state.isFirstRun}
        onFirstVibe={(text) => send("first_vibe", { text })}
      />
    );
  }

  const devPanelProps = {
    pipeline: state.pipeline,
    generationParams: state.generationParams,
    connected: state.connected,
    generating: state.generating,
    queueReady: state.queueReady,
    llmDurationMs: state.llmDurationMs,
    aceDurationMs: state.aceDurationMs,
    generationElapsed: state.generationElapsed,
  };

  return (
    <div className="h-full flex flex-col md:grid md:grid-cols-[2fr_3fr] overflow-hidden">
      {/* ── Left / main panel ── */}
      <div className="flex flex-col h-full min-h-0">
        {/* Header */}
        <header className="flex items-center px-6 py-4 shrink-0 gap-4">
          <RadioDropdown
            currentRadio={state.radioName}
            onSwitch={(name) => send("switch_radio", { name })}
            onCreate={(name, vibe) => send("create_radio", { name, vibe })}
            onDelete={(name) => send("delete_radio", { name })}
          />
          <div className="flex-1 flex justify-center">
            <AudioVisualizer isPlaying={state.isPlaying} getAnalyser={getAnalyser} />
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`w-2 h-2 rounded-full ${state.connected ? "bg-like" : "bg-dislike animate-pulse"}`}
              title={state.connected ? "Connected" : "Reconnecting..."}
            />
            <button
              onClick={() => setShowShare(true)}
              className="text-neutral-500 hover:text-white"
              title="Share"
            >
              &#8942;
            </button>
          </div>
        </header>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          <NowPlaying
            track={state.nowPlaying}
            elapsed={state.elapsed}
            duration={state.duration}
            onSeek={seekTo}
            onShowLyrics={state.nowPlaying?.lyrics ? () => setShowLyrics(true) : undefined}
          />

          <GenerationBadge
            generating={state.generating}
            queueReady={state.queueReady}
            elapsed={state.generationElapsed}
            params={state.generationParams}
            pipeline={state.pipeline}
          />

          <div className="border-t border-neutral-800 mx-6" />

          {/* History: inline on mobile, hidden on desktop (shown in right panel) */}
          <div className="md:hidden">
            <History radioName={state.radioName} nowPlayingId={state.nowPlaying?.id} onPlayUrl={playUrl} />
          </div>

          {/* DevPanel + Event log: inline on mobile (collapsed by default), hidden on desktop */}
          <div className="md:hidden">
            <DevPanel {...devPanelProps} defaultCollapsed />
            <EventLog events={state.events} defaultCollapsed />
          </div>
        </div>

        {/* Sticky bottom: reaction input + controls */}
        <ReactionInput onSubmit={(text) => send("reaction", { text })} />

        <Controls
          isPlaying={state.isPlaying}
          volume={state.volume}
          onTogglePause={togglePause}
          onSkip={() => send("skip")}
          onLike={() => send("like")}
          onDislike={() => send("dislike")}
          onSave={() => send("save")}
          onVolumeChange={setVolume}
          onCleanData={() => setShowClean(true)}
        />

        {/* iOS safe area padding */}
        <div className="pb-[env(safe-area-inset-bottom)] shrink-0" />
      </div>

      {/* ── Right panel — desktop only ── */}
      <div className="hidden md:flex md:flex-col border-l border-neutral-800 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-y-auto">
          <History radioName={state.radioName} nowPlayingId={state.nowPlaying?.id} onPlayUrl={playUrl} />
        </div>
        <DevPanel {...devPanelProps} />
        <EventLog events={state.events} />
      </div>

      {/* Overlays */}
      <LyricsView
        show={showLyrics}
        lyrics={state.nowPlaying?.lyrics ?? ""}
        elapsed={state.elapsed}
        duration={state.duration}
        trackTags={state.nowPlaying?.tags ?? ""}
        onClose={() => setShowLyrics(false)}
        lyricsTimestamps={state.nowPlaying?.lyrics_timestamps}
      />

      <ShareOverlay show={showShare} onClose={() => setShowShare(false)} />

      <CleanDataDialog
        open={showClean}
        onClose={() => setShowClean(false)}
        onConfirm={() => send("clean_radio")}
        radioName={state.radioName}
      />

      {state.error && (
        <div className="fixed top-0 left-0 right-0 bg-dislike/90 text-white text-sm text-center py-2 z-50">
          {state.error}
        </div>
      )}
    </div>
  );
}
