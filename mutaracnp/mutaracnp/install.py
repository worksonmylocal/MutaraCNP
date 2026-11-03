import frappe


def after_install():
	create_roles()
	create_material_request_custom_fields()
	create_employee_custom_fields()
	set_site_config()
	seed_core_data()
	frappe.db.commit()
	print("MutaraCNP: post-install setup complete.")


def create_roles():
	"""Create the module's roles if missing. Flat roles only - Mutara is one
	farm, so there's no per-farm role family to maintain."""
	roles = ["Field Worker", "Storekeeper", "CNP Agronomist", "Farm Manager", "General Manager"]
	for role_name in roles:
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
			}).insert(ignore_permissions=True)
			print(f"MutaraCNP: created role {role_name}")


def create_material_request_custom_fields():
	"""Traceability fields on Material Request, for whatever procurement a
	submitted programme eventually triggers."""
	fields = [
		("custom_fertilizer_programme", "Fertilizer Programme", "Fertilizer Programme", "material_request_type"),
		("custom_block_fertilizer_plan", "Block Fertilizer Plan", "Block Fertilizer Plan", "custom_fertilizer_programme"),
	]
	for fieldname, label, options, insert_after in fields:
		name = f"Material Request-{fieldname}"
		if not frappe.db.exists("Custom Field", name):
			frappe.get_doc({
				"doctype": "Custom Field",
				"dt": "Material Request",
				"fieldname": fieldname,
				"label": label,
				"fieldtype": "Link",
				"options": options,
				"insert_after": insert_after,
				"read_only": 1,
			}).insert(ignore_permissions=True)
			print(f"MutaraCNP: created Material Request custom field {fieldname}")


def create_employee_custom_fields():
	"""MutaraCNP's own field-team fields on Employee - kept separate from the
	HR reports_to line, which stays the real org chart."""
	fieldname = "custom_field_supervisor"
	if not frappe.db.exists("Custom Field", f"Employee-{fieldname}"):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Employee",
			"fieldname": fieldname,
			"label": "Field Supervisor (MutaraCNP)",
			"fieldtype": "Link",
			"options": "Employee",
			"insert_after": "reports_to",
			"description": "Who manages this employee for fertilizer field-application purposes - set via the field app's Manage Team, separate from the HR reporting line above.",
		}).insert(ignore_permissions=True)
		print("MutaraCNP: created Employee custom_field_supervisor field")

	block_fieldname = "custom_assigned_block"
	if not frappe.db.exists("Custom Field", f"Employee-{block_fieldname}"):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Employee",
			"fieldname": block_fieldname,
			"label": "Assigned Block (MutaraCNP)",
			"fieldtype": "Link",
			"options": "Farm Block",
			"insert_after": "custom_field_supervisor",
		}).insert(ignore_permissions=True)
		print("MutaraCNP: created Employee custom_assigned_block field")


def set_site_config():
	"""Allow the field page and dashboard API calls (same-origin, login-protected)."""
	from frappe.installer import update_site_config
	update_site_config("ignore_csrf", 1)
	print("MutaraCNP: set ignore_csrf")


def seed_core_data():
	"""Mutara's own master data shell - the one farm record, the module
	settings, and the five crops the farm will plan for. No sections, blocks,
	rates, tiers or demo transactional data - that's the user's own farm
	layout and master data, entered once the shell is reviewed."""
	farm_name = "Mutara"
	if not frappe.db.exists("CNP Farm", farm_name):
		frappe.get_doc({
			"doctype": "CNP Farm",
			"farm_name": farm_name,
			"is_active": 1,
		}).insert(ignore_permissions=True)
		print(f"MutaraCNP: created CNP Farm {farm_name}")

	settings = frappe.get_single("Crop Nutrition Planning Settings")
	changed = False
	if not settings.farm:
		settings.farm = farm_name
		changed = True
	if settings.upcoming_alert_days in (None, 0):
		settings.upcoming_alert_days = 14
		changed = True
	if settings.variance_threshold_pct in (None, 0):
		settings.variance_threshold_pct = 15
		changed = True

	# One Soil Buildup Factor row per nutrient, left at 0 until real soil
	# sampling data is available - the row existing is what matters here, so
	# the settings page is ready to edit rather than empty, without faking a
	# number no one has supplied yet.
	existing_nutrients = {row.nutrient for row in settings.soil_buildup_factors}
	for nutrient in ["N", "P", "K", "Ca", "Mg", "S", "Mn", "B", "Mo", "Zn"]:
		if nutrient not in existing_nutrients:
			settings.append("soil_buildup_factors", {"nutrient": nutrient, "buildup_factor": 0})
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		print("MutaraCNP: configured Crop Nutrition Planning Settings")

	crops = [
		("Avocado", 1),
		("Cabbages", 0),
		("Potatoes", 0),
		("Onions", 0),
		("Passion Fruit", 0),
	]
	for crop_name, is_primary in crops:
		if not frappe.db.exists("Crop", crop_name):
			frappe.get_doc({
				"doctype": "Crop",
				"crop_name": crop_name,
				"is_primary_crop": is_primary,
			}).insert(ignore_permissions=True)
			print(f"MutaraCNP: created Crop {crop_name}")
