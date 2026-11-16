"""
Shared settings for the whole project: which brands we track, where reviews
come from, and the fixed list of themes Claude will tag reviews with.

Keeping the theme list fixed (instead of letting the AI invent new labels
every week) is what makes week-to-week comparison possible.
"""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Two separate datasets that never mix:
#   real   (default)  real public reviews        -> data/real/,  reports/
#   sample            fictional test reviews     -> data/,       reports/sample/
# Choose with an environment variable, e.g.  WPI_DATASET=sample python src/build_report.py
DATASET = os.environ.get("WPI_DATASET", "real")
if DATASET == "sample":
    DATA_DIR = PROJECT_DIR / "data"
    REPORTS_DIR = PROJECT_DIR / "reports" / "sample"
else:
    DATA_DIR = PROJECT_DIR / "data" / "real"
    REPORTS_DIR = PROJECT_DIR / "reports"
DATA_DIR.mkdir(parents=True, exist_ok=True)

REVIEWS_CSV = DATA_DIR / "reviews.csv"          # all collected reviews
DB_PATH = Path(os.environ.get("WPI_DB", DATA_DIR / "insights.sqlite"))  # analysis results

# Where real reviews come from. Trustpilot pages per brand (checked Nov 2026).
# Sportstech (DE) is a broad home-fitness brand that also sells walking pads; its
# page covers the whole shop, so it is a delivery/service benchmark for Germany.
# Decathlon is not here: its Trustpilot page is about the whole store, not walking pads.
TRUSTPILOT_DOMAINS = {
    "moov":       ["moovmore.com"],
    "walkingpad": ["walkingpad.com", "uk.walkingpad.com", "fr.walkingpad.com"],
    "merach":     ["merachfit.eu", "merachfit.de", "uk.merachfit.com", "fr.merachfit.com"],
    "sportstech": ["sportstech.de"],
    "urevo":      ["urevo.com"],
    "sperax":     ["sperax.com"],
}

# Only reviewers from these countries are used (Europe incl. UK), so competitors
# are compared on the same market as Moov. Country = what the reviewer set on Trustpilot.
EUROPE = {
    "AL", "AD", "AT", "BA", "BE", "BG", "BY", "CH", "CY", "CZ", "DE", "DK", "EE", "ES",
    "FI", "FO", "FR", "GB", "GI", "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU",
    "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO", "RS", "SE", "SI",
    "SK", "SM", "UA", "VA", "XK",
}

# --- Brands -----------------------------------------------------------------
# "key" is used in files; "name" is what the dashboard shows.
BRANDS = [
    {"key": "moov",       "name": "Moov",                  "is_focus": True},
    {"key": "walkingpad", "name": "WalkingPad (KingSmith)", "is_focus": False},
    {"key": "merach",     "name": "Merach",                "is_focus": False},
    {"key": "sportstech", "name": "Sportstech",            "is_focus": False},
    {"key": "urevo",      "name": "UREVO",                 "is_focus": False},
    {"key": "sperax",     "name": "Sperax",                "is_focus": False},
    {"key": "decathlon",  "name": "Decathlon",             "is_focus": False},
]
BRAND_NAMES = {b["key"]: b["name"] for b in BRANDS}

# --- Review sources ----------------------------------------------------------
# Trustpilot reviews talk about the COMPANY (delivery, service, refunds).
# Marketplace / product-page reviews talk about the PRODUCT (noise, motor, belt).
SOURCES = {
    "trustpilot": "Trustpilot (company reviews)",
    "amazon":     "Amazon (product reviews)",
    "decathlon":  "Decathlon.nl/.de (product reviews)",
}

# --- Theme taxonomy -----------------------------------------------------------
# Three groups, matching the brief: why people buy, what hurts after purchase,
# and what delights them after purchase.
THEMES = {
    "purchase_driver": {
        "compact_size":     "Compact / fits under desk / small home",
        "quiet_motor":      "Quiet enough for home or calls",
        "price_value":      "Price / value for money",
        "design_look":      "Looks good in the living room / office",
        "work_from_home":   "Move more while working from home",
        "brand_trust":      "Trusted brand / good reviews before buying",
        "app_features":     "App, remote, step tracking",
    },
    "pain_point": {
        "delivery_delay":        "Delivery took longer than promised",
        "preorder_communication":"Pre-order: unclear or changing dates, little updates",
        "damaged_in_transit":    "Arrived damaged / missing parts",
        "assembly_setup":        "Hard to set up / unclear manual",
        "noise":                 "Too noisy / squeaking",
        "durability":            "Broke down / motor or belt failure within months",
        "app_connectivity":      "App or remote does not connect",
        "returns_refunds":       "Difficult or slow returns / refunds",
        "warranty_claims":       "Warranty claim slow or refused",
        "customer_service":      "Customer service slow, unreachable or unhelpful",
    },
    "delight": {
        "daily_habit":       "Became a daily habit / more steps",
        "quiet_while_working": "Can walk during calls / work",
        "easy_to_store":     "Easy to move and store away",
        "helpful_support":   "Support solved a problem quickly and kindly",
        "fast_delivery":     "Arrived quickly / smooth delivery",
        "build_quality":     "Feels solid, well made",
    },
}

THEME_GROUP_LABELS = {
    "purchase_driver": "Purchase drivers",
    "pain_point": "Post-purchase pain points",
    "delight": "Post-purchase delight",
}


def all_theme_keys():
    return [k for group in THEMES.values() for k in group]


def theme_group(theme_key):
    for group, themes in THEMES.items():
        if theme_key in themes:
            return group
    return None


# --- Customer journey of a walking pad buyer ---------------------------------
# Every theme belongs to one stage after the order button. Purchase drivers
# ("why they buy") come before the order and are shown separately.
JOURNEY = [
    {"key": "order",    "name": "Order & wait",          "themes": ["preorder_communication", "delivery_delay", "fast_delivery"]},
    {"key": "delivery", "name": "Delivery & condition",  "themes": ["damaged_in_transit"]},
    {"key": "setup",    "name": "Unbox & set up",        "themes": ["assembly_setup"]},
    {"key": "use",      "name": "First weeks of use",    "themes": ["noise", "app_connectivity", "daily_habit",
                                                                    "quiet_while_working", "easy_to_store", "build_quality"]},
    {"key": "service",  "name": "Customer service",      "themes": ["customer_service", "helpful_support"]},
    {"key": "after",    "name": "Returns & warranty",    "themes": ["durability", "returns_refunds", "warranty_claims"]},
]
STAGE_OF = {t: s["key"] for s in JOURNEY for t in s["themes"]}

# Who would own the cause of each problem in a team like the one in the
# vacancy (roles, not people). Used by the Problem Vault prototype.
PROBLEM_OWNER = {
    "preorder_communication": "CX Lead + E-commerce (order status)",
    "delivery_delay":         "Supply chain",
    "damaged_in_transit":     "Supply chain (carriers, packaging)",
    "assembly_setup":         "Product (manual, quick start)",
    "noise":                  "Product",
    "durability":             "Product (quality)",
    "app_connectivity":       "Product (app)",
    "returns_refunds":        "CX Lead + Product",
    "warranty_claims":        "CX Lead + Product",
    "customer_service":       "CX Lead",
}

# A brand needs at least this many reviews in the period to be compared.
MIN_REVIEWS = 30
