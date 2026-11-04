import frappe


def after_install():
	create_roles()
	create_material_request_custom_fields()
	create_employee_custom_fields()
	set_site_config()
	seed_core_data()
	frappe.db.commit()
	print("MutaraCNP: post-install setup complete.")


def after_migrate():
	"""`bench migrate` doesn't resync an already-existing Workspace from its
	source JSON the way it does a DocType - without this, an edit to the
	workspace file (new link, new card) just sits there unused on every site
	that already has the record, every migrate, until someone notices and
	force-reloads it by hand."""
	frappe.reload_doc("MutaraCNP", "workspace", "mutaracnp", force=True)
	frappe.db.commit()


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


def _create_custom_field_safely(spec):
	"""Insert one Custom Field, tolerating failure. Adding any custom field to
	a doctype makes Frappe re-validate *every* field already on it (including
	ones belonging to other apps/customisations entirely unrelated to
	MutaraCNP) - on a site with a pre-existing dangling field (e.g. a stray
	Link whose target doctype no longer exists), that re-validation throws
	and would otherwise abort the whole install over something MutaraCNP
	didn't create and has no business fixing uninvited. One bad field
	elsewhere on the site should degrade to "this one field didn't get
	added," not "the app didn't install.\""""
	name = f"{spec['dt']}-{spec['fieldname']}"
	if frappe.db.exists("Custom Field", name):
		return
	try:
		frappe.get_doc({"doctype": "Custom Field", **spec}).insert(ignore_permissions=True)
		frappe.db.commit()
		print(f"MutaraCNP: created {spec['dt']} custom field {spec['fieldname']}")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=f"MutaraCNP install: could not add {spec['dt']}.{spec['fieldname']}",
			message=frappe.get_traceback(),
		)
		print(
			f"MutaraCNP: WARNING - could not create {spec['dt']} custom field "
			f"{spec['fieldname']} (likely an unrelated pre-existing field on this "
			f"site's {spec['dt']} doctype failed validation when re-checked - see "
			"Error Log). Continuing install without it."
		)


def create_material_request_custom_fields():
	"""Traceability fields on Material Request, for whatever procurement a
	submitted programme eventually triggers."""
	_create_custom_field_safely({
		"dt": "Material Request", "fieldname": "custom_fertilizer_programme",
		"label": "Fertilizer Programme", "fieldtype": "Link", "options": "Fertilizer Programme",
		"insert_after": "material_request_type", "read_only": 1,
	})
	_create_custom_field_safely({
		"dt": "Material Request", "fieldname": "custom_block_fertilizer_plan",
		"label": "Block Fertilizer Plan", "fieldtype": "Link", "options": "Block Fertilizer Plan",
		"insert_after": "custom_fertilizer_programme", "read_only": 1,
	})


def create_employee_custom_fields():
	"""MutaraCNP's own field-team fields on Employee - kept separate from the
	HR reports_to line, which stays the real org chart."""
	_create_custom_field_safely({
		"dt": "Employee", "fieldname": "custom_field_supervisor",
		"label": "Field Supervisor (MutaraCNP)", "fieldtype": "Link", "options": "Employee",
		"insert_after": "reports_to",
		"description": "Who manages this employee for fertilizer field-application purposes - set via the field app's Manage Team, separate from the HR reporting line above.",
	})
	_create_custom_field_safely({
		"dt": "Employee", "fieldname": "custom_assigned_block",
		"label": "Assigned Block (MutaraCNP)", "fieldtype": "Link", "options": "Farm Block",
		"insert_after": "custom_field_supervisor",
	})


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
