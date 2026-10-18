"""
Agent推理引擎 - 基于真实数据的智能分析
每个Agent根据自身领域查询数据库，生成分析报告和建议
"""
import sqlite3
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

DB_PATH = r"D:\项目\开发部\开发git\02\建筑行业检测及信息咨询公司agent\src\data\db\jianjian.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class AgentBrain:
    """Agent推理引擎 - 核心分析能力"""
    
    # 各Agent的分析模板和关注指标
    ANALYSIS_TEMPLATES = {
        "智管": {
            "keywords": ["经营", "概况", "简报", "分析", "汇总", "整体", "全局", "业绩"],
            "queries": ["dashboard", "business"],
        },
        "智财": {
            "keywords": ["财务", "收入", "支出", "利润", "成本", "预算", "收款", "付款", "账", "资金", "税务", "发票", "报销", "结算"],
            "queries": ["finance"],
        },
        "智项": {
            "keywords": ["项目", "进度", "工期", "节点", "延期", "风险", "计划", "安排", "验收", "竣工", "交付", "变更"],
            "queries": ["projects"],
        },
        "智检": {
            "keywords": ["检测", "报告", "标准", "质量", "合格", "不合格", "试验", "样品", "鉴定", "评估", "验收", "无损检测", "强度", "承载力"],
            "queries": ["inspections", "reports"],
        },
        "智人": {
            "keywords": ["人员", "员工", "招聘", "培训", "证书", "到期", "排班", "绩效", "考勤"],
            "queries": ["staff"],
        },
        "智客": {
            "keywords": ["客户", "商机", "回访", "满意度", "跟进", "合同", "签约"],
            "queries": ["customers", "contracts"],
        },
        "智法": {
            "keywords": ["合规", "法规", "标准", "资质", "检定", "证书", "审查", "风险", "预警", "许可证", "备案", "年审", "抽检"],
            "queries": ["compliance", "equipment"],
        },
        "智设": {
            "keywords": ["设备", "检定", "维护", "保养", "故障", "校准", "巡检"],
            "queries": ["equipment"],
        },
        "智仓": {
            "keywords": ["库存", "采购", "耗材", "材料", "仓库", "补货", "物资", "供应商", "到货", "质检"],
            "queries": ["materials", "procurement"],
        },
        "智装": {
            "keywords": ["装修", "装饰", "设计", "施工", "材料", "工艺", "验收", "环保", "甲醛", "涂料", "地板", "防水", "防火", "隔声", "精装", "毛坯"],
            "queries": ["projects", "materials", "inspections"],
        },
        "智咨": {
            "keywords": ["咨询", "政策", "市场", "分析", "方案", "评估", "可行性", "标准", "法规", "招投标", "造价", "监理", "报建", "审批"],
            "queries": ["knowledge", "projects", "customers"],
        },
    }
    
    def analyze(self, agent_name: str, query: str, context: dict = None) -> dict:
        """
        核心推理方法：根据Agent角色和查询内容，结合实时数据生成分析结果
        推理流程：意图识别 -> 数据查询 -> 模式匹配 -> 结论生成 -> 建议输出
        """
        context = context or {}
        conn = get_db()
        
        # Step 1: 意图识别 - 确定用户想要什么
        intent = self._recognize_intent(query, agent_name)
        
        # Step 2: 数据采集 - 从数据库获取相关数据
        data = self._collect_data(conn, agent_name, intent, context)
        
        # Step 3: 模式识别 - 检测异常、趋势、风险
        patterns = self._detect_patterns(agent_name, data)
        
        # Step 4: 结论生成 - 基于数据和模式生成分析结论
        conclusion = self._generate_conclusion(agent_name, intent, data, patterns)
        
        # Step 5: 建议输出 - 生成可操作的建议
        suggestions = self._generate_suggestions(agent_name, intent, data, patterns)
        
        conn.close()
        
        return {
            "agent": agent_name,
            "intent": intent,
            "summary": conclusion,
            "risks": patterns.get("risks", []),
            "opportunities": patterns.get("opportunities", []),
            "suggestions": suggestions,
            "data_points": patterns.get("metrics", {}),
            "raw_data": self._sanitize_for_response(data),
        }
    
    def _recognize_intent(self, query: str, agent_name: str) -> str:
        """意图识别 - 分析用户查询的意图"""
        query_lower = query.lower()
        
        # 关键词匹配
        if any(k in query_lower for k in ["你好", "在吗", "help", "帮助"]):
            return "greeting"
        if any(k in query_lower for k in ["日报", "今日", "今天"]):
            return "daily_report"
        if any(k in query_lower for k in ["周报", "本周", "这周"]):
            return "weekly_report"
        if any(k in query_lower for k in ["月报", "本月", "这个月"]):
            return "monthly_report"
        if any(k in query_lower for k in ["风险", "预警", "危险", "问题"]):
            return "risk_analysis"
        if any(k in query_lower for k in ["建议", "怎么办", "怎么处理", "如何应对"]):
            return "recommendation"
        if any(k in query_lower for k in ["统计", "汇总", "概况", "情况"]):
            return "overview"
        if any(k in query_lower for k in ["对比", "比较", "差异", "变化"]):
            return "comparison"
        if any(k in query_lower for k in ["预测", "预计", "趋势", "走向"]):
            return "forecast"
        if any(k in query_lower for k in ["为什么", "原因", "为何", "怎么"]):
            return "explanation"
        
        # 基于Agent角色推断
        templates = self.ANALYSIS_TEMPLATES.get(agent_name, {})
        for keyword in templates.get("keywords", []):
            if keyword in query_lower:
                return f"{agent_name}_{keyword}"
        
        return "general_query"
    
    def _collect_data(self, conn, agent_name: str, intent: str, context: dict) -> dict:
        """数据采集 - 根据Agent角色收集相关数据"""
        data = {}
        
        try:
            # 通用数据
            data["today"] = date.today().isoformat()
            data["week_start"] = (date.today() - timedelta(days=date.today().weekday())).isoformat()
            data["month_start"] = date.today().replace(day=1).isoformat()
            
            # 按Agent角色采集数据
            if agent_name in ["智管", "智项"]:
                data["projects"] = self._fetch_projects(conn)
                data["inspections"] = self._fetch_inspections(conn)
            
            if agent_name in ["智管", "智财"]:
                data["transactions"] = self._fetch_transactions(conn)
                data["contracts"] = self._fetch_contracts(conn)
            
            if agent_name in ["智管", "智检"]:
                data["reports"] = self._fetch_reports(conn)
            
            if agent_name in ["智管", "智人"]:
                data["staff"] = self._fetch_staff(conn)
            
            if agent_name in ["智管", "智客"]:
                data["customers"] = self._fetch_customers(conn)
            
            if agent_name in ["智管", "智法", "智设"]:
                data["equipment"] = self._fetch_equipment(conn)
            
            if agent_name in ["智管", "智仓"]:
                data["materials"] = self._fetch_materials(conn)
                data["procurement"] = self._fetch_procurement(conn)
            
            if agent_name in ["智法", "智检"]:
                data["knowledge"] = self._fetch_knowledge(conn)
            
            # Intent-specific数据补充
            if intent == "daily_report":
                data.update(self._daily_snapshot(conn))
            elif intent == "risk_analysis":
                data.update(self._risk_assessment(conn, agent_name))
            elif intent == "monthly_report":
                data.update(self._monthly_snapshot(conn))
                
        except Exception as e:
            data["error"] = str(e)
        
        return data
    
    def _detect_patterns(self, agent_name: str, data: dict) -> dict:
        """模式识别 - 检测异常、趋势和风险"""
        patterns = {"risks": [], "opportunities": [], "metrics": {}}
        
        # 项目风险检测
        if "projects" in data:
            for p in data["projects"]:
                if p["risk"] == "high":
                    patterns["risks"].append(f"高风险项目：{p['name']}（进度{p['progress']}%）")
                if p["status"] in ["active", "report"]:
                    end_date = p.get("end_date", "")
                    if end_date:
                        days_left = (datetime.strptime(end_date, "%Y-%m-%d").date() - date.today()).days
                        if 0 < days_left <= 14:
                            patterns["risks"].append(f"项目临近截止：{p['name']}（剩余{days_left}天）")
                        elif days_left < 0:
                            patterns["risks"].append(f"项目已超期：{p['name']}（逾期{-days_left}天）")
        
        # 财务风险检测
        if "transactions" in data:
            income = sum(t["amount"] for t in data["transactions"] if t["type"] == "income")
            expense = sum(t["amount"] for t in data["transactions"] if t["type"] == "expense")
            ar = sum(t["amount"] for t in data["transactions"] if t["type"] == "income" and t["status"] == "pending")
            patterns["metrics"]["total_income"] = round(income / 10000, 1)
            patterns["metrics"]["total_expense"] = round(expense / 10000, 1)
            patterns["metrics"]["ar_amount"] = round(ar / 10000, 1)
            if ar > 0:
                patterns["risks"].append(f"应收账款 {ar/10000:.1f}万元待收回")
        
        # 设备风险检测
        if "equipment" in data:
            for e in data["equipment"]:
                if e["status"] == "warning":
                    patterns["risks"].append(f"设备预警：{e['name']}（{e.get('cert_status', '')}）")
                cert_due = e.get("cert_due", "")
                if cert_due:
                    days = (datetime.strptime(cert_due, "%Y-%m-%d").date() - date.today()).days
                    if 0 < days <= 30:
                        patterns["risks"].append(f"设备检定即将到期：{e['name']}（{days}天）")
        
        # 库存风险检测
        if "materials" in data:
            for m in data["materials"]:
                if m["stock"] <= m.get("min_stock", 0):
                    patterns["risks"].append(f"库存不足：{m['name']}（当前{m['stock']}，最低{m['min_stock']}）")
        
        # 商机检测
        if "customers" in data:
            active_customers = [c for c in data["customers"] if c["status"] == "active" and c.get("amount", 0) > 0]
            patterns["opportunities"] = [f"{c['name']} - 合作金额{c['amount']/10000:.1f}万" for c in active_customers[:3]]
        
        # 合规检测
        if "knowledge" in data:
            compliance_docs = [k for k in data["knowledge"] if k.get("category") in ["法规标准", "合规制度"]]
            if compliance_docs:
                patterns["opportunities"].append(f"最新{len(compliance_docs)}条合规文档待学习")
        
        return patterns
    
    def _generate_conclusion(self, agent_name: str, intent: str, data: dict, patterns: dict) -> str:
        """结论生成 - 基于数据生成分析结论"""
        if intent == "greeting":
            return f"我是{AGENT_PROFILES.get(agent_name, {}).get('name', agent_name)}，{AGENT_PROFILES.get(agent_name, {}).get('desc', '随时为您服务')}。请问有什么可以帮您？"
        
        if intent == "daily_report":
            return self._daily_conclusion(data, patterns)
        
        if intent == "risk_analysis":
            return self._risk_conclusion(data, patterns)
        
        if intent == "overview":
            return self._overview_conclusion(agent_name, data, patterns)
        
        # 默认结论
        return self._default_conclusion(agent_name, data, patterns, intent)
    
    def _generate_suggestions(self, agent_name: str, intent: str, data: dict, patterns: dict) -> List[str]:
        """建议生成 - 基于分析结果生成可操作建议"""
        suggestions = []
        
        # 风险类建议
        for risk in patterns.get("risks", []):
            if "高风险" in risk:
                suggestions.append(f"建议立即召开专题会议，制定风险应对方案")
            elif "临近截止" in risk or "超期" in risk:
                suggestions.append(f"建议增加资源投入，确保按时完成")
            elif "应收账款" in risk:
                suggestions.append(f"建议本周安排专人跟进回款，必要时启动催收程序")
            elif "检定即将到期" in risk:
                suggestions.append(f"建议立即安排送检，避免影响正常检测工作")
            elif "库存不足" in risk:
                suggestions.append(f"建议立即发起采购申请，补充库存")
        
        # 机会类建议
        for opp in patterns.get("opportunities", []):
            suggestions.append(f"建议把握机会：{opp}")
        
        # 通用建议
        if intent == "monthly_report" or intent == "weekly_report":
            suggestions.append("建议下周继续跟踪各项指标执行情况")
        
        if not suggestions:
            suggestions.append("建议持续关注业务动态，及时发现问题并调整策略")
        
        return suggestions[:5]  # 最多5条建议
    
    def _daily_conclusion(self, data: dict, patterns: dict) -> str:
        """每日简报结论"""
        lines = []
        projects = data.get("projects", [])
        active = [p for p in projects if p["status"] in ["active", "report"]]
        lines.append(f"今日经营概况：共{len(projects)}个项目，其中{len(active)}个在进行中")
        
        if patterns.get("risks"):
            lines.append(f"⚠️ 发现{len(patterns['risks'])}项风险需关注：{'；'.join(patterns['risks'][:3])}")
        
        if "transactions" in data:
            income = sum(t["amount"] for t in data["transactions"] if t["type"] == "income")
            lines.append(f"💰 累计收入{income/10000:.1f}万元")
        
        return " ".join(lines)
    
    def _risk_conclusion(self, data: dict, patterns: dict) -> str:
        """风险分析结论"""
        if not patterns.get("risks"):
            return "✅ 当前无明显风险，各项指标运行正常"
        
        risk_count = len(patterns["risks"])
        lines = [f"⚠️ 检测到{risk_count}项风险："]
        for r in patterns["risks"][:5]:
            lines.append(f"  - {r}")
        return "\n".join(lines)
    
    def _overview_conclusion(self, agent_name: str, data: dict, patterns: dict) -> str:
        """概览结论"""
        role_info = AGENT_PROFILES.get(agent_name, {})
        lines = [f"【{role_info.get('name', agent_name)}】业务概览："]
        
        if agent_name in ["智管", "智项"] and "projects" in data:
            total = len(data["projects"])
            active = len([p for p in data["projects"] if p["status"] in ["active", "report"]])
            completed = len([p for p in data["projects"] if p["status"] == "completed"])
            lines.append(f"  项目：总计{total}个，进行中{active}个，已完成{completed}个")
        
        if agent_name in ["智管", "智财"] and "transactions" in data:
            inc = sum(t["amount"] for t in data["transactions"] if t["type"] == "income")
            exp = sum(t["amount"] for t in data["transactions"] if t["type"] == "expense")
            lines.append(f"  财务：收入{inc/10000:.1f}万，支出{exp/10000:.1f}万")
        
        if agent_name in ["智管", "智检"] and "reports" in data:
            total_r = len(data["reports"])
            completed_r = len([r for r in data["reports"] if r["status"] == "completed"])
            lines.append(f"  报告：总计{total_r}份，已完成{completed_r}份")
        
        if agent_name in ["智管", "智人"] and "staff" in data:
            total_s = len(data["staff"])
            lines.append(f"  人员：在职{total_s}人")
        
        if agent_name in ["智管", "智客"] and "customers" in data:
            lines.append(f"  客户：{len(data['customers'])}家")
        
        return "\n".join(lines)
    
    def _default_conclusion(self, agent_name: str, data: dict, patterns: dict, intent: str) -> str:
        """默认结论"""
        parts = [f"关于\"{intent}\"的分析："]
        
        # 添加关键数据点
        metrics = patterns.get("metrics", {})
        if metrics:
            parts.append(f"关键指标：{json.dumps(metrics, ensure_ascii=False)}")
        
        # 添加风险
        if patterns.get("risks"):
            parts.append(f"风险提示：{'; '.join(patterns['risks'][:3])}")
        
        return " ".join(parts)
    
    def _daily_snapshot(self, conn) -> dict:
        """每日快照"""
        today = date.today().isoformat()
        week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        
        projects = conn.execute("SELECT * FROM projects WHERE status IN ('active','report')").fetchall()
        inspections = conn.execute("SELECT * FROM inspections WHERE status NOT IN ('completed','cancelled')").fetchall()
        transactions = conn.execute("SELECT * FROM transactions WHERE date >= ?", (week_start,)).fetchall()
        
        week_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        week_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
        
        return {
            "daily_projects": len(projects),
            "daily_inspections": len(inspections),
            "week_income": week_income,
            "week_expense": week_expense,
        }
    
    def _risk_assessment(self, conn, agent_name: str) -> dict:
        """风险评估"""
        risks = {}
        
        # 项目风险
        high_risk = conn.execute("SELECT * FROM projects WHERE risk='high'").fetchall()
        if high_risk:
            risks["project_high"] = [{"id": r["id"], "name": r["name"]} for r in high_risk]
        
        # 设备风险
        warning_equip = conn.execute("SELECT * FROM equipment WHERE status='warning'").fetchall()
        if warning_equip:
            risks["equipment_warning"] = [{"id": e["id"], "name": e["name"], "cert_due": e["cert_due"]} for e in warning_equip]
        
        # 库存风险
        low_stock = conn.execute("SELECT * FROM materials WHERE stock <= min_stock").fetchall()
        if low_stock:
            risks["material_low_stock"] = [{"id": m["id"], "name": m["name"], "stock": m["stock"]} for m in low_stock]
        
        # 应收账款
        ar = conn.execute("SELECT SUM(amount) as total FROM transactions WHERE type='income' AND status='pending'").fetchone()
        if ar and ar["total"] and ar["total"] > 0:
            risks["accounts_receivable"] = {"amount": ar["total"]}
        
        return risks
    
    def _monthly_snapshot(self, conn) -> dict:
        """月度快照"""
        month_start = date.today().replace(day=1).isoformat()
        
        transactions = conn.execute("SELECT * FROM transactions WHERE date >= ?", (month_start,)).fetchall()
        contracts = conn.execute("SELECT * FROM contracts WHERE sign_date >= ? OR created_at >= ?", (month_start, month_start)).fetchall()
        
        month_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        month_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
        
        return {
            "month_income": month_income,
            "month_expense": month_expense,
            "month_profit": month_income - month_expense,
            "new_contracts": len(contracts),
        }
    
    # ========== 数据查询方法 ==========
    def _fetch_projects(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()]
    
    def _fetch_inspections(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM inspections ORDER BY created_at DESC").fetchall()]
    
    def _fetch_transactions(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY date DESC").fetchall()]
    
    def _fetch_contracts(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM contracts ORDER BY sign_date DESC").fetchall()]
    
    def _fetch_reports(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()]
    
    def _fetch_staff(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM staff WHERE status='active' ORDER BY id").fetchall()]
    
    def _fetch_customers(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM customers WHERE status='active' ORDER BY amount DESC").fetchall()]
    
    def _fetch_equipment(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM equipment ORDER BY id").fetchall()]
    
    def _fetch_materials(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM materials ORDER BY id").fetchall()]
    
    def _fetch_procurement(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM procurement ORDER BY order_date DESC").fetchall()]
    
    def _fetch_knowledge(self, conn) -> List[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM knowledge ORDER BY updated DESC LIMIT 20").fetchall()]
    
    def _sanitize_for_response(self, data: dict) -> dict:
        """清理数据用于响应（移除敏感信息）"""
        sanitized = {}
        for k, v in data.items():
            if isinstance(v, list):
                sanitized[k] = [dict(row) if hasattr(row, 'keys') else row for row in v[:10]]
            elif isinstance(v, dict):
                sanitized[k] = {kk: vv for kk, vv in v.items() if kk != "password"}
            else:
                sanitized[k] = v
        return sanitized


from .agents import AGENT_PROFILES


