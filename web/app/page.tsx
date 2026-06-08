"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API = "";

type SkillRow = {
  skill: string;
  weighted_delta: number;
  regression_rate: number;
  n_tasks: number;
  status: string;
  owners: string[];
};

function VerdictBadge({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-gray-600 text-xs">no data</span>;
  if (delta >= 0.05) return <span className="bg-emerald-900 text-emerald-300 text-xs px-2 py-0.5 rounded">PASS</span>;
  if (delta >= 0) return <span className="bg-yellow-900 text-yellow-300 text-xs px-2 py-0.5 rounded">WARN</span>;
  return <span className="bg-red-900 text-red-300 text-xs px-2 py-0.5 rounded">BLOCK</span>;
}

function DeltaBar({ value }: { value: number }) {
  const pct = Math.min(Math.max((value + 0.5) / 1.0, 0), 1) * 100;
  const color = value >= 0.05 ? "bg-emerald-500" : value >= 0 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-gray-800 rounded overflow-hidden">
        <div className={`h-full ${color} rounded`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs tabular-nums ${value >= 0 ? "text-emerald-400" : "text-red-400"}`}>
        {value >= 0 ? "+" : ""}{value.toFixed(3)}
      </span>
    </div>
  );
}

export default function LeaderboardPage() {
  const [rows, setRows] = useState<SkillRow[]>([]);
  const [skills, setSkills] = useState<{ name: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/leaderboard`).then((r) => r.json()),
      fetch(`${API}/api/skills`).then((r) => r.json()),
    ]).then(([lb, sk]) => {
      setRows(lb.leaderboard || []);
      setSkills(sk.skills || []);
      setLoading(false);
    });
  }, []);

  const evalledNames = new Set(rows.map((r) => r.skill));
  const unevaluated = skills.filter((s) => !evalledNames.has(s.name));

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Leaderboard</h1>
        <Link href="/eval" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded transition-colors">
          Run Eval →
        </Link>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-gray-500 text-sm">No eval results yet. <Link href="/eval" className="text-indigo-400 underline">Run an eval</Link> to populate.</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-gray-500 text-xs border-b border-gray-800">
              <th className="text-left py-2 pr-4">Skill</th>
              <th className="text-left py-2 pr-4">Weighted Δ</th>
              <th className="text-left py-2 pr-4">Regression rate</th>
              <th className="text-left py-2 pr-4">Tasks</th>
              <th className="text-left py-2">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.skill} className="border-b border-gray-900 hover:bg-gray-900 transition-colors">
                <td className="py-2.5 pr-4">
                  <Link href={`/skills/${r.skill}`} className="text-indigo-300 hover:text-white">
                    {r.skill}
                  </Link>
                </td>
                <td className="py-2.5 pr-4"><DeltaBar value={r.weighted_delta} /></td>
                <td className="py-2.5 pr-4 text-gray-400">{(r.regression_rate * 100).toFixed(0)}%</td>
                <td className="py-2.5 pr-4 text-gray-500">{r.n_tasks}</td>
                <td className="py-2.5"><VerdictBadge delta={r.weighted_delta} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {unevaluated.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xs text-gray-600 uppercase tracking-wider mb-3">Not yet evaluated</h2>
          <div className="flex flex-wrap gap-2">
            {unevaluated.map((s) => (
              <Link
                key={s.name}
                href={`/skills/${s.name}`}
                className="text-xs text-gray-500 border border-gray-800 px-2 py-1 rounded hover:border-indigo-700 hover:text-indigo-300 transition-colors"
              >
                {s.name}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
