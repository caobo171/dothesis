/* ===== DoThesis Home page (dashboard) ===== */

/* --- Multi-project data --- */
const HOME_PROJECTS = [
  {
    id: 'p1',
    title: { en: 'TikTok livestream buying behavior of Gen Z in Hà Nội',
             vi: 'Hành vi mua hàng qua livestream TikTok của Gen Z tại Hà Nội' },
    field: { en: 'Marketing · Consumer behavior', vi: 'Marketing · Hành vi tiêu dùng' },
    status: { M1: 'done', M2: 'in_progress', M3: 'needs_review', M4: 'locked', M5: 'locked' },
    progress: 38,
    lastTouched: { en: 'just now · M2 · 26 turns', vi: 'vừa xong · M2 · 26 lượt' },
    paradigm: 'Quantitative · PLS-SEM',
    next: { en: 'Confirm G1 + G2 → draft Chapter 2', vi: 'Chốt G1 + G2 → dựng Chương 2' },
    review: true,
  },
  {
    id: 'p2',
    title: { en: 'Remote-work burnout among junior developers (mixed-methods)',
             vi: 'Burnout của lập trình viên trẻ khi làm việc từ xa (hỗn hợp)' },
    field: { en: 'Organizational behavior', vi: 'Hành vi tổ chức' },
    status: { M1: 'done', M2: 'done', M3: 'done', M4: 'in_progress', M5: 'locked' },
    progress: 64,
    lastTouched: { en: 'yesterday · M4 · running CFA', vi: 'hôm qua · M4 · đang chạy CFA' },
    paradigm: 'Mixed · Sequential explanatory',
    next: { en: 'Drop TR3 & re-run CFA', vi: 'Bỏ TR3 và chạy lại CFA' },
    review: false,
  },
  {
    id: 'p3',
    title: { en: 'Phenomenology of first-gen students at public universities',
             vi: 'Hiện tượng học sinh viên thế hệ đầu tại đại học công lập' },
    field: { en: 'Education · Qualitative', vi: 'Giáo dục · Định tính' },
    status: { M1: 'done', M2: 'done', M3: 'done', M4: 'done', M5: 'in_progress' },
    progress: 86,
    lastTouched: { en: '3 days ago · M5 · §5.2 edited', vi: '3 ngày trước · M5 · §5.2' },
    paradigm: 'Qualitative · Phenomenological',
    next: { en: 'Polish discussion · export DOCX', vi: 'Hoàn chỉnh thảo luận · xuất DOCX' },
    review: false,
  },
  {
    id: 'p4',
    title: { en: 'Untitled — pilot scoping for fintech adoption among SMEs',
             vi: 'Chưa đặt tên — khảo sát adoption fintech ở DNVVN' },
    field: { en: 'Finance · Tech adoption', vi: 'Tài chính · Tech adoption' },
    status: { M1: 'in_progress', M2: 'locked', M3: 'locked', M4: 'locked', M5: 'locked' },
    progress: 8,
    lastTouched: { en: 'last week · M1 · 4 turns', vi: 'tuần trước · M1 · 4 lượt' },
    paradigm: '— · scoping',
    next: { en: 'Narrow scope to 1 of 3 directions', vi: 'Thu hẹp về 1/3 hướng' },
    review: false,
  },
];

function Home() {
  const [lang, setLang] = React.useState('en');
  const [showWizard, setShowWizard] = React.useState(false);
  const T = (en, vi) => lang === 'vi' ? vi : en;

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)', minHeight: 720 }}>
      <HomeSidebar lang={lang} setLang={setLang} onOpenWizard={() => setShowWizard(true)} />

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        <HomeTopBar lang={lang} />
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ maxWidth: 1180, margin: '0 auto', padding: '28px 36px 60px' }}>
            <Hero lang={lang} onOpenWizard={() => setShowWizard(true)} />

            <StatsRow lang={lang} />

            <SectionHeader
              title={T('Your theses', 'Đề tài của bạn')}
              subtitle={T(`${HOME_PROJECTS.length} active · 1 needs review`,
                          `${HOME_PROJECTS.length} đang hoạt động · 1 cần xem lại`)}
              cta={T('+ New thesis', '+ Đề tài mới')}
              onCta={() => setShowWizard(true)}
            />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
              {HOME_PROJECTS.map(p => <ProjectCard key={p.id} p={p} lang={lang} />)}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, marginTop: 32 }}>
              <RecentActivity lang={lang} />
              <LibraryAndTips lang={lang} />
            </div>
          </div>
        </div>
      </main>

      {showWizard && (
        <EntryWizard
          lang={lang}
          onClose={() => setShowWizard(false)}
          onComplete={() => { window.location.href = 'DoThesis.html'; }}
        />
      )}
    </div>
  );
}

/* ---------- Sidebar (home variant: global nav, projects switcher) ---------- */
function HomeSidebar({ lang, setLang, onOpenWizard }) {
  const items = [
    { id: 'home',     icon: '⌂', label: { en: 'Home', vi: 'Trang chủ' }, active: true },
    { id: 'projects', icon: '◷', label: { en: 'All projects', vi: 'Mọi đề tài' }, count: 4 },
    { id: 'library',  icon: '📚', label: { en: 'Library', vi: 'Thư viện' }, count: 218 },
    { id: 'analyses', icon: '∑', label: { en: 'Analyses', vi: 'Phân tích' } },
    { id: 'exports',  icon: '↓', label: { en: 'Exports', vi: 'Xuất bản' } },
  ];
  const meta = [
    { id: 'credits',  icon: '◈', label: { en: 'Credits & billing', vi: 'Tín dụng' } },
    { id: 'settings', icon: '⚙', label: { en: 'Settings', vi: 'Cài đặt' } },
  ];
  return (
    <aside style={{
      width: 264, minWidth: 264, background: 'white',
      borderRight: '1px solid var(--ink-200)', height: '100vh',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '20px 22px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--primary)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: 'white', fontWeight: 800, fontSize: 18,
        }}>D</span>
        <div>
          <div style={{ fontWeight: 800, fontSize: 17.5, letterSpacing: '-.01em' }}>DoThesis</div>
          <div style={{ fontSize: 11, color: 'var(--ink-500)', letterSpacing: '.08em', textTransform: 'uppercase', marginTop: 1 }}>
            {lang === 'vi' ? 'Trợ lý luận văn' : 'Thesis copilot'}
          </div>
        </div>
      </div>

      <nav style={{ padding: '6px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {items.map(it => <NavRow key={it.id} it={it} lang={lang} />)}
      </nav>

      <div style={{ padding: '12px 14px 4px', fontSize: 11, color: 'var(--ink-500)', fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase' }}>
        {lang === 'vi' ? 'Pinned' : 'Pinned'}
      </div>
      <div style={{ padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {HOME_PROJECTS.slice(0, 3).map(p => (
          <button key={p.id} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '8px 10px', borderRadius: 10, textAlign: 'left',
            color: 'var(--ink-700)',
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--ink-50)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
            <span style={{
              width: 22, height: 22, borderRadius: 6,
              background: p.review ? 'var(--review-50)' : 'var(--primary-50)',
              color: p.review ? 'var(--review-text)' : 'var(--primary-700)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 800, 
            }}>{p.review ? '⚠' : '✦'}</span>
            <span style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--ink-800)',
                           display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {p.title[lang]}
            </span>
          </button>
        ))}
      </div>

      <div style={{ flex: 1 }}></div>

      <div style={{ padding: '6px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {meta.map(it => <NavRow key={it.id} it={it} lang={lang} />)}
        <NavRow lang={lang} it={{ id: 'lang', icon: '🌐',
          label: { en: lang === 'en' ? 'English (switch to Tiếng Việt)' : 'English', vi: lang === 'vi' ? 'Tiếng Việt (switch to English)' : 'Tiếng Việt' } }}
          onClick={() => setLang(lang === 'en' ? 'vi' : 'en')} />
      </div>

      {/* Help widget (same style as workspace) */}
      <div style={{ position: 'relative', margin: '8px 14px 16px' }}>
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
          borderRadius: 16, padding: '22px 16px 14px', color: 'white', textAlign: 'center',
          position: 'relative', overflow: 'hidden',
        }}>
          <svg width="220" height="120" style={{ position: 'absolute', top: -10, left: -40, opacity: .08 }} viewBox="0 0 220 120">
            <circle cx="40" cy="20" r="80" stroke="white" strokeWidth="1" fill="none"/>
            <circle cx="40" cy="20" r="58" stroke="white" strokeWidth="1" fill="none"/>
          </svg>
          <div style={{ fontWeight: 700, fontSize: 14, position: 'relative' }}>
            {lang === 'vi' ? 'Bắt đầu nhanh' : 'Quick start'}
          </div>
          <div style={{ fontSize: 11.5, color: 'rgba(255,255,255,.7)', marginTop: 4, lineHeight: 1.4, position: 'relative' }}>
            {lang === 'vi'
              ? 'Bạn đã có gì? Để mình bootstrap từ đó.'
              : 'Already have material? Bootstrap from it.'}
          </div>
          <button onClick={onOpenWizard} style={{
            marginTop: 10, width: '100%', padding: '8px 12px', borderRadius: 999,
            background: 'white', color: 'var(--ink-900)', fontSize: 12.5, fontWeight: 700, position: 'relative',
          }}>
            {lang === 'vi' ? 'Mở trợ lý nhập liệu' : 'Open entry wizard'}
          </button>
        </div>
      </div>
    </aside>
  );
}

function NavRow({ it, lang, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '9px 12px', borderRadius: 10, textAlign: 'left',
      background: it.active ? 'var(--primary-50)' : 'transparent',
      color: it.active ? 'var(--primary-700)' : 'var(--ink-700)',
      fontWeight: it.active ? 700 : 500,
      transition: 'background .12s',
    }}
    onMouseEnter={e => { if (!it.active) e.currentTarget.style.background = 'var(--ink-50)'; }}
    onMouseLeave={e => { if (!it.active) e.currentTarget.style.background = 'transparent'; }}>
      <span style={{ width: 18, fontSize: 15, textAlign: 'center' }}>{it.icon}</span>
      <span style={{ flex: 1, fontSize: 13.5 }}>{it.label[lang]}</span>
      {it.count !== undefined && (
        <span style={{ fontSize: 11.5, color: 'var(--ink-500)', background: 'var(--ink-100)', padding: '1px 7px', borderRadius: 999 }}>
          {it.count}
        </span>
      )}
    </button>
  );
}

/* ---------- Top bar ---------- */
function HomeTopBar({ lang }) {
  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 28px', background: 'white',
      borderBottom: '1px solid var(--ink-200)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'var(--ink-50)', borderRadius: 12,
        padding: '7px 12px', flex: 1, maxWidth: 480, color: 'var(--ink-500)',
      }}>
        <span>⌕</span>
        <span style={{ fontSize: 13 }}>
          {lang === 'vi' ? 'Tìm đề tài, tài liệu, gap...' : 'Search projects, sources, gaps…'}
        </span>
        <span style={{ flex: 1 }}></span>
        <span style={{ fontSize: 11, padding: '2px 6px', background: 'white', border: '1px solid var(--ink-200)', borderRadius: 6 }}>⌘K</span>
      </div>
      <span style={{ flex: 1 }}></span>
      <button className="btn btn-secondary" style={{ padding: '7px 14px', fontSize: 13 }}>
        ↗ {lang === 'vi' ? 'Mời đồng tác giả' : 'Invite co-author'}
      </button>
      <button className="btn-icon" title="Notifications" style={{ background: 'var(--danger-50)', color: 'var(--danger-text)' }}>
        <span style={{ position: 'relative', fontSize: 13 }}>
          🔔
          <span style={{ position: 'absolute', top: -3, right: -4, width: 8, height: 8, borderRadius: 999, background: 'var(--danger-600)', border: '1.5px solid white' }}></span>
        </span>
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 34, height: 34, borderRadius: 999,
          background: 'var(--ink-800)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: 'white', fontWeight: 700, fontSize: 13, 
        }}>JD</span>
        <div style={{ lineHeight: 1.15, whiteSpace: 'nowrap' }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Jeendeet Lam</div>
          <div style={{ fontSize: 11, color: 'var(--ink-500)' }}>Pro Student</div>
        </div>
      </div>
    </header>
  );
}

/* ---------- Hero ---------- */
function Hero({ lang, onOpenWizard }) {
  return (
    <section style={{
      position: 'relative',
      borderRadius: 20, padding: '34px 36px 30px',
      background: 'var(--ink-900)',
      color: 'white', overflow: 'hidden', marginBottom: 24,
      border: '1px solid var(--ink-800)',
    }}>
      {/* Decorative line work */}
      <svg width="360" height="260" style={{ position: 'absolute', top: -30, right: -40, opacity: .10 }} viewBox="0 0 360 260">
        <defs>
          <radialGradient id="blob" cx="50%" cy="40%">
            <stop offset="0%" stopColor="#FFFFFF"/>
            <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0"/>
          </radialGradient>
        </defs>
        <ellipse cx="180" cy="120" rx="160" ry="110" fill="url(#blob)"/>
      </svg>
      <svg width="420" height="200" style={{ position: 'absolute', bottom: -40, left: 30, opacity: .10 }} viewBox="0 0 420 200" fill="none">
        <path d="M0 100 Q 60 30 140 90 T 280 90 T 420 90" stroke="white" strokeWidth="1"/>
        <path d="M0 120 Q 60 50 140 110 T 280 110 T 420 110" stroke="white" strokeWidth="1"/>
        <path d="M0 140 Q 60 70 140 130 T 280 130 T 420 130" stroke="white" strokeWidth="1"/>
      </svg>

      <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-end', gap: 32 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, letterSpacing: '.18em', textTransform: 'uppercase',
                        color: 'rgba(255,255,255,.6)', fontWeight: 700 }}>
            {lang === 'vi' ? 'Buổi chiều · Thứ ba' : 'Tuesday afternoon'}
          </div>
          <h1 style={{ margin: '8px 0 6px', fontSize: 34, fontWeight: 800, letterSpacing: '-.02em',
                       fontFamily: 'var(--font-serif)', lineHeight: 1.1 }}>
            {lang === 'vi' ? 'Chào Jeendeet,' : 'Hello, Jeendeet —'}
            <br/>
            <span style={{ color: 'rgba(255,255,255,.75)', fontWeight: 600 }}>
              {lang === 'vi' ? 'tiếp tục từ chỗ bạn dừng lại?' : 'pick up where you left off?'}
            </span>
          </h1>
          <div style={{ fontSize: 14, color: 'rgba(255,255,255,.7)', maxWidth: 520, marginTop: 8, lineHeight: 1.55 }}>
            {lang === 'vi'
              ? 'Bạn đang ở M2 của TikTok livestream — chỉ còn xác nhận G1, G2 trước khi dựng Chương 2.'
              : "You're in M2 on the TikTok livestream project — confirm G1, G2 and I'll draft Chapter 2."}
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
            <a href="DoThesis.html" className="btn"
              style={{ background: 'white', color: 'var(--ink-900)', padding: '11px 20px', fontSize: 14, textDecoration: 'none' }}>
              ▶ {lang === 'vi' ? 'Tiếp tục đề tài đang làm' : 'Resume current thesis'}
            </a>
            <button onClick={onOpenWizard} className="btn"
              style={{ background: 'rgba(255,255,255,.12)', color: 'white', padding: '11px 20px', fontSize: 14,
                       border: '1px solid rgba(255,255,255,.22)' }}>
              + {lang === 'vi' ? 'Bắt đầu đề tài mới' : 'Start a new thesis'}
            </button>
          </div>
        </div>

        {/* Tokens card */}
        <div style={{
          width: 260,
          background: 'rgba(255,255,255,.08)',
          border: '1px solid rgba(255,255,255,.18)',
          borderRadius: 18, padding: '16px 18px', backdropFilter: 'blur(8px)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
                        color: 'rgba(255,255,255,.7)', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>
            <span>◈</span><span>{lang === 'vi' ? 'Token còn lại' : 'Token balance'}</span>
            <span style={{ marginLeft: 'auto', color: 'rgba(255,255,255,.85)', textTransform: 'none', letterSpacing: 0 }}>Pro Student</span>
          </div>
          <div className="tnum" style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
            <span style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-.02em' }}>184.5k</span>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,.6)' }}>/ 250k</span>
          </div>
          <div style={{ height: 6, background: 'rgba(255,255,255,.16)', borderRadius: 999, marginTop: 10, overflow: 'hidden' }}>
            <div style={{ width: `74%`, height: '100%', background: 'white' }}></div>
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
            <button style={{ flex: 1, padding: '7px 10px', borderRadius: 999,
                             background: 'white', color: 'var(--ink-900)', fontSize: 12.5, fontWeight: 700 }}>
              + {lang === 'vi' ? 'Nạp thêm' : 'Top up'}
            </button>
            <button style={{ padding: '7px 12px', borderRadius: 999,
                             background: 'transparent', color: 'white', fontSize: 12, fontWeight: 600,
                             border: '1px solid rgba(255,255,255,.22)' }}>
              ↗
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------- Stats row ---------- */
function StatsRow({ lang }) {
  const cells = [
    { v: '4',    l: lang === 'vi' ? 'Đề tài đang làm' : 'Active theses',     trend: '+1 this month',  color: 'var(--primary)' },
    { v: '218',  l: lang === 'vi' ? 'Tài liệu trong thư viện' : 'Library sources', trend: '+12 this week', color: 'var(--primary)' },
    { v: '38h',  l: lang === 'vi' ? 'Đã tiết kiệm' : 'Saved this term',       trend: 'vs. solo work',   color: 'var(--primary)' },
    { v: '1',  l: lang === 'vi' ? 'Cần xem lại' : 'Needs review',           trend: 'M3 on p1',        color: 'var(--review-600)' },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
      {cells.map((c, i) => (
        <div key={i} style={{
          background: 'white', borderRadius: 16,
          border: '1px solid var(--ink-200)', padding: '16px 18px',
          display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: c.color + '22',
                         display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                         color: c.color, fontWeight: 800, fontSize: 14 }}>
            {['◷', '◇', '✓', '⚠'][i]}
          </div>
          <div className="tnum" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-.02em', marginTop: 2 }}>{c.v}</div>
          <div style={{ fontSize: 12.5, color: 'var(--ink-600)', fontWeight: 500 }}>{c.l}</div>
          <div style={{ fontSize: 11, color: 'var(--ink-400)', marginTop: 2 }}>{c.trend}</div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Section header ---------- */
function SectionHeader({ title, subtitle, cta, onCta }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', margin: '4px 2px 14px' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-.01em',
                     fontFamily: 'var(--font-serif)' }}>
          {title}
        </h2>
        <div style={{ fontSize: 12.5, color: 'var(--ink-500)', marginTop: 4 }}>{subtitle}</div>
      </div>
      {cta && (
        <button onClick={onCta} className="btn btn-primary" style={{ padding: '9px 16px', fontSize: 13.5 }}>
          {cta}
        </button>
      )}
    </div>
  );
}

/* ---------- Project card ---------- */
function ProjectCard({ p, lang }) {
  const modules = window.DT_DATA.MODULES;
  return (
    <a href="DoThesis.html" style={{
      display: 'block', textDecoration: 'none', color: 'inherit',
      background: 'white', borderRadius: 18,
      border: '1px solid var(--ink-200)', padding: '20px 22px',
      transition: 'transform .12s, box-shadow .12s, border-color .12s',
    }}
    onMouseEnter={e => {
      e.currentTarget.style.borderColor = 'var(--primary-100)';
      e.currentTarget.style.boxShadow = 'var(--shadow-pop)';
      e.currentTarget.style.transform = 'translateY(-1px)';
    }}
    onMouseLeave={e => {
      e.currentTarget.style.borderColor = 'var(--ink-200)';
      e.currentTarget.style.boxShadow = 'none';
      e.currentTarget.style.transform = 'translateY(0)';
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--ink-500)', fontWeight: 700,
                       letterSpacing: '.06em', textTransform: 'uppercase',
                       whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '60%' }}>
          {p.field[lang]}
        </span>
        <span style={{ flex: 1 }}></span>
        {p.review && <span className="tag needs_review" style={{ textTransform: 'none', letterSpacing: 0, whiteSpace: 'nowrap', flexShrink: 0 }}>⚠ {lang === 'vi' ? 'Cần xem lại' : 'Needs review'}</span>}
        <span className="tnum" style={{ fontSize: 12, color: 'var(--ink-500)', fontWeight: 600, flexShrink: 0 }}>{p.progress}%</span>
      </div>
      <h3 style={{
        margin: 0, fontSize: 16, fontWeight: 700, lineHeight: 1.35,
        fontFamily: 'var(--font-serif)', color: 'var(--ink-900)', letterSpacing: '-.005em',
        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        minHeight: 44,
      }}>
        {p.title[lang]}
      </h3>
      <div style={{ fontSize: 12, color: 'var(--ink-500)', marginTop: 4 }}>
        {p.paradigm}
      </div>

      {/* Module dots */}
      <div style={{ display: 'flex', gap: 6, marginTop: 14 }}>
        {modules.map(m => {
          const s = p.status[m.id];
          const bg = { done: 'var(--ok-600)', in_progress: 'var(--primary)',
                       needs_review: 'var(--review-600)', locked: 'var(--ink-200)' }[s];
          const fg = s === 'locked' ? 'var(--ink-500)' : 'white';
          return (
            <span key={m.id} title={`${m.id} · ${m.en} · ${s}`} style={{
              flex: 1, padding: '6px 4px', borderRadius: 8,
              background: bg, color: fg,
              textAlign: 'center', fontSize: 11, fontWeight: 700,
              
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            }}>
              {m.id}
              {s === 'done' && <span>✓</span>}
              {s === 'needs_review' && <span>⚠</span>}
            </span>
          );
        })}
      </div>

      <div style={{
        marginTop: 14, paddingTop: 14, borderTop: '1px dashed var(--ink-200)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-500)', fontWeight: 600,
                       textTransform: 'uppercase', letterSpacing: '.04em' }}>
          {lang === 'vi' ? 'Bước tiếp' : 'Next'}
        </span>
        <span style={{ fontSize: 13, color: 'var(--ink-800)', fontWeight: 500, flex: 1 }}>{p.next[lang]}</span>
        <span style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 700 }}>→</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-400)', marginTop: 6 }}>{p.lastTouched[lang]}</div>
    </a>
  );
}

/* ---------- Recent activity timeline ---------- */
function RecentActivity({ lang }) {
  const items = [
    { icon: '✎',  proj: 'TikTok livestream', mod: 'M2',
      what: { en: 'Confirmed G1 + G2 as working gaps', vi: 'Chốt G1 + G2 làm khoảng trống' },
      when: { en: '2 min ago', vi: '2 phút trước' }, color: 'var(--primary)' },
    { icon: '∑',  proj: 'Remote-work burnout', mod: 'M4',
      what: { en: "Ran CFA — TR3 loading .41 (flagged)", vi: 'Chạy CFA — TR3 loading .41 (cảnh báo)' },
      when: { en: 'Yesterday · 16:08', vi: 'Hôm qua · 16:08' }, color: 'var(--review-600)' },
    { icon: '⤴',  proj: 'TikTok livestream', mod: 'M2',
      what: { en: 'Read M1 — gap 1 mapping (focus held)', vi: 'Đọc M1 — đối chiếu G1 (giữ tiêu điểm)' },
      when: { en: 'Yesterday · 14:32', vi: 'Hôm qua · 14:32' }, color: 'var(--ok-600)' },
    { icon: '§',  proj: 'First-gen students', mod: 'M5',
      what: { en: 'Edited §5.2 — added APA citation', vi: 'Sửa §5.2 — thêm trích dẫn APA' },
      when: { en: '3d ago', vi: '3 ngày trước' }, color: 'var(--ink-600)' },
    { icon: '⚠',  proj: 'TikTok livestream', mod: 'M3',
      what: { en: 'M3 auto-flagged needs_review after gap edit', vi: 'M3 tự đánh dấu needs_review sau khi sửa khoảng trống' },
      when: { en: '3d ago', vi: '3 ngày trước' }, color: 'var(--review-600)' },
  ];
  return (
    <div style={{ background: 'white', borderRadius: 18, border: '1px solid var(--ink-200)', padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, letterSpacing: '-.01em' }}>
          {lang === 'vi' ? 'Hoạt động gần đây' : 'Recent activity'}
        </h3>
        <span style={{ flex: 1 }}></span>
        <button className="chip" style={{ fontSize: 12 }}>{lang === 'vi' ? 'Mọi hoạt động' : 'All activity'}</button>
      </div>
      <ol style={{ margin: 0, padding: 0, listStyle: 'none', position: 'relative' }}>
        <span style={{ position: 'absolute', left: 13, top: 12, bottom: 12, width: 2, background: 'var(--ink-100)' }}></span>
        {items.map((it, i) => (
          <li key={i} style={{ position: 'relative', display: 'flex', gap: 12, paddingBottom: i === items.length - 1 ? 0 : 14 }}>
            <span style={{
              width: 28, height: 28, minWidth: 28, borderRadius: 999,
              background: 'white', border: '2px solid ' + it.color, color: it.color,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 800, fontSize: 12, zIndex: 1,
            }}>{it.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, color: 'var(--ink-900)', lineHeight: 1.45 }}>
                {it.what[lang]}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-500)', marginTop: 2,
                              display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{it.mod}</span>
                <span>·</span>
                <span style={{ fontWeight: 500, color: 'var(--ink-700)' }}>{it.proj}</span>
                <span>·</span>
                <span>{it.when[lang]}</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ---------- Library + tips ---------- */
function LibraryAndTips({ lang }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ background: 'white', borderRadius: 18, border: '1px solid var(--ink-200)', padding: '18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, letterSpacing: '-.01em' }}>
            {lang === 'vi' ? 'Thư viện của bạn' : 'Your library'}
          </h3>
          <span style={{ flex: 1 }}></span>
          <span style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>{lang === 'vi' ? '218 nguồn' : '218 sources'}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
          {[
            { name: 'Sun et al. (2019)',        venue: 'Electronic Commerce R&A',     cites: 612, badge: 'Seminal', color: 'var(--ink-800)' },
            { name: 'Hu, Zhang & Wang (2017)',  venue: 'Computers in Human Behavior', cites: 1043, badge: 'Seminal', color: 'var(--ink-800)' },
            { name: 'Wongkitrungrueng & Assarut (2020)', venue: 'J. Business Research', cites: 824, badge: 'Cited 3×', color: 'var(--primary)' },
            { name: 'Aggarwal et al. (2011)',   venue: 'J. of Advertising',            cites: 358, badge: 'Cited 2×', color: 'var(--primary)' },
          ].map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{
                width: 28, height: 36, borderRadius: 4,
                background: 'var(--paper)',
                border: '1px solid var(--ink-200)',
                display: 'inline-flex', alignItems: 'flex-end', justifyContent: 'center',
                fontSize: 8, fontWeight: 800, color: 'var(--ink-500)',
              }}>PDF</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-900)' }}>{s.name}</div>
                <div style={{ fontSize: 11, color: 'var(--ink-500)', fontStyle: 'italic' }}>{s.venue}</div>
              </div>
              <span style={{
                fontSize: 10.5, padding: '2px 7px', borderRadius: 999, fontWeight: 700,
                background: s.color + '18', color: s.color,
              }}>{s.badge}</span>
            </div>
          ))}
        </div>
        <button className="btn btn-secondary" style={{ width: '100%', marginTop: 14, padding: '8px', fontSize: 13 }}>
          {lang === 'vi' ? 'Mở thư viện đầy đủ' : 'Open full library'} →
        </button>
      </div>

      <div style={{
        borderRadius: 16, padding: '18px 20px',
        background: 'var(--primary-50)',
        border: '1px solid var(--primary-100)',
      }}>
        <div style={{ fontSize: 11, color: 'var(--primary)', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>
          {lang === 'vi' ? 'Mẹo' : 'Pro tip'}
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, marginTop: 4, lineHeight: 1.45, color: 'var(--ink-900)',
                       fontFamily: 'var(--font-serif)' }}>
          {lang === 'vi'
            ? 'Bạn có thể hỏi về một module ngay khi đang ở module khác — tiêu điểm sẽ không đổi nếu bạn chỉ đọc.'
            : 'You can ask about any module from any other — focus only shifts on an edit, not a read.'}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button className="chip" style={{ background: 'white' }}>“{lang === 'vi' ? 'G2 là gì?' : 'What is G2?'}”</button>
          <button className="chip" style={{ background: 'white' }}>“{lang === 'vi' ? 'Sửa H1' : 'Edit H1'}”</button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Mount ---------- */
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<Home />);
