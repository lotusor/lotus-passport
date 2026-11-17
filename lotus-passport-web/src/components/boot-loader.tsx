'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useT } from './motion';

const BOOT_KEY = 'lp.booted';
const TYPE_MS = 7;
const LINE_GAP = 60;
const BAR_WIDTH = 26;
const PROBE_CAP_MS = 2600;

interface ScriptLine {
  label: string;
  hold: number;
  detail?: string;
  probe?: 'health' | 'dev';
}

const SCRIPT: ScriptLine[] = [
  { label: '> mounting /dev/identity', hold: 120 },
  { label: '> loading auth kernel', hold: 130 },
  { label: '> RS256 keyring', hold: 110, detail: 'KID ACTIVE' },
  { label: '> device trust gate', hold: 110, detail: 'ARMED' },
  { label: '> backend handshake', hold: 0, probe: 'health' },
  { label: '> session policy', hold: 100, probe: 'dev' },
  { label: '> rendering liquid glass', hold: 160 },
];

interface TimelineLine extends ScriptLine {
  start: number;
  typeEnd: number;
  end: number;
}

function buildTimeline(): { lines: TimelineLine[]; total: number } {
  let t = 0;
  const lines = SCRIPT.map((s) => {
    const start = t;
    const typeEnd = start + s.label.length * TYPE_MS;
    const end = typeEnd + s.hold + LINE_GAP;
    t = end;
    return { ...s, start, typeEnd, end };
  });
  return { lines, total: t + 320 };
}

async function probe(path: string): Promise<{ ok: boolean; detail: string }> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), PROBE_CAP_MS);
  try {
    const res = await fetch(path, { signal: ctl.signal, cache: 'no-store' });
    if (!res.ok) return { ok: false, detail: `HTTP ${res.status}` };
    if (path.includes('dev/status')) {
      const data = await res.json();
      return { ok: true, detail: data.dev_login_enabled ? 'DEV STUB ON' : 'PROD MODE' };
    }
    return { ok: true, detail: 'HTTP 200' };
  } catch {
    return { ok: false, detail: 'OFFLINE' };
  } finally {
    window.clearTimeout(timer);
  }
}

interface ProbeState {
  health?: { ok: boolean; detail: string };
  dev?: { ok: boolean; detail: string };
}

export function BootLoader() {
  const [elapsed, setElapsed] = useState(0);
  const [probes, setProbes] = useState<ProbeState>({});
  const [exiting, setExiting] = useState(false);
  const [done, setDone] = useState(false);
  const [quick, setQuick] = useState(false);
  const skipAt = useRef<number | null>(null);
  const finished = useRef(false);
  const probesRef = useRef<ProbeState>({});
  const exitT = useT({ duration: 0.4, ease: [0.22, 1, 0.36, 1] });

  const finish = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    try {
      sessionStorage.setItem(BOOT_KEY, '1');
    } catch {
      /* 隐私模式下 sessionStorage 不可用：忽略 */
    }
    if (document.hidden) {
      setDone(true);
      return;
    }
    setExiting(true);
  }, []);

  useEffect(() => {
    if (done) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isQuick = Boolean(sessionStorage.getItem(BOOT_KEY)) || reduced || document.hidden;
    setQuick(isQuick);
    const { total } = buildTimeline();
    const span = isQuick ? (reduced ? 120 : 380) : total;
    const start = performance.now();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    probe('/api/v1/health/').then((r) => {
      probesRef.current = { ...probesRef.current, health: r };
      setProbes(probesRef.current);
    });
    probe('/api/v1/dev/status/').then((r) => {
      probesRef.current = { ...probesRef.current, dev: r };
      setProbes(probesRef.current);
    });

    const tick = window.setInterval(() => {
      const now = performance.now() - start;
      const skipped = skipAt.current !== null;
      const e = skipped ? Math.max(now, span) : now;
      setElapsed(e);
      if (e >= span + (skipped ? 80 : 0)) finish();
    }, 30);

    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Enter' || ev.key === 'Escape') skipAt.current = performance.now() - start;
    };
    const onClick = () => {
      skipAt.current = performance.now() - start;
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onClick);
    return () => {
      window.clearInterval(tick);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onClick);
      document.body.style.overflow = prevOverflow;
    };
  }, [finish, done]);

  if (done) return null;

  const { lines, total } = buildTimeline();
  const skipped = skipAt.current !== null;
  const shown = quick ? lines.slice(0, 1) : lines;
  const resolvedCount = quick
    ? 1
    : shown.filter((l) => skipped || elapsed >= l.end || (l.probe && elapsed >= l.typeEnd && probes[l.probe])).length;
  const progress = quick ? 1 : Math.min(1, resolvedCount / lines.length);
  const filled = Math.round(progress * BAR_WIDTH);
  const bar = '▓'.repeat(filled) + '░'.repeat(BAR_WIDTH - filled);

  return (
    <AnimatePresence onExitComplete={() => setDone(true)}>
      {!exiting && (
        <motion.div
          className="boot"
          role="status"
          aria-label="系统初始化"
          exit={{ opacity: 0, clipPath: 'inset(0 0 100% 0)' }}
          transition={exitT}
        >
          <div className="boot-inner" aria-hidden>
            <div className="boot-head">
              <span>LOTUS PASSPORT // IDENTITY TERMINAL</span>
              <span>BIOS 3.0</span>
            </div>
            {shown.map((l, i) => {
              const local = skipped ? Number.MAX_SAFE_INTEGER : elapsed - l.start;
              if (local < 0) return null;
              const label = quick ? '> resuming secure session' : l.label;
              const typed = quick ? label.length : Math.min(label.length, Math.floor(local / TYPE_MS));
              const probeResult = l.probe ? probes[l.probe] : undefined;
              const typeDone = typed >= label.length;
              const resolved =
                skipped ||
                (l.probe
                  ? typeDone && (probeResult !== undefined || elapsed - l.typeEnd > PROBE_CAP_MS)
                  : elapsed >= l.typeEnd + l.hold);
              const detail = quick
                ? 'WARM BOOT'
                : l.probe
                  ? probeResult?.detail ?? (elapsed - l.typeEnd > PROBE_CAP_MS ? 'TIMEOUT' : '…')
                  : l.detail ?? 'OK';
              const warn = l.probe && probeResult ? !probeResult.ok : l.probe && detail === 'TIMEOUT';
              return (
                <div className="boot-line" key={i}>
                  <span>{label.slice(0, typed)}</span>
                  {typeDone && (
                    <>
                      <span className="boot-dots" />
                      <span className={warn ? 'warn' : 'ok'}>{resolved ? detail : '…'}</span>
                    </>
                  )}
                </div>
              );
            })}
            <div className="boot-line">
              <span className="boot-cursor" />
            </div>
            <div className="boot-bar">
              [{bar}] {Math.round(progress * 100)}%
            </div>
            <div className="boot-skip">点击任意处 / ENTER 跳过</div>
          </div>
          <span className="sr-only">系统初始化中，请稍候</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}