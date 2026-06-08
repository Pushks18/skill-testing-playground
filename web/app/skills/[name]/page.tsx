"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import Link from "next/link";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const API = "";

type Commit = { sha: string; message: string; date: string; author: string };
type EvalTask = { task_id: string; delta: number; task_weight: number };
type SkillDetail = {
  name: string;
  content: string;
  description: string;
  version: string;
  status: string;
  owners: string[];
  tags: string[];
  last_eval: {
    weighted_delta: number;
    regression_rate: number;
    n_tasks: number;
    tasks: EvalTask[];
  } | null;
  history: Commit[];
};

function TaskDeltaRow({ t }: { t: EvalTask }) {
  return (
    <div className="flex items-center justify-between text-xs py-1 border-b border-gray-900">
      <span className="text-gray-400">{t.task_id}</span>
      <div className="flex items-center gap-3">
        <span className="text-gray-600">w={t.task_weight}</span>
        <span className={`tabular-nums ${t.delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
          {t.delta >= 0 ? "+" : ""}{t.delta.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

export default function SkillDetailPage() {
  const { name } = useParams<{ name: string }>();
  const [data, setData] = useState<SkillDetail | null>(null);
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/skills/${name}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setContent(d.content); });
  }, [name]);

  const save = async () => {
    setSaving(true);
    await fetch(`${API}/api/skills/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (!data) return <p className="text-gray-500 text-sm">Loading…</p>;

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-2 text-sm text-gray-600 mb-4">
        <Link href="/skills" className="hover:text-gray-300">Skills</Link>
        <span>/</span>
        <span className="text-white">{name}</span>
      </div>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">{name}</h1>
          <p className="text-sm text-gray-500 mt-1 max-w-xl">{data.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-1 rounded border ${data.status === "active" ? "border-emerald-700 text-emerald-400" : "border-gray-700 text-gray-500"}`}>
            {data.status}
          </span>
          <Link
            href={`/eval?skill=${name}`}
            className="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded transition-colors"
          >
            Run Eval
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Editor */}
        <div className="col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 uppercase tracking-wider">SKILL.md</span>
            <button
              onClick={save}
              disabled={saving}
              className="text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1.5 rounded transition-colors disabled:opacity-50"
            >
              {saved ? "Saved ✓" : saving ? "Saving…" : "Save"}
            </button>
          </div>
          <div className="border border-gray-800 rounded-lg overflow-hidden h-[520px]">
            <MonacoEditor
              language="markdown"
              theme="vs-dark"
              value={content}
              onChange={(v) => setContent(v ?? "")}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: "off",
                wordWrap: "on",
                scrollBeyondLastLine: false,
                padding: { top: 12 },
              }}
            />
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Last eval */}
          {data.last_eval ? (
            <div>
              <h3 className="text-xs text-gray-600 uppercase tracking-wider mb-3">Last Eval</h3>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="bg-gray-900 rounded p-2">
                  <div className={`text-lg font-bold ${data.last_eval.weighted_delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {data.last_eval.weighted_delta >= 0 ? "+" : ""}{data.last_eval.weighted_delta.toFixed(3)}
                  </div>
                  <div className="text-xs text-gray-600">weighted Δ</div>
                </div>
                <div className="bg-gray-900 rounded p-2">
                  <div className="text-lg font-bold text-gray-300">
                    {(data.last_eval.regression_rate * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs text-gray-600">regression</div>
                </div>
              </div>
              <div className="max-h-48 overflow-y-auto">
                {data.last_eval.tasks.map((t) => <TaskDeltaRow key={t.task_id} t={t} />)}
              </div>
            </div>
          ) : (
            <div>
              <h3 className="text-xs text-gray-600 uppercase tracking-wider mb-2">Last Eval</h3>
              <p className="text-xs text-gray-700">No eval data yet.</p>
            </div>
          )}

          {/* Git history */}
          {(data.history ?? []).length > 0 && (
            <div>
              <h3 className="text-xs text-gray-600 uppercase tracking-wider mb-3">Git History</h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.history.map((c) => (
                  <div key={c.sha} className="text-xs">
                    <span className="text-gray-700 font-mono">{c.sha}</span>
                    <span className="text-gray-500 mx-1">·</span>
                    <span className="text-gray-400">{c.message}</span>
                    <div className="text-gray-700">{c.date} · {c.author}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tags + owners */}
          <div>
            <h3 className="text-xs text-gray-600 uppercase tracking-wider mb-2">Metadata</h3>
            <div className="text-xs text-gray-500 space-y-1">
              <div>version: {data.version}</div>
              <div>owners: {data.owners.join(", ") || "—"}</div>
              <div className="flex flex-wrap gap-1 mt-1">
                {data.tags.map((t) => (
                  <span key={t} className="bg-gray-900 px-1.5 py-0.5 rounded text-gray-600">{t}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
