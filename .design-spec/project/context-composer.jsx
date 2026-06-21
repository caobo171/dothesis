/* ===== Right rail: live context_store slices + composer ===== */

function ContextPanel({ project, lang, focusId, freshKey }) {
  const cs = project.contextStore;
  const isFresh = (key) => freshKey === key;

  return (
    <aside style={{
      width: 340, minWidth: 340,
      borderLeft: '1px solid var(--ink-200)',
      background: 'white',
      height: '100vh',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid var(--ink-200)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>
          {lang === 'vi' ? 'Kho ngữ cảnh' : 'Context store'}
        </span>
        <span className="tag continue" style={{ textTransform: 'none', letterSpacing: 0 }}>
          context_store.json
        </span>
        <span style={{ flex: 1 }}></span>
        <button className="btn-icon" style={{ width: 28, height: 28, fontSize: 13 }} title="Raw JSON">{ }</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

        <CtxSection
          label={lang === 'vi' ? 'M1 · Chủ đề & câu hỏi' : 'M1 · Topic & questions'}
          status="done" lang={lang}
        >
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase' }}>
            research_title
          </div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 14, lineHeight: 1.45, color: 'var(--ink-900)', marginTop: 3 }}>
            {cs.research_title[lang]}
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', marginTop: 10 }}>
            research_questions ({cs.research_questions[lang].length})
          </div>
          <ol style={{ margin: '6px 0 0 18px', padding: 0, fontSize: 12.5, color: 'var(--ink-700)', lineHeight: 1.45 }}>
            {cs.research_questions[lang].map((q, i) => <li key={i} style={{ marginBottom: 2 }}>{q}</li>)}
          </ol>
        </CtxSection>

        <CtxSection
          label={lang === 'vi' ? 'M2 · Khoảng trống & giả thuyết' : 'M2 · Gaps & hypotheses'}
          status="in_progress" lang={lang} fresh={isFresh('M2.gaps')}
        >
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase' }}>
            research_gaps ({cs.research_gaps.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {cs.research_gaps.map(g => (
              <div key={g.id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                fontSize: 12.5, lineHeight: 1.4,
              }}>
                <span style={{
                  padding: '1px 6px', borderRadius: 4,
                  background: g.confirmed ? 'var(--ok-50)' : 'var(--ink-100)',
                  color: g.confirmed ? 'var(--ok-text)' : 'var(--ink-600)',
                  fontWeight: 800, fontSize: 11,
                  flexShrink: 0,
                }}>{g.id}</span>
                <span style={{ color: 'var(--ink-700)' }}>
                  {(g[lang] || '').slice(0, 90)}{g[lang].length > 90 ? '…' : ''}
                </span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', marginTop: 12 }}>
            hypotheses ({cs.hypotheses.length})
          </div>
          <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
            {cs.hypotheses.map(h => (
              <li key={h.id} style={{ fontSize: 12.5, color: 'var(--ink-700)' }}>
                <span style={{ fontWeight: 700, color: 'var(--primary-700)', marginRight: 6 }}>{h.id}</span>
                {h[lang]}
              </li>
            ))}
          </ul>
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', marginTop: 12 }}>
            literature_sources
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <span className="tnum" style={{ fontSize: 22, fontWeight: 800, color: 'var(--ink-900)' }}>{cs.literature_sources}</span>
            <span style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
              {lang === 'vi' ? 'bài · 28 đã trích · 13 chưa' : 'papers · 28 cited · 13 unused'}
            </span>
          </div>
        </CtxSection>

        <CtxSection
          label={lang === 'vi' ? 'M3 · Phương pháp & mô hình' : 'M3 · Methodology & model'}
          status="needs_review" lang={lang}
        >
          <div style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase' }}>
            methodology
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6, fontSize: 12.5 }}>
            <KV k={lang === 'vi' ? 'Hệ hình' : 'Paradigm'} v={cs.methodology.paradigm} />
            <KV k={lang === 'vi' ? 'Thiết kế' : 'Design'} v={cs.methodology.design} />
            <KV k={lang === 'vi' ? 'Công cụ' : 'Tool'} v={cs.methodology.tool} />
            <KV k={lang === 'vi' ? 'Mẫu' : 'Sample'} v={`n ≥ ${cs.methodology.sampling.minSize} (target ${cs.methodology.sampling.targetSize})`} />
          </div>
          <div style={{
            marginTop: 10, padding: '8px 10px', borderRadius: 8,
            background: 'var(--review-50)', color: 'var(--review-text)',
            fontSize: 11.5, lineHeight: 1.4, fontWeight: 600,
          }}>
            ⚠ {lang === 'vi'
              ? 'Cần xem lại — G1/G2 vừa được chốt, hãy đối chiếu H1–H3.'
              : 'Needs review — G1/G2 just confirmed; re-ground H1–H3.'}
          </div>
        </CtxSection>

        <CtxSection
          label={lang === 'vi' ? 'M4 · Phân tích · M5 · Viết' : 'M4 · Analysis · M5 · Writing'}
          status="locked" lang={lang}
        >
          <div style={{ fontSize: 12.5, color: 'var(--ink-500)', lineHeight: 1.45 }}>
            {lang === 'vi'
              ? 'Khoá mềm — bạn vẫn có thể hỏi hoặc bắt đầu, mình sẽ hỏi lại nếu thiếu phụ thuộc.'
              : 'Soft-locked — you can ask or start; I\'ll prompt if a dependency is missing.'}
          </div>
        </CtxSection>

      </div>

      <div style={{ padding: '10px 16px', borderTop: '1px solid var(--ink-200)', background: 'var(--ink-50)', display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, color: 'var(--ink-500)' }}>
        <span>◷</span>
        <span>{lang === 'vi' ? 'Phiên bản' : 'Snapshot'} #18 · {lang === 'vi' ? '14:32 hôm nay' : '14:32 today'}</span>
        <span style={{ flex: 1 }}></span>
        <button style={{ color: 'var(--primary)', fontWeight: 600, fontSize: 12 }}>
          {lang === 'vi' ? 'Xem lịch sử' : 'View history'}
        </button>
      </div>
    </aside>
  );
}

function CtxSection({ label, status, lang, children, fresh }) {
  const ring = {
    done: 'var(--ok-600)', in_progress: 'var(--primary)',
    needs_review: 'var(--review-600)', locked: 'var(--ink-300)',
  }[status];
  return (
    <div className={fresh ? 'fresh' : ''} style={{
      border: '1px solid var(--ink-200)', borderRadius: 12,
      background: 'white',
      padding: '12px 14px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: 999, background: ring }}></span>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--ink-800)' }}>{label}</span>
        <span style={{ flex: 1 }}></span>
        {status === 'needs_review' && <span style={{ color: 'var(--review-600)', fontSize: 13 }}>⚠</span>}
        <button style={{ fontSize: 11.5, color: 'var(--ink-400)' }}>▸</button>
      </div>
      {children}
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
      <span style={{ minWidth: 80, color: 'var(--ink-500)' }}>{k}</span>
      <span style={{ flex: 1, color: 'var(--ink-800)', fontWeight: 500 }}>{v}</span>
    </div>
  );
}

/* ===== Composer ===== */

function Composer({ lang, focusId, project, onSend, expert, onExpertChange }) {
  const [text, setText] = React.useState('');
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const taRef = React.useRef(null);
  const pickerRef = React.useRef(null);

  React.useEffect(() => {
    const el = taRef.current; if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(160, el.scrollHeight) + 'px';
  }, [text]);

  React.useEffect(() => {
    if (!pickerOpen) return;
    const onDoc = (e) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) setPickerOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [pickerOpen]);

  const placeholder = expert
    ? { en: `Ask ${expert.name.en} — they'll handle this turn`,
        vi: `Hỏi ${expert.name.vi} — chuyên gia sẽ trả lời` }[lang]
    : { en: `Reply to DoThesis (currently in ${focusId}) — or ask about any module`,
        vi: `Trả lời DoThesis (đang ở ${focusId}) — hoặc hỏi về module bất kỳ` }[lang];

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };
  const send = () => {
    if (!text.trim()) return;
    onSend?.(text);
    setText('');
  };

  return (
    <div style={{ padding: '14px 24px 22px', background: 'var(--bg)' }}>
      <div style={{
        background: 'white',
        border: '1px solid var(--ink-200)',
        borderRadius: 18,
        padding: '10px 12px 10px 16px',
        boxShadow: 'var(--shadow-card)',
        display: 'flex', flexDirection: 'column', gap: 8,
        outline: expert ? '2px solid var(--primary)' : 'none',
        outlineOffset: -2,
      }}>
        {/* Active expert chip */}
        {expert && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '6px 8px 6px 8px', borderRadius: 12,
            background: 'var(--primary-50)', border: '1px solid var(--primary-100)',
          }}>
            <ExpertAvatar e={expert} size={26} />
            <div style={{ lineHeight: 1.2 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--primary-700)' }}>
                {lang === 'vi' ? 'Đang hỏi ' : 'Consulting '}{expert.name[lang]}
              </div>
              <div style={{ fontSize: 11, color: 'var(--primary-700)', opacity: .75 }}>
                {expert.tagline[lang]}
              </div>
            </div>
            <span style={{ flex: 1 }}></span>
            <button onClick={() => onExpertChange?.(null)}
              style={{ padding: '4px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                       color: 'var(--primary-700)' }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(37,64,255,.08)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              ✕ {lang === 'vi' ? 'Đổi' : 'Clear'}
            </button>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <textarea
            ref={taRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKey}
            placeholder={placeholder}
            rows={1}
            style={{
              flex: 1, resize: 'none', border: 'none', outline: 'none',
              background: 'transparent',
              fontSize: 14.5, lineHeight: 1.5, padding: '6px 0',
              color: 'var(--ink-900)',
              fontFamily: 'var(--font)',
            }}
          />
          <button onClick={send}
            className="btn btn-primary"
            style={{ padding: '8px 14px', alignSelf: 'flex-end' }}
            disabled={!text.trim()}>
            <span>{lang === 'vi' ? 'Gửi' : 'Send'}</span>
            <span style={{ opacity: .8 }}>↵</span>
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 4, borderTop: '1px solid var(--ink-100)', position: 'relative' }}>
          {/* Ask an expert */}
          <div ref={pickerRef} style={{ position: 'relative' }}>
            <button onClick={() => setPickerOpen(o => !o)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '5px 12px 5px 6px', borderRadius: 999,
                fontSize: 12.5, fontWeight: 600,
                color: expert ? 'var(--primary-700)' : 'var(--ink-700)',
                background: pickerOpen ? 'var(--ink-100)' : 'transparent',
                border: '1px solid ' + (expert ? 'var(--primary-200)' : 'var(--ink-200)'),
                transition: 'background .12s, border-color .12s',
              }}
              onMouseEnter={e => { if (!pickerOpen) e.currentTarget.style.background = 'var(--ink-100)'; }}
              onMouseLeave={e => { if (!pickerOpen) e.currentTarget.style.background = 'transparent'; }}>
              {expert
                ? (<><ExpertAvatar e={expert} size={20} /><span>{expert.name[lang]}</span></>)
                : (<><span style={{
                      width: 20, height: 20, borderRadius: 999,
                      background: 'var(--ink-200)', color: 'var(--ink-600)',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 12, fontWeight: 700,
                    }}>@</span><span>{lang === 'vi' ? 'Hỏi chuyên gia' : 'Ask an expert'}</span></>)}
              <span style={{ fontSize: 9, opacity: .55 }}>▾</span>
            </button>

            {pickerOpen && (
              <ExpertPicker
                lang={lang}
                focusId={focusId}
                selected={expert?.id}
                onSelect={(e) => { onExpertChange?.(e); setPickerOpen(false); }}
              />
            )}
          </div>

          <ComposerAction icon="📎" label={lang === 'vi' ? 'Đính tệp' : 'Attach'} />
          <ComposerAction icon="◇" label={lang === 'vi' ? 'Vẽ mô hình' : 'Draw model'} />
          <span style={{ flex: 1 }}></span>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 11, color: 'var(--ink-400)' }}>
        <span>⌘K {lang === 'vi' ? 'để chuyển module' : 'to jump module'}</span>
        <span>·</span>
        <span>Shift+↵ {lang === 'vi' ? 'để xuống dòng' : 'for newline'}</span>
      </div>
    </div>
  );
}

/* ---- Expert avatar (serif initial in primary square) ---- */
function ExpertAvatar({ e, size = 32 }) {
  return (
    <span style={{
      width: size, height: size, minWidth: size, borderRadius: Math.round(size * 0.24),
      background: 'var(--primary)', color: 'white',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 800,
      fontSize: Math.round(size * 0.5),
      letterSpacing: '-.02em',
    }}>{e.avatar}</span>
  );
}

/* ---- Expert picker popover ---- */
function ExpertPicker({ lang, focusId, selected, onSelect }) {
  const experts = window.DT_DATA.EXPERTS;
  const relevant = experts.filter(e => e.modules.includes(focusId));
  const other    = experts.filter(e => !e.modules.includes(focusId));

  return (
    <div style={{
      position: 'absolute', bottom: 'calc(100% + 8px)', left: 0,
      width: 380, maxHeight: 480, overflow: 'hidden',
      background: 'white', borderRadius: 16,
      border: '1px solid var(--ink-200)', boxShadow: 'var(--shadow-pop)',
      zIndex: 30, display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        padding: '10px 14px 8px',
        borderBottom: '1px solid var(--ink-100)',
      }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--ink-900)' }}>
          {lang === 'vi' ? 'Chọn chuyên gia phù hợp' : 'Pick a specialist'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-500)', marginTop: 2 }}>
          {lang === 'vi'
            ? 'Mỗi chuyên gia có nền tảng và giọng điệu khác — thread vẫn chỉ một.'
            : 'Each one has its own grounding and voice — still one thread.'}
        </div>
      </div>

      <div style={{ overflowY: 'auto', padding: '4px 6px 8px' }}>
        {relevant.length > 0 && (
          <PickerGroup label={lang === 'vi'
              ? `Phù hợp với ${focusId}`
              : `Suggested for ${focusId}`}>
            {relevant.map(e => (
              <ExpertOption key={e.id} e={e} lang={lang}
                selected={selected === e.id}
                onClick={() => onSelect(e)} />
            ))}
          </PickerGroup>
        )}
        <PickerGroup label={lang === 'vi' ? 'Tất cả chuyên gia' : 'All experts'}>
          {other.map(e => (
            <ExpertOption key={e.id} e={e} lang={lang}
              selected={selected === e.id}
              onClick={() => onSelect(e)} />
          ))}
        </PickerGroup>
      </div>

      <div style={{
        padding: '8px 14px', borderTop: '1px solid var(--ink-100)',
        display: 'flex', alignItems: 'center', gap: 8, background: 'var(--ink-50)',
      }}>
        <button onClick={() => onSelect(null)}
          style={{ fontSize: 11.5, color: 'var(--ink-600)', fontWeight: 600,
                   padding: '4px 8px', borderRadius: 6 }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--ink-100)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
          {lang === 'vi' ? '← Trả về DoThesis' : '← Use base DoThesis'}
        </button>
        <span style={{ flex: 1 }}></span>
        <span style={{ fontSize: 10.5, color: 'var(--ink-400)' }}>
          {lang === 'vi' ? '6 chuyên gia · không tốn thêm token' : '6 experts · no extra token cost'}
        </span>
      </div>
    </div>
  );
}

function PickerGroup({ label, children }) {
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{
        padding: '8px 10px 4px',
        fontSize: 10.5, fontWeight: 700, color: 'var(--ink-500)',
        letterSpacing: '.08em', textTransform: 'uppercase',
      }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>{children}</div>
    </div>
  );
}

function ExpertOption({ e, lang, selected, onClick }) {
  return (
    <button onClick={onClick}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '8px 10px', borderRadius: 10, textAlign: 'left',
        background: selected ? 'var(--primary-50)' : 'transparent',
        border: selected ? '1px solid var(--primary-100)' : '1px solid transparent',
      }}
      onMouseEnter={ev => { if (!selected) ev.currentTarget.style.background = 'var(--ink-50)'; }}
      onMouseLeave={ev => { if (!selected) ev.currentTarget.style.background = 'transparent'; }}>
      <ExpertAvatar e={e} size={32} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink-900)' }}>{e.name[lang]}</span>
          {e.modules.map(m => (
            <span key={m} style={{
              fontSize: 10, fontWeight: 700, 
              padding: '0 5px', borderRadius: 4,
              background: 'var(--ink-100)', color: 'var(--ink-600)',
            }}>{m}</span>
          ))}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-500)', marginTop: 1, lineHeight: 1.4 }}>
          {e.tagline[lang]}
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-400)', marginTop: 4, fontStyle: 'italic' }}>
          “{e.sample[lang]}”
        </div>
      </div>
      {selected && <span style={{ color: 'var(--primary)', fontSize: 14 }}>✓</span>}
    </button>
  );
}

function ComposerAction({ icon, label }) {
  return (
    <button title={label} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '6px 10px', borderRadius: 8,
      fontSize: 12.5, color: 'var(--ink-600)', fontWeight: 500,
    }}
    onMouseEnter={e => e.currentTarget.style.background = 'var(--ink-100)'}
    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <span style={{ fontSize: 14 }}>{icon}</span><span>{label}</span>
    </button>
  );
}

window.ContextPanel = ContextPanel;
window.Composer = Composer;
window.ExpertAvatar = ExpertAvatar;
window.Composer = Composer;
