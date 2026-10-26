import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, X } from 'lucide-react'

type ToastContextValue = { notify: (message: string) => void }
const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('')
  const notify = useCallback((next: string) => {
    setMessage(next)
    window.setTimeout(() => setMessage(''), 2800)
  }, [])
  const value = useMemo(() => ({ notify }), [notify])
  return <ToastContext.Provider value={value}>
    {children}
    <AnimatePresence>{message && <motion.div className="toast" role="status" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
      <CheckCircle2 size={18} /><span>{message}</span><button aria-label="Dismiss notification" onClick={() => setMessage('')}><X size={16} /></button>
    </motion.div>}</AnimatePresence>
  </ToastContext.Provider>
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside ToastProvider')
  return context
}
