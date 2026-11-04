import frappe


def execute():
	"""Potassium Schedule turned out to be unnecessary once Fertilizer Schedule
	was corrected to key by fertilizer Item (matching the real calculation
	engine) rather than nutrient - MOP and K2SO4 just get their own rows in
	Fertilizer Schedule like any other product, so the separate table was
	dead weight from day one, never used by any real data."""
	if frappe.db.exists("DocType", "Potassium Schedule"):
		frappe.delete_doc("DocType", "Potassium Schedule", ignore_permissions=True, force=True)
		frappe.db.commit()
