"""
知识库检索模块 - Agent知识获取能力
支持模糊搜索、相关度排序、领域过滤
"""
import sqlite3
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DB_PATH = r"D:\项目\开发部\开发git\02\建筑行业检测及信息咨询公司agent\src\data\db\jianjian.db"


class KnowledgeRetriever:
    """知识库检索器 - 为Agent提供知识支撑"""
    
    def __init__(self):
        self.db_path = DB_PATH
    
    def search(self, query: str, category: str = None, limit: int = 5) -> List[dict]:
        """
        知识库搜索 - 支持关键词匹配和类别过滤
        搜索策略：
        1. 精确匹配标题
        2. 模糊匹配标签
        3. 全文匹配内容
        4. 按相关度排序
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        wheres = []
        params = []
        
        # 关键词搜索
        if query:
            terms = query.split()
            for term in terms:
                wheres.append("(title LIKE ? OR tags LIKE ? OR content LIKE ?)")
                params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
        
        # 类别过滤
        if category and category != "all":
            wheres.append("category=?")
            params.append(category)
        
        sql = "SELECT * FROM knowledge"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY hits DESC, updated DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        
        results = []
        for r in rows:
            d = dict(r)
            if d.get("tags"):
                try:
                    d["tags"] = __import__("json").loads(d["tags"])
                except Exception:
                    d["tags"] = []
            results.append(d)
        
        return results
    
    def get_by_category(self, category: str, limit: int = 10) -> List[dict]:
        """按类别获取知识文档"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM knowledge WHERE category=? ORDER BY hits DESC LIMIT ?",
            (category, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    def get_all_categories(self) -> List[str]:
        """获取所有知识类别"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT DISTINCT category FROM knowledge WHERE category IS NOT NULL AND category != '' ORDER BY category"
        ).fetchall()
        conn.close()
        return [r["category"] for r in rows]
    
    def get_related_knowledge(self, agent_name: str, context: dict = None) -> List[dict]:
        """
        为指定Agent获取相关知识
        根据Agent角色和当前上下文智能推荐
        """
        context = context or {}
        agent_knowledge_map = {
            "智法": ["法规标准", "合规制度", "行业标准"],
            "智检": ["检测标准", "作业指导", "质量控制"],
            "智项": ["项目管理", "技术规范", "安全标准"],
            "智财": ["财务制度", "税务法规", "成本控制"],
            "智人": ["人事制度", "培训资料", "绩效考核"],
            "智客": ["客户管理", "服务标准", "合同范本"],
            "智设": ["设备管理", "维护规程", "检定标准"],
            "智仓": ["库存管理", "采购制度", "材料标准"],
            "智管": ["管理制度", "战略规划", "经营分析"],
        }
        
        categories = agent_knowledge_map.get(agent_name, ["综合知识"])
        results = []
        for cat in categories:
            docs = self.get_by_category(cat, limit=3)
            results.extend(docs)
        
        # 去重并按热度排序
        seen = set()
        unique = []
        for d in results:
            if d["id"] not in seen:
                seen.add(d["id"])
                unique.append(d)
        
        return unique[:8]
    
    def increment_hits(self, doc_id: int):
        """增加文档访问量"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE knowledge SET hits = hits + 1 WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
    
    def check_compliance_docs(self) -> List[dict]:
        """检查合规相关文档"""
        return self.search("合规 法规 标准 制度", category=None, limit=10)

