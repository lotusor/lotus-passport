"use client";

import * as React from "react";
import { Reveal } from "@/components/motion/Reveal";
import { Card, Badge } from "@/components/ui";
import { oauthClients, SCOPE_LABELS, type OAuthClient } from "@/lib/data";

export function OAuthClients() {
  return (
    <>
      <Reveal>
        <p className="text-sm leading-relaxed text-ink-muted">
          以下应用已接入莲花通行证，可使用你的通行证账号登录。授权范围以各应用实际申请为准。
        </p>
      </Reveal>

      <div className="space-y-6">
        {oauthClients.map((c: OAuthClient, i: number) => {
          const planned = c.id === "c-1"; // 仅项目 1（E-algo Rank）为已接入
          return (
            <Reveal key={c.id} delay={i * 0.05}>
              <Card className="overflow-hidden">
                <div className="flex items-start justify-between gap-4 border-b border-line p-5 sm:p-6">
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-accent/80 to-warn/70 text-base font-bold text-white">
                      {c.name.slice(0, 1)}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-ink">{c.name}</h3>
                        <Badge tone={planned ? "success" : "warn"}>
                          {planned ? "已接入" : "暂定"}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-sm text-ink-muted">{c.description}</p>
                    </div>
                  </div>
                </div>
                <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {c.scopes.map((s) => (
                      <Badge key={s} tone="accent">
                        {SCOPE_LABELS[s]}
                      </Badge>
                    ))}
                  </div>
                  <div className="text-xs text-ink-muted">最近使用 {c.lastUsed}</div>
                </div>
              </Card>
            </Reveal>
          );
        })}
      </div>
    </>
  );
}
