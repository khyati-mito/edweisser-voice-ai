# Small, static, illustrative dataset grounded in the real categories/bundles listed
# on edelweissmf.com as of Sept 2026. This is NOT live scheme/NAV data -- it exists
# only so the chatbot recommends from a fixed, real-sounding catalog instead of
# inventing fund names.

FUND_CATEGORIES = [
    {
        "name": "Equity Funds",
        "description": "Invest predominantly in equity and equity-related instruments; higher risk, higher long-term growth potential.",
        "risk": "high",
        "horizon": "long (5+ years)",
    },
    {
        "name": "Hybrid Funds",
        "description": "Mix of equity and debt; moderate risk, balanced growth and stability.",
        "risk": "medium",
        "horizon": "medium (3-5 years)",
    },
    {
        "name": "Debt Funds",
        "description": "Invest in fixed-income instruments; lower risk, stable but modest returns.",
        "risk": "low",
        "horizon": "short-medium (1-3 years)",
    },
    {
        "name": "Equity Index Funds/ETFs",
        "description": "Passively track an equity index at low cost.",
        "risk": "high",
        "horizon": "long (5+ years)",
    },
    {
        "name": "Debt Index Funds/ETFs",
        "description": "Passively track a debt index at low cost.",
        "risk": "low",
        "horizon": "short-medium (1-3 years)",
    },
    {
        "name": "Target Maturity Funds",
        "description": "Debt funds with a fixed maturity date, useful for goal-based investing with a known time horizon.",
        "risk": "low-medium",
        "horizon": "matches target date",
    },
    {
        "name": "Precious Metals",
        "description": "Gold/silver-linked funds, used for diversification and as a hedge.",
        "risk": "medium",
        "horizon": "any, as a diversifier",
    },
]

GOAL_BUNDLES = [
    {"name": "Pehli SIP", "goal": "first-time investor starting a small regular SIP", "risk": "low-medium"},
    {"name": "Minor Money Box", "goal": "building a fund for a child's future/education", "risk": "medium"},
    {"name": "Retirement Box", "goal": "long-term retirement corpus building", "risk": "medium-high"},
    {"name": "Market Cap Champs", "goal": "wealth creation diversified across market caps", "risk": "high"},
    {"name": "Low-Cost Equity", "goal": "cost-conscious long-term equity exposure via index funds", "risk": "high"},
    {"name": "Gold-Equity-Debt", "goal": "diversified portfolio combining gold, equity and debt", "risk": "medium"},
]

SAMPLE_SCHEMES = [
    {
        "name": "Edelweiss Mid Cap Fund",
        "category": "Equity Funds",
        "description": "Open-ended equity scheme predominantly investing in mid cap stocks.",
        "risk": "high",
    },
    {
        "name": "Altiva Equity EX-Top 100 Long-Short Fund",
        "category": "Equity Funds",
        "description": "Open-ended equity strategy investing in equity and equity-related instruments, including limited short exposure via derivatives, ex-top 100 stocks.",
        "risk": "high",
    },
]

DISCLAIMER = (
    "This is an illustrative demo recommendation based on a small sample dataset, "
    "not live scheme data and not registered investment advice. Please consult a "
    "SEBI-registered mutual fund distributor or investment advisor, and read the "
    "Scheme Information Document, before investing."
)


def catalog_as_context() -> str:
    lines = ["Fund categories:"]
    for c in FUND_CATEGORIES:
        lines.append(f"- {c['name']}: {c['description']} (risk: {c['risk']}, horizon: {c['horizon']})")
    lines.append("\nGoal-based bundles:")
    for b in GOAL_BUNDLES:
        lines.append(f"- {b['name']}: for {b['goal']} (risk: {b['risk']})")
    lines.append("\nSample named schemes:")
    for s in SAMPLE_SCHEMES:
        lines.append(f"- {s['name']} ({s['category']}): {s['description']} (risk: {s['risk']})")
    return "\n".join(lines)
