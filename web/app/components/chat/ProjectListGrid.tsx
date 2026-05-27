"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, ChevronRight } from "lucide-react";

import { NewProjectModal } from "./NewProjectModal";


type Project = {
  id: string;
  name: string;
  field: string | null;
  language: string;
  status: string;
  current_module: string;
  context_store: { m1_topic?: { confirmed_at?: string | null } | null };
  created_at: string;
  updated_at: string;
};


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export function ProjectListGrid() {
  const { data: projects, mutate } = useSWR<Project[]>("/projects", fetcher, { dedupingInterval: 0 });
  const [modalOpen, setModalOpen] = useState(false);
  const router = useRouter();

  // After creation: revalidate the project list and route the user directly
  // into the new project. That's the typical next action and saves a click.
  const handleCreated = (project: { id: string; name: string }) => {
    void mutate();
    setModalOpen(false);
    router.push(`/chat/projects/${project.id}`);
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Your projects</h1>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1 bg-purple-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-purple-700"
        >
          <Plus className="w-4 h-4" /> New project
        </button>
      </div>

      <NewProjectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />

      {/* Wizard banner removed 2026-05-27 — chat UI is the primary surface now (full M1–M5 module flow is shipped). */}

      {projects && projects.length === 0 && (
        <div className="text-center py-12 text-gray-500">No projects yet. Click the New project button to get started.</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects?.map(p => (
          <Link
            key={p.id}
            href={`/chat/projects/${p.id}`}
            className="block bg-white border border-gray-200 rounded-lg p-4 hover:border-purple-400 hover:shadow-sm transition-all"
          >
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center justify-between">
              {p.name}
              <ChevronRight className="w-4 h-4 text-gray-400" />
            </h3>
            <p className="text-xs text-gray-500">
              {p.field ?? "no field"} · {p.language} · {p.current_module}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
