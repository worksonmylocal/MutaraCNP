"""
Integration between MutaraCNP and ERPNext core modules: stock lookups and
the Purchase Receipt -> Fertilizer Budget actuals hook.

Mutara's store-issue flow runs on MutaraCNP's own Fertilizer Store Request
doctype (Requested -> Approved -> Issued/Rejected, via its own Workflow
fixture) rather than ERPNext's Material Request - that keeps the shell
self-contained instead of depending on site-specific Material Request
customisations (business units, purpose categories) that a fresh farm
won't have. That is the one deliberate divergence from the reference app's
*current* api.py (which had since moved to Material Request); it matches
how the reference app itself worked before that migration.
"""

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import flt

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def get_grouped_sum(doctype, sum_field, group_field, filters=None):
	"""Sum `sum_field` grouped by `group_field`, respecting `filters` (same
	shape as frappe.get_all's filters dict) - returns {group_value: total}."""
	table = frappe.qb.DocType(doctype)
	query = (
		frappe.qb.from_(table)
		.select(table[group_field], Sum(table[sum_field]).as_(sum_field))
		.groupby(table[group_field])
	)
	for field, value in (filters or {}).items():
		column = table[field]
		if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
			query = query.where(column.isin(value[1]))
		else:
			query = query.where(column == value)
	return {row[group_field]: flt(row[sum_field]) for row in query.run(as_dict=True)}


def get_stock_qty(item_code, warehouse=None):
	if not item_code:
		return 0
	filters = {"item_code": item_code}
	if warehouse:
		filters["warehouse"] = warehouse
	return flt(frappe.db.get_value("Bin", filters, "actual_qty"))


def month_to_date(month_name):
	"""Return the next occurrence of the 1st of the given month as a date string."""
	from frappe.utils import getdate, today
	today_date = getdate(today())
	if month_name not in MONTHS:
		return today()
	month_idx = MONTHS.index(month_name) + 1
	year = today_date.year if month_idx >= today_date.month else today_date.year + 1
	return f"{year}-{month_idx:02d}-01"


def get_farm_warehouse(farm=None):
	"""Mutara's one farm's fertilizer store warehouse. `farm` is accepted for
	call-site compatibility but ignored - there is only one."""
	row = frappe.get_all("CNP Farm", filters={"is_active": 1}, fields=["warehouse"], limit=1)
	return row[0].warehouse if row else None


def get_farm_company(farm=None):
	warehouse = get_farm_warehouse(farm)
	return frappe.db.get_value("Warehouse", warehouse, "company") if warehouse else None


def is_fertilizer(item_code):
	"""Whether an item is a fertilizer, by item group."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	return group in ("Fertilizer", "Crop Inputs", "Agrochemicals")


def update_budget_on_receipt(doc, method=None):
	"""Purchase Receipt on_submit hook: update the actuals on the most recent
	submitted Fertilizer Budget for every received fertilizer line."""
	fertilizer_items = [item for item in doc.get("items", []) if is_fertilizer(item.item_code)]
	if not fertilizer_items:
		return

	budgets = frappe.get_all(
		"Fertilizer Budget", filters={"docstatus": 1}, fields=["name"],
		order_by="creation desc", limit=1,
	)
	if not budgets:
		return

	budget = frappe.get_doc("Fertilizer Budget", budgets[0].name)
	changed = False
	for item in fertilizer_items:
		for line in budget.get("budget_lines", []):
			if line.fertilizer_product == item.item_code:
				line.actual_quantity_kg = flt(line.actual_quantity_kg) + flt(item.qty)
				line.actual_unit_price = flt(item.rate)
				line.actual_total_cost = flt(line.actual_quantity_kg) * flt(item.rate)
				changed = True
				break

	if not changed:
		return

	budget.total_actual = sum(flt(l.actual_total_cost) for l in budget.get("budget_lines", []))
	budget.save(ignore_permissions=True)
	frappe.msgprint(f"Fertilizer Budget {budget.name} updated with received quantities.", alert=True)


def mark_plan_issued_from_stock_entry(doc, method=None):
	"""Stock Entry on_submit hook. The store-issue flow normally runs on
	Fertilizer Store Request's own Workflow, but a Stock Entry can still be
	raised and linked back to a request for stock-ledger traceability - when
	that happens, flip the request (and its Block Fertilizer Plan) to
	Issued too, so the field app sees it as ready without a second manual step.
	"""
	requests = frappe.get_all(
		"Fertilizer Store Request",
		filters={"stock_entry": doc.name, "status": ["!=", "Issued"]},
		fields=["name", "block_fertilizer_plan"],
	)
	for request in requests:
		frappe.db.set_value("Fertilizer Store Request", request.name, "status", "Issued")
		if request.block_fertilizer_plan:
			frappe.db.set_value("Block Fertilizer Plan", request.block_fertilizer_plan, "status", "Issued")
