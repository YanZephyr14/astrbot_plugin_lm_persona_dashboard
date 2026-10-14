"""main.py - LivingMemory 人格记忆看板插件主入口

提供独立的可视化控制台 Web API 与状态监控指令，
在不修改原 LivingMemory 插件的基础上实现按人格设定（Persona）深度分类查看与维护记忆。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.api.web import error_response, json_response, request

try:
    from .store import LivingMemoryStore
except ImportError:
    from store import LivingMemoryStore  # type: ignore

PLUGIN_NAME = "astrbot_plugin_lm_persona_dashboard"


@register(
    "astrbot_plugin_lm_persona_dashboard",
    "YanZephyr",
    "LivingMemory 专属辅助增强插件：按人格设定（Persona）深度分类、检索、洞察与管理长期记忆。",
    "v1.0.0",
    "https://github.com/YanZephyr14/astrbot_plugin_lm_persona_dashboard",
)
class LMPersonaDashboardPlugin(Star):
    """LivingMemory 人格记忆看板插件"""

    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.context = context
        self.config = config or {}

        custom_dir = str(self.config.get("custom_data_dir", "") or "")
        self.store = LivingMemoryStore(custom_data_dir=custom_dir)

        # 注册 Web API
        self._register_routes()

    def _register_routes(self) -> None:
        """注册插件 Web API 路由"""
        if not hasattr(self.context, "register_web_api"):
            logger.warning(
                "[LMPersonaDashboard] 当前 AstrBot 内核缺少 register_web_api 能力"
            )
            return

        routes = [
            (f"/{PLUGIN_NAME}/status", self.api_status, ["GET"], "获取数据库连接状态"),
            (
                f"/{PLUGIN_NAME}/set_active_db",
                self.api_set_active_db,
                ["POST"],
                "切换当前数据库",
            ),
            (
                f"/{PLUGIN_NAME}/personas",
                self.api_personas,
                ["GET"],
                "获取人格分类概览",
            ),
            (
                f"/{PLUGIN_NAME}/memories",
                self.api_memories,
                ["GET"],
                "分页检索记忆列表",
            ),
            (
                f"/{PLUGIN_NAME}/memory/<memory_id>",
                self.api_memory_detail,
                ["GET"],
                "获取记忆详情",
            ),
            (
                f"/{PLUGIN_NAME}/memory/update",
                self.api_memory_update,
                ["POST"],
                "编辑记忆与转移人格",
            ),
            (
                f"/{PLUGIN_NAME}/memory/batch_persona",
                self.api_batch_persona,
                ["POST"],
                "批量转移记忆所属人格",
            ),
            (
                f"/{PLUGIN_NAME}/memory/delete",
                self.api_memory_delete,
                ["POST"],
                "归档或删除记忆",
            ),
            (f"/{PLUGIN_NAME}/export", self.api_export, ["GET"], "导出人格记忆数据"),
        ]

        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(path, handler, methods, desc)
            except Exception as exc:
                logger.error(f"[LMPersonaDashboard] 注册路由 {path} 失败: {exc}")

    async def initialize(self) -> None:
        """异步初始化"""
        status = await self.store.get_status()
        if status["connected"]:
            logger.info(
                f"[LMPersonaDashboard] 已连接 LivingMemory 数据库: {status['db_path']} "
                f"(共 {status['documents_count']} 条记忆, {status['personas_count']} 个人格分类)"
            )
        else:
            logger.warning(
                f"[LMPersonaDashboard] 未自动检测到 LivingMemory 数据库: {status['message']}"
            )

    async def terminate(self) -> None:
        """插件销毁清理"""
        pass

    # ─────────────────────────────────────────────────────────
    # Web API Handlers
    # ─────────────────────────────────────────────────────────

    async def api_status(self):
        """GET /status 获取数据库连接状态与候选路径"""
        status = await self.store.get_status()
        return json_response(status)

    async def api_set_active_db(self):
        """POST /set_active_db 动态切换活动数据库"""
        payload = await request.json(default={})
        target_path = str(payload.get("path", "")).strip()
        if not target_path:
            return error_response("数据库路径不能为空", status_code=400)

        success = self.store.set_active_db_path(target_path)
        if not success:
            return error_response("指定的数据库路径不存在或无效", status_code=400)

        status = await self.store.get_status()
        return json_response({"success": True, "status": status})

    async def api_personas(self):
        """GET /personas 获取所有人格分类汇总列表"""
        try:
            personas = await self.store.get_personas_summary(self.context)
            return json_response({"personas": personas})
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 获取人格汇总失败: {exc}", exc_info=True)
            return error_response(f"获取人格汇总失败: {exc}", status_code=500)

    async def api_memories(self):
        """GET /memories 按人格及多维条件分页获取记忆"""
        query = request.query
        persona_id = query.get("persona_id")
        keyword = query.get("keyword", "")
        status = query.get("status", "all")
        memory_type = query.get("type", "all")
        sort = query.get("sort", "created_desc")
        session_id = query.get("session_id", "")

        try:
            page = int(query.get("page", 1))
            page_size = int(query.get("page_size", self.config.get("page_size", 15)))
        except (ValueError, TypeError):
            page, page_size = 1, 15

        try:
            data = await self.store.list_memories(
                persona_id=persona_id,
                keyword=keyword,
                status=status,
                memory_type=memory_type,
                sort=sort,
                session_id=session_id,
                page=page,
                page_size=page_size,
            )
            return json_response(data)
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 查询记忆列表失败: {exc}", exc_info=True)
            return error_response(f"查询记忆列表失败: {exc}", status_code=500)

    async def api_memory_detail(self, memory_id: str):
        """GET /memory/<memory_id> 获取记忆详情（含原子记忆与上下文）"""
        try:
            mid = int(memory_id)
        except (ValueError, TypeError):
            return error_response("无效的记忆 ID", status_code=400)

        try:
            detail = await self.store.get_memory_detail(mid)
            if not detail:
                return error_response(f"未找到 ID 为 {mid} 的记忆", status_code=404)
            return json_response(detail)
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 获取记忆详情失败: {exc}", exc_info=True)
            return error_response(f"获取记忆详情失败: {exc}", status_code=500)

    async def api_memory_update(self):
        """POST /memory/update 编辑单条记忆（支持修改人格归属、内容、重要性等）"""
        if not self.config.get("enable_editing", True):
            return error_response("当前看板配置已禁用编辑功能", status_code=403)

        payload = await request.json(default={})
        try:
            mid = int(payload.get("id"))
        except (ValueError, TypeError):
            return error_response("缺少有效记忆 ID", status_code=400)

        updates = {}
        for k in ("text", "persona_id", "memory_type", "importance", "status"):
            if k in payload:
                updates[k] = payload[k]

        try:
            await self.store.update_memory(mid, updates)
            detail = await self.store.get_memory_detail(mid)
            return json_response({"success": True, "memory": detail})
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 更新记忆失败: {exc}", exc_info=True)
            return error_response(f"更新记忆失败: {exc}", status_code=500)

    async def api_batch_persona(self):
        """POST /memory/batch_persona 批量转移记忆所属人格设定"""
        if not self.config.get("enable_editing", True):
            return error_response("当前看板配置已禁用编辑功能", status_code=403)

        payload = await request.json(default={})
        memory_ids = payload.get("ids", [])
        target_persona_id = str(payload.get("target_persona_id", "")).strip()

        if not isinstance(memory_ids, list) or not memory_ids:
            return error_response("请选择至少一条需要转移的记忆", status_code=400)

        valid_ids = []
        for x in memory_ids:
            try:
                valid_ids.append(int(x))
            except (ValueError, TypeError):
                continue

        try:
            updated_count = await self.store.batch_update_persona(
                valid_ids, target_persona_id
            )
            return json_response({"success": True, "updated_count": updated_count})
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 批量转移人格失败: {exc}", exc_info=True)
            return error_response(f"批量转移人格失败: {exc}", status_code=500)

    async def api_memory_delete(self):
        """POST /memory/delete 归档或删除记忆"""
        if not self.config.get("enable_deletion", True):
            return error_response("当前看板配置已禁用删除功能", status_code=403)

        payload = await request.json(default={})
        try:
            mid = int(payload.get("id"))
        except (ValueError, TypeError):
            return error_response("缺少有效记忆 ID", status_code=400)

        soft = bool(payload.get("soft", True))

        try:
            await self.store.delete_memory(mid, soft=soft)
            return json_response({"success": True, "id": mid, "soft": soft})
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 删除记忆失败: {exc}", exc_info=True)
            return error_response(f"删除记忆失败: {exc}", status_code=500)

    async def api_export(self):
        """GET /export 导出指定人格的记忆数据"""
        query = request.query
        persona_id = query.get("persona_id")
        fmt = query.get("format", "json").lower()
        if fmt not in ("json", "csv"):
            fmt = "json"

        try:
            content = await self.store.export_memories(
                persona_id=persona_id, export_format=fmt
            )
            return json_response(
                {
                    "format": fmt,
                    "persona_id": persona_id or "__all__",
                    "content": content,
                }
            )
        except Exception as exc:
            logger.error(f"[LMPersonaDashboard] 导出记忆失败: {exc}", exc_info=True)
            return error_response(f"导出记忆失败: {exc}", status_code=500)

    # ─────────────────────────────────────────────────────────
    # 交互指令
    # ─────────────────────────────────────────────────────────

    @filter.command("lm_persona")
    async def cmd_lm_persona(self, event: AstrMessageEvent):
        """查看 LivingMemory 各角色人格设定的记忆概况与看板入口"""
        status = await self.store.get_status()
        if not status["connected"]:
            yield event.plain_result(
                "⚠️ LivingMemory 人格记忆看板：未连接到有效的数据库。\n"
                f"原因：{status['message']}\n"
                "可在插件配置中填写 custom_data_dir 指定路径。"
            )
            return

        personas = await self.store.get_personas_summary(self.context)
        # 过滤掉 __all__ 汇总项进行展示
        specific_personas = [p for p in personas if p["persona_id"] != "__all__"]

        lines = [
            "🧠 【LivingMemory 人格记忆概览】",
            f"📊 数据库状态: 正常 ({status['documents_count']} 条记忆, {len(specific_personas)} 个人格设定)",
            "──────────────────",
        ]

        for p in specific_personas:
            p_title = (
                p["name"]
                if p["name"] == p["persona_id"]
                else f"{p['name']} ({p['persona_id']})"
            )
            lines.append(
                f"👤 {p_title}\n"
                f"   ├ 记忆: {p['total_count']} 条 (活跃 {p['active_count']} / 归档 {p['archived_count']})\n"
                f"   ├ 原子记忆: {p['atom_count']} 个\n"
                f"   └ 最近记忆: {p['latest_time_display']}"
            )

        lines.extend(
            [
                "──────────────────",
                "💡 提示：请前往 WebUI 控制台 -> 插件 -> LM 人格记忆看板，享受完整的分类检索、详情透视与人格转移功能！",
            ]
        )

        yield event.plain_result("\n".join(lines))
