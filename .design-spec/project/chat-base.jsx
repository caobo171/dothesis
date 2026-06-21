/* ===== Chat thread: header (focus bar), message bubbles, block renderers ===== */

function FocusBar({ T, project, focusId, lang, onJumpVersion, onHome }) {
  const m = window.DT_DATA.MODULES.find(x => x.id === focusId);
  const status = project.status[focusId];
  const phaseLabel = {
    M2: { en: 'Gap analysis', vi: 'Phân tích khoảng trống' },
    M4: { en: 'Measurement model', vi: 'Mô hình đo lường' },
  }[focusId];
  const statusLabel = { en: { done: 'Done', in_progress: 'In progress', locked: 'Locked', needs_review: 'Needs review' },
                        vi: { done: 'Hoàn tất', in_progress: 'Đang làm', locked: 'Khoá', needs_review: 'Cần xem lại' } }[lang][status];
  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 22px',
      background: 'white',
      borderBottom: '1px solid var(--ink-200)',
      position: 'sticky', top: 0, zIndex: 5,
      minHeight: 60,
    }}>
      <a href="Home.html" onClick={(e) => { if (onHome) { e.preventDefault(); onHome(); } }}
         className="btn-icon" title={lang === 'vi' ? 'Về trang chủ' : 'Back to home'}
         style={{ textDecoration: 'none', flexShrink: 0 }}>←</a>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
        <span style={{
          padding: '4px 9px', borderRadius: 8, flexShrink: 0,
          background: 'var(--primary-50)', color: 'var(--primary-700)',
          fontWeight: 800, fontSize: 12.5, letterSpacing: '.04em',
        }}>{focusId}</span>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden' }}>
          <span style={{ fontSize: 15, fontWeight: 700, textOverflow: 'ellipsis', overflow: 'hidden' }}>{m[lang]}</span>
          {phaseLabel && (
            <span style={{ fontSize: 12.5, color: 'var(--ink-500)' }}>· {phaseLabel[lang]}</span>
          )}
        </div>
        <span className={`tag ${status}`} style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>{statusLabel}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <button className="btn-icon" title={lang === 'vi' ? 'Lịch sử phiên bản' : 'Versions'} onClick={onJumpVersion}>⤴︎</button>
        <button className="btn-icon" title={lang === 'vi' ? 'Xuất' : 'Export'}>↓</button>
        <button className="btn-icon" style={{ background: 'var(--danger-50)', color: 'var(--danger-text)' }} title="Notifications">
          <span style={{ position: 'relative', fontSize: 13 }}>
            🔔
            <span style={{ position: 'absolute', top: -3, right: -4, width: 8, height: 8, borderRadius: 999, background: 'var(--danger-600)', border: '1.5px solid white' }}></span>
          </span>
        </button>
        <span style={{ width: 1, height: 22, background: 'var(--ink-200)', margin: '0 4px' }}></span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 30, height: 30, borderRadius: 999,
            background: 'var(--ink-800)',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: 'white', fontWeight: 700, fontSize: 12, 
          }}>JD</span>
          <div style={{ lineHeight: 1.15, whiteSpace: 'nowrap' }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>Jeendeet Lam</div>
            <div style={{ fontSize: 10.5, color: 'var(--ink-500)' }}>{lang === 'vi' ? 'Pro Student' : 'Pro Student'}</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/* ===== Message bubble ===== */
function MessageBubble({ turn, lang, project, isLast }) {
  if (turn.role === 'user') return <UserBubble turn={turn} lang={lang} />;
  return <AssistantBubble turn={turn} lang={lang} project={project} isLast={isLast} />;
}

function UserBubble({ turn, lang }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '12px 0' }}>
      <div style={{
        maxWidth: 580,
        background: 'var(--primary)',
        color: 'white',
        padding: '11px 16px',
        borderRadius: '18px 18px 4px 18px',
        fontSize: 14.5, lineHeight: 1.5,
        boxShadow: '0 1px 0 rgba(11,16,32,.04)',
      }}>
        {turn.blocks.map((b, i) => <Block key={i} block={b} lang={lang} variant="user" />)}
      </div>
    </div>
  );
}

function AssistantBubble({ turn, lang, project, isLast }) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '12px 0', alignItems: 'flex-start' }}>
      <Avatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>DoThesis</span>
          {turn.module && (
            <span style={{
              padding: '2px 7px', borderRadius: 6,
              background: 'var(--primary-50)', color: 'var(--primary-700)',
              fontWeight: 800, fontSize: 11, letterSpacing: '.03em',
            }}>{turn.module}</span>
          )}
          {turn.phase && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>· {turn.phase}</span>
          )}
          {turn.router && <RouterBadge router={turn.router} lang={lang} />}
          <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--ink-400)' }}>just now</span>
        </div>
        <div style={{
          background: 'white',
          border: '1px solid var(--ink-200)',
          borderRadius: '4px 18px 18px 18px',
          padding: '14px 18px',
          fontSize: 14.5, lineHeight: 1.55,
          color: 'var(--ink-800)',
          boxShadow: 'var(--shadow-card)',
        }}>
          {turn.blocks.map((b, i) => <Block key={i} block={b} lang={lang} variant="assistant" project={project} />)}
        </div>
        {turn.quickReplies && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {turn.quickReplies.map((q, i) => (
              <button key={i} className="chip">{q[lang]}</button>
            ))}
          </div>
        )}
        {isLast && (
          <div style={{ display: 'flex', gap: 4, marginTop: 8, color: 'var(--ink-400)' }}>
            <MicroAction icon="↻" label={lang === 'vi' ? 'Tạo lại' : 'Regenerate'} />
            <MicroAction icon="⌘" label={lang === 'vi' ? 'Sao chép' : 'Copy'} />
            <MicroAction icon="✦" label={lang === 'vi' ? 'Lưu vào ngữ cảnh' : 'Pin to context'} />
            <MicroAction icon="✗" label={lang === 'vi' ? 'Không chính xác' : 'Mark inaccurate'} />
          </div>
        )}
      </div>
    </div>
  );
}

function Avatar() {
  return (
    <span style={{
      width: 34, height: 34, minWidth: 34, borderRadius: 8,
      background: 'var(--primary)',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      color: 'white', fontWeight: 800, fontSize: 15,
      marginTop: 22,
    }}>D</span>
  );
}

function RouterBadge({ router, lang }) {
  const { intent, target } = router;
  const map = {
    en: { read: `Read · ${target}`, mutate: `Mutate · ${target}`, continue: 'Continue' },
    vi: { read: `Đọc · ${target}`, mutate: `Sửa · ${target}`, continue: 'Tiếp tục' },
  };
  return (
    <span className={`tag ${intent}`} title={
      intent === 'read'
        ? (lang === 'vi' ? 'Tiêu điểm không đổi · chỉ đọc state slice' : 'Focus stays · reads a state slice only')
        : (lang === 'vi' ? 'Tiêu điểm chuyển · cờ ⚠ áp xuống các module phụ thuộc' : 'Focus shifts · downstream modules flagged ⚠')
    }>
      {intent === 'read' ? '👁' : '✎'} {map[lang][intent]}
    </span>
  );
}

function MicroAction({ icon, label }) {
  return (
    <button title={label} style={{
      width: 28, height: 28, borderRadius: 8,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 13, color: 'var(--ink-400)',
    }}
    onMouseEnter={e => { e.currentTarget.style.background = 'var(--ink-100)'; e.currentTarget.style.color = 'var(--ink-700)'; }}
    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--ink-400)'; }}>
      {icon}
    </button>
  );
}

/* ===== Block dispatcher ===== */
function Block({ block, lang, variant, project }) {
  switch (block.type) {
    case 'md':              return <MD text={block[lang]} variant={variant} />;
    case 'state-of-lit':    return <StateOfLitBlock lang={lang} />;
    case 'gaps':            return <GapList lang={lang} project={project} />;
    case 'sources':         return <FoundingSourcesBlock lang={lang} />;
    case 'gap-draft':       return <GapDraft lang={lang} />;
    case 'doc-preview':     return <DocPreview lang={lang} />;
    case 'outline':         return <OutlineBlock lang={lang} />;
    case 'results-table':   return <ResultsTable lang={lang} />;
    case 'model-canvas':    return <ModelCanvas lang={lang} />;
    default: return null;
  }
}

/* Very small markdown-ish: **bold**, `code`, line breaks. */
function MD({ text, variant }) {
  // split by paragraphs
  const paragraphs = (text || '').split(/\n\n+/);
  return (
    <div>
      {paragraphs.map((p, i) => (
        <p key={i} style={{ margin: i === 0 ? '0' : '8px 0 0' }}
           dangerouslySetInnerHTML={{ __html: mdInline(p, variant) }} />
      ))}
    </div>
  );
}
function mdInline(s, variant) {
  // escape
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // **bold**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // `code`
  const codeBg = variant === 'user' ? 'rgba(255,255,255,.18)' : 'var(--ink-100)';
  const codeFg = variant === 'user' ? 'white' : 'var(--ink-800)';
  s = s.replace(/`([^`]+)`/g, `<code style="background:${codeBg};color:${codeFg};padding:1px 6px;border-radius:6px;font-size:.88em;font-family:var(--font-mono);">$1</code>`);
  // single newlines as <br>
  s = s.replace(/\n/g, '<br/>');
  return s;
}

window.FocusBar = FocusBar;
window.MessageBubble = MessageBubble;
