'use client';

import { useId, useState, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react';
import { IconAlert, IconEye, IconEyeOff } from './icons';

interface FieldShellProps {
  label: string;
  error?: string | null;
  hint?: ReactNode;
  children: (id: string, describedBy: string | undefined, invalid: boolean) => ReactNode;
}

function FieldShell({ label, error, hint, children }: FieldShellProps) {
  const id = useId();
  const errId = `${id}-err`;
  const hintId = `${id}-hint`;
  const describedBy = [error ? errId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      {children(id, describedBy, Boolean(error))}
      {error && (
        <p className="field-err" id={errId} role="alert">
          <IconAlert width={14} height={14} />
          {error}
        </p>
      )}
      {hint && !error && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  );
}

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  error?: string | null;
  hint?: ReactNode;
}

export function TextField({ label, error, hint, ...rest }: TextFieldProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy, invalid) => (
        <input className="input" id={id} aria-describedby={describedBy} aria-invalid={invalid} {...rest} />
      )}
    </FieldShell>
  );
}

export function PasswordField({ label, error, hint, ...rest }: TextFieldProps) {
  const [visible, setVisible] = useState(false);
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy, invalid) => (
        <span className="input-wrap">
          <input
            className="input"
            id={id}
            type={visible ? 'text' : 'password'}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            {...rest}
          />
          <button
            type="button"
            className="btn btn-ghost btn-icon btn-sm input-affix"
            aria-label={visible ? '隐藏密码' : '显示密码'}
            aria-pressed={visible}
            onClick={() => setVisible((v) => !v)}
          >
            {visible ? <IconEyeOff width={16} height={16} /> : <IconEye width={16} height={16} />}
          </button>
        </span>
      )}
    </FieldShell>
  );
}

interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  label: string;
  error?: string | null;
  hint?: ReactNode;
}

export function TextAreaField({ label, error, hint, ...rest }: TextAreaFieldProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy, invalid) => (
        <textarea className="textarea" id={id} aria-describedby={describedBy} aria-invalid={invalid} {...rest} />
      )}
    </FieldShell>
  );
}