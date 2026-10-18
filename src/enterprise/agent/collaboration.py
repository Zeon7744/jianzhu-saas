"""
Agent协作通信模块
实现分布式Agent之间的消息传递、任务协调和信息交换
"""
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class MessageType(str, Enum):
    RISK_ALERT = "risk_alert"          # 风险警报
    OPPORTUNITY = "opportunity"        # 商机通知
    RESOURCE_REQUEST = "resource_request"  # 资源请求
    COMPLIANCE_ISSUE = "compliance_issue"  # 合规问题
    COMPLETION_NOTICE = "completion_notice"  # 完成通知
    QUERY_FORWARD = "query_forward"    # 查询转发
    COLLABORATION_REQUEST = "collaboration_request"  # 协作请求


@dataclass
class AgentMessage:
    """Agent间通信消息"""
    msg_id: str
    msg_type: MessageType
    sender: str
    content: str
    priority: str  # high, normal, low
    timestamp: str
    recipients: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    reply_to: Optional[str] = None
    status: str = "sent"  # sent, delivered, replied


class AgentMessageBus:
    """Agent消息总线 - 分布式通信基础设施"""
    
    def __init__(self):
        self._messages: List[AgentMessage] = []
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._msg_counter = 0
    
    def _gen_msg_id(self) -> str:
        self._msg_counter += 1
        return f"MSG{int(time.time())}{self._msg_counter:04d}"
    
    def publish(self, sender: str, msg_type: MessageType, content: str, 
                priority: str = "normal", metadata: dict = None,
                recipients: List[str] = None) -> AgentMessage:
        """发布消息到总线"""
        with self._lock:
            msg = AgentMessage(
                msg_id=self._gen_msg_id(),
                msg_type=msg_type,
                sender=sender,
                content=content,
                priority=priority,
                timestamp=datetime.now().isoformat(),
                recipients=recipients or [],
                metadata=metadata or {},
            )
            self._messages.append(msg)
        
        # 触发订阅者
        self._notify(msg)
        return msg
    
    def subscribe(self, agent_name: str, handler: Callable):
        """注册消息处理函数"""
        with self._lock:
            if agent_name not in self._handlers:
                self._handlers[agent_name] = []
            self._handlers[agent_name].append(handler)
    
    def _notify(self, msg: AgentMessage):
        """通知相关Agent"""
        with self._lock:
            handlers = []
            if msg.msg_type in self._handlers:
                handlers.extend(self._handlers[msg.msg_type])
            if msg.sender in self._handlers:
                handlers.extend(self._handlers[msg.sender])
            # 广播给所有订阅者
            for agent_name, h_list in self._handlers.items():
                if agent_name != msg.sender:
                    handlers.extend(h_list)
            
            for handler in handlers:
                try:
                    handler(msg)
                except Exception:
                    pass
    
    def get_messages(self, sender: str = None, msg_type: str = None, 
                     limit: int = 50) -> List[dict]:
        """获取消息列表"""
        with self._lock:
            msgs = self._messages
            if sender:
                msgs = [m for m in msgs if m.sender == sender]
            if msg_type:
                msgs = [m for m in msgs if m.msg_type == msg_type]
            return [
                {
                    "id": m.msg_id,
                    "type": m.msg_type.value,
                    "sender": m.sender,
                    "content": m.content,
                    "priority": m.priority,
                    "timestamp": m.timestamp,
                    "status": m.status,
                    "recipients": m.recipients,
                }
                for m in msgs[-limit:]
            ]
    
    def get_agent_history(self, agent_name: str, limit: int = 20) -> List[dict]:
        """获取指定Agent的消息历史"""
        return self.get_messages(sender=agent_name, limit=limit)
    
    def get_active_agents(self) -> List[str]:
        """获取活跃Agent列表"""
        return list(self._handlers.keys())


# 全局消息总线实例
agent_message_bus = AgentMessageBus()


class AgentCollaborator:
    """Agent协作管理器 - 协调多Agent联合分析"""
    
    def __init__(self, brain):
        self.brain = brain
        self.bus = agent_message_bus
    
    def collaborative_analysis(self, query: str, primary_agent: str, 
                                include_agents: List[str] = None) -> dict:
        """
        协作分析：主Agent发起，协同多个Agent共同分析
        流程：主Agent分析 -> 发现问题 -> 转发相关Agent -> 汇总结果
        """
        from .agents import get_collaborators
        
        # Step 1: 主Agent分析
        primary_result = self.brain.analyze(primary_agent, query)
        
        # Step 2: 识别需要协作的Agent
        collaborators = []
        if include_agents:
            collaborators = include_agents
        else:
            # 根据主Agent的协作关系自动选择
            possible = get_collaborators(primary_agent)
            # 基于风险发现选择相关Agent
            risks = primary_result.get("risks", [])
            for risk in risks:
                if "设备" in risk or "检定" in risk:
                    if "智设" in possible:
                        collaborators.append("智设")
                elif "库存" in risk or "采购" in risk:
                    if "智仓" in possible:
                        collaborators.append("智仓")
                elif "合规" in risk or "法规" in risk:
                    if "智法" in possible:
                        collaborators.append("智法")
                elif "客户" in risk or "商机" in risk:
                    if "智客" in possible:
                        collaborators.append("智客")
                elif "人员" in risk or "证书" in risk:
                    if "智人" in possible:
                        collaborators.append("智人")
        
        # Step 3: 向协作Agent转发
        collaboration_results = []
        for coll_agent in collaborators[:3]:  # 最多3个协作方
            try:
                # 发送协作请求
                self.bus.publish(
                    sender=primary_agent,
                    msg_type=MessageType.COLLABORATION_REQUEST,
                    content=f"请协助分析：{query}",
                    priority="normal",
                    metadata={"original_agent": primary_agent, "query": query},
                    recipients=[coll_agent],
                )
                
                # 协作Agent独立分析
                coll_result = self.brain.analyze(coll_agent, query)
                collaboration_results.append({
                    "agent": coll_agent,
                    "result": coll_result,
                })
            except Exception as e:
                collaboration_results.append({
                    "agent": coll_agent,
                    "error": str(e),
                })
        
        # Step 4: 汇总结果
        all_suggestions = primary_result.get("suggestions", [])
        all_risks = primary_result.get("risks", [])
        all_opportunities = primary_result.get("opportunities", [])
        
        for cr in collaboration_results:
            if "result" in cr:
                all_suggestions.extend(cr["result"].get("suggestions", []))
                all_risks.extend(cr["result"].get("risks", []))
                all_opportunities.extend(cr["result"].get("opportunities", []))
        
        return {
            "primary_agent": primary_agent,
            "collaborators": [cr["agent"] for cr in collaboration_results],
            "primary_result": primary_result,
            "collaboration_results": collaboration_results,
            "summary": self._merge_summary(primary_result, collaboration_results),
            "all_risks": list(set(all_risks)),
            "all_suggestions": list(set(all_suggestions))[:5],
            "all_opportunities": list(set(all_opportunities)),
        }
    
    def _merge_summary(self, primary: dict, collaborations: list) -> str:
        """合并多Agent分析结果"""
        lines = [primary.get("summary", "")]
        for cr in collaborations:
            if "result" in cr:
                agent_name = cr["agent"]
                summary = cr["result"].get("summary", "")
                if summary:
                    lines.append(f"[{agent_name}补充] {summary}")
        return "\n\n".join(lines)
    
    def proactive_alert(self, alert_type: str, content: str, 
                        severity: str = "normal") -> dict:
        """主动预警 - 系统检测到问题后自动通知相关Agent"""
        from .agents import get_message_recipients
        
        msg_type = MessageType.RISK_ALERT
        if "商机" in content or "机会" in content:
            msg_type = MessageType.OPPORTUNITY
        elif "合规" in content or "法规" in content:
            msg_type = MessageType.COMPLIANCE_ISSUE
        
        recipients = get_message_recipients(alert_type)
        
        msg = self.bus.publish(
            sender="SYSTEM",
            msg_type=msg_type,
            content=content,
            priority=severity,
            metadata={"alert_type": alert_type},
            recipients=recipients,
        )
        
        return {
            "message_id": msg.msg_id,
            "recipients": msg.recipients,
            "status": "published",
        }


# 启动时自动注册默认消息处理器
def _default_message_handler(msg: AgentMessage):
    """默认消息处理：记录到agent_logs表"""
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "db" / "jianjian.db"
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO agent_logs (agent, action, content, result, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg.sender, msg.msg_type.value, msg.content[:200], 
             f" forwarded to {msg.recipients}", msg.timestamp)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

agent_message_bus.subscribe("SYSTEM", _default_message_handler)

