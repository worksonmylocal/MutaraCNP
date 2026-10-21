import frappe
from frappe.utils import flt
from mutaracnp.mutaracnp.utils.product_labels import label_products


def execute(filters=None):
    filters = filters or {}
    return label_products(get_columns(), get_data(filters))


def get_columns():
    return [
        {"label": "Block",         "fieldname": "block",              "fieldtype": "Link", "options": "Farm Block", "width": 120},
        {"label": "Product",       "fieldname": "fertilizer_product", "fieldtype": "Link", "options": "Item",       "width": 130},
        {"label": "Month",         "fieldname": "application_month",  "fieldtype": "Data", "width": 100},
        {"label": "Planned (Kg)",  "fieldname": "planned_kg",         "fieldtype": "Float", "width": 110},
        {"label": "Applied (Kg)",  "fieldname": "actual_kg",          "fieldtype": "Float", "width": 110},
        {"label": "Variance (Kg)", "fieldname": "variance_kg",        "fieldtype": "Float", "width": 110},
        {"label": "Variance (%)",  "fieldname": "variance_pct",       "fieldtype": "Percent", "width": 100},
        {"label": "Status",        "fieldname": "status",             "fieldtype": "Data", "width": 100},
    ]


def get_data(filters):
    conditions = {"docstatus": 1}
    if filters.get("farm"):
        conditions["farm"] = filters["farm"]
    if filters.get("season"):
        conditions["season"] = filters["season"]
    if filters.get("block"):
        conditions["block"] = filters["block"]

    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters=conditions,
        fields=["name", "block", "fertilizer_product", "application_month",
                "total_kg_required", "status"],
    )

    rows = []
    for plan in plans:
        applications = frappe.get_all(
            "Fertilizer Application",
            filters={"block_fertilizer_plan": plan.name, "docstatus": 1},
            fields=["actual_quantity_applied_kg"],
        )
        actual_kg = sum(flt(a.actual_quantity_applied_kg) for a in applications)
        planned = flt(plan.total_kg_required)
        variance = actual_kg - planned
        var_pct = (variance / planned * 100) if planned else 0

        rows.append({
            "block":              plan.block,
            "fertilizer_product": plan.fertilizer_product,
            "application_month":  plan.application_month,
            "planned_kg":         round(planned, 2),
            "actual_kg":          round(actual_kg, 2),
            "variance_kg":        round(variance, 2),
            "variance_pct":       round(var_pct, 1),
            "status":             plan.status,
        })

    return sorted(rows, key=lambda r: (r["block"], r["fertilizer_product"]))
