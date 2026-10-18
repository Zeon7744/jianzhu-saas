"""
企业版 Agent 模块
从 jianzhu-agent 合并而来，提供企业级智能分析能力
"""
from .react_agent import ReActAgent, ReActStep, ReActResult
from .brain import AgentBrain
from .knowledge import KnowledgeBase
from .collaboration import AgentCollaboration
from .agents import (
    ZhiGuanAgent, ZhiCaiAgent, ZhiXiangAgent, ZhiJianAgent,
    ZhiAnAgent, ZhiShiAgent, create_agent
)

__all__ = [
    "ReActAgent", "ReActStep", "ReActResult",
    "AgentBrain", "KnowledgeBase", "AgentCollaboration",
    "ZhiGuanAgent", "ZhiCaiAgent", "ZhiXiangAgent", "ZhiJianAgent",
    "ZhiAnAgent", "ZhiShiAgent", "create_agent",
]
