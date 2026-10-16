// Liste des conversations de la barre latérale, en lignes SwipeRow (React Bits) :
// clic = ouvrir, glisser à gauche = Renommer / Supprimer, glisser jusqu'au bout = supprimer.
import { useRef, useState } from 'react';
import { HugeiconsIcon } from '@hugeicons/react';
import { BubbleChatIcon, Delete02Icon, PencilEdit02Icon } from '@hugeicons/core-free-icons';

import SwipeRow from './SwipeRow';

const TAP_SLOP = 6;
const ROW_H = 52;
const GAP = 6;

const icon = glyph => <HugeiconsIcon icon={glyph} size={18} strokeWidth={2} />;

// created_at arrive en UTC sans fuseau (« 2026-10-16 17:04:00.123 »).
const ago = stamp => {
  const t = Date.parse(`${String(stamp).replace(' ', 'T')}Z`);
  if (Number.isNaN(t)) return '';
  const min = Math.round((Date.now() - t) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `il y a ${h} h`;
  const d = Math.round(h / 24);
  if (d < 7) return `il y a ${d} j`;
  return new Date(t).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
};

export default function ConversationList({ items = [], activeId = null, onSelect, onRename, onDelete }) {
  const [openId, setOpenId] = useState(null);
  const [gone, setGone] = useState(() => new Set());
  const press = useRef(null);

  const visible = items.filter(it => !gone.has(it.id));
  if (!visible.length) return <div className="conv-empty">aucune enquête</div>;

  return (
    <div className="conv-list">
      {visible.map(it => {
        const active = it.id === activeId;
        const actions = [
          { id: 'delete', label: 'Supprimer', icon: icon(Delete02Icon) },
          {
            id: 'rename',
            label: 'Renommer',
            icon: icon(PencilEdit02Icon),
            color: '#52525b',
            onSelect: () => {
              const title = window.prompt('Nouveau nom du chat :', it.title);
              if (title && title.trim() && title.trim() !== it.title) onRename?.(it.id, title.trim());
            }
          }
        ];
        return (
          <div
            key={it.id}
            className="conv-list__item"
            onPointerDownCapture={e => {
              press.current = { x: e.clientX, y: e.clientY, wasOpen: openId !== null };
            }}
            onClick={e => {
              const p = press.current;
              press.current = null;
              if (!p || p.wasOpen) return;
              if (Math.hypot(e.clientX - p.x, e.clientY - p.y) > TAP_SLOP) return;
              if (!e.target.closest('.swipe-row__surface') || e.target.closest('.swipe-row__toggle')) return;
              onSelect?.(it.id);
            }}
          >
            <SwipeRow
              label={it.title}
              actions={actions}
              open={openId === it.id}
              onOpenChange={isOpen => setOpenId(cur => (isOpen ? it.id : cur === it.id ? null : cur))}
              onCommit={a => {
                if (a.id !== 'delete') return;
                setGone(s => new Set(s).add(it.id));
                onDelete?.(it.id);
              }}
              rowColor={active ? '#3f3f46' : '#27272a'}
              drawerColor="#52525b"
              height={ROW_H}
              radius={12}
              actionWidth={76}
              style={{ marginBottom: GAP }}
            >
              <span className="conv-list__icon" data-active={active ? '' : undefined}>
                {icon(BubbleChatIcon)}
              </span>
              <span className="conv-list__text">
                <span className="conv-list__title">{it.title}</span>
                <span className="conv-list__sub">{ago(it.created_at)}</span>
              </span>
            </SwipeRow>
          </div>
        );
      })}
    </div>
  );
}
