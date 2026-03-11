"""
config.py — إعدادات الأقسام (Tiers)
كل قسم له: اسم، حد رأس المال، Lot افتراضي
"""

# تعريف الأقسام بالترتيب (min_capital بالدولار)
TIERS = {
    1: {"name": "🥉 Tier 1",  "label": "tier_1",  "min": 0,    "max": 99,    "default_lot": 0.01},
    2: {"name": "🥈 Tier 2",  "label": "tier_2",  "min": 100,  "max": 499,   "default_lot": 0.02},
    3: {"name": "🥇 Tier 3",  "label": "tier_3",  "min": 500,  "max": 999,   "default_lot": 0.05},
    4: {"name": "💎 Tier 4",  "label": "tier_4",  "min": 1000, "max": 1499,  "default_lot": 0.10},
    5: {"name": "👑 Tier 5",  "label": "tier_5",  "min": 1500, "max": 2999,  "default_lot": 0.15},
    6: {"name": "🚀 Tier 6",  "label": "tier_6",  "min": 3000, "max": 999999,"default_lot": 0.30},
}

TIER_DESCRIPTIONS = {
    1: "50$ – 99$",
    2: "100$ – 499$",
    3: "500$ – 999$",
    4: "1,000$ – 1,499$",
    5: "1,500$ – 2,999$",
    6: "3,000$+",
}


def get_tier_by_capital(capital: float) -> int:
    """إرجاع رقم القسم بناءً على رأس المال"""
    for tier_num, tier in TIERS.items():
        if tier["min"] <= capital <= tier["max"]:
            return tier_num
    return 1  # افتراضي


def get_tier_info(tier_num: int) -> dict:
    return TIERS.get(tier_num, TIERS[1])
