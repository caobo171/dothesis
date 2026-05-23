"use client";

import { Sidebar } from "../components/shared";
import { Wizard } from "../components/wizard";

export default function WizardPage() {
  return (
    <div className="app">
      <Sidebar />
      <Wizard />
    </div>
  );
}
