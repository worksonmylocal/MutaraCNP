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
    return label_products(get_columns(), get_data(programme))


def get_columns():
    return [
        {"label": "Month",        "fieldname": "month",       "fieldtype": "Data",     "width": 110},
        {"label": "Product",      "fieldname": "product",     "fieldtype": "Link",     "options": "Item", "width": 150},
        {"label": "Quantity (Kg)","fieldname": "qty",         "fieldtype": "Float",    "width": 130},
        {"label": "Unit Price",   "fieldname": "unit_price",  "fieldtype": "Currency", "width": 120},
        {"label": "Cost (Ksh)",   "fieldname": "cost",        "fieldtype": "Currency", "width": 150},
    ]


def get_data(programme):
    # Aggregate qty per (month, product)
    matrix = {}
    for line in programme.get("programme_lines", []):
        key = (line.application_month, line.fertilizer_product)
        matrix[key] = matrix.get(key, 0) + flt(line.total_kg)

    # Price cache
    price_cache = {}
    def get_price(product):
        if product not in price_cache:
            price_cache[product] = flt(frappe.db.get_value(
                "Item Price", {"item_code": product, "buying": 1}, "price_list_rate"
            ))
        return price_cache[product]

    rows = []
    for (month, product), qty in matrix.items():
        price = get_price(product)
        rows.append({
            "month":      month,
            "product":    product,
            "qty":        round(qty, 1),
            "unit_price": price,
            "cost":       round(qty * price, 2),
            "_month_idx": MONTH_ORDER.index(month) if month in MONTH_ORDER else 99,
        })

    # Sort by calendar month, then product
    rows.sort(key=lambda r: (r["_month_idx"], r["product"]))
    for r in rows:
        del r["_month_idx"]

    return rows
