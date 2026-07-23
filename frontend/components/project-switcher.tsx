"use client";

import { useEffect, useState } from "react";
import { api, getCurrentProjectId, setCurrentProjectId } from "@/lib/api";
import type { Project } from "@/lib/types";

/**
 * Project switcher (multi-project #47). Lives at the top of the sidebar.
 * - Loads projects, shows the active one, lets you switch or create.
 * - On switch/create, persists to localStorage and reloads so every page
 *   re-fetches scoped to the new project.
 * - When no project exists, forces a create so the app is never headerless.
 */
export function ProjectSwitcher() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listProjects()
      .then((ps) => {
        setProjects(ps);
        const stored = getCurrentProjectId();
        const valid = ps.find((p) => p.id === stored);
        if (valid) {
          setCurrentId(valid.id);
        } else if (ps.length > 0) {
          setCurrentProjectId(ps[0].id);
          setCurrentId(ps[0].id);
        } else {
          // No projects at all → force create.
          setCreating(true);
          setOpen(true);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function switchTo(id: string) {
    setCurrentProjectId(id);
    window.location.reload();
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const p = await api.createProject(newName.trim(), newCategory.trim());
      setCurrentProjectId(p.id);
      window.location.reload();
    } finally {
      setBusy(false);
    }
  }

  const current = projects.find((p) => p.id === currentId);

  if (loading) {
    return <div className="text-[#8b93a1] text-xs px-2 py-2">加载项目…</div>;
  }

  return (
    <div className="relative mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-md bg-[#1c202a] hover:bg-[#232833] transition-colors text-left"
      >
        <div className="min-w-0">
          <div className="text-[9px] text-[#5f6774] uppercase tracking-wider">当前项目</div>
          <div className="text-[13px] text-white truncate">{current?.name ?? "选择项目"}</div>
        </div>
        <span className="text-[#8b93a1] text-xs flex-none">▾</span>
      </button>

      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-[#12151c] border border-[#232833] rounded-lg shadow-xl p-1.5">
          <div className="max-h-48 overflow-auto">
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => (p.id === currentId ? setOpen(false) : switchTo(p.id))}
                className={`w-full text-left px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                  p.id === currentId ? "bg-[#4f46e5] text-white" : "text-[#c7ccd6] hover:bg-[#1c202a]"
                }`}
              >
                <div className="truncate">{p.name}</div>
                {p.category && <div className="text-[10px] text-[#8b93a1] truncate">{p.category}</div>}
              </button>
            ))}
          </div>
          <div className="border-t border-[#232833] mt-1.5 pt-1.5">
            {creating ? (
              <div className="space-y-1.5 p-1">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="项目名称"
                  className="w-full bg-[#1c202a] border border-[#232833] rounded px-2 py-1.5 text-[13px] text-white placeholder:text-[#5f6774] focus:outline-none focus:border-[#4f46e5]"
                />
                <input
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  placeholder="研究品类（如 项目管理工具）"
                  className="w-full bg-[#1c202a] border border-[#232833] rounded px-2 py-1.5 text-[13px] text-white placeholder:text-[#5f6774] focus:outline-none focus:border-[#4f46e5]"
                />
                <div className="flex gap-1.5">
                  <button
                    onClick={handleCreate}
                    disabled={!newName.trim() || busy}
                    className="flex-1 bg-[#4f46e5] hover:bg-[#4338ca] disabled:opacity-50 text-white text-xs py-1.5 rounded transition-colors"
                  >
                    {busy ? "创建中…" : "创建并切换"}
                  </button>
                  {projects.length > 0 && (
                    <button
                      onClick={() => setCreating(false)}
                      className="px-2 text-[#8b93a1] hover:text-white text-xs"
                    >
                      取消
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="w-full text-left px-2.5 py-1.5 rounded-md text-[13px] text-[#8b93a1] hover:bg-[#1c202a] hover:text-white transition-colors"
              >
                + 新建项目
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
