"use client";

import { useEffect, useState } from "react";

const API = "";

type OptimizerRun = {
  run: string;
  target: string;
  improved: boolean;
  baseline_test_mixed: number | null;
  best_test_mixed: number | null;
  baseline_selection_score: number | null;
  best_selection_score: number | null;
  proposed_file: string | null;
  crashed: boolean;
  dir: string;
};

type RunDetail = {
  report: Record<string, unknown>;
  initial_artifact: string | null;
  best_skill: string | null;
  skill_versions: string[];
};

type ObsLinks = {
  langsmith_project: string;
  langsmith_project_url: string;
};

function pct(v: number | null): string {
  if (v === null) return "—";
  return (v * 100).toFixed(0) + "%";
}

function ImprovBadge({ run }: { run: OptimizerRun }) {
  if (run.crashed) {
    return (
      <span className="bg-red-900 text-red-300 text-xs px-2 py-0.5 rounded">
        crashed
      </span>
    );
  }
  if (!run.proposed_file && !run.improved) {
    return (
      <span className="bg-gray-800 text-gray-500 text-xs px-2 py-0.5 rounded">
        no proposal
      </span>
    );
  }
  if (run.improved) {
    return (
      <span className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded">
        IMPROVED
      </span>
    );
  }
  return (
    <span className="bg-gray-800 text-gray-500 text-xs px-2 py-0.5 rounded">
      no gain
    </span>
  );
}

function ScoreArrow({
  baseline,
  best,
}: {
  baseline: number | null;
  best: number | null;
}) {
  if (baseline === null && best === null) return <span className="text-gray-600">—</span>;
  const bStr = pct(baseline);
  const bestStr = pct(best);
  const improved =
    baseline !== null && best !== null && best > baseline;
  const color = improved ? "text-emerald-400" : "text-gray-400";
  return (
    <span className={`tabular-nums ${color}`}>
      {bStr} → {bestStr}
    </span>
  );
}

function RunDetailPanel({
  tag,
  onClose,
}: {
  tag: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    setDetail(null);
    fetch(`${API}/api/optimizer-runs/${tag}`)
      .then((r) => r.json())
      .then(setDetail);
  }, [tag]);

  return (
    <div className="mt-2 mb-4 border border-indigo-800 rounded-lg bg-gray-950 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-indigo-300 font-mono">{tag}</span>
        <button
          onClick={onClose}
          className="text-xs text-gray-600 hover:text-gray-300 transition-colors"
        >
          close ×
        </button>
      </div>

      {!detail ? (
        <p className="text-gray-600 text-xs">Loading…</p>
      ) : (
        <>
          {/* Before / After artifacts */}
          {(detail.initial_artifact || detail.best_skill) && (
            <div className="mb-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                    Before (initial_artifact)
                  </div>
                  <pre className="bg-black border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-auto max-h-64 whitespace-pre-wrap break-words">
                    {detail.initial_artifact ?? "(none)"}
                  </pre>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                    After (best_skill)
                  </div>
                  <pre className="bg-black border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-auto max-h-64 whitespace-pre-wrap break-words">
                    {detail.best_skill ?? "(same as initial — no accepted edits)"}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* Skill version list */}
          {detail.skill_versions.length > 0 && (
            <div className="mb-4">
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">
                Optimizer skill versions ({detail.skill_versions.length})
              </div>
              <div className="flex flex-wrap gap-1">
                {detail.skill_versions.map((v) => (
                  <span
                    key={v}
                    className="text-xs font-mono bg-gray-900 text-gray-500 px-1.5 py-0.5 rounded"
                  >
                    {v}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Raw report (collapsible) */}
          <div>
            <button
              onClick={() => setShowRaw((p) => !p)}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
            >
              {showRaw ? "▾ hide raw report" : "▸ show raw report JSON"}
            </button>
            {showRaw && (
              <pre className="mt-2 bg-black border border-gray-800 rounded p-3 text-xs text-gray-400 overflow-auto max-h-64 whitespace-pre-wrap">
                {JSON.stringify(detail.report, null, 2)}
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function ObservabilityPage() {
  const [runs, setRuns] = useState<OptimizerRun[]>([]);
  const [links, setLinks] = useState<ObsLinks | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/optimizer-runs`).then((r) => r.json()),
      fetch(`${API}/api/observability/links`).then((r) => r.json()),
    ]).then(([rd, ld]) => {
      setRuns(rd.runs || []);
      setLinks(ld);
      setLoading(false);
    });
  }, []);

  const langsmithUrl = links
    ? `${links.langsmith_project_url}/projects/${encodeURIComponent(links.langsmith_project)}`
    : "#";

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Observability</h1>
        {links && (
          <a
            href={langsmithUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded transition-colors"
          >
            Open traces in LangSmith →
          </a>
        )}
      </div>

      {/* LangSmith project badge */}
      {links && (
        <div className="mb-6 bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 flex items-center gap-3">
          <span className="text-xs text-gray-500 uppercase tracking-wider">LangSmith project</span>
          <span className="text-xs font-mono text-indigo-300">{links.langsmith_project}</span>
        </div>
      )}

      {/* Optimizer runs table */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300">Optimizer Runs</h2>
        <span className="text-xs text-gray-600">{runs.length} runs</span>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="text-gray-500 text-sm">
          No optimizer runs found in{" "}
          <code className="text-gray-400">eval/optimizer_output/</code>.
        </p>
      ) : (
        <div>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left py-2 pr-4">Run tag</th>
                <th className="text-left py-2 pr-4">Target</th>
                <th className="text-left py-2 pr-4">Selection (baseline→best)</th>
                <th className="text-left py-2 pr-4">Test (baseline→best)</th>
                <th className="text-left py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <>
                  <tr
                    key={run.run}
                    className="border-b border-gray-900 hover:bg-gray-900 transition-colors cursor-pointer"
                    onClick={() =>
                      setExpanded(expanded === run.run ? null : run.run)
                    }
                  >
                    <td className="py-2.5 pr-4">
                      <span className="text-indigo-300 hover:text-white text-xs font-mono">
                        {run.run}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-gray-400 text-xs">
                      {run.target || "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-xs">
                      <ScoreArrow
                        baseline={run.baseline_selection_score}
                        best={run.best_selection_score}
                      />
                    </td>
                    <td className="py-2.5 pr-4 text-xs">
                      <ScoreArrow
                        baseline={run.baseline_test_mixed}
                        best={run.best_test_mixed}
                      />
                    </td>
                    <td className="py-2.5">
                      <ImprovBadge run={run} />
                    </td>
                  </tr>
                  {expanded === run.run && (
                    <tr key={`${run.run}-detail`} className="border-b border-indigo-900">
                      <td colSpan={5} className="p-0">
                        <RunDetailPanel
                          tag={run.run}
                          onClose={() => setExpanded(null)}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>

          {/* How to read this */}
          <div className="mt-8 border border-gray-800 rounded-lg px-4 py-3 text-xs text-gray-600 space-y-1">
            <div className="text-gray-500 font-semibold mb-1">How to read this</div>
            <div>
              <span className="text-gray-400">Selection split</span> — the tasks
              the optimizer used to select edits (contains known failure cases).
              Improvement evidence comes from this split.
            </div>
            <div>
              <span className="text-gray-400">Test split</span> — held-out tasks
              the optimizer never saw. Guards against non-regression on unrelated
              tasks.
            </div>
            <div>
              <span className="text-emerald-600">IMPROVED</span> = selection
              score went up AND a proposed file was produced.{" "}
              <span className="text-gray-500">no proposal</span> = optimizer found
              nothing better.{" "}
              <span className="text-red-600">crashed</span> = run failed mid-way.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
