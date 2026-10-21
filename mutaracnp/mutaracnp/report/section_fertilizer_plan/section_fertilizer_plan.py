import frappe
from frappe.utils import flt
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

    programme = frappe.get_doc("Fertilizer Programme", programme_name)
    return label_products(get_columns(), get_data(programme, filters))


def get_columns():
    return [
        {"label": "Section",        "fieldname": "section",       "fieldtype": "Link",  "options": "Section", "width": 220},
        {"label": "Product",        "fieldname": "product",       "fieldtype": "Link",  "options": "Item",    "width": 120},
        {"label": "Month",          "fieldname": "month",         "fieldtype": "Data",  "width": 100},
        {"label": "Blocks",         "fieldname": "block_count",   "fieldtype": "Int",   "width": 80},
        {"label": "Area (Ha)",      "fieldname": "area_ha",       "fieldtype": "Float", "width": 100},
        {"label": "Rate (Kg/Ha)",   "fieldname": "kg_per_ha",     "fieldtype": "Float", "width": 110},
        {"label": "Total Kg",       "fieldname": "total_kg",      "fieldtype": "Float", "width": 120},
    ]


def get_data(programme, filters):
    area_by_block = {row.block: flt(row.area_ha) for row in programme.get("block_yield_data", [])}

    # (section, product, month) -> {total_kg, blocks: set()}
    groups = {}
    for line in programme.get("programme_lines", []):
        if filters.get("section") and line.section != filters["section"]:
            continue
        if filters.get("fertilizer_product") and line.fertilizer_product != filters["fertilizer_product"]:
            continue

        key = (line.section, line.fertilizer_product, line.application_month)
        group = groups.setdefault(key, {"total_kg": 0, "blocks": set()})
        group["total_kg"] += flt(line.total_kg)
        group["blocks"].add(line.block)

    rows = []
    for (section, product, month), group in groups.items():
        area_ha = sum(area_by_block.get(b, 0) for b in group["blocks"])
        rows.append({
            "section":     section,
            "product":     product,
            "month":       month,
            "block_count": len(group["blocks"]),
            "area_ha":     round(area_ha, 2),
            "kg_per_ha":   round(group["total_kg"] / area_ha, 2) if area_ha else 0,
            "total_kg":    round(group["total_kg"], 2),
            "_month_idx":  MONTH_ORDER.index(month) if month in MONTH_ORDER else 99,
        })

    rows.sort(key=lambda r: (r["section"], r["product"], r["_month_idx"]))
    for r in rows:
        del r["_month_idx"]

    return rows
