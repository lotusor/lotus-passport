"use client";

import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";

/** 页面加载时自动从 localStorage 恢复会话，只运行一次。 */
export function SessionRestore() {
  const { restore } = useAuth();
  useEffect(() => {
    restore();
  }, [restore]);
  return null;
}