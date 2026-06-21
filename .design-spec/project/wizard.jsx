/* ===== Entry Wizard: declare → import → bootstrap ===== */

function EntryWizard({ lang, onClose, onComplete }) {
  const [step, setStep] = React.useState(1);
  const [have, setHave] = React.useState(new Set(['topic', 'model']));

  const items = window.DT_DATA.HAVE_ITEMS;

  const toggle = (id) => {
    const next = new Set(have);
    if (next.has(id)) next.delete(id); else next.add(id);
    setHave(next);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: 'rgba(11,16,32,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24, backdropFilter: 'blur(4px)',
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 920,
          background: 'white', borderRadius: 24,
          boxShadow: 'var(--shadow-pop)',
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          maxHeight: '90vh',
        }}>

        {/* Header */}
        <div style={{ padding: '20px 28px 16px', borderBottom: '1px solid var(--ink-200)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'var(--primary)',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: 'white', fontWeight: 800, fontSize: 18,
          }}>D</span>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>
              {lang === 'vi' ? 'Khởi tạo đề tài' : 'Bootstrap your thesis'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-500)' }}>
              {lang === 'vi'
                ? 'Một lần khởi tạo — sau đó là một cuộc chat'
                : 'One-time bootstrap — then it\'s one chat thread'}
            </div>
          </div>
          <div style={{ flex: 1 }}></div>
          <Stepper step={step} lang={lang} />
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>

        {step === 1 && <StepDeclare items={items} have={have} toggle={toggle} lang={lang} />}
        {step === 2 && <StepImport have={have} items={items} lang={lang} />}
        {step === 3 && <StepReconcile have={have} lang={lang} />}

        {/* Footer */}
        <div style={{
          padding: '16px 28px', borderTop: '1px solid var(--ink-200)',
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'var(--ink-50)',
        }}>
          <span style={{ fontSize: 12, color: 'var(--ink-500)' }}>
            {step === 1 && (lang === 'vi'
              ? `${have.size} mục đã chọn — phần còn lại bạn có thể thêm bất kỳ lúc nào`
              : `${have.size} declared — you can add the rest anytime`)}
            {step === 2 && (lang === 'vi' ? 'Đang phân tích · gọi pipeline GROBID / pyreadstat' : 'Parsing · running GROBID / pyreadstat')}
            {step === 3 && (lang === 'vi' ? 'Đối chiếu phụ thuộc · áp cùng quy tắc lan truyền' : 'Reconciling deps · same propagation rule as edits')}
          </span>
          <span style={{ flex: 1 }}></span>
          {step > 1 && (
            <button className="btn btn-ghost" onClick={() => setStep(step - 1)}>
              ← {lang === 'vi' ? 'Quay lại' : 'Back'}
            </button>
          )}
          {step < 3 ? (
            <button className="btn btn-primary" onClick={() => setStep(step + 1)}>
              {lang === 'vi' ? 'Tiếp tục' : 'Continue'} →
            </button>
          ) : (
            <button className="btn btn-primary" onClick={onComplete}>
              {lang === 'vi' ? 'Vào trò chuyện · ' : 'Drop into chat · '} M2 ⚠
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Stepper({ step, lang }) {
  const labels = lang === 'vi'
    ? ['Khai báo', 'Nhập', 'Đối chiếu']
    : ['Declare', 'Import', 'Reconcile'];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {labels.map((l, i) => {
        const n = i + 1;
        const active = step === n, done = step > n;
        return (
          <React.Fragment key={l}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                width: 22, height: 22, borderRadius: 999,
                background: done ? 'var(--ok-600)' : active ? 'var(--primary)' : 'var(--ink-200)',
                color: 'white', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 800,
              }}>{done ? '✓' : n}</span>
              <span style={{ fontSize: 12.5, fontWeight: active || done ? 700 : 500, color: active || done ? 'var(--ink-900)' : 'var(--ink-500)' }}>{l}</span>
            </div>
            {i < 2 && <span style={{ width: 18, height: 1, background: 'var(--ink-200)' }}></span>}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function StepDeclare({ items, have, toggle, lang }) {
  return (
    <div style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-.01em' }}>
        {lang === 'vi' ? 'Bạn đã có gì rồi?' : 'What do you already have?'}
      </div>
      <div style={{ fontSize: 13.5, color: 'var(--ink-600)', marginTop: 4, marginBottom: 18 }}>
        {lang === 'vi'
          ? 'Đánh dấu mọi thứ bạn mang theo. Mình sẽ dùng đúng pipeline mà từng module dùng — không có hệ thống nhập riêng.'
          : 'Tick everything you\'re bringing. We\'ll use the same parsers each module uses — not a separate import stack.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
        {items.map(it => {
          const on = have.has(it.id);
          return (
            <button key={it.id} onClick={() => toggle(it.id)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, textAlign: 'left',
                padding: '14px 14px', borderRadius: 14,
                background: on ? 'var(--primary-50)' : 'white',
                border: on ? '2px solid var(--primary)' : '1px solid var(--ink-200)',
                transition: 'all .12s',
              }}>
              <span style={{
                width: 34, height: 34, borderRadius: 10,
                background: on ? 'white' : 'var(--ink-50)',
                color: on ? 'var(--primary)' : 'var(--ink-600)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 16, fontWeight: 700,
                border: on ? '1px solid var(--primary-100)' : '1px solid var(--ink-200)',
              }}>{it.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--ink-900)' }}>{it[lang]}</div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-500)', marginTop: 2 }}>
                  → {it.mod} · {window.DT_DATA.MODULE_BLURB[it.mod][lang]}
                </div>
              </div>
              <span style={{
                width: 18, height: 18, borderRadius: 5,
                background: on ? 'var(--primary)' : 'white',
                border: on ? 'none' : '1.5px solid var(--ink-300)',
                color: 'white', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 800, flexShrink: 0,
              }}>{on && '✓'}</span>
            </button>
          );
        })}
      </div>
      <div style={{
        marginTop: 16, padding: '12px 14px', borderRadius: 12,
        background: 'var(--ink-50)', border: '1px dashed var(--ink-300)',
        display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5, color: 'var(--ink-600)',
      }}>
        <span style={{ fontSize: 16 }}>ℹ</span>
        <span>{lang === 'vi'
          ? 'Bạn cũng có thể bắt đầu trống và để mình dẫn dắt. Khoá module chỉ là gợi ý — không phải tường chắn.'
          : 'You can also start empty and let me drive. Module locks are recommendations, never walls.'}</span>
      </div>
    </div>
  );
}

function StepImport({ have, items, lang }) {
  const selected = items.filter(i => have.has(i.id));
  return (
    <div style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-.01em' }}>
        {lang === 'vi' ? 'Nhập từng mục' : 'Import each item'}
      </div>
      <div style={{ fontSize: 13.5, color: 'var(--ink-600)', marginTop: 4, marginBottom: 18 }}>
        {lang === 'vi'
          ? 'Cùng pipeline mà module sẽ dùng về sau — GROBID cho PDF, pyreadstat cho .sav, v.v.'
          : 'Same pipeline each module will use later — GROBID for PDFs, pyreadstat for .sav, etc.'}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {selected.map(it => (
          <ImportRow key={it.id} item={it} lang={lang} />
        ))}
      </div>
    </div>
  );
}

function ImportRow({ item, lang }) {
  // Different per kind, but visually similar
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: 14, borderRadius: 14,
      border: '1px solid var(--ink-200)', background: 'white',
    }}>
      <span style={{
        width: 38, height: 38, borderRadius: 10,
        background: 'var(--ink-50)', color: 'var(--ink-700)',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16, fontWeight: 700,
      }}>{item.icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>{item[lang]}</div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
          {item.id === 'topic' && (lang === 'vi' ? 'Gõ trực tiếp · 1 câu là đủ' : 'Type · one sentence is enough')}
          {item.id === 'references' && (lang === 'vi' ? 'PDF · DOI · danh sách' : 'PDF · DOI · plain list')}
          {item.id === 'model' && (lang === 'vi' ? 'Mô tả · vẽ trên canvas · tải file' : 'Describe · draw on canvas · upload')}
          {item.id === 'data' && (lang === 'vi' ? '.sav · .csv · SmartPLS · phỏng vấn' : '.sav · .csv · SmartPLS · transcripts')}
          {item.id === 'draft' && (lang === 'vi' ? 'Word · sẽ phân chia chương' : 'Word · sections auto-detected')}
          {item.id === 'gaps' && (lang === 'vi' ? 'Dán · suy ra từ references' : 'Paste · derive from refs')}
          {item.id === 'instrument' && (lang === 'vi' ? 'Word · PDF' : 'Word · PDF')}
        </div>
      </div>
      {item.id === 'topic'
        ? <input
            placeholder={lang === 'vi' ? 'Gen Z mua hàng livestream TikTok…' : 'Gen Z TikTok livestream buying…'}
            style={{
              minWidth: 320, padding: '8px 12px', borderRadius: 10,
              border: '1px solid var(--ink-300)', fontSize: 13, fontFamily: 'var(--font)',
              outline: 'none',
            }}
            defaultValue={lang === 'vi' ? 'Hành vi mua livestream TikTok của Gen Z tại Hà Nội' : 'Gen Z livestream buying on TikTok in Hà Nội'}
            className="focus-ring"
          />
        : <button className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 13 }}>
            {lang === 'vi' ? 'Tải lên' : 'Upload'} ↑
          </button>}
    </div>
  );
}

function StepReconcile({ have, lang }) {
  // Simulated outcome: topic + model declared → M2 needs_review (the worked example from PRD)
  return (
    <div style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-.01em' }}>
        {lang === 'vi' ? 'Đối chiếu phụ thuộc' : 'Reconciling dependencies'}
      </div>
      <div style={{ fontSize: 13.5, color: 'var(--ink-600)', marginTop: 4, marginBottom: 18 }}>
        {lang === 'vi'
          ? 'Cùng quy tắc lan truyền dùng cho mutate trong chat — áp dụng ngay tại bước nhập.'
          : 'Same propagation rule as a mid-chat mutate — applied at intake.'}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 18 }}>
        {[
          { id: 'M1', status: 'done',         lab: { en: 'Topic',     vi: 'Chủ đề' } },
          { id: 'M2', status: 'needs_review', lab: { en: 'Literature', vi: 'Tài liệu' } },
          { id: 'M3', status: 'done',         lab: { en: 'Model',     vi: 'Mô hình' } },
          { id: 'M4', status: 'locked',       lab: { en: 'Analysis',  vi: 'Phân tích' } },
          { id: 'M5', status: 'locked',       lab: { en: 'Writing',   vi: 'Viết' } },
        ].map(m => (
          <div key={m.id} style={{
            padding: 12, borderRadius: 12, textAlign: 'center',
            background: m.status === 'done' ? 'var(--ok-50)'
                       : m.status === 'needs_review' ? 'var(--review-50)' : 'var(--ink-50)',
            border: '1px solid ' + (m.status === 'done' ? '#A5E6C2'
                       : m.status === 'needs_review' ? '#FFD8A0' : 'var(--ink-200)'),
          }}>
            <div style={{ fontWeight: 800, fontSize: 13,
                          color: m.status === 'done' ? 'var(--ok-text)' :
                                 m.status === 'needs_review' ? 'var(--review-text)' : 'var(--ink-500)' }}>
              {m.id}
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-800)', marginTop: 4 }}>
              {m.lab[lang]}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--ink-500)', marginTop: 4 }}>
              {m.status === 'done' && (lang === 'vi' ? '✓ Đã có' : '✓ Imported')}
              {m.status === 'needs_review' && (lang === 'vi' ? '⚠ Lỗ hổng' : '⚠ Gap')}
              {m.status === 'locked' && (lang === 'vi' ? '○ Khoá mềm' : '○ Soft lock')}
            </div>
          </div>
        ))}
      </div>

      <div style={{
        padding: 16, borderRadius: 14,
        background: 'var(--review-50)', border: '1px solid #FFD8A0',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 16 }}>⚠</span>
          <span style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--review-text)' }}>
            {lang === 'vi' ? 'Lỗ hổng phụ thuộc: M2' : 'Dependency hole: M2'}
          </span>
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--ink-800)', lineHeight: 1.5, fontFamily: 'var(--font-serif)' }}>
          {lang === 'vi'
            ? '"Bạn đã có chủ đề và mô hình rồi, nhưng chưa có tổng quan tài liệu để neo H1/H2 — mình dựng tổng quan ngay để giả thuyết được nền, hay bạn muốn sang phân tích dữ liệu trước?"'
            : '"You\'ve got a topic and a model, but no literature review backing H1/H2 yet — build that now so they\'re grounded, or skip ahead to data analysis?"'}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--review-text)', marginTop: 8, fontWeight: 600 }}>
          {lang === 'vi'
            ? 'Tiêu điểm vào: M2 · mở mềm, không bắt buộc'
            : 'Entry focus: M2 · soft prompt, not enforced'}
        </div>
      </div>
    </div>
  );
}

window.EntryWizard = EntryWizard;
