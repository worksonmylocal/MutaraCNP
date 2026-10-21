"""Show fertilizer products by name, not by bare Item code, in reports.

Generic on purpose: reports key the product as "product" or
"fertilizer_product" depending on where their data comes from, so this keys
off the column's `options` (whether it points at Item) rather than its
fieldname, and every report gets the same treatment from one place.
"""

import frappe


def label_products(columns, rows):
	"""Put a readable name column in front of every Item-code column."""
	code_fields = [
		col["fieldname"] for col in columns
		if isinstance(col, dict)
		and col.get("options") == "Item"
		and col.get("fieldname")
	]
	if not code_fields:
		return columns, rows

	codes = {row.get(f) for row in rows for f in code_fields if row.get(f)}
	names = _names_for(codes)

	new_columns = []
	for col in columns:
		if isinstance(col, dict) and col.get("fieldname") in code_fields:
			new_columns.append({
				"label": col.get("label") or "Product",
				"fieldname": col["fieldname"] + "_name",
				"fieldtype": "Data",
				"width": col.get("width") or 150,
			})
			new_columns.append({**col, "label": "Code", "width": 110})
		else:
			new_columns.append(col)

	for row in rows:
		for f in code_fields:
			code = row.get(f)
			if code:
				row[f + "_name"] = names.get(code) or code

	return new_columns, rows


def _names_for(codes):
	codes = [c for c in codes if c]
	if not codes:
		return {}
	return {
		row.name: row.item_name
		for row in frappe.get_all(
			"Item", filters={"name": ["in", codes]}, fields=["name", "item_name"]
		)
	}
