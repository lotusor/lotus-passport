'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { PasswordField } from '@/components/field';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconSpinner, IconTrash } from '@/components/icons';
import { Modal } from '@/components/modal';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { clearTokens } from '@/lib/tokens';

interface DangerPanelProps {
  hasPassword: boolean;
}

export function DangerPanel({ hasPassword }: DangerPanelProps) {
  const router = useRouter();
  const { push } = useToast();
  const [open, setOpen] = useState(false);
  const [ack, setAck] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    if (busy || !ack) return;
    setBusy(true);
    setError(null);
    try {
      await api('/profile/', {
        method: 'DELETE',
        body: { confirm: true, ...(hasPassword ? { current_password: password } : {}) },
      });
      clearTokens();
      setOpen(false);
      push('info', '账户已注销', '全部会话已吊销，身份数据已清除');
      router.replace('/login');
    } catch (err) {
      setError(err instanceof ApiException ? err.message : '网络异常，请稍后重试');
      setBusy(false);
    }
  };

  return (
    <GlassPanel className="panel danger-panel">
      <div className="panel-head">
        <h2 className="flex items-center gap-3" style={{ fontSize: 'var(--fs-body)', color: 'var(--red)' }}>
          <IconTrash width={18} height={18} />
          注销账户
        </h2>
        <span className="chip chip--red">
          <span className="chip-dot" />
          不可恢复
        </span>
      </div>
      <p className="dim small mb-4">
        注销将永久删除你的身份资料、第三方绑定、设备与会话记录，并吊销全部令牌。接入应用中的业务数据由各应用自行处理。
      </p>
      <button type="button" className="btn btn-danger" onClick={() => setOpen(true)}>
        注销账户…
      </button>

      <Modal
        open={open}
        onClose={() => {
          setOpen(false);
          setError(null);
        }}
        title="确认注销账户？"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setOpen(false)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={!ack || busy || (hasPassword && !password)}
              onClick={onConfirm}
            >
              {busy ? <IconSpinner width={16} height={16} /> : null}
              永久注销
            </button>
          </>
        }
      >
        <div className="flex-col gap-4">
          <p className="notice notice--red">
            <IconAlert />
            此操作不可撤销。注销后无法再用任何方式登录该身份。
          </p>
          <label className="flex gap-3 items-center small" style={{ cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              style={{ width: 18, height: 18, accentColor: 'var(--red)' }}
            />
            我已了解注销不可恢复，仍要继续
          </label>
          {hasPassword && (
            <PasswordField
              label="账户密码（安全验证）"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          {error && (
            <p className="field-err" role="alert">
              <IconAlert width={14} height={14} />
              {error}
            </p>
          )}
        </div>
      </Modal>
    </GlassPanel>
  );
}