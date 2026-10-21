import frappe
from frappe.utils import flt
from mutaracnp.mutaracnp.utils.product_labels import label_products


def execute(filters=None):
    filters = filters or {}
    return label_products(get_columns(), get_data(filters))


def get_columns():
    return [
        {"label": "Date",          "fieldname": "application_date",          "fieldtype": "Date",  "width": 100},
        {"label": "Block",         "fieldname": "block",                     "fieldtype": "Link",  "options": "Farm Block", "width": 110},
        {"label": "Product",       "fieldname": "fertilizer_product",        "fieldtype": "Link",  "options": "Item",       "width": 130},
        {"label": "Planned (Kg)",  "fieldname": "planned_quantity_kg",       "fieldtype": "Float", "width": 100},
        {"label": "Applied (Kg)",  "fieldname": "actual_quantity_applied_kg","fieldtype": "Float", "width": 100},
        {"label": "Variance (Kg)", "fieldname": "variance_kg",               "fieldtype": "Float", "width": 100},
        {"label": "Method",        "fieldname": "application_method",        "fieldtype": "Data",  "width": 110},
        {"label": "Weather",       "fieldname": "weather_conditions",        "fieldtype": "Data",  "width": 100},
        {"label": "Supervisor",    "fieldname": "supervisor",                "fieldtype": "Link",  "options": "Employee",   "width": 130},
        {"label": "Stock Entry",   "fieldname": "stock_entry",               "fieldtype": "Link",  "options": "Stock Entry","width": 140},
        {"label": "Reference",     "fieldname": "name",                      "fieldtype": "Link",  "options": "Fertilizer Application", "width": 150},
    ]


def get_data(filters):
    conditions = {"docstatus": 1}

    if filters.get("farm"):
        conditions["farm"] = filters["farm"]
    if filters.get("from_date") and filters.get("to_date"):
        conditions["application_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        conditions["application_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        conditions["application_date"] = ["<=", filters["to_date"]]

    if filters.get("block"):
        conditions["block"] = filters["block"]
    if filters.get("fertilizer_product"):
        conditions["fertilizer_product"] = filters["fertilizer_product"]
    if filters.get("supervisor"):
        conditions["supervisor"] = filters["supervisor"]

    records = frappe.get_all(
        "Fertilizer Application",
        filters=conditions,
        fields=[
            "name", "application_date", "block", "fertilizer_product",
            "planned_quantity_kg", "actual_quantity_applied_kg", "variance_kg",
            "application_method", "weather_conditions",
            "supervisor", "stock_entry",
        ],
        order_by="application_date asc, block asc",
    )
    return records
