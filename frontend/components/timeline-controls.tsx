"use client";

type TimelineControlsProps = {
  totalTicks: number;
  animTick: number;
  onScrub: (nextTick: number) => void;
  speed: number;
  onSpeedChange: (nextSpeed: number) => void;
  paused?: boolean;
  onPauseToggle?: () => void;
  className?: string;
};

export function TimelineControls({
  totalTicks,
  animTick,
  onScrub,
  speed,
  onSpeedChange,
  paused = false,
  onPauseToggle,
  className = "",
}: TimelineControlsProps) {
  const maxTick = Math.max(totalTicks - 1, 0);
  const boundedTick = Math.max(0, Math.min(animTick, maxTick));
  const tickMarks = [0, 0.2, 0.35, 0.5, 0.65, 0.8, 1];
  const speedMarks = [1.0, 2.0, 4.0];
  const timelinePct = maxTick === 0 ? 0 : (boundedTick / maxTick) * 100;
  const timelineLeft = `calc(${timelinePct}% - 1px)`;
  const speedPct = ((speed - 1.0) / 3.0) * 100;

  return (
    <div className={`pt-2 border-t border-border/40 ${className}`}>
      <div className="flex items-end gap-3">
        {onPauseToggle && (
          <button
            onClick={onPauseToggle}
            aria-label={paused ? "Resume" : "Pause"}
            className="shrink-0 h-7 w-7 flex items-center justify-center rounded border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors mb-0"
          >
            {paused ? (
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5,3 19,12 5,21" />
              </svg>
            ) : (
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                <rect x="5" y="4" width="4" height="16" rx="1" />
                <rect x="15" y="4" width="4" height="16" rx="1" />
              </svg>
            )}
          </button>
        )}
        <div className="flex-1 min-w-0">
          <div className="mb-1.5 flex items-center justify-between text-[9px] font-mono text-muted-foreground">
            <span>t=0</span>
            <span className="opacity-70">t = {Math.round(boundedTick)}</span>
            <span>t={maxTick}</span>
          </div>

          <div className="relative h-7">
            <div className="absolute left-0 right-0 top-1/2 h-[2px] -translate-y-1/2 bg-primary/80" />
            {tickMarks.map((p, idx) => (
              <div
                key={idx}
                className="absolute top-1/2 h-4 w-[2px] -translate-x-1/2 -translate-y-1/2 bg-primary/80"
                style={{ left: `${p * 100}%` }}
              />
            ))}

            {/* Vertical playhead that remains upright at all t values */}
            <div
              className="pointer-events-none absolute top-1/2 h-6 w-[2px] -translate-y-1/2 bg-primary"
              style={{ left: timelineLeft }}
            />
            <div
              className="pointer-events-none absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-primary bg-background shadow-[0_0_0_1px_rgba(37,99,235,0.2)]"
              style={{ left: `${timelinePct}%` }}
            />

            <input
              aria-label="Simulation timeline"
              type="range"
              min={0}
              max={maxTick}
              step={0.01}
              value={boundedTick}
              onChange={(e) => onScrub(Number(e.target.value))}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            />
          </div>
        </div>

        <div className="w-[120px] shrink-0">
          <div className="mb-1.5 text-right text-[9px] font-mono text-muted-foreground">
            Speed x{speed.toFixed(1)}
          </div>
          <div className="relative h-7">
            <div className="absolute left-1 right-1 top-1/2 h-[2px] -translate-y-1/2 bg-primary/70" />
            {speedMarks.map((mark) => (
              <div
                key={mark}
                className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/70 bg-card"
                style={{ left: `${((mark - 1.0) / 3.0) * 100}%` }}
              />
            ))}
            <input
              aria-label="Playback speed"
              type="range"
              min={1.0}
              max={4.0}
              step={0.25}
              value={speed}
              onChange={(e) => onSpeedChange(Number(e.target.value))}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            />
            <div
              className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary shadow-[0_0_0_1px_rgba(37,99,235,0.4)]"
              style={{ left: `${speedPct}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[9px] font-mono text-muted-foreground/90">
            <span>x1</span>
            <span>x4</span>
          </div>
        </div>
      </div>
    </div>
  );
}
