"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Reveal } from "@/components/motion/Reveal";
import { Card, SectionCard, Button, Badge, Toggle } from "@/components/ui";
import {
  Smartphone,
  Desktop,
  Tablet,
  MapPin,
  ShieldCheck,
  Trash,
  History,
  Check,
  Alert,
} from "@/components/icons";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth-context";
import {
  getDevices,
  revokeDevice,
  setDeviceTrust,
  getSessions,
  getLoginHistory,
} from "@/lib/passport-api";
import type { AuthDevice, Session, LoginEvent } from "@/lib/data";

const typeIcon = {
  desktop: Desktop,
  mobile: Smartphone,
  tablet: Tablet,
} as const;

function DeviceGlyph({ type }: { type: AuthDevice["type"] }) {
  const Icon = typeIcon[type];
  return (
    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
      <Icon className="h-5 w-5" />
    </span>
  );
}

/** 状态占位（加载 / 错误）。 */
function StatusBlock({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) {
    return (
      <div className="rounded-3xl border border-danger/30 bg-danger-soft/40 p-6 text-sm text-danger">
        加载失败：{error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="rounded-3xl border border-line bg-surface p-8 text-center text-sm text-ink-muted shadow-soft">
        加载中…
      </div>
    );
  }
  return null;
}

export function DevicesView() {
  const { accessToken } = useAuth();

  const [devices, setDevices] = React.useState<AuthDevice[]>([]);
  const [sessions, setSessions] = React.useState<Session[] | null>(null);
  const [events, setEvents] = React.useState<LoginEvent[] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!accessToken) return;
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        const [d, s, h] = await Promise.all([
          getDevices(accessToken),
          getSessions(accessToken),
          getLoginHistory(accessToken),
        ]);
        if (!alive) return;
        setDevices(d);
        setSessions(s);
        setEvents(h);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "加载失败，请刷新重试");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [accessToken]);

  // 「当前设备」以当前会话为准（后端设备表无 current 标记，会话才是准确身份来源）。
  const currentSession = sessions?.find((s) => s.current);
  const hero = currentSession
    ? {
        name: currentSession.device || "当前设备",
        os: currentSession.os || "",
        browser: currentSession.browser,
        location: currentSession.location,
      }
    : null;

  // 授权设备列表里若与当前会话同浏览器，则标记为「本机」。
  const currentBrowser = currentSession?.browser;
  const isCurrentDevice = (d: AuthDevice) =>
    Boolean(currentBrowser) && d.browser === currentBrowser;

  const revoke = async (id: string) => {
    if (!accessToken) return;
    setBusyId(id);
    try {
      await revokeDevice(accessToken, id);
      setDevices((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "撤销设备失败");
    } finally {
      setBusyId(null);
    }
  };

  const toggleTrust = async (id: string) => {
    if (!accessToken) return;
    const target = devices.find((d) => d.id === id);
    if (!target) return;
    setBusyId(id);
    try {
      await setDeviceTrust(accessToken, id, !target.trusted);
      setDevices((prev) =>
        prev.map((d) => (d.id === id ? { ...d, trusted: !d.trusted } : d))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新信任状态失败");
    } finally {
      setBusyId(null);
    }
  };

  const [filter, setFilter] = React.useState<"all" | "success" | "failed">("all");
  const filtered = (events || []).filter(
    (e) => filter === "all" || e.status === filter
  );

  return (
    <>
      {/* Current device feature card */}
      <Reveal>
        <Card className="overflow-hidden p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              {hero && <DeviceGlyph type="desktop" />}
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold text-ink">
                    {hero?.name ?? "当前设备"}
                  </h2>
                  <Badge tone="success">当前设备</Badge>
                </div>
                <p className="mt-0.5 text-sm text-ink-muted">
                  {[hero?.os, hero?.browser].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 font-medium text-success">
                <ShieldCheck className="h-4 w-4" /> 已信任
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-ink/5 px-3 py-1 font-medium text-ink-muted">
                <MapPin className="h-4 w-4" /> {hero?.location ?? "—"}
              </span>
            </div>
          </div>
        </Card>
      </Reveal>

      {/* Authorized devices */}
      <Reveal delay={0.04}>
        <SectionCard
          icon={Smartphone}
          title="授权设备"
          description="这些设备已通过验证，可长期保持登录。关闭信任后该设备下次需重新验证身份。"
        >
          <StatusBlock loading={loading} error={error} />
          {!loading && !error && (
            <ul className="divide-y divide-line">
              <AnimatePresence initial={false}>
                {devices.map((d) => {
                  const Icon = typeIcon[d.type];
                  return (
                    <motion.li
                      key={d.id}
                      layout
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <DeviceGlyph type={d.type} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-ink">{d.name}</p>
                            {isCurrentDevice(d) && <Badge tone="success">本机</Badge>}
                          </div>
                          <p className="text-sm text-ink-muted">
                            {d.os} · {d.browser}
                          </p>
                          <p className="text-xs text-ink-muted">
                            {d.location} · 首次信任 {d.firstTrusted} · {d.lastActive}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 pl-14 sm:pl-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-ink-soft">信任</span>
                          <Toggle
                            checked={d.trusted}
                            onChange={() => toggleTrust(d.id)}
                            label={`信任 ${d.name}`}
                          />
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busyId === d.id}
                          onClick={() => revoke(d.id)}
                          className="text-danger hover:bg-danger-soft"
                        >
                          <Trash className="h-4 w-4" /> 撤销
                        </Button>
                      </div>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
              {devices.length === 0 && (
                <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-ink-muted">
                  暂无授权设备
                </li>
              )}
            </ul>
          )}
        </SectionCard>
      </Reveal>

      {/* Login history */}
      <Reveal delay={0.08}>
        <SectionCard
          icon={History}
          title="登录历史"
          description="最近的登录活动。若发现陌生地点或失败尝试，请立即修改密码并撤销设备。"
        >
          <StatusBlock loading={loading} error={error} />
          {!loading && !error && (
            <>
              <div className="mb-4 flex gap-2">
                {(
                  [
                    { k: "all", t: "全部" },
                    { k: "success", t: "成功" },
                    { k: "failed", t: "失败" },
                  ] as const
                ).map((f) => (
                  <button
                    key={f.k}
                    onClick={() => setFilter(f.k)}
                    className={cn(
                      "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors min-h-[40px]",
                      filter === f.k
                        ? "bg-ink text-white"
                        : "bg-ink/5 text-ink-muted hover:text-ink"
                    )}
                  >
                    {f.t}
                  </button>
                ))}
              </div>

              <ul className="space-y-2">
                {filtered.map((e) => {
                  const failed = e.status === "failed";
                  return (
                    <li
                      key={e.id}
                      className={cn(
                        "flex items-center gap-3 rounded-2xl border p-3.5",
                        failed
                          ? "border-danger/30 bg-danger-soft/40"
                          : "border-line bg-surface"
                      )}
                    >
                      <span
                        className={cn(
                          "grid h-9 w-9 shrink-0 place-items-center rounded-xl",
                          failed
                            ? "bg-danger-soft text-danger"
                            : "bg-success-soft text-success"
                        )}
                      >
                        {failed ? (
                          <Alert className="h-4 w-4" />
                        ) : (
                          <Check className="h-4 w-4" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">
                          {e.device}
                          {failed && (
                            <span className="ml-2 text-danger">登录失败</span>
                          )}
                        </p>
                        <p className="text-xs text-ink-muted">
                          {e.time} · {e.location} · {e.ip}
                        </p>
                      </div>
                    </li>
                  );
                })}
                {filtered.length === 0 && (
                  <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-ink-muted">
                    暂无符合条件的记录
                  </li>
                )}
              </ul>
            </>
          )}
        </SectionCard>
      </Reveal>
    </>
  );
}
