"""store.py - LivingMemory 数据库连接与人格记忆数据服务层

负责智能探测并连接 LivingMemory SQLite 数据库，
提供按人格设定 (Persona) 深度分类、聚合统计、检索、编辑与转移服务。
"""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@dataclass
class PersonaSummary:
    """人格分类汇总信息"""

    persona_id: str
    name: str
    display_title: str
    system_prompt: str = ""
    is_configured: bool = False
    total_count: int = 0
    active_count: int = 0
    archived_count: int = 0
    atom_count: int = 0
    latest_time: float = 0.0
    avg_importance: float = 0.5
    type_distribution: dict[str, int] = field(default_factory=dict)


class LivingMemoryStore:
    """LivingMemory 数据库交互层"""

    def __init__(self, custom_data_dir: str = ""):
        self.custom_data_dir = custom_data_dir.strip()
        self._active_db_path: Path | None = None
        self._active_conv_db_path: Path | None = None

    def find_all_candidates(self) -> list[dict[str, Any]]:
        """扫描环境中所有可能的 LivingMemory 数据库候选路径

        Returns:
            list[dict]: 候选数据库元信息列表，按最后修改时间倒序排列
        """
        candidates: list[Path] = []

        # 1. 用户自定义配置目录
        if self.custom_data_dir:
            custom_p = Path(self.custom_data_dir)
            if custom_p.is_file() and custom_p.name.endswith(".db"):
                candidates.append(custom_p)
            elif custom_p.is_dir():
                candidates.append(custom_p / "livingmemory.db")

        # 2. 当前 AstrBot 标准数据持久化目录
        try:
            standard_dir = (
                Path(get_astrbot_data_path())
                / "plugin_data"
                / "astrbot_plugin_livingmemory"
            )
            candidates.append(standard_dir / "livingmemory.db")
        except Exception as exc:
            logger.debug(f"读取标准 AstrBot 数据目录异常: {exc}")

        # 3. 桌面启动器实例目录 (~/.astrbot_launcher/instances/*/core/data/plugin_data/astrbot_plugin_livingmemory/)
        launcher_instances_dir = Path.home() / ".astrbot_launcher" / "instances"
        if launcher_instances_dir.is_dir():
            try:
                for inst_dir in launcher_instances_dir.iterdir():
                    if not inst_dir.is_dir():
                        continue
                    db_candidate = (
                        inst_dir
                        / "core"
                        / "data"
                        / "plugin_data"
                        / "astrbot_plugin_livingmemory"
                        / "livingmemory.db"
                    )
                    if db_candidate.exists():
                        candidates.append(db_candidate)
            except Exception as exc:
                logger.debug(f"扫描启动器实例目录异常: {exc}")

        # 4. 工作区中的参考资源目录（用于离线调试）
        workspace_ref = Path("参考资源/astrbot_plugin_livingmemory/livingmemory.db")
        if workspace_ref.exists():
            candidates.append(workspace_ref.resolve())

        # 去重并筛选出真实存在的数据库
        unique_paths: list[Path] = []
        seen = set()
        for p in candidates:
            resolved = p.resolve()
            if resolved not in seen and resolved.is_file():
                seen.add(resolved)
                unique_paths.append(resolved)

        # 格式化元数据并按修改时间倒序
        result: list[dict[str, Any]] = []
        for p in unique_paths:
            try:
                stat = p.stat()
                result.append(
                    {
                        "path": str(p),
                        "dir": str(p.parent),
                        "size_bytes": stat.st_size,
                        "size_display": f"{stat.st_size / (1024 * 1024):.2f} MB",
                        "mtime": stat.st_mtime,
                        "mtime_display": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    }
                )
            except Exception:
                continue

        result.sort(key=lambda x: x["mtime"], reverse=True)
        return result

    def resolve_db_path(self) -> Path | None:
        """解析并返回当前应使用的 livingmemory.db 路径"""
        if self._active_db_path and self._active_db_path.is_file():
            return self._active_db_path

        candidates = self.find_all_candidates()
        if candidates:
            best_path = Path(candidates[0]["path"])
            self._active_db_path = best_path
            self._active_conv_db_path = (
                best_path.parent / "conversations.db"
                if (best_path.parent / "conversations.db").is_file()
                else None
            )
            return best_path

        return None

    def set_active_db_path(self, path_str: str) -> bool:
        """动态指定当前使用的数据库路径

        Args:
            path_str: 数据库文件路径或其所在目录

        Returns:
            bool: 切换是否成功
        """
        p = Path(path_str.strip())
        if p.is_dir():
            p = p / "livingmemory.db"
        if p.is_file():
            self._active_db_path = p.resolve()
            conv_p = p.parent / "conversations.db"
            self._active_conv_db_path = conv_p if conv_p.is_file() else None
            return True
        return False

    @asynccontextmanager
    async def _get_db(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """安全获取只读/写异步 SQLite 连接并启用 WAL 模式"""
        db_path = self.resolve_db_path()
        if not db_path or not db_path.is_file():
            raise FileNotFoundError(
                f"未找到 LivingMemory 数据库文件。已扫描候选路径或自定义目录：{self.custom_data_dir or '无'}"
            )

        db = await aiosqlite.connect(str(db_path))
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA busy_timeout = 10000")
            yield db
        finally:
            await db.close()

    async def get_status(self) -> dict[str, Any]:
        """获取当前数据库连接与健康状态"""
        db_path = self.resolve_db_path()
        candidates = self.find_all_candidates()

        if not db_path or not db_path.is_file():
            return {
                "connected": False,
                "db_path": None,
                "message": "未找到有效的 LivingMemory 数据库文件，请确认主插件已运行或在配置中指定 custom_data_dir。",
                "candidates": candidates,
                "documents_count": 0,
                "atoms_count": 0,
                "personas_count": 0,
            }

        try:
            async with self._get_db() as db:
                doc_cur = await db.execute("SELECT COUNT(*) FROM documents")
                doc_cnt = (await doc_cur.fetchone())[0]

                atom_cnt = 0
                try:
                    atom_cur = await db.execute("SELECT COUNT(*) FROM memory_atoms")
                    atom_cnt = (await atom_cur.fetchone())[0]
                except Exception:
                    pass

                persona_cnt = 0
                try:
                    p_cur = await db.execute(
                        "SELECT COUNT(DISTINCT json_extract(metadata, '$.persona_id')) FROM documents"
                    )
                    persona_cnt = (await p_cur.fetchone())[0]
                except Exception:
                    pass

                stat = db_path.stat()
                return {
                    "connected": True,
                    "db_path": str(db_path),
                    "data_dir": str(db_path.parent),
                    "file_size_display": f"{stat.st_size / (1024 * 1024):.2f} MB",
                    "mtime_display": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "documents_count": doc_cnt,
                    "atoms_count": atom_cnt,
                    "personas_count": persona_cnt,
                    "has_conversations_db": (
                        self._active_conv_db_path is not None
                        and self._active_conv_db_path.is_file()
                    ),
                    "candidates": candidates,
                }
        except Exception as exc:
            logger.error(
                f"[LivingMemoryStore] 获取数据库状态异常: {exc}",
                exc_info=True,
            )
            return {
                "connected": False,
                "db_path": str(db_path),
                "message": f"连接数据库失败: {exc}",
                "candidates": candidates,
                "documents_count": 0,
                "atoms_count": 0,
                "personas_count": 0,
            }

    async def get_personas_summary(self, context: Any = None) -> list[dict[str, Any]]:
        """获取按角色人格设定聚合的人格列表与各分类统计

        Args:
            context: AstrBot 上下文，用于读取系统已配置的 Persona 清单

        Returns:
            list[dict]: 人格统计摘要列表，按总记忆数降序
        """
        # 1. 尝试从 AstrBot 上下文收集系统已配置的 Persona
        configured_personas: dict[str, dict[str, Any]] = {}
        if context and hasattr(context, "persona_mgr"):
            try:
                persona_mgr = context.persona_mgr
                system_personas = []
                if hasattr(persona_mgr, "get_all_personas"):
                    system_personas = await persona_mgr.get_all_personas()
                elif hasattr(persona_mgr, "personas"):
                    system_personas = persona_mgr.personas

                for p in system_personas:
                    pid = getattr(p, "persona_id", None)
                    p_name = getattr(p, "name", None) or pid
                    prompt = getattr(p, "system_prompt", "") or ""
                    if pid:
                        configured_personas[str(pid)] = {
                            "persona_id": str(pid),
                            "name": str(p_name),
                            "prompt": str(prompt)[:120],
                        }
            except Exception as exc:
                logger.debug(f"获取系统 Persona 列表提示: {exc}")

        # 2. 从 documents 表统计各 persona_id 的记忆概况
        db_stats: dict[str, dict[str, Any]] = {}
        total_all_count = 0
        total_all_active = 0
        total_all_archived = 0
        all_type_dist: dict[str, int] = {}

        async with self._get_db() as db:
            # 基础聚合
            cur = await db.execute(
                """
                SELECT
                    json_extract(metadata, '$.persona_id') AS pid,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN COALESCE(json_extract(metadata, '$.status'), 'active') = 'active' THEN 1 ELSE 0 END) AS active_count,
                    SUM(CASE WHEN COALESCE(json_extract(metadata, '$.status'), 'active') = 'archived' THEN 1 ELSE 0 END) AS archived_count,
                    MAX(COALESCE(CAST(json_extract(metadata, '$.updated_at') AS REAL), CAST(json_extract(metadata, '$.create_time') AS REAL), 0)) AS latest_time,
                    AVG(COALESCE(CAST(json_extract(metadata, '$.importance') AS REAL), 0.5)) AS avg_importance
                FROM documents
                GROUP BY pid
                """
            )
            rows = await cur.fetchall()

            for r in rows:
                raw_pid = r["pid"]
                pid_key = str(raw_pid).strip() if raw_pid is not None else ""
                t_count = int(r["total_count"] or 0)
                a_count = int(r["active_count"] or 0)
                arc_count = int(r["archived_count"] or 0)
                l_time = float(r["latest_time"] or 0.0)
                imp = float(r["avg_importance"] or 0.5)

                db_stats[pid_key] = {
                    "total_count": t_count,
                    "active_count": a_count,
                    "archived_count": arc_count,
                    "latest_time": l_time,
                    "avg_importance": round(imp, 2),
                    "type_distribution": {},
                    "atom_count": 0,
                }
                total_all_count += t_count
                total_all_active += a_count
                total_all_archived += arc_count

            # 类型分布聚合
            type_cur = await db.execute(
                """
                SELECT
                    json_extract(metadata, '$.persona_id') AS pid,
                    UPPER(COALESCE(json_extract(metadata, '$.memory_type'), 'GENERAL')) AS m_type,
                    COUNT(*) AS cnt
                FROM documents
                GROUP BY pid, m_type
                """
            )
            type_rows = await type_cur.fetchall()
            for tr in type_rows:
                raw_pid = tr["pid"]
                pid_key = str(raw_pid).strip() if raw_pid is not None else ""
                m_type = str(tr["m_type"])
                cnt = int(tr["cnt"])
                if pid_key in db_stats:
                    db_stats[pid_key]["type_distribution"][m_type] = cnt
                all_type_dist[m_type] = all_type_dist.get(m_type, 0) + cnt

            # memory_atoms 数量统计
            try:
                atom_cur = await db.execute(
                    """
                    SELECT persona_id, COUNT(*) as cnt
                    FROM memory_atoms
                    GROUP BY persona_id
                    """
                )
                atom_rows = await atom_cur.fetchall()
                for ar in atom_rows:
                    raw_pid = ar["persona_id"]
                    pid_key = str(raw_pid).strip() if raw_pid is not None else ""
                    cnt = int(ar["cnt"])
                    if pid_key in db_stats:
                        db_stats[pid_key]["atom_count"] = cnt
            except Exception:
                pass

        # 3. 组合所有人格项
        all_keys = set(configured_personas.keys()) | set(db_stats.keys())
        persona_list: list[dict[str, Any]] = []

        for k in all_keys:
            if not k:
                # 空字符串代表未指定/通用人格
                continue

            cfg = configured_personas.get(k)
            st = db_stats.get(
                k,
                {
                    "total_count": 0,
                    "active_count": 0,
                    "archived_count": 0,
                    "latest_time": 0.0,
                    "avg_importance": 0.5,
                    "type_distribution": {},
                    "atom_count": 0,
                },
            )

            name = cfg["name"] if cfg else k
            system_prompt = cfg["prompt"] if cfg else ""

            persona_list.append(
                {
                    "persona_id": k,
                    "name": name,
                    "display_title": f"{name} ({k})" if name != k else name,
                    "system_prompt": system_prompt,
                    "is_configured": cfg is not None,
                    "total_count": st["total_count"],
                    "active_count": st["active_count"],
                    "archived_count": st["archived_count"],
                    "atom_count": st["atom_count"],
                    "latest_time": st["latest_time"],
                    "latest_time_display": (
                        datetime.fromtimestamp(
                            st["latest_time"], tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M")
                        if st["latest_time"] > 0
                        else "-"
                    ),
                    "avg_importance": st["avg_importance"],
                    "type_distribution": st["type_distribution"],
                }
            )

        # 排序：有记忆的按记忆数降序，记忆数相同的按最近时间降序
        persona_list.sort(
            key=lambda x: (x["total_count"], x["latest_time"]), reverse=True
        )

        # 4. 组装“未归属设定 / 通用”项 (若存在)
        unassigned_st = db_stats.get("", None)
        unassigned_item = None
        if unassigned_st and unassigned_st["total_count"] > 0:
            unassigned_item = {
                "persona_id": "__unassigned__",
                "name": "未归属 / 通用记忆",
                "display_title": "未指定人格设定 (Unassigned)",
                "system_prompt": "未关联任何具体角色或由全局/旧会话产生的记忆",
                "is_configured": False,
                "total_count": unassigned_st["total_count"],
                "active_count": unassigned_st["active_count"],
                "archived_count": unassigned_st["archived_count"],
                "atom_count": unassigned_st["atom_count"],
                "latest_time": unassigned_st["latest_time"],
                "latest_time_display": (
                    datetime.fromtimestamp(
                        unassigned_st["latest_time"], tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M")
                    if unassigned_st["latest_time"] > 0
                    else "-"
                ),
                "avg_importance": unassigned_st["avg_importance"],
                "type_distribution": unassigned_st["type_distribution"],
            }

        # 5. 顶置“全部人格 (All Personas)”汇总项
        all_item = {
            "persona_id": "__all__",
            "name": "全部人格设定",
            "display_title": "所有人格总览 (All Personas)",
            "system_prompt": "查看当前数据库中跨所有角色的人格记忆全貌",
            "is_configured": True,
            "total_count": total_all_count,
            "active_count": total_all_active,
            "archived_count": total_all_archived,
            "atom_count": sum(x.get("atom_count", 0) for x in persona_list)
            + (unassigned_item["atom_count"] if unassigned_item else 0),
            "latest_time": (
                max([x["latest_time"] for x in persona_list] + [0.0])
                if persona_list
                else 0.0
            ),
            "latest_time_display": "-",
            "avg_importance": 0.5,
            "type_distribution": all_type_dist,
        }

        final_result = [all_item]
        final_result.extend(persona_list)
        if unassigned_item:
            final_result.append(unassigned_item)

        return final_result

    async def list_memories(
        self,
        *,
        persona_id: str | None = None,
        keyword: str = "",
        status: str = "all",
        memory_type: str = "all",
        importance_min: float | None = None,
        sort: str = "created_desc",
        session_id: str = "",
        page: int = 1,
        page_size: int = 15,
    ) -> dict[str, Any]:
        """按人格及多维度分页检索记忆列表

        Args:
            persona_id: 人格过滤（None/'__all__' 表示全部，'__unassigned__' 表示未归属，其余为精确 persona_id）
            keyword: 关键词（匹配正文、ID、topics、key_facts）
            status: 状态过滤 (all/active/archived/deleted)
            memory_type: 类型过滤 (all/FACT/PREFERENCE/EVENT/GENERAL/...)
            importance_min: 最低重要性阈值 (0-1)
            sort: 排序选项 (created_desc/created_asc/updated_desc/importance_desc/importance_asc)
            session_id: 会话 ID 过滤
            page: 当前页码（从 1 开始）
            page_size: 每页条数

        Returns:
            dict: 包含 items, total, page, page_size, total_pages, has_more
        """
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        offset = (page - 1) * page_size

        where_clauses: list[str] = []
        params: list[Any] = []

        # 1. 人格过滤
        if persona_id and persona_id not in ("__all__", "all"):
            if persona_id == "__unassigned__":
                where_clauses.append(
                    "(json_extract(metadata, '$.persona_id') IS NULL OR json_extract(metadata, '$.persona_id') = '')"
                )
            else:
                where_clauses.append("json_extract(metadata, '$.persona_id') = ?")
                params.append(persona_id)

        # 2. 状态过滤
        if status and status.lower() != "all":
            where_clauses.append(
                "COALESCE(json_extract(metadata, '$.status'), 'active') = ?"
            )
            params.append(status.lower())

        # 3. 类型过滤
        if memory_type and memory_type.lower() != "all":
            where_clauses.append(
                "UPPER(COALESCE(json_extract(metadata, '$.memory_type'), 'GENERAL')) = ?"
            )
            params.append(memory_type.upper())

        # 4. 最低重要性
        if importance_min is not None and importance_min > 0:
            where_clauses.append(
                "CAST(COALESCE(json_extract(metadata, '$.importance'), 0.5) AS REAL) >= ?"
            )
            params.append(float(importance_min))

        # 5. 会话过滤
        if session_id.strip():
            where_clauses.append("json_extract(metadata, '$.session_id') LIKE ?")
            params.append(f"%{session_id.strip()}%")

        # 6. 关键词检索
        kw = keyword.strip()
        if kw:
            if kw.isdigit():
                where_clauses.append(
                    "(id = ? OR text LIKE ? COLLATE NOCASE OR json_extract(metadata, '$.topics') LIKE ?)"
                )
                params.extend([int(kw), f"%{kw}%", f"%{kw}%"])
            else:
                where_clauses.append(
                    "(text LIKE ? COLLATE NOCASE OR json_extract(metadata, '$.topics') LIKE ? COLLATE NOCASE OR json_extract(metadata, '$.key_facts') LIKE ? COLLATE NOCASE)"
                )
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # 排序映射
        sort_map = {
            "created_desc": "COALESCE(CAST(json_extract(metadata, '$.create_time') AS REAL), 0) DESC, id DESC",
            "created_asc": "COALESCE(CAST(json_extract(metadata, '$.create_time') AS REAL), 0) ASC, id ASC",
            "updated_desc": "COALESCE(CAST(json_extract(metadata, '$.updated_at') AS REAL), CAST(json_extract(metadata, '$.create_time') AS REAL), 0) DESC, id DESC",
            "importance_desc": "COALESCE(CAST(json_extract(metadata, '$.importance') AS REAL), 0.5) DESC, id DESC",
            "importance_asc": "COALESCE(CAST(json_extract(metadata, '$.importance') AS REAL), 0.5) ASC, id ASC",
        }
        order_sql = sort_map.get(sort, sort_map["created_desc"])

        async with self._get_db() as db:
            # 统计总数
            count_cur = await db.execute(
                f"SELECT COUNT(*) as total FROM documents {where_sql}", params
            )
            count_row = await count_cur.fetchone()
            total = int(count_row["total"]) if count_row else 0

            # 查询分页数据
            query_sql = f"""
                SELECT id, text, metadata
                FROM documents
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
            """
            cur = await db.execute(query_sql, params + [page_size, offset])
            rows = await cur.fetchall()

            items: list[dict[str, Any]] = []
            doc_ids = [r["id"] for r in rows]

            # 批量获取关联原子记忆数量
            atom_counts: dict[int, int] = {}
            if doc_ids:
                try:
                    placeholders = ",".join(["?"] * len(doc_ids))
                    a_cur = await db.execute(
                        f"""
                        SELECT parent_memory_id, COUNT(*) as cnt
                        FROM memory_atoms
                        WHERE parent_memory_id IN ({placeholders})
                        GROUP BY parent_memory_id
                        """,
                        doc_ids,
                    )
                    a_rows = await a_cur.fetchall()
                    for ar in a_rows:
                        atom_counts[int(ar["parent_memory_id"])] = int(ar["cnt"])
                except Exception:
                    pass

            for r in rows:
                mid = int(r["id"])
                text = str(r["text"] or "")
                raw_meta = r["metadata"]
                meta: dict[str, Any] = {}
                if isinstance(raw_meta, str) and raw_meta.strip():
                    try:
                        meta = json.loads(raw_meta)
                    except Exception:
                        meta = {}

                # 提取标准字段
                p_id = meta.get("persona_id") or ""
                s_id = meta.get("session_id") or ""
                m_type = (meta.get("memory_type") or "GENERAL").upper()
                st = meta.get("status") or "active"
                imp = float(meta.get("importance", 0.5))
                # 兼容 0-1 与 0-10 比例
                norm_imp = imp / 10.0 if imp > 1.0 else imp

                c_time = float(meta.get("create_time", 0.0))
                u_time = float(meta.get("updated_at", c_time))
                topics = meta.get("topics") or []
                if not isinstance(topics, list):
                    topics = []
                key_facts = meta.get("key_facts") or []
                if not isinstance(key_facts, list):
                    key_facts = []

                items.append(
                    {
                        "id": mid,
                        "text": text,
                        "persona_id": p_id,
                        "session_id": s_id,
                        "memory_type": m_type,
                        "status": st,
                        "importance": round(norm_imp, 2),
                        "importance_score": round(norm_imp * 10.0, 1),
                        "create_time": c_time,
                        "create_time_display": (
                            datetime.fromtimestamp(c_time, tz=timezone.utc).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            if c_time > 0
                            else "-"
                        ),
                        "updated_at": u_time,
                        "topics": topics,
                        "key_facts": key_facts,
                        "atom_count": atom_counts.get(mid, 0),
                        "has_source": bool(meta.get("has_source", False)),
                        "source_message_count": int(
                            meta.get("source_message_count", 0)
                        ),
                    }
                )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_more": page < total_pages,
        }

    async def get_memory_detail(self, memory_id: int) -> dict[str, Any] | None:
        """获取单条记忆的详细信息（含拆解的 Memory Atoms 与上下文消息）

        Args:
            memory_id: 记忆 ID

        Returns:
            dict | None: 详细数据
        """
        async with self._get_db() as db:
            cur = await db.execute(
                "SELECT id, text, metadata FROM documents WHERE id = ?",
                (memory_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None

            raw_meta = row["metadata"]
            meta: dict[str, Any] = {}
            if isinstance(raw_meta, str) and raw_meta.strip():
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    meta = {}

            # 查询关联的 memory_atoms
            atoms: list[dict[str, Any]] = []
            try:
                a_cur = await db.execute(
                    """
                    SELECT id, atom_type, content, entities, importance, confidence,
                           created_at, expires_at, status, reinforcement_count, decay_type,
                           persona_id, session_id
                    FROM memory_atoms
                    WHERE parent_memory_id = ?
                    ORDER BY id ASC
                    """,
                    (memory_id,),
                )
                a_rows = await a_cur.fetchall()
                for ar in a_rows:
                    entities = []
                    try:
                        entities = json.loads(ar["entities"] or "[]")
                    except Exception:
                        pass
                    atoms.append(
                        {
                            "id": ar["id"],
                            "atom_type": ar["atom_type"],
                            "content": ar["content"],
                            "entities": entities,
                            "importance": round(float(ar["importance"] or 0.5), 2),
                            "confidence": round(float(ar["confidence"] or 0.7), 2),
                            "created_at": ar["created_at"],
                            "expires_at": ar["expires_at"],
                            "status": ar["status"],
                            "reinforcement_count": ar["reinforcement_count"],
                            "decay_type": ar["decay_type"],
                            "persona_id": ar["persona_id"],
                        }
                    )
            except Exception as exc:
                logger.debug(f"查询原子记忆异常 (ID={memory_id}): {exc}")

            # 尝试提取会话来源上下文消息 (如果有 conversations.db)
            source_messages: list[dict[str, Any]] = []
            session_id = meta.get("session_id")
            if (
                session_id
                and self._active_conv_db_path
                and self._active_conv_db_path.is_file()
            ):
                try:
                    async with aiosqlite.connect(
                        str(self._active_conv_db_path)
                    ) as conv_db:
                        conv_db.row_factory = aiosqlite.Row
                        c_time = float(meta.get("create_time", 0.0))
                        # 查找在该记忆生成时间点附近的会话消息
                        m_cur = await conv_db.execute(
                            """
                            SELECT role, content, sender_name, timestamp
                            FROM messages
                            WHERE session_id = ? AND timestamp <= ? + 10
                            ORDER BY timestamp DESC
                            LIMIT 6
                            """,
                            (session_id, c_time),
                        )
                        m_rows = await m_cur.fetchall()
                        for mr in reversed(m_rows):
                            source_messages.append(
                                {
                                    "role": mr["role"],
                                    "content": mr["content"],
                                    "sender_name": mr["sender_name"] or mr["role"],
                                    "timestamp": mr["timestamp"],
                                    "time_display": datetime.fromtimestamp(
                                        mr["timestamp"], tz=timezone.utc
                                    ).strftime("%H:%M:%S"),
                                }
                            )
                except Exception as exc:
                    logger.debug(f"查询来源消息异常 (session={session_id}): {exc}")

            c_time = float(meta.get("create_time", 0.0))
            u_time = float(meta.get("updated_at", c_time))
            imp = float(meta.get("importance", 0.5))
            norm_imp = imp / 10.0 if imp > 1.0 else imp

            return {
                "id": int(row["id"]),
                "text": str(row["text"] or ""),
                "persona_id": meta.get("persona_id") or "",
                "session_id": session_id or "",
                "memory_type": (meta.get("memory_type") or "GENERAL").upper(),
                "status": meta.get("status") or "active",
                "importance": round(norm_imp, 2),
                "importance_score": round(norm_imp * 10.0, 1),
                "create_time": c_time,
                "create_time_display": (
                    datetime.fromtimestamp(c_time, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if c_time > 0
                    else "-"
                ),
                "updated_at": u_time,
                "topics": meta.get("topics") or [],
                "key_facts": meta.get("key_facts") or [],
                "atoms": atoms,
                "source_messages": source_messages,
                "raw_metadata": meta,
            }

    async def update_memory(
        self,
        memory_id: int,
        updates: dict[str, Any],
    ) -> bool:
        """更新记忆（支持内容、重要性、类型、状态及转移所属 Persona）

        Args:
            memory_id: 记忆 ID
            updates: 包含要更新的字段字典

        Returns:
            bool: 是否更新成功
        """
        async with self._get_db() as db:
            cur = await db.execute(
                "SELECT text, metadata FROM documents WHERE id = ?",
                (memory_id,),
            )
            row = await cur.fetchone()
            if not row:
                raise ValueError(f"未找到 ID 为 {memory_id} 的记忆")

            raw_meta = row["metadata"]
            meta: dict[str, Any] = {}
            if isinstance(raw_meta, str) and raw_meta.strip():
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    meta = {}

            new_text = str(row["text"])
            if "text" in updates and updates["text"] is not None:
                new_text = str(updates["text"]).strip()
                if not new_text:
                    raise ValueError("记忆内容不能为空")

            # 字段更新
            persona_changed = False
            new_persona_id = None
            if "persona_id" in updates:
                new_persona_id = (
                    str(updates["persona_id"]).strip() if updates["persona_id"] else ""
                )
                meta["persona_id"] = new_persona_id
                persona_changed = True

            if "memory_type" in updates and updates["memory_type"]:
                meta["memory_type"] = str(updates["memory_type"]).upper()

            if "importance" in updates and updates["importance"] is not None:
                try:
                    val = float(updates["importance"])
                    meta["importance"] = min(1.0, max(0.0, val))
                except (ValueError, TypeError):
                    pass

            status_changed = False
            new_status = None
            if "status" in updates and updates["status"]:
                new_status = str(updates["status"]).lower()
                meta["status"] = new_status
                status_changed = True

            meta["updated_at"] = time.time()
            new_metadata_str = json.dumps(meta, ensure_ascii=False)

            await db.execute(
                "UPDATE documents SET text = ?, metadata = ? WHERE id = ?",
                (new_text, new_metadata_str, memory_id),
            )

            # 同步更新 memory_atoms 表
            if persona_changed:
                try:
                    await db.execute(
                        "UPDATE memory_atoms SET persona_id = ? WHERE parent_memory_id = ?",
                        (new_persona_id, memory_id),
                    )
                except Exception as exc:
                    logger.debug(f"同步更新原子记忆 persona_id 提示: {exc}")

            if status_changed:
                try:
                    await db.execute(
                        "UPDATE memory_atoms SET status = ? WHERE parent_memory_id = ?",
                        (new_status, memory_id),
                    )
                except Exception as exc:
                    logger.debug(f"同步更新原子记忆 status 提示: {exc}")

            await db.commit()
            return True

    async def batch_update_persona(
        self,
        memory_ids: list[int],
        target_persona_id: str,
    ) -> int:
        """批量将多条记忆转移到指定人格设定下

        Args:
            memory_ids: 待转移的记忆 ID 列表
            target_persona_id: 目标人格 ID

        Returns:
            int: 成功转移的记忆条数
        """
        if not memory_ids:
            return 0

        target_persona_id = str(target_persona_id or "").strip()
        count = 0
        now = time.time()

        async with self._get_db() as db:
            for mid in memory_ids:
                cur = await db.execute(
                    "SELECT metadata FROM documents WHERE id = ?", (mid,)
                )
                row = await cur.fetchone()
                if not row:
                    continue

                meta: dict[str, Any] = {}
                try:
                    meta = json.loads(row["metadata"] or "{}")
                except Exception:
                    pass

                meta["persona_id"] = target_persona_id
                meta["updated_at"] = now
                new_meta_str = json.dumps(meta, ensure_ascii=False)

                await db.execute(
                    "UPDATE documents SET metadata = ? WHERE id = ?",
                    (new_meta_str, mid),
                )
                try:
                    await db.execute(
                        "UPDATE memory_atoms SET persona_id = ? WHERE parent_memory_id = ?",
                        (target_persona_id, mid),
                    )
                except Exception:
                    pass
                count += 1

            await db.commit()
            return count

    async def delete_memory(self, memory_id: int, soft: bool = True) -> bool:
        """删除或归档单条记忆

        Args:
            memory_id: 记忆 ID
            soft: True 为软删除（标记为 archived/deleted），False 为硬物理删除

        Returns:
            bool: 是否成功
        """
        async with self._get_db() as db:
            if soft:
                cur = await db.execute(
                    "SELECT metadata FROM documents WHERE id = ?",
                    (memory_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return False
                meta: dict[str, Any] = {}
                try:
                    meta = json.loads(row["metadata"] or "{}")
                except Exception:
                    pass
                meta["status"] = "archived"
                meta["updated_at"] = time.time()
                await db.execute(
                    "UPDATE documents SET metadata = ? WHERE id = ?",
                    (json.dumps(meta, ensure_ascii=False), memory_id),
                )
                try:
                    await db.execute(
                        "UPDATE memory_atoms SET status = 'archived' WHERE parent_memory_id = ?",
                        (memory_id,),
                    )
                except Exception:
                    pass
            else:
                await db.execute("DELETE FROM documents WHERE id = ?", (memory_id,))
                try:
                    await db.execute(
                        "DELETE FROM memory_atoms WHERE parent_memory_id = ?",
                        (memory_id,),
                    )
                except Exception:
                    pass

            await db.commit()
            return True

    async def export_memories(
        self,
        persona_id: str | None = None,
        export_format: str = "json",
    ) -> str:
        """导出指定人格的记忆数据

        Args:
            persona_id: 人格 ID（None/'__all__' 表示全部）
            export_format: 导出格式 ('json' 或 'csv')

        Returns:
            str: 导出的文本内容
        """
        res = await self.list_memories(
            persona_id=persona_id,
            status="all",
            page=1,
            page_size=10000,
        )
        items = res["items"]

        if export_format.lower() == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "ID",
                    "Persona",
                    "Type",
                    "Importance",
                    "Status",
                    "Create Time",
                    "Session ID",
                    "Content",
                    "Topics",
                ]
            )
            for it in items:
                writer.writerow(
                    [
                        it["id"],
                        it["persona_id"],
                        it["memory_type"],
                        it["importance"],
                        it["status"],
                        it["create_time_display"],
                        it["session_id"],
                        it["text"],
                        ";".join(it["topics"]),
                    ]
                )
            return output.getvalue()
        else:
            return json.dumps(
                {
                    "export_time": datetime.now(timezone.utc).isoformat(),
                    "persona_id": persona_id or "__all__",
                    "total": len(items),
                    "memories": items,
                },
                ensure_ascii=False,
                indent=2,
            )
