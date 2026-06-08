"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API = "";

type Skill = {
  name: string;
  version: string;
  status: string;
  owners: string[];
  tags: string[];
  weighted_delta: number | null;
  verdict: string | null;
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/skills`)
      .then((r) => r.json())
      .then((d) => { setSkills(d.skills || []); setLoading(false); });
  }, []);

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-xl font-bold text-white mb-6">Skill Library</h1>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {skills.map((s) => (
            <Link
              key={s.name}
              href={`/skills/${s.name}`}
              className="border border-gray-800 rounded-lg p-4 hover:border-indigo-700 hover:bg-gray-900 transition-all group"
            >
              <div className="flex items-start justify-between mb-2">
                <span className="text-indigo-300 font-medium group-hover:text-white transition-colors">
                  {s.name}
                </span>
                <span className="text-xs text-gray-600 border border-gray-800 px-1.5 py-0.5 rounded">
                  v{s.version}
                </span>
              </div>
              <div className="flex flex-wrap gap-1 mb-3">
                {s.tags.map((t) => (
                  <span key={t} className="text-xs text-gray-600 bg-gray-900 px-1.5 py-0.5 rounded">
                    {t}
                  </span>
                ))}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className={`px-2 py-0.5 rounded ${s.status === "active" ? "bg-emerald-900 text-emerald-400" : "bg-gray-800 text-gray-500"}`}>
                  {s.status}
                </span>
                {s.weighted_delta !== null ? (
                  <span className={s.weighted_delta >= 0 ? "text-emerald-400" : "text-red-400"}>
                    Δ {s.weighted_delta >= 0 ? "+" : ""}{s.weighted_delta.toFixed(3)}
                  </span>
                ) : (
                  <span className="text-gray-700">no eval</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
