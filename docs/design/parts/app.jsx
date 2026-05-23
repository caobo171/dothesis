// App entry — router + tweaks + paper context.

const App = () => {
  // Tweakable defaults
  const [t, setTweak] = useTweaks(/*EDITMODE-BEGIN*/{
    "citationStyle": "APA",
    "accent": "#1c2eff",
    "density": "comfortable"
  }/*EDITMODE-END*/);

  // Apply accent color live
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--blue-600", t.accent);
    const soft50 = {
      "#1c2eff": "#f1f3ff",
      "#6e1d2c": "#fbeef0",
      "#0a8a55": "#e8f7ef",
      "#161827": "#eef0f6",
    }[t.accent] || "#f1f3ff";
    const soft100 = {
      "#1c2eff": "#e7eaff",
      "#6e1d2c": "#f3d8de",
      "#0a8a55": "#cfeede",
      "#161827": "#e2e4ee",
    }[t.accent] || "#e7eaff";
    root.style.setProperty("--blue-50", soft50);
    root.style.setProperty("--blue-100", soft100);
  }, [t.accent]);

  // Router state
  const [route, setRoute] = useState("dashboard");
  // For paper context
  const [paperId, setPaperId] = useState("alg-gov-2026");
  const [paperTab, setPaperTab] = useState("run");

  const go = (r, opts) => {
    if (r === "paper") {
      if (opts?.paperId) setPaperId(opts.paperId);
      if (opts?.tab) setPaperTab(opts.tab);
      else setPaperTab("run");
    }
    setRoute(r);
  };

  const { Sidebar } = window.SHARED;
  const { RECENT_DRAFTS } = window.DOTHESIS;
  const paper = RECENT_DRAFTS.find((d) => d.id === paperId) || RECENT_DRAFTS[0];

  let body;
  if (route === "dashboard") body = <Dashboard go={go} />;
  else if (route === "wizard") body = <Wizard go={go} />;
  else if (route === "billing" || route === "affiliate") body = <Billing go={go} />;
  else if (route === "paper") {
    let tabBody;
    if (paperTab === "run") tabBody = <AgentRun go={go} />;
    else if (paperTab === "editor") tabBody = <DraftEditor go={go} citationStyle={t.citationStyle} />;
    else if (paperTab === "citations") tabBody = <Citations go={go} citationStyle={t.citationStyle} />;
    else if (paperTab === "export") tabBody = <Export go={go} citationStyle={t.citationStyle} />;
    body = (
      <PaperShell go={go} paper={paper} tab={paperTab} setTab={setPaperTab}>
        {tabBody}
      </PaperShell>
    );
  } else body = <Dashboard go={go} />;

  return (
    <div className="app" data-screen-label={`DoThesis · ${route}${route === "paper" ? " · " + paperTab : ""}`}>
      <Sidebar route={route} setRoute={(r) => go(r)} />
      {body}
      <TweaksPanel title="DoThesis">
        <TweakSection label="Citation style" />
        <TweakRadio
          label="Style"
          value={t.citationStyle}
          options={["APA", "MLA", "Chicago", "IEEE"]}
          onChange={(v) => setTweak("citationStyle", v)}
        />
        <TweakSection label="Theme" />
        <TweakColor
          label="Accent"
          value={t.accent}
          options={["#1c2eff", "#6e1d2c", "#0a8a55", "#161827"]}
          onChange={(v) => setTweak("accent", v)}
        />
        <TweakRadio
          label="Density"
          value={t.density}
          options={["comfortable", "compact"]}
          onChange={(v) => setTweak("density", v)}
        />
      </TweaksPanel>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
