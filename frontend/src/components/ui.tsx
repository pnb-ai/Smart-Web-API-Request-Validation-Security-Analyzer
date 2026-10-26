import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
  children: ReactNode
}

export function Button({ variant = 'secondary', size = 'md', className = '', children, ...props }: ButtonProps) {
  return <button className={`button button-${variant} ${size === 'sm' ? 'button-small' : ''} ${className}`.trim()} {...props}>{children}</button>
}

export function Card({ className = '', ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={`design-card ${className}`.trim()} {...props} />
}

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }

export function TextInput({ label, hint, id, className = '', ...props }: TextInputProps) {
  const inputId = id ?? props.name ?? label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const hintId = hint ? `${inputId}-hint` : undefined
  return <div className="field-wrap">
    <label className="field-label" htmlFor={inputId}>{label}</label>
    <input className={`text-input ${className}`.trim()} id={inputId} aria-describedby={hintId} {...props} />
    {hint && <small className="field-hint" id={hintId}>{hint}</small>}
  </div>
}
