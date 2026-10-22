"""
收款网关子包：显式导出各网关类，供 billing.py 统一注册。
（补 __init__.py 让 `billing.gateway` 成为正规包，import 不再被静默吞掉）
"""
from .bufpay import BufPayGateway

__all__ = ["BufPayGateway"]
