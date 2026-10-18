# -*- coding: utf-8 -*-
"""
ReAct Agent 思维引擎
Reasoning + Acting loop: Observe -> Think -> Act -> Observe -> ... -> Answer
"""
import sqlite3
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

DB_PATH = str(Path(__file__).parent.parent / "data" / "db" / "jianjian.db")


class Tool(str, Enum):
    QUERY_DB = "query_db"          # 查询数据库表
    SEARCH_KNOWLEDGE = "search_knowledge"  # 搜索知识库
    QUERY_AGENTS = "query_agents"  # 查询其他Agent
    CHECK_RISKS = "check_risks"    # 检查风险
    CALCULATE = "calculate"        # 计算统计


@dataclass
class ReActStep:
    """ReAct推理步骤"""
    step_num: int
    thought: str
    tool: Tool
    tool_input: str
    observation: str
    success: bool


@dataclass
class ReActResult:
    """ReAct推理结果"""
    steps: List[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    tools_used: List[str] = field(default_factory=list)
    agents_involved: List[str] = field(default_factory=list)
    confidence: float = 0.0


class ReActAgent:
    """ReAct思维引擎 - 推理+行动循环"""
    
    # 工具定义
    TOOLS = {
        Tool.QUERY_DB: {
            "description": "查询业务数据库，获取项目、检测、财务、人员等实时数据",
            "params": ["table", "filters"],
        },
        Tool.SEARCH_KNOWLEDGE: {
            "description": "在知识库中搜索相关标准、法规、制度文档",
            "params": ["query", "limit"],
        },
        Tool.QUERY_AGENTS: {
            "description": "向其他数字员工发起查询请求，获取专业领域数据",
            "params": ["agent_name", "question"],
        },
        Tool.CHECK_RISKS: {
            "description": "检查各类风险项（项目延期、资质到期、设备检定等）",
            "params": ["risk_types"],
        },
        Tool.CALCULATE: {
            "description": "对数据进行统计分析（汇总、对比、趋势等）",
            "params": ["data", "operation"],
        },
    }
    
    # Agent工具偏好
    AGENT_TOOL_PREFERENCE = {
        "智管": [Tool.QUERY_DB, Tool.CHECK_RISKS, Tool.CALCULATE, Tool.SEARCH_KNOWLEDGE],
        "智财": [Tool.QUERY_DB, Tool.CALCULATE, Tool.CHECK_RISKS],
        "智项": [Tool.QUERY_DB, Tool.CHECK_RISKS],
        "智检": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE, Tool.CHECK_RISKS],
        "智人": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智客": [Tool.QUERY_DB, Tool.QUERY_AGENTS],
        "智法": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE, Tool.CHECK_RISKS],
        "智设": [Tool.QUERY_DB, Tool.CHECK_RISKS],
        "智安": [Tool.QUERY_DB, Tool.CHECK_RISKS, Tool.SEARCH_KNOWLEDGE],
        "智测": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智洁": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智雷": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智商": [Tool.QUERY_DB, Tool.QUERY_AGENTS],
        "智报": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智合": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智材": [Tool.QUERY_DB, Tool.CHECK_RISKS],
        "智仓": [Tool.QUERY_DB, Tool.CHECK_RISKS],
        "智监": [Tool.QUERY_DB, Tool.SEARCH_KNOWLEDGE],
        "智算": [Tool.QUERY_DB, Tool.CALCULATE],
    }
    
    def __init__(self):
        self.max_steps = 8  # 最大推理步数
        self.history: Dict[str, List[dict]] = {}  # 对话历史
    
    def think(self, agent_name: str, query: str, history: List[dict] = None) -> ReActResult:
        """
        ReAct推理主循环
        1. Observe: 理解用户问题和上下文
        2. Think: 判断需要调用哪些工具
        3. Act: 执行工具调用
        4. Observe: 获取工具返回结果
        5. 重复直到有足够的信息生成答案
        """
        result = ReActResult()
        context = self._build_context(agent_name, query, history)
        
        for step_num in range(1, self.max_steps + 1):
            # Think: 分析当前情况，决定下一步行动
            thought, tool_choice = self._think(agent_name, context, result.steps)
            result.steps.append(ReActStep(
                step_num=step_num,
                thought=thought,
                tool=tool_choice,
                tool_input=self._prepare_tool_input(tool_choice, context, result),
                observation="",
                success=False
            ))
            
            # Act: 执行工具调用
            observation, success = self._act(tool_choice, result.steps[-1].tool_input, agent_name)
            result.steps[-1].observation = observation[:200]  # 截断过长观察
            result.steps[-1].success = success
            result.tools_used.append(tool_choice.value)
            
            if not success:
                result.steps[-1].thought += " [工具调用失败]"
                continue
            
            # 更新context
            context = self._update_context(context, tool_choice, observation)
            
            # 判断是否需要继续推理
            if self._is_sufficient(context, result.steps):
                break
        
        # 生成最终答案
        result.final_answer = self._generate_answer(agent_name, context, result.steps)
        result.confidence = self._calc_confidence(result.steps)
        result.agents_involved = self._extract_agents_involved(context)
        
        return result
    
    def _build_context(self, agent_name: str, query: str, history: List[dict]) -> dict:
        """构建推理上下文"""
        conn = get_db()
        context = {
            "query": query,
            "agent_name": agent_name,
            "date": date.today().isoformat(),
            "history": history or [],
        }
        
        # 预加载Agent领域数据
        conn.close()
        return context
    
    def _think(self, agent_name: str, context: dict, steps: List[ReActStep]) -> Tuple[str, Tool]:
        """思考：基于当前上下文决定使用哪个工具"""
        query = context.get("query", "").lower()
        
        # 如果已有足够数据，直接生成答案
        if len(steps) >= 2 and "rich_data" in context:
            return "已有足够数据，生成最终答案", Tool.CALCULATE
        
        # 基于关键词选择工具
        tool_thoughts = {
            Tool.QUERY_DB: f"需要查询数据库获取{agent_name}相关数据",
            Tool.SEARCH_KNOWLEDGE: "需要搜索知识库获取标准规范支撑",
            Tool.QUERY_AGENTS: f"需要向其他Agent求证{agent_name}领域外的信息",
            Tool.CHECK_RISKS: "需要检查潜在风险项",
            Tool.CALCULATE: "需要对已有数据进行统计分析",
        }
        
        # 优先使用Agent自己的工具偏好
        preferred = self.AGENT_TOOL_PREFERENCE.get(agent_name, [Tool.QUERY_DB])
        
        # 根据query内容选择最合适的工具
        if any(k in query for k in ["风险", "预警", "危险", "问题", "异常"]):
            return tool_thoughts[Tool.CHECK_RISKS], Tool.CHECK_RISKS
        elif any(k in query for k in ["标准", "规范", "法规", "制度", "依据", "查一下"]):
            return tool_thoughts[Tool.SEARCH_KNOWLEDGE], Tool.SEARCH_KNOWLEDGE
        elif any(k in query for k in ["和", "与", "协作", "让", "问问"] and "其他" in query):
            return tool_thoughts[Tool.QUERY_AGENTS], Tool.QUERY_AGENTS
        elif any(k in query for k in ["统计", "计算", "分析", "汇总", "对比", "趋势"]):
            return tool_thoughts[Tool.CALCULATE], Tool.CALCULATE
        elif preferred:
            return tool_thoughts[preferred[0]], preferred[0]
        else:
            return tool_thoughts[Tool.QUERY_DB], Tool.QUERY_DB
    
    def _prepare_tool_input(self, tool: Tool, context: dict, steps: List[ReActStep]) -> str:
        """准备工具输入参数"""
        query = context.get("query", "")
        if tool == Tool.QUERY_DB:
            return json.dumps({"table": "auto", "query_hint": query}, ensure_ascii=False)
        elif tool == Tool.SEARCH_KNOWLEDGE:
            return json.dumps({"query": query, "limit": 5}, ensure_ascii=False)
        elif tool == Tool.QUERY_AGENTS:
            return json.dumps({"question": query}, ensure_ascii=False)
        elif tool == Tool.CHECK_RISKS:
            return json.dumps({"types": ["project", "equipment", "qualification"]}, ensure_ascii=False)
        elif tool == Tool.CALCULATE:
            return json.dumps({"operation": "summary"}, ensure_ascii=False)
        return "{}"
    
    def _act(self, tool: Tool, tool_input: str, agent_name: str) -> Tuple[str, bool]:
        """执行工具调用"""
        try:
            params = json.loads(tool_input) if tool_input else {}
        except:
            params = {}
        
        if tool == Tool.QUERY_DB:
            return self._tool_query_db(params, agent_name)
        elif tool == Tool.SEARCH_KNOWLEDGE:
            return self._tool_search_knowledge(params, agent_name)
        elif tool == Tool.QUERY_AGENTS:
            return self._tool_query_agents(params, agent_name)
        elif tool == Tool.CHECK_RISKS:
            return self._tool_check_risks(params, agent_name)
        elif tool == Tool.CALCULATE:
            return self._tool_calculate(params, agent_name)
        
        return "未知工具调用", False
    
    def _tool_query_db(self, params: dict, agent_name: str) -> Tuple[str, bool]:
        """工具：查询数据库"""
        conn = get_db()
        result = []
        query_hint = params.get("query_hint", "")
        
        # 根据提示词自动判断查询哪些表
        tables_to_query = self._resolve_tables(query_hint, agent_name)
        
        for table in tables_to_query:
            try:
                rows = conn.execute(f"SELECT * FROM [{table}] LIMIT 20").fetchall()
                if rows:
                    result.append(f"[{table}] 共{len(rows)}条: {json.dumps([dict(r) for r in rows[:3]], ensure_ascii=False, default=str)}")
            except:
                pass
        
        conn.close()
        return json.dumps(result, ensure_ascii=False, default=str), len(result) > 0
    
    def _resolve_tables(self, query_hint: str, agent_name: str) -> List[str]:
        """根据查询提示和Agent角色解析需要查询的表"""
        hints = query_hint.lower()
        tables = set()
        
        # 通用表
        tables.add("projects")
        tables.add("staff")
        
        # 根据Agent角色添加表
        if agent_name in ["智管", "智财", "智项"]:
            tables.add("transactions")
            tables.add("contracts")
        if agent_name in ["智管", "智检", "智法", "智设"]:
            tables.add("equipment")
        if agent_name in ["智管", "智客"]:
            tables.add("customers")
        if agent_name in ["智管", "智仓"]:
            tables.add("materials")
            tables.add("procurement")
        if agent_name in ["智法", "智检"]:
            tables.add("qualifications")
        
        # 根据查询内容添加表
        if any(k in hints for k in ["检测", "报告", "标准"]):
            tables.add("inspections")
            tables.add("reports")
        if any(k in hints for k in ["资质", "证书", "检定"]):
            tables.add("qualifications")
        if any(k in hints for k in ["设备", "仪器"]):
            tables.add("equipment")
        if any(k in hints for k in ["财务", "收入", "支出", "成本"]):
            tables.add("transactions")
        if any(k in hints for k in ["客户", "合同"]):
            tables.add("customers")
            tables.add("contracts")
        if any(k in hints for k in ["库存", "材料", "采购"]):
            tables.add("materials")
            tables.add("procurement")
        
        return list(tables)
    
    def _tool_search_knowledge(self, params: dict, agent_name: str) -> Tuple[str, bool]:
        """工具：搜索知识库"""
        from .knowledge import KnowledgeRetriever
        retriever = KnowledgeRetriever()
        results = retriever.search(params.get("query", ""), limit=params.get("limit", 5))
        return json.dumps(results, ensure_ascii=False, default=str), len(results) > 0
    
    def _tool_query_agents(self, params: dict, agent_name: str) -> Tuple[str, bool]:
        """工具：查询其他Agent"""
        from .agents import AGENT_PROFILES
        other_agents = [a for a in AGENT_PROFILES.keys() if a != agent_name]
        return json.dumps({
            "available_agents": other_agents,
            "suggestion": f"可以向以下Agent求证: {', '.join(other_agents[:5])}"
        }, ensure_ascii=False), True
    
    def _tool_check_risks(self, params: dict, agent_name: str) -> Tuple[str, bool]:
        """工具：检查风险"""
        conn = get_db()
        risks = []
        
        # 项目风险
        try:
            projects = conn.execute("SELECT * FROM projects WHERE status IN ('active','report')").fetchall()
            today = date.today()
            for p in projects:
                p = dict(p)
                if p.get("risk") == "high":
                    risks.append(f"高风险项目: {p['name']} (进度{p['progress']}%)")
                end_date = p.get("end_date", "")
                if end_date:
                    days = (datetime.strptime(end_date, "%Y-%m-%d").date() - today).days
                    if 0 < days <= 14:
                        risks.append(f"临近截止: {p['name']} (剩余{days}天)")
                    elif days < 0:
                        risks.append(f"已超期: {p['name']} (逾期{-days}天)")
        except:
            pass
        
        # 设备风险
        try:
            equipment = conn.execute("SELECT * FROM equipment WHERE status='warning'").fetchall()
            for e in equipment:
                risks.append(f"设备预警: {e['name']} ({e.get('model', '')})")
        except:
            pass
        
        # 资质风险
        try:
            quals = conn.execute("SELECT * FROM qualifications WHERE status='active'").fetchall()
            today_str = date.today().isoformat()
            for q in quals:
                q = dict(q)
                if q.get("expiry_date") and q["expiry_date"] <= today_str:
                    risks.append(f"资质已过期: {q['name']} (到期{q['expiry_date']})")
                elif q.get("expiry_date") and q["expiry_date"] <= (today + timedelta(days=90)).isoformat():
                    days_left = (datetime.strptime(q["expiry_date"], "%Y-%m-%d").date() - today).days
                    risks.append(f"资质即将到期: {q['name']} (剩余{days_left}天)")
        except:
            pass
        
        conn.close()
        return json.dumps(risks, ensure_ascii=False), True
    
    def _tool_calculate(self, params: dict, agent_name: str) -> Tuple[str, bool]:
        """工具：统计分析"""
        conn = get_db()
        stats = {}
        
        try:
            stats["project_count"] = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            stats["active_projects"] = conn.execute("SELECT COUNT(*) FROM projects WHERE status IN ('active','report')").fetchone()[0]
            stats["staff_count"] = conn.execute("SELECT COUNT(*) FROM staff WHERE status='active'").fetchone()[0]
            stats["customer_count"] = conn.execute("SELECT COUNT(*) FROM customers WHERE status='active'").fetchone()[0]
            
            # 财务统计
            income = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income'").fetchone()[0]
            expense = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense'").fetchone()[0]
            stats["total_income_wan"] = round(income / 10000, 1)
            stats["total_expense_wan"] = round(expense / 10000, 1)
            stats["profit_wan"] = round((income - expense) / 10000, 1)
        except:
            pass
        
        conn.close()
        return json.dumps(stats, ensure_ascii=False), True
    
    def _update_context(self, context: dict, tool: Tool, observation: str) -> dict:
        """更新推理上下文"""
        if "data_store" not in context:
            context["data_store"] = {}
        context["data_store"][tool.value] = observation
        if tool in [Tool.QUERY_DB, Tool.CHECK_RISKS, Tool.CALCULATE]:
            context["rich_data"] = True
        return context
    
    def _is_sufficient(self, context: dict, steps: List[ReActStep]) -> bool:
        """判断是否有足够信息生成答案"""
        if "rich_data" in context:
            return True
        if len(steps) >= 3:
            return True
        return False
    
    def _generate_answer(self, agent_name: str, context: dict, steps: List[ReActStep]) -> str:
        """生成最终答案"""
        query = context.get("query", "")
        data_store = context.get("data_store", {})
        
        # 构建答案
        parts = []
        
        # 数据来源说明
        sources = []
        for step in steps:
            if step.success:
                sources.append(step.tool.value)
        if sources:
            parts.append(f"【分析依据】通过调用工具获取数据：{', '.join(set(sources))}")
        
        # 基于数据和查询生成回答
        if any(k in query.lower() for k in ["风险", "预警"]):
            risks = data_store.get(Tool.CHECK_RISKS.value, "")
            if risks:
                parts.append(f"【风险检查】{risks}")
            else:
                parts.append("【风险检查】当前无明显风险项")
        
        elif any(k in query.lower() for k in ["财务", "收入", "支出", "利润"]):
            calc = data_store.get(Tool.CALCULATE.value, "")
            if calc:
                parts.append(f"【财务分析】{calc}")
        
        elif any(k in query.lower() for k in ["概况", "简报", "汇总"]):
            calc = data_store.get(Tool.CALCULATE.value, "")
            if calc:
                parts.append(f"【经营概况】{calc}")
        
        elif any(k in query.lower() for k in ["标准", "规范", "法规", "制度"]):
            knowledge = data_store.get(Tool.SEARCH_KNOWLEDGE.value, "")
            if knowledge:
                parts.append(f"【知识检索】{knowledge}")
        
        else:
            # 综合回答
            summary_parts = []
            if Tool.QUERY_DB.value in data_store:
                summary_parts.append("已查询相关业务数据")
            if Tool.CHECK_RISKS.value in data_store:
                summary_parts.append("已完成风险检查")
            if Tool.SEARCH_KNOWLEDGE.value in data_store:
                summary_parts.append("已检索相关知识")
            
            if summary_parts:
                parts.append(f"【综合分析】{'；'.join(summary_parts)}。针对'{query}'，建议您关注上述数据的关联分析。")
            else:
                parts.append(f"已处理您的请求：'{query}'。如需更详细的分析，请提供具体方向。")
        
        return "\n\n".join(parts) if parts else "分析完成"
    
    def _calc_confidence(self, steps: List[ReActStep]) -> float:
        """计算回答置信度"""
        if not steps:
            return 0.1
        successful = sum(1 for s in steps if s.success)
        return min(1.0, successful / max(len(steps), 1))
    
    def _extract_agents_involved(self, context: dict) -> List[str]:
        """提取涉及的Agent"""
        return []  # 简化版，实际可扩展为跨Agent查询


def get_db():
    import sqlite3
    from pathlib import Path
    db_path = str(Path(__file__).parent.parent / "data" / "db" / "jianjian.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
