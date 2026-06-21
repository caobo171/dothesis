/* ===== Threads panel ===== */

function ThreadsPanel({ lang, activeId, onSelect, onNewThread, collapsed, onToggle }) {
  const threads = window.DT_DATA.THREADS;
  const pinned   = threads.filter(t => t.pinned && t.status === 'active');
  const active   = threads.filter(t => !t.pinned && t.status === 'active');
  const archived = threads.filter(t => t.status === 'archived');

  if (collapsed) {
    return (
      <aside style={{
        width: 56, minWidth: 56,
        background: 'white', borderRight: '1px solid var(--ink-200)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        padding: '14px 0', gap: 10,
      }}>
        <button onClick={onToggle} className="btn-icon" title={lang === 'vi' ? 'Mở danh sách thread' : 'Show threads'}>☰</button>
        <button onClick={onNewThread} className="btn-icon" style={{ background: 'var(--primary-50)', color: 'var(--primary)' }} title={lang === 'vi' ? 'Thread mới' : 'New thread'}>+</button>
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
          {[...pinned, ...active].slice(0, 6).map(t => (
            <button key={t.id} onClick={() => onSelect(t.id)}
              title={`${t.module} · ${t.title[lang]}`}
              style={{
                width: 30, height: 30, borderRadius: 8,
                background: activeId === t.id ? 'var(--primary)' : 'var(--ink-100)',
                color: activeId === t.id ? 'white' : 'var(--ink-600)',
                fontWeight: 800, fontSize: 11,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                position: 'relative',
              }}>
              {t.module}
              {t.unread > 0 && (
                <span style={{ position: 'absolute', top: -3, right: -3, width: 14, height: 14, borderRadius: 999,
                               background: 'var(--danger-600)', color: 'white', fontSize: 9, fontWeight: 800,
                               display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1.5px solid white' }}>
                  {t.unread}
                </span>
              )}
            </button>
          ))}
        </div>
      </aside>
    );
  }

  return (
    <aside style={{
      width: 268, minWidth: 268,
      background: 'white', borderRight: '1px solid var(--ink-200)',
      display: 'flex', flexDirection: 'column', height: '100vh',
    }}>
      {/* Header */}
      <div style={{ padding: '14px 16px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase' }}>
            {lang === 'vi' ? 'Trò chuyện' : 'Threads'}
          </div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-.01em', marginTop: 2 }}>
            {threads.filter(t => t.status === 'active').length} {lang === 'vi' ? 'đang mở' : 'open'}
          </div>
        </div>
        <span style={{ flex: 1 }}></span>
        <button onClick={onToggle} className="btn-icon" style={{ width: 30, height: 30, fontSize: 13 }}
          title={lang === 'vi' ? 'Thu gọn' : 'Collapse'}>«</button>
      </div>

      {/* Search + new */}
      <div style={{ padding: '0 14px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button onClick={onNewThread} className="btn btn-primary" style={{ padding: '8px 12px', fontSize: 13, justifyContent: 'flex-start' }}>
          <span style={{ fontSize: 16 }}>+</span>
          <span>{lang === 'vi' ? 'Trò chuyện mới' : 'New thread'}</span>
          <span style={{ flex: 1 }}></span>
          <span style={{ opacity: .7, fontSize: 11, padding: '1px 6px', background: 'rgba(255,255,255,.18)', borderRadius: 5 }}>⌘N</span>
        </button>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 10px', borderRadius: 10,
          background: 'var(--ink-50)', color: 'var(--ink-500)', fontSize: 12.5,
        }}>
          <span>⌕</span>
          <span>{lang === 'vi' ? 'Tìm thread...' : 'Search threads…'}</span>
        </div>
      </div>

      {/* Lists */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 12px' }}>
        <ThreadGroup label={lang === 'vi' ? 'Đã ghim' : 'Pinned'} count={pinned.length}>
          {pinned.map(t => <ThreadRow key={t.id} t={t} lang={lang} active={activeId === t.id} onSelect={onSelect} />)}
        </ThreadGroup>

        <ThreadGroup label={lang === 'vi' ? 'Đang hoạt động' : 'Active'} count={active.length}>
          {active.map(t => <ThreadRow key={t.id} t={t} lang={lang} active={activeId === t.id} onSelect={onSelect} />)}
        </ThreadGroup>

        <ThreadGroup label={lang === 'vi' ? 'Đã lưu trữ' : 'Archived'} count={archived.length} collapsed>
          {archived.map(t => <ThreadRow key={t.id} t={t} lang={lang} active={activeId === t.id} onSelect={onSelect} muted />)}
        </ThreadGroup>
      </div>

      {/* Footer — context */}
      <div style={{
        padding: '10px 14px', borderTop: '1px solid var(--ink-200)',
        background: 'var(--ink-50)',
        display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, color: 'var(--ink-600)',
      }}>
        <span>ℹ︎</span>
        <span style={{ lineHeight: 1.35 }}>
          {lang === 'vi'
            ? 'Mỗi thread chia sẻ cùng context_store của đề tài.'
            : 'All threads share this project\'s context_store.'}
        </span>
      </div>
    </aside>
  );
}

function ThreadGroup({ label, count, children, collapsed }) {
  const [open, setOpen] = React.useState(!collapsed);
  return (
    <div style={{ marginBottom: 6 }}>
      <button onClick={() => setOpen(!open)} style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 6,
        padding: '8px 8px 6px', textAlign: 'left',
        fontSize: 11, color: 'var(--ink-500)', fontWeight: 700,
        letterSpacing: '.1em', textTransform: 'uppercase',
      }}>
        <span style={{ display: 'inline-block', width: 10, transform: open ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform .15s' }}>▸</span>
        <span>{label}</span>
        <span style={{ color: 'var(--ink-400)', fontWeight: 600, letterSpacing: 0, textTransform: 'none' }}>{count}</span>
      </button>
      {open && <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</div>}
    </div>
  );
}

function ThreadRow({ t, lang, active, onSelect, muted }) {
  const modColor = 'var(--primary)';
  return (
    <button onClick={() => onSelect(t.id)}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '10px 10px',
        borderRadius: 10, textAlign: 'left',
        background: active ? 'var(--primary-50)' : 'transparent',
        opacity: muted ? .65 : 1,
        position: 'relative',
        transition: 'background .12s',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--ink-50)'; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}>
      {active && <span style={{ position: 'absolute', left: -8, top: 14, bottom: 14, width: 3, borderRadius: 2, background: 'var(--primary)' }}></span>}
      <span style={{
        width: 30, height: 30, minWidth: 30, borderRadius: 8,
        background: active ? 'white' : 'var(--ink-50)',
        border: `1px solid ${active ? modColor : 'var(--ink-200)'}`,
        color: modColor,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 800, fontSize: 11, letterSpacing: '.04em',
        marginTop: 1,
      }}>{t.module}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {t.pinned && !muted && <span style={{ fontSize: 10, color: 'var(--ink-400)' }}>📌</span>}
          <span style={{
            fontSize: 13, fontWeight: 700, color: 'var(--ink-900)', lineHeight: 1.3,
            display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden', flex: 1,
          }}>{t.title[lang]}</span>
          {t.unread > 0 && (
            <span style={{
              minWidth: 18, height: 18, padding: '0 5px', borderRadius: 999,
              background: 'var(--danger-600)', color: 'white',
              fontSize: 10, fontWeight: 800,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>{t.unread}</span>
          )}
        </div>
        <div style={{
          fontSize: 12, color: 'var(--ink-500)', marginTop: 2, lineHeight: 1.35,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          <span style={{ color: t.lastAuthor === 'assistant' ? 'var(--primary)' : 'var(--ink-600)', fontWeight: 600 }}>
            {t.lastAuthor === 'assistant' ? 'D' : 'You'}:
          </span>{' '}
          {t.preview[lang]}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, fontSize: 11, color: 'var(--ink-400)' }}>
          <span>{t.lastAt[lang]}</span>
          <span>·</span>
          <span>{t.turns} {lang === 'vi' ? 'lượt' : 'turns'}</span>
          <span>·</span>
          <span className="tnum">{t.tokens}</span>
        </div>
      </div>
    </button>
  );
}

window.ThreadsPanel = ThreadsPanel;
window.ThreadGroup = ThreadGroup;
window.ThreadRow = ThreadRow;
