"""
7天试用期管理器
- 首次登录自动开启7天试用
- Day 4 发送提醒邮件（可选）
- Day 7 自动降级为免费版
- 保留试用期间数据
"""
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path


class TrialManager:
    """试用期管理"""
    
    TRIAL_DAYS = 7
    REMINDER_DAY = 4
    
    def __init__(self, storage_path="."):
        self.storage = Path(storage_path) / ".trial_data.json"
        self._data = self._load()
    
    def _load(self):
        if self.storage.exists():
            try:
                return json.loads(self.storage.read_text())
            except:
                return {}
        return {}
    
    def _save(self):
        self.storage.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
    
    def start_trial(self, tenant_id):
        """开始试用期"""
        if tenant_id in self._data:
            return self.get_status(tenant_id)
        
        now = time.time()
        self._data[tenant_id] = {
            "start_time": now,
            "end_time": now + self.TRIAL_DAYS * 86400,
            "reminder_sent": False,
            "downgraded": False,
            "status": "trial",
        }
        self._save()
        return self.get_status(tenant_id)
    
    def get_status(self, tenant_id):
        """获取试用状态"""
        info = self._data.get(tenant_id)
        if not info:
            return {
                "tenant_id": tenant_id,
                "status": "free",
                "days_left": None,
                "has_trial": False,
            }
        
        now = time.time()
        end_time = info.get("end_time", 0)
        days_left = max(0, int((end_time - now) / 86400))
        is_expired = now > end_time
        
        # 自动降级
        if is_expired and not info.get("downgraded"):
            self._data[tenant_id]["status"] = "free"
            self._data[tenant_id]["downgraded"] = True
            self._save()
        
        return {
            "tenant_id": tenant_id,
            "status": info.get("status", "free"),
            "has_trial": True,
            "days_left": days_left,
            "reminder_due": days_left <= (self.TRIAL_DAYS - self.REMINDER_DAY),
            "expired": is_expired,
        }
    
    def check_reminder(self, tenant_id, send_func=None):
        """检查是否需要发送提醒"""
        info = self._data.get(tenant_id)
        if not info:
            return False
        
        now = time.time()
        days_left = int((info.get("end_time", 0) - now) / 86400)
        
        # Day 4 发送提醒（剩余3天）
        if days_left == 3 and not info.get("reminder_sent"):
            self._data[tenant_id]["reminder_sent"] = True
            self._save()
            
            if send_func:
                send_func(tenant_id)
            return True
        
        return False
    
    def list_all(self):
        """列出所有试用用户"""
        result = []
        for tid, info in self._data.items():
            now = time.time()
            days_left = max(0, int((info.get("end_time", 0) - now) / 86400))
            result.append({
                "tenant_id": tid,
                "days_left": days_left,
                "status": info.get("status"),
            })
        return sorted(result, key=lambda x: x["days_left"])
    
    def cleanup_expired(self, days=30):
        """清理过期的试用记录（保留30天）"""
        cutoff = time.time() - days * 86400
        to_remove = [tid for tid, info in self._data.items() 
                     if info.get("end_time", 0) < cutoff]
        for tid in to_remove:
            del self._data[tid]
        self._save()
        return len(to_remove)


# 全局单例
_trial_manager = None

def get_trial_manager(storage_path="."):
    global _trial_manager
    if _trial_manager is None:
        _trial_manager = TrialManager(storage_path)
    return _trial_manager
