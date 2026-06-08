"use client";

import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

const API = "";

function EvalRunner() {
  const params = useSearchParams();
  const [skills, setSkills] = useState<string[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [selectedSkill, setSelectedSkill] = useState(params.get("skill") || "");
  const [selectedModel, setSelectedModel] = useState("google/gemini-2.5-flash");
  const [trials, setTrials] = useState(3);
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [verdict, setVerdict] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/skills`).then((r) => r.json()),
      fetch(`${API}/api/models`).then((r) => r.json()),
    ]).then(([sd, md]) => {
      setSkills((sd.skills || []).map((s: { name: string }) => s.name));
      setModels(md.models || []);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const runEval = async () => {
    if (!selectedSkill) return;
    setRunning(true);
    setLines([]);
    setVerdict(null);

    const res = await fetch(`${API}/api/eval/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_name: selectedSkill, trials, model: selectedModel }),
    });

    const reader = res.body?.getReader();
    const decoder = new TextDecoder();

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          const text = line.slice(6);
          if (text.startsWith("__DONE__")) {
            setVerdict(text.replace("__DONE__ ", "").trim());
          } else if (text.trim()) {
            setLines((prev) => [...prev, text]);
          }
        }
      }
    }
    setRunning(false);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-bold text-white mb-6">Eval Runner</h1>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Skill</label>
            <select
              value={selectedSkill}
              onChange={(e) => setSelectedSkill(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 focus:outline-none focus:border-indigo-600"
            >
              <option value="">— select —</option>
              {skills.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 focus:outline-none focus:border-indigo-600"
            >
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Trials</label>
            <input
              type="number"
              min={1}
              max={10}
              value={trials}
              onChange={(e) => setTrials(parseInt(e.target.value) || 1)}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 w-20 focus:outline-none focus:border-indigo-600"
            />
          </div>
          <button
            onClick={runEval}
            disabled={running || !selectedSkill}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm px-4 py-1.5 rounded transition-colors"
          >
            {running ? "Running…" : "Run Eval"}
          </button>
        </div>
      </div>

      {(lines.length > 0 || verdict) && (
        <div>
          <div className="bg-black border border-gray-800 rounded-lg p-4 font-mono text-xs text-gray-300 h-96 overflow-y-auto">
            {lines.map((l, i) => (
              <div key={i} className={`leading-5 ${l.includes("BLOCK") ? "text-red-400" : l.includes("PASS") ? "text-emerald-400" : l.includes("WARN") ? "text-yellow-400" : ""}`}>
                {l}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {verdict && (
            <div className={`mt-4 text-center text-sm font-bold py-3 rounded border ${
              verdict === "PASS"
                ? "border-emerald-700 text-emerald-400 bg-emerald-950"
                : verdict === "BLOCK"
                ? "border-red-700 text-red-400 bg-red-950"
                : "border-yellow-700 text-yellow-400 bg-yellow-950"
            }`}>
              GATE VERDICT: {verdict}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function EvalPage() {
  return (
    <Suspense fallback={<p className="text-gray-500 text-sm">Loading…</p>}>
      <EvalRunner />
    </Suspense>
  );
}
