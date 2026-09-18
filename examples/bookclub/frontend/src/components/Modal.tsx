import { useEffect, type ReactNode } from 'react';
import { CloseIcon } from './Icons';

export default function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close"><CloseIcon /></button></div>
        {children}
      </section>
    </div>
  );
}

