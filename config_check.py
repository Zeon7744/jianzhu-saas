"""
配置校验脚本：启动前检查必要环境变量是否已配。
用法：python config_check.py [gateway_name]
示例：
  python config_check.py              # 检查当前 JZ_SAAS_BILLING_GATEWAY
  python config_check.py aishouqian   # 强制检查爱收钱配置
"""
import os
import sys


# 各网关所需的环境变量
REQUIRED_ENVS = {
    "noop": [],
    "aishouqian": [
        "JZ_AISHOUQIAN_MCH_NO",
        "JZ_AISHOUQIAN_TOKEN",
        "JZ_AISHOUQIAN_APPID",
    ],
    "wepay": [
        "JZ_WXPAY_MCHID",
        "JZ_WXPAY_APPID",
        "JZ_WXPAY_API_KEY",
        "JZ_WXPAY_SERIAL_NO",
        "JZ_WXPAY_PRIVATE_KEY",
    ],
}

# 可选但建议配置
RECOMMENDED_ENVS = {
    "JZ_JWT_SECRET": "JWT 签名密钥（生产环境必须修改）",
    "JZ_WXPAY_NOTIFY_URL": "微信支付回调地址（使用 wepay 时必需）",
}


def check_gateway(gateway_name):
    """检查指定网关的配置完整性。"""
    print(f"\n{'='*50}")
    print(f"检查网关: {gateway_name}")
    print(f"{'='*50}")

    if gateway_name not in REQUIRED_ENVS:
        print(f"❌ 未知网关: {gateway_name}")
        print(f"   可选值: {', '.join(REQUIRED_ENVS.keys())}")
        return False

    required = REQUIRED_ENVS[gateway_name]
    if not required:
        print(f"✅ {gateway_name} 无需额外配置")
        return True

    missing = []
    configured = []
    for env_name in required:
        value = os.environ.get(env_name)
        if value:
            # 不打印值，只标记已配置
            configured.append(env_name)
        else:
            missing.append(env_name)

    if configured:
        print(f"\n✅ 已配置 ({len(configured)}/{len(required)}):")
        for name in configured:
            print(f"   ✓ {name}")

    if missing:
        print(f"\n❌ 缺失 ({len(missing)}/{len(required)}):")
        for name in missing:
            print(f"   ✗ {name}")
        print(f"\n💡 请在 .env 文件中配置以上变量，或导出到环境变量")
        return False

    print(f"\n✅ {gateway_name} 配置完整！")
    return True


def check_recommended():
    """检查可选但建议配置的环境变量。"""
    print(f"\n{'='*50}")
    print("检查推荐配置")
    print(f"{'='*50}")

    warnings = []
    for env_name, description in RECOMMENDED_ENVS.items():
        value = os.environ.get(env_name)
        if not value:
            warnings.append((env_name, description))
        else:
            # 特殊检查：JWT 密钥是否使用了默认值
            if env_name == "JZ_JWT_SECRET" and value == "change-me-in-production":
                warnings.append((env_name, "⚠️ 使用了默认值，生产环境必须修改！"))
            else:
                print(f"   ✓ {env_name}")

    if warnings:
        print(f"\n⚠️ 建议配置 ({len(warnings)}):")
        for name, desc in warnings:
            print(f"   ! {name}: {desc}")

    return len(warnings) == 0


def main():
    # 确定要检查的网关
    if len(sys.argv) > 1:
        gateway_name = sys.argv[1]
    else:
        gateway_name = os.environ.get("JZ_SAAS_BILLING_GATEWAY", "noop")

    print(f"\njianzhu-saas 配置校验")
    print(f"当前网关: {gateway_name}")

    # 检查必需配置
    gateway_ok = check_gateway(gateway_name)

    # 检查推荐配置
    recommended_ok = check_recommended()

    # 汇总
    print(f"\n{'='*50}")
    print("校验结果")
    print(f"{'='*50}")

    if gateway_ok and recommended_ok:
        print("✅ 所有配置检查通过！可以启动服务。")
        return 0
    elif gateway_ok:
        print("⚠️ 网关配置通过，但有推荐配置未设置。可以启动，但建议完善。")
        return 0
    else:
        print("❌ 必需配置缺失，无法启动网关。请先配置环境变量。")
        print("\n💡 快速开始：")
        print("   1. 复制模板: cp .env.example .env")
        print("   2. 编辑 .env 填入真实值")
        print("   3. 重新运行此脚本检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
