/* ===== Rich content blocks for chat messages ===== */

/* ----- 1. State of literature: camp breakdown ----- */
function StateOfLitBlock({ lang }) {
  const camps = window.DT_DATA.STATE_OF_LIT;
  const total = camps.reduce((s, c) => s + c.papers, 0);
  return (
    <div style={{
      marginTop: 10, padding: 14, borderRadius: 14,
      background: 'var(--surface-2)', border: '1px solid var(--ink-200)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>
          {lang === 'vi' ? 'Bản đồ trường phái lý thuyết' : 'Theoretical camps'}
        </span>
        <span className="tag in_progress" style={{ textTransform: 'none', letterSpacing: 0 }}>
          {total} {lang === 'vi' ? 'bài' : 'papers'}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 12, height: 8, borderRadius: 999, overflow: 'hidden', background: 'var(--ink-100)' }}>
        {camps.map((c, i) => (
          <span key={i} title={c.camp} style={{
            width: `${(c.papers / total) * 100}%`,
            background: ['var(--primary)', 'var(--primary-500)', 'var(--primary-200)', 'var(--ink-300)'][i % 4],
          }}></span>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {camps.map((c, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2,
              background: ['var(--primary)', 'var(--primary-500)', 'var(--primary-200)', 'var(--ink-300)'][i % 4] }}></span>
            <span style={{ flex: 1, fontWeight: 600, color: 'var(--ink-800)' }}>{c.camp}</span>
            <span style={{ color: 'var(--ink-500)', fontSize: 12, marginRight: 10 }}>e.g. {c.sample}</span>
            <span className="tnum" style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--ink-700)', fontWeight: 700, minWidth: 22, textAlign: 'right' }}>{c.papers}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ----- 2. Gap cards ----- */
function GapList({ lang, project }) {
  const gaps = project.contextStore.research_gaps;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
      {gaps.map(g => <GapCard key={g.id} gap={g} lang={lang} />)}
    </div>
  );
}

function GapCard({ gap, lang }) {
  return (
    <div style={{
      padding: 14, borderRadius: 14,
      background: 'white', border: '1px solid var(--ink-200)',
      boxShadow: '0 1px 0 rgba(11,16,32,.03)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{
          padding: '2px 8px', borderRadius: 6,
          background: 'var(--primary-50)', color: 'var(--primary-700)',
          fontWeight: 800, fontSize: 12,
        }}>{gap.id}</span>
        <span className={`tag ${gap.relevance.toLowerCase()}`} style={{ textTransform: 'none', letterSpacing: 0 }}>
          {lang === 'vi'
            ? { High: 'Mức độ cao', Medium: 'Mức độ vừa', Low: 'Mức độ thấp' }[gap.relevance]
            : `${gap.relevance} relevance`}
        </span>
        {gap.confirmed
          ? <span className="tag done" style={{ textTransform: 'none', letterSpacing: 0 }}>{lang === 'vi' ? '✓ Đã chốt' : '✓ Confirmed'}</span>
          : <span className="tag mutate" style={{ textTransform: 'none', letterSpacing: 0 }}>{lang === 'vi' ? '· Đề xuất' : '· Proposed'}</span>}
      </div>
      <div style={{ fontSize: 14, color: 'var(--ink-900)', lineHeight: 1.5, textWrap: 'pretty' }}>
        {gap[lang]}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-500)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em' }}>
          {lang === 'vi' ? 'Bằng chứng' : 'Evidence'}
        </span>
        {gap.papers.map((p, i) => (
          <Citation key={i} paper={p} />
        ))}
      </div>
    </div>
  );
}

function Citation({ paper }) {
  return (
    <span className={`cite ${paper.verified ? '' : 'unverified'}`}>
      <span>{paper.author}, {paper.year}</span>
      {paper.page !== null && paper.page !== undefined && (
        <span className="pg">· p.{paper.page}</span>
      )}
      {!paper.verified && <span title="Page not yet verified" style={{ fontSize: 10 }}>⚠</span>}
    </span>
  );
}

/* ----- 3. Gap draft (cross-module mutation) ----- */
function GapDraft({ lang }) {
  return (
    <div style={{
      marginTop: 12, padding: 14, borderRadius: 14,
      background: 'var(--review-50)', border: '1px solid #FFD8A0',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          padding: '2px 8px', borderRadius: 6,
          background: 'var(--review-600)', color: 'white',
          fontWeight: 800, fontSize: 12,
        }}>G4 (draft)</span>
        <span className="tag mutate" style={{ textTransform: 'none', letterSpacing: 0 }}>
          {lang === 'vi' ? 'Mới · chưa neo bằng chứng' : 'New · evidence pending'}
        </span>
      </div>
      <div style={{ fontSize: 14, color: 'var(--ink-900)', lineHeight: 1.5 }}>
        {lang === 'vi'
          ? 'Hành vi mua bốc đồng trên livestream trong bối cảnh làm việc/học từ xa của Gen Z chưa được kiểm định — đa số nghiên cứu hiện có lấy mẫu trước đại dịch.'
          : 'Impulsive livestream buying among Gen Z in remote-work / remote-study contexts is untested — most existing samples were drawn pre-pandemic.'}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        <button className="btn btn-primary" style={{ padding: '7px 14px', fontSize: 13 }}>
          {lang === 'vi' ? 'Tìm bằng chứng (Semantic Scholar)' : 'Find evidence (Semantic Scholar)'}
        </button>
        <button className="btn btn-secondary" style={{ padding: '7px 14px', fontSize: 13 }}>
          {lang === 'vi' ? 'Viết lại nhẹ hơn' : 'Soften scope'}
        </button>
        <span style={{ flex: 1 }}></span>
        <span style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
          {lang === 'vi' ? 'Sẽ kích hoạt ⚠ cho M3 · M4 · M5' : 'Will flag ⚠ M3 · M4 · M5'}
        </span>
      </div>
    </div>
  );
}

/* ----- 4. Chapter 2 doc preview ----- */
function DocPreview({ lang }) {
  const sections = lang === 'vi'
    ? [
        { num: '2.1', title: 'Hiện diện xã hội trong môi trường livestream', cite: 'Sun et al., 2019' },
        { num: '2.2', title: 'Niềm tin streamer và tương tác bán xã hội', cite: 'Hu, Zhang & Wang, 2017' },
        { num: '2.3', title: 'Tín hiệu khan hiếm và mua bốc đồng', cite: 'Aggarwal et al., 2011' },
        { num: '2.4', title: 'Khoảng trống nghiên cứu (G1, G2)', cite: null },
      ]
    : [
        { num: '2.1', title: 'Social presence in livestream environments', cite: 'Sun et al., 2019' },
        { num: '2.2', title: 'Streamer trust and parasocial interaction',  cite: 'Hu, Zhang & Wang, 2017' },
        { num: '2.3', title: 'Scarcity cues and impulsive purchasing',     cite: 'Aggarwal et al., 2011' },
        { num: '2.4', title: 'Research gaps (G1, G2)',                     cite: null },
      ];
  return (
    <div style={{
      marginTop: 12, padding: 0, borderRadius: 14,
      background: 'white', border: '1px solid var(--ink-200)',
      overflow: 'hidden', boxShadow: 'var(--shadow-card)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 14px', background: 'var(--ink-50)', borderBottom: '1px solid var(--ink-200)',
      }}>
        <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--ink-600)' }}>chapter-2.draft.docx</span>
        <span className="tag in_progress" style={{ textTransform: 'none', letterSpacing: 0 }}>
          ~ 2,840 {lang === 'vi' ? 'từ' : 'words'}
        </span>
        <span style={{ flex: 1 }}></span>
        <button className="btn-icon" style={{ width: 28, height: 28, fontSize: 13 }} title="Open in editor">⤢</button>
        <button className="btn-icon" style={{ width: 28, height: 28, fontSize: 13 }} title="Download">↓</button>
      </div>
      <div style={{ padding: '16px 22px', color: 'var(--ink-800)' }}>
        <div style={{ fontSize: 11.5, color: 'var(--ink-500)', fontFamily: 'var(--font)', letterSpacing: '.06em', textTransform: 'uppercase', fontWeight: 700 }}>
          {lang === 'vi' ? 'Chương 2 · Tổng quan tài liệu' : 'Chapter 2 · Literature Review'}
        </div>
        <h3 style={{ margin: '4px 0 14px', fontSize: 19, fontWeight: 700, color: 'var(--ink-900)', letterSpacing: '-.01em' }}>
          {lang === 'vi'
            ? 'Hành vi mua bốc đồng trên livestream: từ S-O-R đến tương tác bán xã hội'
            : 'Impulsive livestream buying: from S-O-R to parasocial interaction'}
        </h3>
        <p style={{ margin: '0 0 10px', fontSize: 14, lineHeight: 1.6 }}>
          {lang === 'vi'
            ? 'Văn liệu về thương mại trên livestream phát triển nhanh quanh ba trụ cột: tác động kích thích–phản hồi của các tín hiệu môi trường, vai trò trung gian của trạng thái nội tại người xem, và các tín hiệu khan hiếm như chất xúc tác. '
            : 'The livestream commerce literature has grown rapidly around three pillars: stimulus–response effects of environmental cues, the mediating role of viewers\' internal states, and scarcity cues as accelerants. '}
          <span className="cite">Sun et al., 2019<span className="pg"> · p.41</span></span>{' '}
          {lang === 'vi'
            ? 'phác hoạ khung S-O-R cho livestream Taobao; '
            : 'sketch an S-O-R frame for Taobao livestream; '}
          <span className="cite">Wongkitrungrueng &amp; Assarut, 2020<span className="pg"> · p.545</span></span>{' '}
          {lang === 'vi' ? 'mở rộng sang lòng tin và sự tham gia.' : 'extend it to trust and engagement.'}
        </p>
        <ul style={{ margin: '8px 0 0', padding: 0, listStyle: 'none', borderTop: '1px dashed var(--ink-200)' }}>
          {sections.map(s => (
            <li key={s.num} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 0', borderBottom: '1px dashed var(--ink-200)',
              fontFamily: 'var(--font)',
            }}>
              <span style={{ width: 30, fontSize: 12, fontWeight: 700, color: 'var(--ink-500)' }}>{s.num}</span>
              <span style={{ flex: 1, fontSize: 13.5, color: 'var(--ink-800)' }}>{s.title}</span>
              {s.cite && <span className="cite" style={{ fontSize: 11 }}>{s.cite}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* ----- 5. Pipeline outline (M4) ----- */
function OutlineBlock({ lang }) {
  const steps = window.DT_DATA.M4_OUTLINE;
  return (
    <div style={{
      marginTop: 10, padding: 14, borderRadius: 14,
      background: 'white', border: '1px solid var(--ink-200)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>
          {lang === 'vi' ? 'Phác outline phân tích · PLS-SEM' : 'Proposed pipeline · PLS-SEM'}
        </span>
        <span className="tag continue" style={{ textTransform: 'none', letterSpacing: 0 }}>
          {lang === 'vi' ? 'Bạn có thể bỏ / sắp xếp lại' : 'Drag to reorder'}
        </span>
      </div>
      <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {steps.map(s => (
          <li key={s.step} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '8px 10px', borderRadius: 10,
            background: s.status === 'done' ? 'var(--ok-50)' : 'var(--ink-50)',
          }}>
            <span style={{
              width: 22, height: 22, borderRadius: 999,
              background: s.status === 'done' ? 'var(--ok-600)' : 'white',
              color: s.status === 'done' ? 'white' : 'var(--ink-500)',
              border: s.status === 'done' ? 'none' : '1.5px solid var(--ink-300)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 700, fontSize: 11.5,
            }}>{s.status === 'done' ? '✓' : s.step}</span>
            <span style={{ flex: 1, fontSize: 13.5, color: 'var(--ink-800)', fontWeight: 500 }}>
              {s.name[lang]}
            </span>
            <code style={{ background: 'white', padding: '2px 8px', borderRadius: 6,
                           border: '1px solid var(--ink-200)', fontSize: 11.5,
                           color: 'var(--ink-600)', fontFamily: 'var(--font-mono)' }}>{s.op}</code>
            <button className="btn-icon" style={{ width: 24, height: 24, fontSize: 12 }}>✕</button>
          </li>
        ))}
      </ol>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" style={{ padding: '8px 16px', fontSize: 13 }}>
          ▶ {lang === 'vi' ? 'Chạy bước 1–4' : 'Run steps 1–4'}
        </button>
        <button className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 13 }}>
          + {lang === 'vi' ? 'Thêm bước' : 'Add step'}
        </button>
        <span style={{ flex: 1 }}></span>
        <span style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
          {lang === 'vi' ? 'Chạy trong sandbox · whitelist · không có mạng' : 'Sandbox · whitelisted ops · no network'}
        </span>
      </div>
    </div>
  );
}

/* ----- 6. Results table ----- */
function ResultsTable({ lang }) {
  const rows = window.DT_DATA.M4_RESULTS;
  const head = lang === 'vi'
    ? ['Thang đo', 'Items', 'α', 'AVE', 'CR', 'Cảnh báo']
    : ['Construct', 'Items', 'α', 'AVE', 'CR', 'Flag'];
  return (
    <div style={{
      marginTop: 10, borderRadius: 14, overflow: 'hidden',
      border: '1px solid var(--ink-200)', background: 'white',
    }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '2fr .5fr .5fr .5fr .5fr 1.2fr',
        padding: '10px 14px', background: 'var(--ink-50)',
        fontSize: 11, fontWeight: 700, color: 'var(--ink-500)',
        textTransform: 'uppercase', letterSpacing: '.06em',
      }}>
        {head.map((h, i) => <span key={i} style={{ textAlign: i === 0 ? 'left' : 'right' }}>{h}</span>)}
      </div>
      {rows.map((r, i) => {
        const flagged = !!r.flag;
        return (
          <div key={i} style={{
            display: 'grid', gridTemplateColumns: '2fr .5fr .5fr .5fr .5fr 1.2fr',
            padding: '10px 14px', alignItems: 'center',
            fontSize: 13.5, color: 'var(--ink-800)',
            borderTop: '1px solid var(--ink-200)',
            background: flagged ? 'var(--danger-50)' : 'white',
            fontVariantNumeric: 'tabular-nums',
          }}>
            <span style={{ fontWeight: 600 }}>{r.name}</span>
            <span style={{ textAlign: 'right' }}>{r.items}</span>
            <span style={{ textAlign: 'right' }}>{r.alpha}</span>
            <span style={{ textAlign: 'right', color: flagged ? 'var(--danger-text)' : 'inherit', fontWeight: flagged ? 700 : 400 }}>{r.AVE}</span>
            <span style={{ textAlign: 'right' }}>{r.CR}</span>
            <span style={{ textAlign: 'right' }}>
              {r.flag && <span className="tag high" style={{ textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>⚠ {r.flag}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ----- 7. Model canvas thumbnail ----- */
function ModelCanvas({ lang }) {
  return (
    <div style={{
      marginTop: 10, padding: 14, borderRadius: 14,
      background: 'white', border: '1px solid var(--ink-200)',
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
        {lang === 'vi' ? 'Mô hình khái niệm' : 'Conceptual model'}
      </div>
      <svg viewBox="0 0 600 240" style={{ width: '100%', height: 240 }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink-500)"/>
          </marker>
        </defs>
        {/* nodes */}
        {[
          { x: 30,  y: 50,  w: 130, h: 50, l: lang === 'vi' ? 'Niềm tin streamer' : 'Streamer trust', color: 'var(--primary)' },
          { x: 30,  y: 140, w: 130, h: 50, l: lang === 'vi' ? 'Hiện diện xã hội' : 'Social presence', color: 'var(--primary)' },
          { x: 235, y: 95,  w: 140, h: 50, l: lang === 'vi' ? 'Tương tác bán xã hội' : 'Parasocial interaction', color: 'var(--ink-700)' },
          { x: 440, y: 95,  w: 130, h: 50, l: lang === 'vi' ? 'Ý định mua bốc đồng' : 'Impulsive intention', color: 'var(--primary-700)' },
          { x: 280, y: 195, w: 130, h: 30, l: lang === 'vi' ? 'Khan hiếm (điều tiết)' : 'Scarcity (mod.)', color: 'var(--ink-600)' },
        ].map((n, i) => (
          <g key={i}>
            <rect x={n.x} y={n.y} width={n.w} height={n.h} rx="10" fill="white" stroke={n.color} strokeWidth="1.5"/>
            <text x={n.x + n.w/2} y={n.y + n.h/2 + 4} fontSize="11" textAnchor="middle" fill="var(--ink-800)" fontWeight="600">{n.l}</text>
          </g>
        ))}
        {/* edges */}
        <g stroke="var(--ink-500)" strokeWidth="1.5" fill="none" markerEnd="url(#arrow)">
          <path d="M 160 75 L 235 110" />
          <path d="M 160 165 L 235 130" />
          <path d="M 375 120 L 440 120" />
          <path d="M 160 75 Q 300 30 440 110" stroke="var(--primary)" strokeDasharray="4 3"/>
          <path d="M 345 195 L 440 145" stroke="var(--ink-600)" strokeDasharray="2 3"/>
        </g>
        <text x="430" y="50" fontSize="11" fill="var(--primary)" fontStyle="italic">H1 (direct)</text>
        <text x="300" y="80" fontSize="10.5" fill="var(--ink-600)">H2 (mediation)</text>
        <text x="320" y="180" fontSize="10.5" fill="var(--ink-600)">H3 (mod.)</text>
      </svg>
    </div>
  );
}

window.StateOfLitBlock = StateOfLitBlock;
window.GapList = GapList;

/* ----- Founding citations: seminal papers grouped by camp, with page-cited quotes ----- */
function FoundingSourcesBlock({ lang }) {
  const camps = window.DT_DATA.FOUNDING_SOURCES;
  const total = camps.reduce((s, c) => s + c.papers.length, 0);
  return (
    <div style={{
      marginTop: 10, padding: 0, borderRadius: 14, overflow: 'hidden',
      background: 'white', border: '1px solid var(--ink-200)',
    }}>
      <div style={{
        padding: '10px 14px', background: 'var(--ink-50)',
        borderBottom: '1px solid var(--ink-200)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>
          {lang === 'vi' ? '📚 Tài liệu nền' : '📚 Foundational citations'}
        </span>
        <span className="tag in_progress" style={{ textTransform: 'none', letterSpacing: 0 }}>
          {total} {lang === 'vi' ? 'bài seminal · 41 tổng' : 'seminal · 41 indexed'}
        </span>
        <span style={{ flex: 1 }}></span>
        <span style={{ fontSize: 11, color: 'var(--ink-500)' }}>APA 7</span>
      </div>
      <div style={{ padding: '4px 0' }}>
        {camps.map((c, i) => (
          <div key={i}>
            <div style={{
              padding: '12px 16px 6px',
              fontSize: 11, fontWeight: 700, color: 'var(--ink-500)',
              letterSpacing: '.06em', textTransform: 'uppercase',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: 2,
                background: ['var(--primary)', 'var(--primary-500)', 'var(--primary-200)', 'var(--ink-300)'][i % 4] }}></span>
              <span>{c.camp[lang]}</span>
              <span style={{ flex: 1 }}></span>
              <span style={{ color: 'var(--ink-400)', letterSpacing: 0, textTransform: 'none', fontWeight: 500 }}>
                {c.papers.length} {lang === 'vi' ? 'bài' : 'papers'}
              </span>
            </div>
            {c.papers.map((p, j) => <SourceRow key={j} p={p} lang={lang} />)}
          </div>
        ))}
      </div>
      <div style={{
        padding: '10px 14px', background: 'var(--ink-50)',
        borderTop: '1px solid var(--ink-200)',
        display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--ink-600)',
      }}>
        <span>{lang === 'vi' ? '✓ Tất cả số trang đã xác minh qua GROBID' : '✓ All pages verified via GROBID'}</span>
        <span style={{ flex: 1 }}></span>
        <button className="chip" style={{ fontSize: 12 }}>
          + {lang === 'vi' ? 'Thêm bài từ Semantic Scholar' : 'Add from Semantic Scholar'}
        </button>
        <button className="chip" style={{ fontSize: 12 }}>
          ↗ {lang === 'vi' ? 'Mở thư viện đầy đủ' : 'Open full library'}
        </button>
      </div>
    </div>
  );
}

function SourceRow({ p, lang }) {
  return (
    <div style={{
      padding: '12px 16px 14px',
      borderTop: '1px solid var(--ink-100)',
      display: 'flex', gap: 14, alignItems: 'flex-start',
    }}>
      <div style={{
        width: 38, minWidth: 38, height: 48, borderRadius: 6,
        background: 'var(--paper)',
        border: '1px solid var(--ink-200)',
        position: 'relative',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        boxShadow: '1px 1px 0 var(--ink-150)',
      }}>
        {p.seminal && (
          <span style={{
            position: 'absolute', top: -6, right: -6,
            width: 18, height: 18, borderRadius: 999,
            background: 'var(--ink-900)', color: 'white',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, fontWeight: 800,
          }} title="Seminal">★</span>
        )}
        <span style={{ fontSize: 9, fontWeight: 800, color: 'var(--primary)', padding: '2px 0' }}>PDF</span>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink-900)' }}>{p.author}</span>
          <span style={{ fontSize: 12.5, color: 'var(--ink-500)' }}>({p.year})</span>
          <span style={{ fontSize: 11, color: 'var(--primary)', background: 'var(--primary-50)', padding: '1px 6px', borderRadius: 999, fontWeight: 600 }}>
            {p.cites.toLocaleString()} {lang === 'vi' ? 'trích' : 'cites'}
          </span>
        </div>
        <div style={{ fontSize: 13.2, color: 'var(--ink-800)', lineHeight: 1.4, marginTop: 3, fontWeight: 500, textWrap: 'pretty' }}>
          {p.title}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-500)', marginTop: 3, fontStyle: 'italic' }}>
          {p.venue}, {p.vol}{p.doi && <> · <span style={{ fontFamily: 'var(--font-mono)', fontStyle: 'normal' }}>doi:{p.doi}</span></>}
        </div>
        <div style={{
          marginTop: 8, padding: '8px 10px 8px 12px',
          borderLeft: '3px solid var(--primary)',
          background: 'var(--primary-50)',
          borderRadius: '0 8px 8px 0',
          fontFamily: 'var(--font-serif)', fontSize: 13.5, color: 'var(--ink-800)', lineHeight: 1.5,
        }}>
          {p.quote[lang]}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 6 }}>
        <button className="btn-icon" style={{ width: 26, height: 26, fontSize: 11 }} title={lang === 'vi' ? 'Mở PDF tại trang ' + p.page : 'Open PDF at p.' + p.page}>⤴</button>
        <button className="btn-icon" style={{ width: 26, height: 26, fontSize: 11 }} title={lang === 'vi' ? 'Trích dẫn' : 'Insert citation'}>“ ”</button>
        <button className="btn-icon" style={{ width: 26, height: 26, fontSize: 11 }} title={lang === 'vi' ? 'Gắn cờ' : 'Flag'}>✗</button>
      </div>
    </div>
  );
}

window.FoundingSourcesBlock = FoundingSourcesBlock;
window.GapDraft = GapDraft;
window.DocPreview = DocPreview;
window.OutlineBlock = OutlineBlock;
window.ResultsTable = ResultsTable;
window.ModelCanvas = ModelCanvas;
