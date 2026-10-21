import frappe


def before_uninstall():
	"""Remove everything after_install() created outside MutaraCNP's own
	doctypes - those are dropped automatically by Frappe's uninstall. Site
	config (ignore_csrf) is deliberately left alone - it's shared, site-wide.
	"""
	remove_material_request_custom_fields()
	remove_employee_custom_fields()
	remove_roles()
	frappe.db.commit()
	print("MutaraCNP: uninstall cleanup complete.")


def remove_material_request_custom_fields():
	for fieldname in ("custom_fertilizer_programme", "custom_block_fertilizer_plan"):
		name = f"Material Request-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
			print(f"MutaraCNP: removed Custom Field {name}")


def remove_employee_custom_fields():
	for fieldname in ("custom_field_supervisor", "custom_assigned_block"):
		name = f"Employee-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
			print(f"MutaraCNP: removed Custom Field {name}")


def remove_roles():
	"""Field Worker, Storekeeper and CNP Agronomist are specific to this app.
	Farm Manager / General Manager are left alone on uninstall - broader
	roles another app or the site's own setup may also depend on."""
	role_names = ["Field Worker", "Storekeeper", "CNP Agronomist"]
	for role_name in role_names:
		if not frappe.db.exists("Role", role_name):
			continue
		frappe.db.delete("Has Role", {"role": role_name})
		frappe.delete_doc("Role", role_name, ignore_permissions=True, force=True)
		print(f"MutaraCNP: removed role {role_name}")
