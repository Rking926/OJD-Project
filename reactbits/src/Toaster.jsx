// Pile de notifications SwipeToast (React Bits) en bas à droite de l'écran.
// Le JS vanilla appelle ReactBits.toast({ title, description, kind }) ; on
// glisse un toast vers le bas pour le fermer, sinon il part tout seul.
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { HugeiconsIcon } from '@hugeicons/react';
import { Alert02Icon, CheckmarkCircle02Icon, InformationCircleIcon } from '@hugeicons/core-free-icons';

import SwipeToast from './SwipeToast';

const KINDS = {
  success: { icon: CheckmarkCircle02Icon, color: '#22c55e', duration: 4000 },
  error: { icon: Alert02Icon, color: '#ef4444', duration: 7000 },
  info: { icon: InformationCircleIcon, color: '#38bdf8', duration: 4000 }
};
const MAX_VISIBLE = 4;

let push = null;
const queue = [];
let nextId = 1;

function Toaster() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    push = t => setToasts(list => [...list, t].slice(-MAX_VISIBLE));
    queue.splice(0).forEach(push);
    return () => {
      push = null;
    };
  }, []);

  const remove = id => setToasts(list => list.filter(t => t.id !== id));

  return (
    <div className="ojd-toaster">
      {toasts.map(t => {
        const kind = KINDS[t.kind] || KINDS.info;
        return (
          <SwipeToast
            key={t.id}
            inline
            title={t.title}
            description={t.description || ''}
            actionLabel={t.actionLabel || ''}
            onAction={t.onAction}
            icon={<HugeiconsIcon icon={kind.icon} size={18} strokeWidth={2} color={kind.color} />}
            fuseColor={kind.color}
            duration={t.duration ?? kind.duration}
            closeButton
            onClose={() => remove(t.id)}
          />
        );
      })}
    </div>
  );
}

// Monte la pile à la première notification, puis empile.
export function toast(options) {
  const t = { id: nextId++, ...(typeof options === 'string' ? { title: options } : options) };
  if (push) {
    push(t);
    return;
  }
  queue.push(t);
  if (queue.length === 1 && !document.querySelector('.ojd-toaster-host')) {
    const host = document.createElement('div');
    host.className = 'ojd-toaster-host';
    document.body.appendChild(host);
    createRoot(host).render(<Toaster />);
  }
}
