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

    # Build product -> {month: total_kg} matrix
    matrix = {}
    months_used = set()
    for line in programme.get("programme_lines", []):
        product = line.fertilizer_product
        month = line.application_month
        matrix.setdefault(product, {})
        matrix[product][month] = matrix[product].get(month, 0) + flt(line.total_kg)
        months_used.add(month)

    # Order the months that actually appear
    ordered_months = [m for m in MONTH_ORDER if m in months_used]

    columns = get_columns(ordered_months)
    data = get_data(matrix, ordered_months)
    return label_products(columns, data)


def get_columns(ordered_months):
    cols = [
        {"label": "Fertilizer Product", "fieldname": "product", "fieldtype": "Link", "options": "Item", "width": 160},
    ]
    for m in ordered_months:
        cols.append({"label": m, "fieldname": month_key(m), "fieldtype": "Float", "width": 100})
    cols.append({"label": "Season Total (Kg)", "fieldname": "season_total", "fieldtype": "Float", "width": 140})
    return cols


def get_data(matrix, ordered_months):
    rows = []
    for product, month_data in matrix.items():
        row = {"product": product}
        season_total = 0
        for m in ordered_months:
            qty = round(month_data.get(m, 0), 1)
            row[month_key(m)] = qty
            season_total += qty
        row["season_total"] = round(season_total, 1)
        rows.append(row)

    return sorted(rows, key=lambda r: r["season_total"], reverse=True)


def month_key(month):
    return "m_" + month.lower()
