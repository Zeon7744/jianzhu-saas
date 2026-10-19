# -*- coding: utf-8 -*-
"""
数字巡检员 - 移动端拍照 → AI识别隐患 → 自动生成报告

核心场景：
  安全巡检：拍照上传 → AI识别安全隐患 → 生成整改报告
  质检评定：上传台账 → AI风险评分 → 预警推送
  材料验收：扫码录入 → 自动比对合同 → 异常告警

合规要求：
  - 巡检照片不存储原始图像，仅保留 AI 分析结果（7天自动清除）
  - 用户需授权数据采集（隐私协议弹窗）
  - AI 标注自动添加在报告页脚
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .ai_labeling import AILabelingEngine, AI_LABEL_FOOTER


class HazardType(str, Enum):
    """隐患类型枚举"""
    SAFETY_EQUIPMENT = "safety_equipment"      # 安全防护设备缺失
    ELECTRICAL_HAZARD = "electrical_hazard"    # 电气隐患
    STRUCTURE_ISSUE = "structure_issue"        # 结构问题
    FIRE_RISK = "fire_risk"                    # 消防风险
    VENTILATION = "ventilation"                # 通风问题
    OTHER = "other"                            # 其他


class RiskSeverity(str, Enum):
    """风险等级枚举"""
    CRITICAL = "critical"    # 严重
    HIGH = "high"            # 高危
    MEDIUM = "medium"        # 中危
    LOW = "low"              # 低危


@dataclass
class HazardRecord:
    """单条隐患记录"""
    record_id: str
    hazard_type: HazardType
    severity: RiskSeverity
    description: str
    location: str
    photo_ref: str           # 照片临时引用（不存原始图）
    detected_at: float = field(default_factory=time.time)
    suggested_fix: str = ""
    status: str = "pending"  # pending / fixed / ignored

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "hazard_type": self.hazard_type.value,
            "severity": self.risk_level.value,
            "description": self.description,
            "location": self.location,
            "photo_ref": self.photo_ref,
            "detected_at": self.detected_at,
            "suggested_fix": self.suggested_fix,
            "status": self.status,
        }


class DigitalInspectorTool:
    """
    数字巡检员工具类。

    模拟移动端拍照 → AI识别 → 报告生成的完整流程。
    支持安全巡检、质检评定、材料验收三个场景。
    """

    def __init__(self, project_id: str = ""):
        self.project_id = project_id or str(uuid.uuid4())[:8]
        self._hazards: List[HazardRecord] = []
        self._inspection_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 主入口：安全巡检（移动端拍照场景）
    # ------------------------------------------------------------------
    def inspect_safety(self, photo_ref: str, location: str = "",
                       notes: str = "") -> Dict[str, Any]:
        """
        安全巡检入口：模拟拍照上传后 AI 识别隐患。

        Args:
            photo_ref: 照片临时引用ID（不存原始图）
            location: 巡检位置
            notes: 人工备注

        Returns:
            巡检报告（含隐患列表 + 综合评分）
        """
        # 模拟 AI 识别结果（实际对接视觉模型）
        detected_hazards = self._simulate_ai_detection(photo_ref, location, notes)

        for h in detected_hazards:
            h.record_id = f"H-{uuid.uuid4().hex[:8]}"
            h.photo_ref = photo_ref
            self._hazards.append(h)

        report = self._build_report(detected_hazards)
        self._inspection_history.append(report)
        return report

    def _simulate_ai_detection(self, photo_ref: str, location: str,
                               notes: str) -> List[HazardRecord]:
        """
        模拟 AI 视觉识别结果。
        真实场景对接 CLIP / YOLO 等视觉模型。
        """
        # Mock: 根据 photo_ref 和 notes 返回不同的隐患组合
        seed = hash(photo_ref + notes) % 100
        if seed < 30:
            return [
                HazardRecord(
                    record_id="",
                    hazard_type=HazardType.SAFETY_EQUIPMENT,
                    severity=RiskSeverity.HIGH,
                    description="安全网缺失或破损",
                    location=location or "3层脚手架区域",
                    photo_ref=photo_ref,
                    suggested_fix="立即修补安全网，验收合格后方可继续施工",
                )
            ]
        elif seed < 60:
            return [
                HazardRecord(
                    record_id="",
                    hazard_type=HazardType.ELECTRICAL_HAZARD,
                    severity=RiskSeverity.CRITICAL,
                    description="临时用电线路裸露",
                    location=location or "配电房入口",
                    photo_ref=photo_ref,
                    suggested_fix="立即停止使用，联系电工规范整改",
                ),
                HazardRecord(
                    record_id="",
                    hazard_type=HazardType.FIRE_RISK,
                    severity=RiskSeverity.MEDIUM,
                    description="灭火器临近有效期",
                    location=location or "1层东侧走廊",
                    photo_ref=photo_ref,
                    suggested_fix="更换有效期内灭火器",
                ),
            ]
        else:
            return [
                HazardRecord(
                    record_id="",
                    hazard_type=HazardType.STRUCTURE_ISSUE,
                    severity=RiskSeverity.LOW,
                    description="模板支撑轻微倾斜",
                    location=location or "B区5层梁板",
                    photo_ref=photo_ref,
                    suggested_fix="加固支撑体系，复测垂直度",
                )
            ]

    # ------------------------------------------------------------------
    # 质检评定
    # ------------------------------------------------------------------
    def risk_score(self) -> Dict[str, Any]:
        """计算当前项目风险综合评分（0-100，越低越危险）"""
        if not self._hazards:
            return {"score": 100, "level": "safe", "message": "暂无巡检记录"}

        severity_weights = {
            RiskSeverity.CRITICAL: 40,
            RiskSeverity.HIGH: 25,
            RiskSeverity.MEDIUM: 15,
            RiskSeverity.LOW: 5,
        }
        total_penalty = sum(
            severity_weights.get(h.severity, 0)
            for h in self._hazards
            if h.status == "pending"
        )
        score = max(0, 100 - total_penalty)
        level = "safe" if score >= 70 else ("warning" if score >= 40 else "danger")
        return {
            "score": score,
            "level": level,
            "total_hazards": len(self._hazards),
            "pending": sum(1 for h in self._hazards if h.status == "pending"),
            "message": self._level_message(level),
        }

    @staticmethod
    def _level_message(level: str) -> str:
        return {
            "safe": "当前项目风险等级：安全，建议继续保持",
            "warning": "当前项目风险等级：警告，请尽快处理 pending 隐患",
            "danger": "当前项目风险等级：危险，请立即安排整改！",
        }.get(level, "未知等级")

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------
    def _build_report(self, hazards: List[HazardRecord]) -> Dict[str, Any]:
        """生成巡检报告（含 AI 标注页脚）"""
        return {
            "report_id": f"RPT-{uuid.uuid4().hex[:8]}",
            "project_id": self.project_id,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_hazards": len(hazards),
            "by_severity": {
                s.value: sum(1 for h in hazards if h.severity == s)
                for s in RiskSeverity
            },
            "hazards": [h.to_dict() for h in hazards],
            "ai_footer": AI_LABEL_FOOTER,
        }

    def list_all_hazards(self) -> List[Dict[str, Any]]:
        """列出所有历史隐患记录"""
        return [h.to_dict() for h in self._hazards]

    def fix_hazard(self, record_id: str) -> bool:
        """标记隐患为已修复"""
        for h in self._hazards:
            if h.record_id == record_id:
                h.status = "fixed"
                return True
        return False
