"""
Business catalog for the synthetic tenant "Sahyadri Retail" (a fictional Indian omnichannel retailer).

This single file is the source of truth for every dimension value. The data generator, the
no-code app metadata, the NLU lexicon and the eval corpus all read from here, so a value can
never exist in one layer and be missing from another.
"""
from datetime import date

TENANT_NAME = "Sahyadri Retail"
APP_NAME = "Lumen"  # the fictional no-code BI platform

DATA_START = date(2025, 1, 1)
DATA_END = date(2026, 9, 30)  # inclusive; "today" for the agent is DATA_END + 1 day

REGION_CITIES = {
    "North": ["Delhi", "Chandigarh", "Jaipur", "Lucknow"],
    "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi"],
    "East": ["Kolkata", "Bhubaneswar", "Patna"],
    "West": ["Mumbai", "Pune", "Ahmedabad", "Goa"],
    "Central": ["Bhopal", "Indore", "Nagpur"],
}
REGIONS = list(REGION_CITIES)
CITIES = [c for cs in REGION_CITIES.values() for c in cs]
CITY_REGION = {c: r for r, cs in REGION_CITIES.items() for c in cs}

# Each city is served by one distribution centre (warehouse)
CITY_WAREHOUSE = {
    "Delhi": "Delhi DC", "Chandigarh": "Delhi DC", "Jaipur": "Delhi DC", "Lucknow": "Delhi DC",
    "Chennai": "Chennai DC", "Kochi": "Chennai DC",
    "Bengaluru": "Bengaluru DC", "Hyderabad": "Bengaluru DC",
    "Kolkata": "Kolkata DC", "Bhubaneswar": "Kolkata DC", "Patna": "Kolkata DC",
    "Mumbai": "Mumbai DC", "Goa": "Mumbai DC",
    "Ahmedabad": "Ahmedabad DC", "Pune": "Ahmedabad DC",
    "Bhopal": "Nagpur DC", "Indore": "Nagpur DC", "Nagpur": "Nagpur DC",
}
WAREHOUSES = sorted(set(CITY_WAREHOUSE.values()))
WAREHOUSE_REGION = {w: CITY_REGION[c] for c, w in CITY_WAREHOUSE.items()}

CHANNELS = ["Online Store", "Mobile App", "Retail Stores", "Marketplace"]

CATEGORY_PRODUCTS = {
    "Electronics": ["Smartphones", "Laptops", "Headphones", "Smartwatches"],
    "Home & Kitchen": ["Cookware", "Small Appliances", "Furniture", "Home Decor"],
    "Fashion": ["Men's Apparel", "Women's Apparel", "Footwear", "Accessories"],
    "Grocery": ["Staples", "Snacks", "Beverages", "Personal Care"],
    "Beauty": ["Skincare", "Makeup", "Haircare", "Fragrances"],
    "Sports": ["Fitness Equipment", "Sportswear", "Outdoor Gear", "Cycles"],
}
CATEGORIES = list(CATEGORY_PRODUCTS)
PRODUCTS = [p for ps in CATEGORY_PRODUCTS.values() for p in ps]
PRODUCT_CATEGORY = {p: c for c, ps in CATEGORY_PRODUCTS.items() for p in ps}

SEGMENTS = ["New", "Regular", "Premium", "Corporate"]
CARRIERS = ["BlueDart", "Delhivery", "Ecom Express", "In-house Fleet"]
MKT_CHANNELS = ["Search Ads", "Social Media", "Email", "Affiliates", "TV"]
ISSUE_TYPES = ["Delivery Delay", "Damaged Item", "Refund", "Payment Issue", "Product Quality", "Account"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]

# Campaign calendar: (name, start, end)
CAMPAIGNS = [
    ("Republic Day Sale", date(2025, 1, 20), date(2025, 1, 31)),
    ("Holi Colours Fest", date(2025, 3, 5), date(2025, 3, 16)),
    ("Summer Sale", date(2025, 5, 1), date(2025, 5, 20)),
    ("Monsoon Deals", date(2025, 7, 1), date(2025, 7, 15)),
    ("Independence Day Sale", date(2025, 8, 8), date(2025, 8, 17)),
    ("Diwali Dhamaka", date(2025, 10, 5), date(2025, 10, 25)),
    ("Year End Bash", date(2025, 12, 15), date(2025, 12, 31)),
    ("Republic Day Sale 2026", date(2026, 1, 20), date(2026, 1, 31)),
    ("Spring Launch", date(2026, 3, 1), date(2026, 3, 31)),
    ("Summer Sale 2026", date(2026, 5, 1), date(2026, 5, 20)),
    ("Monsoon Deals 2026", date(2026, 7, 1), date(2026, 7, 15)),
    ("Back to School", date(2026, 8, 20), date(2026, 9, 10)),
]
CAMPAIGN_NAMES = [c[0] for c in CAMPAIGNS] + ["Always-On"]

# ---------------------------------------------------------------------------
# Synonyms: user vocabulary -> canonical value. Keys are lower-case.
# ---------------------------------------------------------------------------
VALUE_SYNONYMS = {
    "region": {
        "north india": "North", "northern": "North", "north zone": "North",
        "south india": "South", "southern": "South", "south zone": "South",
        "east india": "East", "eastern": "East", "east zone": "East",
        "west india": "West", "western": "West", "west zone": "West",
        "central india": "Central", "central zone": "Central",
    },
    "city": {
        "bangalore": "Bengaluru", "blr": "Bengaluru", "bengalore": "Bengaluru", "banglore": "Bengaluru",
        "bombay": "Mumbai", "madras": "Chennai", "calcutta": "Kolkata", "new delhi": "Delhi",
        "ncr": "Delhi", "hyd": "Hyderabad", "cochin": "Kochi", "poona": "Pune",
    },
    "channel": {
        "website": "Online Store", "web": "Online Store", "online": "Online Store", "e-commerce site": "Online Store",
        "web store": "Online Store", "app": "Mobile App", "mobile app": "Mobile App", "android app": "Mobile App",
        "ios app": "Mobile App", "stores": "Retail Stores", "store": "Retail Stores", "offline": "Retail Stores",
        "retail": "Retail Stores", "physical stores": "Retail Stores", "brick and mortar": "Retail Stores",
        "marketplaces": "Marketplace", "amazon": "Marketplace", "flipkart": "Marketplace", "third-party": "Marketplace",
    },
    "category": {
        "electronic": "Electronics", "gadgets": "Electronics", "consumer electronics": "Electronics",
        "home": "Home & Kitchen", "kitchen": "Home & Kitchen", "home and kitchen": "Home & Kitchen",
        "apparel": "Fashion", "clothing": "Fashion", "clothes": "Fashion",
        "groceries": "Grocery", "fmcg": "Grocery", "food": "Grocery",
        "cosmetics": "Beauty", "beauty products": "Beauty",
        "sport": "Sports", "sporting goods": "Sports", "fitness": "Sports",
    },
    "product": {
        "phones": "Smartphones", "mobiles": "Smartphones", "smartphone": "Smartphones", "mobile phones": "Smartphones",
        "laptop": "Laptops", "notebooks": "Laptops", "earphones": "Headphones", "headphone": "Headphones",
        "earbuds": "Headphones", "watches": "Smartwatches", "smartwatch": "Smartwatches",
        "appliances": "Small Appliances", "mens apparel": "Men's Apparel", "men's clothing": "Men's Apparel",
        "womens apparel": "Women's Apparel", "women's clothing": "Women's Apparel", "shoes": "Footwear",
        "perfumes": "Fragrances", "perfume": "Fragrances", "bicycles": "Cycles", "bikes": "Cycles",
        "gym equipment": "Fitness Equipment",
    },
    "segment": {
        "new customers": "New", "first-time": "New", "first time": "New", "repeat": "Regular",
        "regular customers": "Regular", "loyalty": "Premium", "vip": "Premium", "premium members": "Premium",
        "b2b": "Corporate", "enterprise": "Corporate", "business customers": "Corporate",
    },
    "warehouse": {
        "delhi warehouse": "Delhi DC", "chennai warehouse": "Chennai DC", "bengaluru warehouse": "Bengaluru DC",
        "bangalore dc": "Bengaluru DC", "bangalore warehouse": "Bengaluru DC", "kolkata warehouse": "Kolkata DC",
        "mumbai warehouse": "Mumbai DC", "ahmedabad warehouse": "Ahmedabad DC", "nagpur warehouse": "Nagpur DC",
    },
    "carrier": {"blue dart": "BlueDart", "ecom": "Ecom Express", "own fleet": "In-house Fleet", "inhouse": "In-house Fleet"},
    "mkt_channel": {
        "google ads": "Search Ads", "sem": "Search Ads", "search": "Search Ads", "social": "Social Media",
        "instagram": "Social Media", "facebook": "Social Media", "meta ads": "Social Media", "emails": "Email",
        "newsletter": "Email", "affiliate": "Affiliates", "television": "TV",
    },
    "issue_type": {
        "late delivery": "Delivery Delay", "delayed delivery": "Delivery Delay", "damaged": "Damaged Item",
        "refunds": "Refund", "payment": "Payment Issue", "payments": "Payment Issue", "quality": "Product Quality",
        "login": "Account",
    },
    "priority": {"urgent": "Critical", "p1": "Critical", "p2": "High", "p3": "Medium", "p4": "Low"},
    "campaign": {"diwali": "Diwali Dhamaka", "diwali sale": "Diwali Dhamaka", "spring": "Spring Launch",
                 "back-to-school": "Back to School"},
}

DIMENSION_VALUES = {
    "region": REGIONS,
    "city": CITIES,
    "channel": CHANNELS,
    "category": CATEGORIES,
    "product": PRODUCTS,
    "segment": SEGMENTS,
    "warehouse": WAREHOUSES,
    "carrier": CARRIERS,
    "mkt_channel": MKT_CHANNELS,
    "issue_type": ISSUE_TYPES,
    "priority": PRIORITIES,
    "campaign": CAMPAIGN_NAMES,
}

DIMENSION_LABELS = {
    "region": "Region", "city": "City", "channel": "Sales Channel", "category": "Category",
    "product": "Product", "segment": "Customer Segment", "warehouse": "Warehouse", "carrier": "Carrier",
    "mkt_channel": "Marketing Channel", "issue_type": "Issue Type", "priority": "Priority", "campaign": "Campaign",
}

# How users refer to a dimension when asking for a breakdown ("by city", "region-wise").
DIMENSION_SYNONYMS = {
    "region": ["region", "regions", "zone", "zones", "regionwise", "region-wise", "zone-wise"],
    "city": ["city", "cities", "citywise", "city-wise", "location", "locations"],
    "channel": ["channel", "channels", "sales channel", "sales channels", "channel-wise"],
    "category": ["category", "categories", "category-wise", "product category", "product categories"],
    "product": ["product", "products", "sku", "skus", "item", "items", "product-wise"],
    "segment": ["segment", "segments", "customer segment", "customer segments", "customer type", "cohort"],
    "warehouse": ["warehouse", "warehouses", "dc", "dcs", "distribution centre", "distribution center", "fulfilment centre"],
    "carrier": ["carrier", "carriers", "courier", "couriers", "logistics partner", "logistics partners"],
    "mkt_channel": ["marketing channel", "marketing channels", "ad channel", "ad channels", "media"],
    "issue_type": ["issue type", "issue types", "issue", "issues", "ticket type", "reason", "reasons"],
    "priority": ["priority", "priorities", "severity"],
    "campaign": ["campaign", "campaigns"],
}
