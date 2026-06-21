/* ===== Sidebar: brand, module tracker, token meter, help widget ===== */

const SidebarStyles = {
  root: {
    width: 296, minWidth: 296,
    display: 'flex', flexDirection: 'column',
    background: 'white',
    borderRight: '1px solid var(--ink-200)',
    height: '100vh',
    position: 'relative',
  },
  brand: {
    padding: '18px 20px 14px',
    display: 'flex', alignItems: 'center', gap: 10,
  },
  brandMark: {
    width: 36, height: 36, borderRadius: 8,
    background: 'var(--primary)',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    color: 'white', fontWeight: 800, fontSize: 18,
  },
  brandName: { fontWeight: 800, fontSize: 17.5, letterSpacing: '-.01em' },
  brandSub:  { fontSize: 11, color: 'var(--ink-500)', letterSpacing: '.08em', textTransform: 'uppercase', marginTop: 1 },

  projChip: {
    margin: '0 14px 10px',
    padding: '10px 12px',
    background: 'var(--ink-50)',
    borderRadius: 12,
    border: '1px solid var(--ink-200)',
    cursor: 'pointer',
  },
};

function Sidebar({ T, project, focusId, onFocus, lang, onOpenWizard,
                   threads, activeThreadId, onSelectThread, onNewThread }) {
  return (
    <aside style={SidebarStyles.root}>
      {/* Brand */}
      <div style={SidebarStyles.brand}>
        <span style={SidebarStyles.brandMark}>D</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={SidebarStyles.brandName}>DoThesis</div>
          <div style={SidebarStyles.brandSub}>{lang === 'vi' ? 'Trợ lý luận văn' : 'Thesis copilot'}</div>
        </div>
        <a href="Home.html" className="btn-icon" style={{ width: 28, height: 28, fontSize: 13, textDecoration: 'none' }}
           title={lang === 'vi' ? 'Về trang chủ' : 'Home'}>⌂</a>
      </div>

      {/* Project switcher chip */}
      <div style={SidebarStyles.projChip}>
        <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase' }}>
          {lang === 'vi' ? 'Đề tài' : 'Project'}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, marginTop: 3, color: 'var(--ink-900)', lineHeight: 1.35,
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {project.name[lang]}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, fontSize: 11.5, color: 'var(--ink-500)' }}>
          <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{project.field[lang]}</span>
          <span style={{ marginLeft: 'auto' }}>⌄</span>
        </div>
      </div>

      {/* Threads list (no tabs) */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <ThreadList threads={threads} activeId={activeThreadId} onSelect={onSelectThread}
                     onNew={onNewThread} lang={lang} />
      </div>

      {/* Token meter */}
      <TokenMeter project={project} lang={lang} />

      {/* Help widget */}
      <HelpWidget lang={lang} onOpenWizard={onOpenWizard} />
    </aside>
  );
}

function SidebarTab({ label, badge, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, padding: '8px 10px', borderRadius: 10,
      background: active ? 'var(--primary-50)' : 'transparent',
      color: active ? 'var(--primary-700)' : 'var(--ink-600)',
      fontWeight: active ? 700 : 600, fontSize: 12.5,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
      transition: 'background .12s',
    }}
    onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--ink-50)'; }}
    onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}>
      <span>{label}</span>
      <span style={{
        padding: '1px 7px', borderRadius: 999, fontSize: 10.5, fontWeight: 700,
        background: active ? 'white' : 'var(--ink-100)',
        color: active ? 'var(--primary-700)' : 'var(--ink-500)',
      }}>{badge}</span>
    </button>
  );
}

function WorkflowList({ modules, project, focusId, onFocus, lang }) {
  return (
    <nav style={{ padding: '0 12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
      {modules.map((m, i) => (
        <ModuleRow
          key={m.id}
          m={m}
          index={i}
          status={project.status[m.id]}
          isFocus={focusId === m.id}
          onFocus={() => onFocus(m.id)}
          lang={lang}
          isLast={i === modules.length - 1}
        />
      ))}
    </nav>
  );
}

function ThreadList({ threads, activeId, onSelect, onNew, lang }) {
  const pinned   = threads.filter(t => t.pinned && t.status === 'active');
  const active   = threads.filter(t => !t.pinned && t.status === 'active');
  const archived = threads.filter(t => t.status === 'archived');
  return (
    <div style={{ padding: '0 8px 8px' }}>
      <button onClick={onNew} className="btn btn-primary"
        style={{ width: '100%', padding: '8px 12px', fontSize: 13, justifyContent: 'flex-start', marginBottom: 8 }}>
        <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
        <span>{lang === 'vi' ? 'Trò chuyện mới' : 'New thread'}</span>
        <span style={{ flex: 1 }}></span>
        <span style={{ opacity: .75, fontSize: 10.5, padding: '1px 6px', background: 'rgba(255,255,255,.18)', borderRadius: 5 }}>⌘N</span>
      </button>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: 10,
        background: 'var(--ink-50)', color: 'var(--ink-500)', fontSize: 12, marginBottom: 8,
      }}>
        <span>⌕</span>
        <span>{lang === 'vi' ? 'Tìm thread…' : 'Search threads…'}</span>
      </div>

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
  );
}

function ModuleRow({ m, index, status, isFocus, onFocus, lang, isLast }) {
  const blurb = window.DT_DATA.MODULE_BLURB[m.id][lang];
  const num = m.id; // M1, M2 …
  const isClickable = status !== 'locked';
  const statusLabel = {
    en: { done: 'Done', in_progress: 'In progress', locked: 'Locked', needs_review: 'Needs review' },
    vi: { done: 'Hoàn tất', in_progress: 'Đang làm', locked: 'Khoá', needs_review: 'Cần xem lại' },
  }[lang][status];

  return (
    <div style={{ position: 'relative' }}>
      {/* vertical track */}
      {!isLast && (
        <span style={{
          position: 'absolute', left: 30, top: 38, bottom: -2, width: 2,
          background: status === 'done' ? 'var(--ok-600)' : 'var(--ink-200)',
          opacity: 0.7,
        }}></span>
      )}

      <button
        onClick={onFocus}
        className="focus-ring"
        style={{
          width: '100%', textAlign: 'left',
          display: 'flex', alignItems: 'flex-start', gap: 12,
          padding: '10px 10px 10px 10px',
          borderRadius: 12,
          background: isFocus ? 'var(--primary-50)' : 'transparent',
          color: isFocus ? 'var(--primary-700)' : 'var(--ink-800)',
          cursor: isClickable ? 'pointer' : 'not-allowed',
          opacity: status === 'locked' ? 0.6 : 1,
          transition: 'background .15s',
        }}
        onMouseEnter={(e) => { if (!isFocus && isClickable) e.currentTarget.style.background = 'var(--ink-50)'; }}
        onMouseLeave={(e) => { if (!isFocus) e.currentTarget.style.background = 'transparent'; }}
      >
        <StatusBadge status={status} num={num} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{m[lang]}</span>
            {status === 'needs_review' && <span style={{ fontSize: 14, lineHeight: 1 }}>⚠</span>}
          </div>
          <div style={{ fontSize: 11.5, color: isFocus ? 'var(--primary-600)' : 'var(--ink-500)', marginTop: 2, lineHeight: 1.35 }}>
            {blurb}
          </div>
          <div style={{ fontSize: 10.5, color: 'var(--ink-400)', marginTop: 4, letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 600 }}>
            {statusLabel}
          </div>
        </div>
      </button>
    </div>
  );
}

function StatusBadge({ status, num }) {
  const palettes = {
    done:         { bg: 'var(--ok-600)',   fg: 'white',           ring: 'rgba(31,157,98,.18)' },
    in_progress:  { bg: 'var(--primary)',  fg: 'white',           ring: 'rgba(37,64,255,.18)' },
    locked:       { bg: 'var(--ink-200)',  fg: 'var(--ink-500)',  ring: 'transparent' },
    needs_review: { bg: 'var(--review-50)', fg: 'var(--review-text)', ring: 'rgba(224,136,0,.20)' },
  };
  const p = palettes[status];
  return (
    <span style={{
      width: 38, height: 38, minWidth: 38, borderRadius: 10,
      background: p.bg, color: p.fg,
      boxShadow: `0 0 0 4px ${p.ring}`,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 800, fontSize: 12.5, letterSpacing: '.04em',
      
      position: 'relative',
    }}>
      {status === 'done'
        ? <span style={{ fontSize: 16 }}>✓</span>
        : num}
    </span>
  );
}

function TokenMeter({ project, lang }) {
  const total = project.tokens.balance + project.tokens.used;
  const pct = (project.tokens.balance / total) * 100;
  return (
    <div style={{ margin: '6px 14px 10px', padding: '12px 14px',
                  background: 'var(--ink-50)', borderRadius: 14,
                  border: '1px solid var(--ink-200)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--ink-500)', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>
        <span>◈</span>
        <span>{lang === 'vi' ? 'Số dư token' : 'Token balance'}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--primary)', textTransform: 'none', letterSpacing: 0, fontSize: 10.5 }}>
          {project.tokens.plan}
        </span>
      </div>
      <div className="tnum" style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-.02em' }}>
          {(project.tokens.balance / 1000).toFixed(1)}k
        </span>
        <span style={{ fontSize: 12, color: 'var(--ink-500)' }}>
          / {(total / 1000).toFixed(0)}k
        </span>
      </div>
      <div style={{ height: 6, background: 'var(--ink-200)', borderRadius: 999, marginTop: 8, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--primary)' }}></div>
      </div>
      <button className="btn btn-secondary" style={{ marginTop: 10, width: '100%', padding: '7px 12px', fontSize: 12.5 }}>
        + {lang === 'vi' ? 'Nạp thêm token' : 'Top up tokens'}
      </button>
    </div>
  );
}

function HelpWidget({ lang, onOpenWizard }) {
  return (
    <div style={{ position: 'relative', margin: '0 14px 16px' }}>
      <span style={{
        position: 'absolute', top: -16, left: '50%', transform: 'translateX(-50%)',
        width: 32, height: 32, borderRadius: 999,
        background: 'var(--ink-900)', color: 'white',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 800, fontSize: 16,
        boxShadow: '0 6px 16px rgba(11,16,32,.30)',
      }}>?</span>
      <div style={{
        background: 'var(--ink-900)',
        borderRadius: 16, padding: '22px 16px 14px',
        color: 'white', textAlign: 'center',
        position: 'relative', overflow: 'hidden',
      }}>
        {/* subtle decorative arcs */}
        <svg width="220" height="120" style={{ position: 'absolute', top: -10, left: -40, opacity: .08 }} viewBox="0 0 220 120">
          <circle cx="40" cy="20" r="80" stroke="white" strokeWidth="1" fill="none"/>
          <circle cx="40" cy="20" r="58" stroke="white" strokeWidth="1" fill="none"/>
        </svg>
        <div style={{ fontWeight: 700, fontSize: 14, position: 'relative' }}>
          {lang === 'vi' ? 'Hướng dẫn nhanh' : 'Quick start'}
        </div>
        <div style={{ fontSize: 11.5, color: 'rgba(255,255,255,.7)', marginTop: 4, lineHeight: 1.4, position: 'relative' }}>
          {lang === 'vi'
            ? 'Bạn đã có dữ liệu sẵn? Khởi tạo nhanh từ những gì bạn có.'
            : 'Already have material? Bootstrap from what you have.'}
        </div>
        <button onClick={onOpenWizard}
          style={{
            marginTop: 10, width: '100%', padding: '8px 12px', borderRadius: 999,
            background: 'white', color: 'var(--ink-900)',
            fontSize: 12.5, fontWeight: 700, position: 'relative',
          }}>
          {lang === 'vi' ? 'Mở trợ lý nhập liệu' : 'Open entry wizard'}
        </button>
        <button style={{
            marginTop: 6, width: '100%', padding: '7px 12px', borderRadius: 999,
            border: '1px solid rgba(255,255,255,.18)', color: 'white',
            fontSize: 12, fontWeight: 600, position: 'relative',
          }}>
          {lang === 'vi' ? 'Liên hệ Fanpage' : 'Contact support'}
        </button>
      </div>
    </div>
  );
}

window.Sidebar = Sidebar;
