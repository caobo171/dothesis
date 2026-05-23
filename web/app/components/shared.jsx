"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";

export const BrandMark = ({ size = 38 }) => (
  <div className="brand-mark" style={{ width: size, height: size }}>
    <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none">
      <path
        d="M19 4c-7 0-13 6-13 13v3h3c7 0 13-6 13-13V4Z"
        fill="white"
        opacity="0.95"
      />
      <path d="M16 8 5 19" stroke="#1c2eff" strokeWidth="2" strokeLinecap="round" />
      <path d="M14 14H8" stroke="#1c2eff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  </div>
);

export const Brand = () => (
  <div className="brand">
    <BrandMark />
    <div className="brand-text">
      <div className="brand-name">Do<span className="accent">Thesis</span></div>
      <div className="brand-tag">Draft with conviction</div>
    </div>
  </div>
);

const NAV = [
  { href: "/", label: "Dashboard", icon: "home" },
  { href: "/wizard", label: "New thesis", icon: "plus", badge: "AI" },
];

export const Sidebar = () => {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <Brand />
      <nav className="nav">
        <div className="nav-section">Workspace</div>
        {NAV.map((n) => {
          const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={`nav-item ${active ? "active" : ""}`}
            >
              <Icon name={n.icon} className="nav-icon" />
              <span>{n.label}</span>
              {n.badge && <span className="nav-badge">{n.badge}</span>}
            </Link>
          );
        })}
      </nav>
      <HelpCard />
    </aside>
  );
};

const HelpCard = () => (
  <div className="helpcard">
    <div className="q">?</div>
    <h4>Need a hand?</h4>
    <p>Office hours, prompt templates, exemplar theses — all in one place.</p>
    <button className="help-btn primary">Open Help Center</button>
    <button className="help-btn">Contact a Writing Coach</button>
  </div>
);

export const Topbar = ({ crumbs = [], rightExtra }) => (
  <div className="topbar">
    <div className="topbar-left">
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          <span className={i === crumbs.length - 1 ? "crumb-current" : ""}>{c}</span>
          {i < crumbs.length - 1 && <Icon name="chevron-right" size={14} stroke={2} />}
        </React.Fragment>
      ))}
    </div>
    <div className="topbar-right">
      {rightExtra}
      <button className="iconbtn" aria-label="Notifications">
        <Icon name="bell" />
        <span className="dot" />
      </button>
      <div className="user-chip">
        <div className="user-avatar">JN</div>
        <div className="user-meta">
          <div className="user-name">jeendeet</div>
          <div className="user-email">jeendeet@gmail.com</div>
        </div>
        <button className="iconbtn" style={{ width: 32, height: 32, marginLeft: 4 }} aria-label="Sign out">
          <Icon name="logout" size={14} />
        </button>
      </div>
    </div>
  </div>
);

export const Badge = ({ status, children }) => {
  const map = {
    running: { cls: "run", label: "Running" },
    pause: { cls: "pause", label: "Paused" },
    ok: { cls: "ok", label: "Verified" },
    stop: { cls: "stop", label: "Stopped" },
    queue: { cls: "idle", label: "Queued" },
    done: { cls: "ok", label: "Done" },
  };
  const def = map[status] || { cls: "idle", label: status };
  return (
    <span className={`badge ${def.cls}`}>
      {status === "running" && <span className="pulse" />}
      {children || def.label}
    </span>
  );
};

export const Card = ({ title, subtitle, action, children, padded = true, className = "" }) => (
  <div className={`card ${className}`}>
    {(title || action) && (
      <div className="card-header">
        <div>
          {title && <div className="section-title">{title}</div>}
          {subtitle && <div style={{ fontSize: 13, color: "var(--ink-500)", marginTop: 4 }}>{subtitle}</div>}
        </div>
        {action}
      </div>
    )}
    <div className={padded ? "card-body" : ""}>{children}</div>
  </div>
);

export const ProgressBar = ({ value, color = "var(--blue-600)", track = "var(--ink-100)", height = 8 }) => (
  <div style={{ width: "100%", background: track, borderRadius: 999, height, overflow: "hidden" }}>
    <div
      style={{
        width: `${Math.max(0, Math.min(1, value)) * 100}%`,
        height: "100%",
        background: color,
        borderRadius: 999,
        transition: "width 0.5s ease",
      }}
    />
  </div>
);

export const KPI = ({ label, value, sub, accent }) => (
  <div style={{
    padding: "18px 20px",
    border: "1px solid var(--ink-100)",
    borderRadius: 14,
    background: "var(--paper)",
    display: "flex", flexDirection: "column", gap: 6,
  }}>
    <div style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase",
                  color: "var(--ink-400)", fontWeight: 700 }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 800, color: accent || "var(--ink-900)",
                  letterSpacing: "-0.02em", lineHeight: 1.05 }}>{value}</div>
    {sub && <div style={{ fontSize: 12, color: "var(--ink-500)", fontWeight: 500 }}>{sub}</div>}
  </div>
);
