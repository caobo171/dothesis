/**
 * Design-system primitives used by the landing page, ported from the Claude
 * Design project's `_ds_bundle.js`.
 *
 * These are deliberately NOT the shadcn components in app/components/ui: those
 * are tuned for dense in-app surfaces (8px radius, form sizing) while the
 * marketing page needs the design system's pill CTAs, tone badges, module chips
 * and caveat rules. Styling comes from the `.ds-*` classes in ../landing.css,
 * so the markup here stays a thin, faithful mirror of the bundle.
 *
 * Server components by default — none of them hold state.
 */
import type { CSSProperties, ElementType, ReactNode } from "react";

type Tone = "run" | "pause" | "ok" | "stop" | "idle" | "dark";

const TONES: Record<string, Tone> = {
  run: "run",
  pause: "pause",
  ok: "ok",
  stop: "stop",
  idle: "idle",
  dark: "dark",
};

const cx = (...parts: Array<string | false | undefined>) =>
  parts.filter(Boolean).join(" ");

/**
 * Status pill inherited from the Survify badge set. `pulse` shows the
 * halo-pulse dot that means "the agent is working right now".
 */
export function Badge({
  tone = "idle",
  pulse = false,
  className = "",
  children,
}: {
  tone?: Tone;
  pulse?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const t = TONES[tone] ?? "idle";
  return (
    <span className={cx("ds-badge", `ds-badge--${t}`, className)}>
      {pulse && <span className="ds-badge__pulse" aria-hidden="true" />}
      {children}
    </span>
  );
}

const VARIANTS = [
  "default",
  "secondary",
  "outline",
  "ghost",
  "dark",
  "destructive",
  "link",
] as const;
type Variant = (typeof VARIANTS)[number];

const SIZES: Record<string, string> = {
  sm: "ds-btn--sm",
  default: "",
  lg: "ds-btn--lg",
  icon: "ds-btn--icon",
};

/**
 * The product's button. Two shapes ship: the shadcn 8px-radius rectangle
 * (forms, dialogs, toolbars) and the 999px pill (page-level CTAs). Hover always
 * DARKENS a filled button.
 */
export function Button({
  variant = "default",
  size = "default",
  pill = false,
  block = false,
  as: Tag = "button",
  href,
  icon,
  iconAfter,
  className = "",
  style,
  children,
}: {
  variant?: Variant;
  size?: keyof typeof SIZES;
  pill?: boolean;
  block?: boolean;
  as?: ElementType;
  href?: string;
  icon?: ReactNode;
  iconAfter?: ReactNode;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const v = VARIANTS.includes(variant) ? variant : "default";
  const cls = cx(
    "ds-btn",
    `ds-btn--${v}`,
    SIZES[size] ?? "",
    pill && "ds-btn--pill",
    block && "ds-btn--block",
    className,
  );
  return (
    <Tag className={cls} href={href} style={style}>
      {icon}
      {children}
      {iconAfter}
    </Tag>
  );
}

/**
 * Surface container. 12px radius + hairline border + near-invisible shadow by
 * default; `panel` bumps to the product's 18px card radius used by dashboard
 * cards, rails and list panels. `interactive` adds the 1px hover lift.
 */
export function Card({
  panel = false,
  interactive = false,
  className = "",
  style,
  children,
}: {
  panel?: boolean;
  interactive?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <div
      className={cx(
        "ds-card",
        panel && "ds-card--panel",
        interactive && "ds-card--hover",
        className,
      )}
      style={style}
    >
      {children}
    </div>
  );
}

export type ModuleStatus = "in_progress" | "done" | "locked";

const LABELS: Record<ModuleStatus, string> = {
  in_progress: "In progress",
  done: "Done",
  locked: "Locked",
};

/** Uppercase, wide-tracked state pill used in the chat header and theses table. */
export function StatusTag({
  status = "in_progress",
  icon,
  children,
  className = "",
}: {
  status?: ModuleStatus;
  icon?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <span className={cx("ds-status", `ds-status--${status}`, className)}>
      {icon}
      {children ?? LABELS[status] ?? status}
    </span>
  );
}

/**
 * An inline reference. A DOI link means an academic paper; anything else is a
 * web source — pass the matching icon so the reader can tell them apart.
 */
export function CitationChip({
  label,
  title,
  url,
  icon,
}: {
  label: string;
  title?: string;
  url?: string;
  icon?: ReactNode;
}) {
  const href = (url || "").replace(/^doi:\s*/i, "https://doi.org/");
  return (
    <span
      className="ds-cite-wrap"
      style={{
        position: "relative",
        display: "inline-flex",
        verticalAlign: "baseline",
      }}
    >
      <a
        className="ds-cite"
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        title={title || label}
      >
        {icon}
        {label}
      </a>
    </span>
  );
}

/**
 * The assistant's answer. No avatar, no border, no shadow, full measure — long
 * analytical answers should read as a document, not a chat log of boxed quotes.
 */
export function AssistantTurn({
  module,
  footer,
  className = "",
  children,
}: {
  module?: string;
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("ds-turn-assistant", className)} data-role="assistant">
      {module && (
        <div className="ds-turn-assistant__label">
          <span className="ds-module-chip ds-module-chip--quiet">{module}</span>
        </div>
      )}
      <div className="ds-prose" style={{ minWidth: 0 }}>
        {children}
      </div>
      {footer && <div className="ds-turn-assistant__foot">{footer}</div>}
    </div>
  );
}

/** The honesty rule under a tool: what it can, and cannot, tell you. */
export function Caveat({
  lead,
  className = "",
  children,
}: {
  lead?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <p className={cx("ds-caveat", className)}>
      {lead && <strong style={{ color: "var(--ink-700)" }}>{lead} </strong>}
      {children}
    </p>
  );
}
