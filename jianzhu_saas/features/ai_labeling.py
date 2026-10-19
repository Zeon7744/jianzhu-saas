# -*- coding: utf-8 -*-
"""
AI内容标注引擎 - 合规标注与页脚生成

根据《互联网信息服务深度合成管理规定》及各大平台规则，
为 AI 生成内容自动添加合规标识。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Dict, List, Optional


class Platform(str, Enum):
    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    XIAOHONGSHU = "xiaohongshu"
    YOUTUBE = "youtube"
    WECHAT = "wechat"


# 各平台要求的 AI 标注文本
PLATFORM_LABELS: Dict[Platform, str] = {
    Platform.DOUYIN: "本内容由AI辅助生成",
    Platform.BILIBILI: "AI生成内容，仅供参考",
    Platform.XIAOHONGSHU: "本文部分内容由AI辅助创作",
    Platform.YOUTUBE: "Altered or synthetic content",
    Platform.WECHAT: "本内容含AI生成元素",
}

# 通用合规页脚模板
AI_LABEL_FOOTER = """\
──────────────────────────────
【AI生成内容声明】
本内容部分或全部由人工智能生成，不构成专业建议。
依据《互联网信息服务深度合成管理规定》第17条，
已对AI生成内容进行显著标识。
生成时间：{timestamp}
──────────────────────────────
"""


class AILabelingEngine:
    """
    AI内容标注引擎。

    功能：
    - 为文本/报告自动添加AI标识
    - 校验内容是否满足各平台标注要求
    - 生成合规页脚
    """

    def __init__(self, platforms: Optional[List[Platform]] = None):
        self.platforms = platforms or list(Platform)
        self._label_count: int = 0

    def add_label(self, content: str) -> str:
        """在内容末尾追加AI标注"""
        footer = AI_LABEL_FOOTER.format(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        self._label_count += 1
        return content.rstrip() + "\n\n" + footer

    def check_compliance(self, content: str,
                         target_platform: Platform) -> Dict[str, Any]:
        """
        检查内容是否满足指定平台的AI标注要求。

        Returns:
            {passed: bool, issues: [...], suggestion: str}
        """
        required_label = PLATFORM_LABELS.get(target_platform, "")
        has_label = required_label in content or "AI" in content or "人工智能" in content

        issues: List[str] = []
        if not has_label:
            issues.append(f"内容未包含'{required_label}'标识")

        return {
            "platform": target_platform.value,
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestion": f"请在内容中添加标注：{required_label}",
        }

    def generate_footer(self, platforms: Optional[List[Platform]] = None) -> str:
        """生成多平台合规页脚"""
        plats = platforms or self.platforms
        lines = ["──────────────────────────────", "【AI生成内容声明】"]
        lines.append("本内容部分或全部由人工智能生成，仅供参考。")
        lines.append("依据《互联网信息服务深度合成管理规定》第17条，")
        lines.append("已对AI生成内容进行显著标识。")
        for p in plats:
            lines.append(f"  • {p.value}: {PLATFORM_LABELS[p]}")
        lines.append(f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("──────────────────────────────")
        return "\n".join(lines)

    @property
    def label_count(self) -> int:
        """已标注内容数量（用于审计）"""
        return self._label_count
