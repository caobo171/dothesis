/* ===== App: shell + scenarios + tweaks ===== */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  thread: 'th-current',
  lang: 'en',
  showContext: true,
  showWizard: false,
  sidebarTab: 'threads',
  density: 'comfy',
  primary: '#2540FF'
}/*EDITMODE-END*/;

const THREAD_TO_SCENARIO = {
  'th-current':  'M2-output',
  'th-method':   'M3-method',
  'th-m4':       'M4-analysis',
  'th-readclub': 'M2-reading',
  'th-topic':    'M1-archived',
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [showWizard, setShowWizard] = React.useState(false);
  const [freshKey, setFreshKey] = React.useState(null);
  const [expert, setExpert] = React.useState(null);

  React.useEffect(() => {
    if (t.showWizard) setShowWizard(true);
  }, [t.showWizard]);

  // Resolve thread → scenario, then build state
  const scenario = THREAD_TO_SCENARIO[t.thread] || 'M2-output';
  const { project, transcript } = React.useMemo(() => buildScenario(scenario), [scenario]);
  const threadMeta = window.DT_DATA.THREADS.find(th => th.id === t.thread) || window.DT_DATA.THREADS[0];

  // CSS var for primary (live tweak)
  React.useEffect(() => {
    document.documentElement.style.setProperty('--primary', t.primary);
    document.documentElement.style.setProperty('--primary-600', t.primary);
  }, [t.primary]);

  // Fresh-write highlight on mutate scenarios
  React.useEffect(() => {
    if (scenario === 'M4-mutate-M2') {
      setFreshKey('M2.gaps');
      const id = setTimeout(() => setFreshKey(null), 2600);
      return () => clearTimeout(id);
    }
  }, [scenario]);

  const lang = t.lang;
  const focusId = project.focus;

  const scrollRef = React.useRef(null);
  // Reset to top of the conversation when thread changes.
  React.useEffect(() => {
    const el = scrollRef.current; if (!el) return;
    el.scrollTop = 0;
  }, [t.thread]);

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)', minHeight: 720 }}>
      <Sidebar
        T={null}
        project={project}
        focusId={focusId}
        onFocus={(id) => {/* read-only in this prototype */}}
        lang={lang}
        onOpenWizard={() => setShowWizard(true)}
        threads={window.DT_DATA.THREADS}
        activeThreadId={t.thread}
        onSelectThread={(id) => setTweak('thread', id)}
        onNewThread={() => setShowWizard(true)}
      />

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        <FocusBar T={null} project={project} focusId={focusId} lang={lang} threadMeta={threadMeta} />

        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '8px 24px 0' }}>
          <div style={{ maxWidth: 880, margin: '0 auto', padding: '12px 0 12px' }}>
            <ConversationHeader project={project} lang={lang} thread={threadMeta} />
            {transcript.map((turn, i) => (
              <MessageBubble
                key={`${t.thread}-${i}`}
                turn={turn}
                lang={lang}
                project={project}
                isLast={i === transcript.length - 1}
              />
            ))}
            <ChatHint lang={lang} scenario={scenario} />
          </div>
        </div>

        <Composer lang={lang} focusId={focusId} project={project}
          expert={expert} onExpertChange={setExpert}
          onSend={() => {}} />
      </main>

      {t.showContext && (
        <ContextPanel project={project} lang={lang} focusId={focusId} freshKey={freshKey} />
      )}

      {showWizard && (
        <EntryWizard
          lang={lang}
          onClose={() => { setShowWizard(false); setTweak('showWizard', false); }}
          onComplete={() => { setShowWizard(false); setTweak('showWizard', false); setTweak('thread', 'th-current'); }}
        />
      )}

      <DoThesisTweaks t={t} setTweak={setTweak} />
    </div>
  );
}

function ConversationHeader({ project, lang, thread }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 4px 16px', borderBottom: '1px dashed var(--ink-200)', marginBottom: 8 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-.01em',
                          color: 'var(--ink-900)',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {thread.title[lang]}
          </span>
          {thread.pinned && <span style={{ fontSize: 11, color: 'var(--ink-400)' }}>📌</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 11.5, color: 'var(--ink-500)' }}>
          <span style={{
            padding: '2px 7px', borderRadius: 6, fontWeight: 800,
            background: 'var(--primary-50)', color: 'var(--primary-700)', fontSize: 11,
          }}>{thread.module}</span>
          <span>·</span>
          <span>{thread.turns} {lang === 'vi' ? 'lượt' : 'turns'}</span>
          <span>·</span>
          <span className="tnum">{thread.tokens} {lang === 'vi' ? 'tok' : 'tok'}</span>
          <span>·</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: 'var(--ok-600)' }}></span>
            {lang === 'vi' ? 'Bộ nhớ đầy đủ' : 'FULL memory'}
          </span>
        </div>
      </div>
      <button className="chip" style={{ fontSize: 12 }}>☆ {lang === 'vi' ? 'Ghim' : 'Pin'}</button>
      <button className="chip" style={{ fontSize: 12 }}>⎘ {lang === 'vi' ? 'Lưu trữ' : 'Archive'}</button>
    </div>
  );
}

function ChatHint({ lang, scenario }) {
  const hint = {
    'M2-output':     { en: 'Try jumping threads from the left rail — each thread keeps its own history but reads the same context_store.',
                       vi: 'Thử nhảy giữa các thread bên trái — mỗi thread có lịch sử riêng nhưng cùng đọc context_store.' },
    'M3-method':     { en: 'A short "sanity check" thread — read-only into M3.',
                       vi: 'Thread kiểm tra ngắn — chỉ đọc M3.' },
    'M4-analysis':   { en: 'Try: "run a t-test of TI by gender" — handled by the sandbox.',
                       vi: 'Thử: "chạy t-test TI theo giới tính" — chạy trong sandbox.' },
    'M2-reading':    { en: 'A focused reading-club thread on one seminal paper.',
                       vi: 'Thread đọc tập trung vào một bài seminal.' },
    'M1-archived':   { en: 'Archived — read-only history of the topic decision.',
                       vi: 'Lưu trữ — chỉ đọc lịch sử quyết định chủ đề.' },
  }[scenario];
  if (!hint) return null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '10px 14px', borderRadius: 12,
      background: 'var(--primary-50)', color: 'var(--primary-700)',
      fontSize: 12.5, fontWeight: 600,
      margin: '14px 0 6px',
      border: '1px dashed var(--primary-100)',
    }}>
      <span>💡</span><span>{hint[lang]}</span>
    </div>
  );
}

/* ===== Scenarios — produce {project, transcript} based on a key ===== */

function buildScenario(scenario) {
  const D = window.DT_DATA;
  const project = JSON.parse(JSON.stringify(D.PROJECT));

  switch (scenario) {
    case 'M2-gaps':
      project.focus = 'M2';
      return { project, transcript: D.TRANSCRIPT_M2.slice(0, 5) };

    case 'M2-output':
      project.focus = 'M2';
      return { project, transcript: D.TRANSCRIPT_M2 };

    case 'M3-method':
      project.focus = 'M3';
      return { project, transcript: D.TRANSCRIPT_M3_METHOD };

    case 'M2-reading':
      project.focus = 'M2';
      return { project, transcript: D.TRANSCRIPT_M2_READING };

    case 'M1-archived':
      project.focus = 'M1';
      return { project, transcript: D.TRANSCRIPT_M1_ARCHIVED };

    case 'M4-analysis':
      project.focus = 'M4';
      project.status.M2 = 'done';
      project.status.M3 = 'done';
      project.status.M4 = 'in_progress';
      return { project, transcript: D.TRANSCRIPT_M4.slice(0, 3) };

    case 'M4-mutate-M2':
      project.focus = 'M2';
      project.status.M2 = 'in_progress';
      project.status.M3 = 'needs_review';
      project.status.M4 = 'needs_review';
      project.status.M5 = 'needs_review';
      project.contextStore.research_gaps.push({
        id: 'G4',
        en: 'Impulsive livestream buying among Gen Z in remote-work / remote-study contexts is untested.',
        vi: 'Hành vi mua bốc đồng trên livestream với Gen Z bối cảnh làm việc/học từ xa chưa được kiểm định.',
        relevance: 'Medium',
        confirmed: false,
        papers: [],
      });
      return { project, transcript: D.TRANSCRIPT_M4 };

    default:
      project.focus = 'M2';
      return { project, transcript: D.TRANSCRIPT_M2.slice(0, 5) };
  }
}

/* ===== Tweaks Panel ===== */

function DoThesisTweaks({ t, setTweak }) {
  const threads = window.DT_DATA.THREADS.map(th => th.id);
  return (
    <TweaksPanel>
      <TweakSection label="Active thread" />
      <TweakSelect
        label="Thread"
        value={t.thread}
        options={threads}
        onChange={(v) => setTweak('thread', v)}
      />
      <TweakButton label="Open entry wizard" onClick={() => setTweak('showWizard', true)} />

      <TweakSection label="Language & UI" />
      <TweakRadio
        label="Language"
        value={t.lang}
        options={['en', 'vi']}
        onChange={(v) => setTweak('lang', v)}
      />
      <TweakToggle
        label="Show context_store rail"
        value={t.showContext}
        onChange={(v) => setTweak('showContext', v)}
      />

      <TweakSection label="Brand" />
      <TweakColor
        label="Primary"
        value={t.primary}
        options={['#2540FF', '#1B30CC', '#0E4F8A', '#1F4D3F']}
        onChange={(v) => setTweak('primary', v)}
      />
    </TweaksPanel>
  );
}

/* ===== Mount ===== */
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
