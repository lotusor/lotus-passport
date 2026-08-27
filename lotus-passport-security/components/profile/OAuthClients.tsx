"use client";

import * as React from "react";
import { Reveal } from "@/components/motion/Reveal";
import { Card, Badge } from "@/components/ui";
import { Sparkles } from "@/components/icons";

/**
 * 开发者应用（§9.5）——后端子系统尚未建设（无 OAuthClient 模型/接口）。
 * 本页不再展示 mock 数据，改为明确的「规划中」空态，避免用户误以为
 * 可以在这里管理真实应用。后端落地后再切回列表 + CRUD UI。
 */
export function OAuthClients() {
  return (
    <>
      <Reveal>
        <p className="text-sm leading-relaxed text-ink-muted">
          以下应用已接入莲花通行证，可使用你的通行证账号登录。授权范围以各应用实际申请为准。
        </p>
      </Reveal>

      <Reveal delay={0.05}>
        <Card className="p-8 text-center">
          <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-accent-soft text-accent">
            <Sparkles className="h-6 w-6" />
          </span>
          <h3 className="text-lg font-semibold text-ink">开发者应用管理 · 规划中</h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-muted">
            该功能的后端子系统（应用注册 / 密钥轮换 / 授权范围管理）尚未上线，
            当前仅通过管理员白名单方式接入应用。首个接入应用为
            <Badge tone="success" >E-algo Rank</Badge>
            （rank.eacm.cn）。
          </p>
        </Card>
      </Reveal>
    </>
  );
}
