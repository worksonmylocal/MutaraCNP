import frappe
from frappe.utils import flt
from mutaracnp.mutaracnp.utils.product_labels import label_products


def execute(filters=None):
    filters = filters or {}
    budget_name = filters.get("fertilizer_budget")
    if not budget_name:
        frappe.throw("Please select a Fertilizer Budget")

    budget = frappe.get_doc("Fertilizer Budget", budget_name)
    return label_products(get_columns(), get_data(budget))


def get_columns():
    return [
        {"label": "Product",              "fieldname": "product",             "fieldtype": "Link",     "options": "Item", "width": 150},
        {"label": "Budget Qty (Kg)",      "fieldname": "planned_quantity_kg", "fieldtype": "Float",    "width": 120},
        {"label": "Actual Qty (Kg)",      "fieldname": "actual_quantity_kg",  "fieldtype": "Float",    "width": 120},
        {"label": "Budget Price",         "fieldname": "budgeted_unit_price", "fieldtype": "Currency", "width": 110},
        {"label": "Actual Price",         "fieldname": "actual_unit_price",   "fieldtype": "Currency", "width": 110},
        {"label": "Budget Cost",          "fieldname": "budgeted_total_cost", "fieldtype": "Currency", "width": 130},
        {"label": "Actual Cost",          "fieldname": "actual_total_cost",   "fieldtype": "Currency", "width": 130},
        {"label": "Volume Var (Kg)",      "fieldname": "volume_variance_kg",  "fieldtype": "Float",    "width": 120},
        {"label": "Price Var",            "fieldname": "price_variance_ksh",  "fieldtype": "Currency", "width": 120},
        {"label": "Total Var",            "fieldname": "total_variance_ksh",  "fieldtype": "Currency", "width": 130},
    ]


def get_data(budget):
    rows = []
    for line in budget.get("budget_lines", []):
        rows.append({
            "product":             line.fertilizer_product,
            "planned_quantity_kg": flt(line.planned_quantity_kg),
            "actual_quantity_kg":  flt(line.actual_quantity_kg),
            "budgeted_unit_price": flt(line.budgeted_unit_price),
            "actual_unit_price":   flt(line.actual_unit_price),
            "budgeted_total_cost": flt(line.budgeted_total_cost),
            "actual_total_cost":   flt(line.actual_total_cost),
            "volume_variance_kg":  flt(line.volume_variance_kg),
            "price_variance_ksh":  flt(line.price_variance_ksh),
            "total_variance_ksh":  flt(line.total_variance_ksh),
        })
    return sorted(rows, key=lambda r: r["budgeted_total_cost"], reverse=True)
