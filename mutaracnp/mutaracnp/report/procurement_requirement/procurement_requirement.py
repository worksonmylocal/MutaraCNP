import frappe
from frappe.utils import flt
import math
from mutaracnp.mutaracnp.utils.product_labels import label_products


def execute(filters=None):
    filters = filters or {}
    return label_products(get_columns(), get_data(filters))


def get_columns():
    return [
        {"label": "Fertilizer Product", "fieldname": "product",      "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Season Total (Kg)",  "fieldname": "total_kg",     "fieldtype": "Float", "width": 150},
        {"label": "Stock On Hand (Kg)", "fieldname": "stock_kg",     "fieldtype": "Float", "width": 150},
        {"label": "Shortfall (Kg)",     "fieldname": "shortfall_kg", "fieldtype": "Float", "width": 140},
        {"label": "Order Qty (Rounded)","fieldname": "order_qty",    "fieldtype": "Float", "width": 150},
        {"label": "First Required",     "fieldname": "first_month",  "fieldtype": "Data",  "width": 130},
    ]


def get_data(filters):
    programme_name = filters.get("fertilizer_programme")
    if not programme_name:
        frappe.throw("Please select a Fertilizer Programme")

    programme = frappe.get_doc("Fertilizer Programme", programme_name)
    warehouse = frappe.db.get_value("CNP Farm", programme.farm, "warehouse") if programme.farm else None
    bag_sizes = get_bag_sizes(programme.crop)

    # Aggregate requirements per product
    requirements = {}
    for line in programme.get("programme_lines", []):
        product = line.fertilizer_product
        if product not in requirements:
            requirements[product] = {"total_kg": 0, "first_month": line.application_month}
        requirements[product]["total_kg"] += flt(line.total_kg)

    rows = []
    for product, req in requirements.items():
        stock = get_stock_qty(product, warehouse)
        shortfall = max(req["total_kg"] - stock, 0)
        order_qty = round_order_qty(shortfall, product, bag_sizes)

        rows.append({
            "product":      product,
            "total_kg":     round(req["total_kg"], 1),
            "stock_kg":     round(stock, 1),
            "shortfall_kg": round(shortfall, 1),
            "order_qty":    order_qty,
            "first_month":  req["first_month"],
        })

    return sorted(rows, key=lambda r: r["shortfall_kg"], reverse=True)


def get_stock_qty(item_code, warehouse=None):
    filters = {"item_code": item_code}
    if warehouse:
        filters["warehouse"] = warehouse
    result = frappe.db.get_value("Bin", filters, "actual_qty")
    return flt(result)


def get_bag_sizes(crop):
    """Read bag_weight_kg per product from the crop's Crop Nutrient Rule rows,
    instead of a hardcoded table, so it stays in sync with the calculation engine."""
    if not crop:
        return {}
    rows = frappe.get_all(
        "Crop Nutrient Rule",
        filters={"crop": crop},
        fields=["fertilizer_product", "bag_weight_kg"],
    )
    return {r.fertilizer_product: flt(r.bag_weight_kg) for r in rows if r.bag_weight_kg}


def round_order_qty(shortfall, product, bag_sizes):
    if shortfall <= 0:
        return 0
    bag = bag_sizes.get(product, 50)
    return math.ceil(shortfall / bag) * bag
