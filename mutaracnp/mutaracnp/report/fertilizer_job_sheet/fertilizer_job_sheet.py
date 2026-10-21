import frappe
from mutaracnp.mutaracnp.utils.product_labels import label_products

MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def execute(filters=None):
    filters = filters or {}
    programme_name = filters.get("fertilizer_programme")
    if not programme_name:
        frappe.throw("Please select a Fertilizer Programme")

    return label_products(get_columns(), get_data(filters))


def get_columns():
    return [
        {"label": "Section",       "fieldname": "section",              "fieldtype": "Link",  "options": "Section",    "width": 220},
        {"label": "Product",       "fieldname": "fertilizer_product",   "fieldtype": "Link",  "options": "Item",       "width": 100},
        {"label": "Month",         "fieldname": "application_month",    "fieldtype": "Data",  "width": 100},
        {"label": "Block",         "fieldname": "block",                "fieldtype": "Link",  "options": "Farm Block", "width": 120},
        {"label": "Rate (Kg/Ha)",  "fieldname": "application_rate_kg_ha","fieldtype": "Float", "width": 100},
        {"label": "Total Kg",      "fieldname": "total_kg_required",    "fieldtype": "Float", "width": 100},
        {"label": "Tree Count",    "fieldname": "tree_count",           "fieldtype": "Int",   "width": 90},
        {"label": "Dose/Tree (g)", "fieldname": "dose_per_tree_g",      "fieldtype": "Float", "width": 100},
        {"label": "Status",        "fieldname": "status",               "fieldtype": "Data",  "width": 90},
        {"label": "Job",           "fieldname": "name",                 "fieldtype": "Link",  "options": "Block Fertilizer Plan", "width": 220},
    ]


def get_data(filters):
    conditions = {"docstatus": 1, "fertilizer_programme": filters["fertilizer_programme"]}
    if filters.get("section"):
        conditions["section"] = filters["section"]
    if filters.get("fertilizer_product"):
        conditions["fertilizer_product"] = filters["fertilizer_product"]
    if filters.get("application_month"):
        conditions["application_month"] = filters["application_month"]
    if filters.get("status"):
        conditions["status"] = filters["status"]

    rows = frappe.get_all(
        "Block Fertilizer Plan",
        filters=conditions,
        fields=[
            "name", "section", "fertilizer_product", "application_month", "block",
            "application_rate_kg_ha", "total_kg_required", "tree_count",
            "dose_per_tree_g", "status",
        ],
    )

    for r in rows:
        r["_month_idx"] = MONTH_ORDER.index(r["application_month"]) if r["application_month"] in MONTH_ORDER else 99

    rows.sort(key=lambda r: (r["section"] or "", r["fertilizer_product"], r["_month_idx"], r["block"]))
    for r in rows:
        del r["_month_idx"]

    return rows
