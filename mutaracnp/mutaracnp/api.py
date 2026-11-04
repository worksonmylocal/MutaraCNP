"""
Whitelisted API methods for MutaraCNP's mobile field app, dashboards and
Agronomist Desk.

Mutara is single-farm, so none of these take or branch on a `farm`
parameter the way the multi-farm reference app's api.py does - every
record already belongs to the one CNP Farm, so there's nothing to scope
between. A few functions keep a `farm=None` parameter for call-site
compatibility with ported frontend code; it is accepted and ignored.

The nutrient-rate calculation engine (utils/calculation_engine.py) now exists
and desk_calculate / get_yield_tier_distribution call into it for real.
desk_get_rate_grid, desk_save_rates and export_programme_excel remain
stubbed - they're a manual block-by-block rate override layer on top of the
engine's own output, a separate feature the engine itself doesn't need.
"""

import frappe
from frappe.utils import cint, flt, now_datetime, today, getdate, date_diff

from mutaracnp.mutaracnp.utils.integration import get_grouped_sum, get_farm_warehouse, get_stock_qty
from mutaracnp.mutaracnp.utils.calculation_engine import calculate_programme, get_yield_tier

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

CALC_ENGINE_PENDING = {
	"calculation_engine_pending": True,
	"message": "The fertilizer rate calculation engine hasn't been built yet for Mutara - this is next.",
}


def _current_employee():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _the_farm():
	rows = frappe.get_all("CNP Farm", filters={"is_active": 1}, fields=["name"], limit=1)
	return rows[0].name if rows else None


def _attach_product_names(rows, code_field="fertilizer_product", name_field=None):
	"""Attach a readable Item name alongside every Item-code field, batched
	into one query rather than a lookup per row."""
	codes = list({r.get(code_field) for r in rows if r.get(code_field)})
	if not codes:
		return rows
	names = {
		row.name: row.item_name
		for row in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name"])
	}
	target = name_field or (code_field + "_name")
	for r in rows:
		code = r.get(code_field)
		if code:
			r[target] = names.get(code) or code
	return rows


def _product_terms(doc):
	terms = [t.strip() for t in (doc.search_terms or "").replace(",", "\n").splitlines() if t.strip()]
	return terms or ([doc.product_name] if doc.product_name else [])


def _product_excludes(doc):
	return [t.strip() for t in (doc.exclude_terms or "").replace(",", "\n").splitlines() if t.strip()]


# ---------------------------------------------------------------------------
# Mobile / field app
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def mobile_login(usr, pwd):
	"""Token login for the bundled mobile app - the app authenticates once
	here and uses the returned api_key/api_secret as an Authorization header
	on every later call, since cookies don't survive its cross-origin calls."""
	from frappe.core.doctype.user.user import User

	result = User.find_by_credentials(usr, pwd)
	if not result or not result.get("is_authenticated") or not result.get("enabled"):
		frappe.throw("Incorrect user or password.", frappe.AuthenticationError)

	user_doc = frappe.get_doc("User", result["name"])

	dirty = False
	if not user_doc.api_key:
		user_doc.api_key = frappe.generate_hash(length=15)
		dirty = True

	api_secret = user_doc.get_password("api_secret", raise_exception=False)
	if not api_secret:
		api_secret = frappe.generate_hash(length=15)
		user_doc.api_secret = api_secret
		dirty = True

	if dirty:
		user_doc.save(ignore_permissions=True)

	return {
		"api_key": user_doc.api_key,
		"api_secret": api_secret,
		"full_name": user_doc.full_name,
		"user": user_doc.name,
	}


@frappe.whitelist(allow_guest=False)
def get_token():
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def get_blocks_with_pending_work():
	plans = frappe.get_all(
		"Block Fertilizer Plan",
		filters={"docstatus": 1, "status": ["in", ["Planned", "Issued"]]},
		fields=["block"], distinct=True,
	)
	return sorted(set(p.block for p in plans))


@frappe.whitelist()
def get_pending_plans_for_block(block, programme=None):
	filters = {"docstatus": 1, "block": block, "status": ["in", ["Planned", "Issued"]]}
	if programme:
		filters["fertilizer_programme"] = programme
	plans = frappe.get_all(
		"Block Fertilizer Plan", filters=filters,
		fields=["name", "fertilizer_product", "application_month", "total_kg_required", "status"],
		order_by="application_month",
	)
	_attach_request_status(plans)
	return _attach_product_names(plans)


@frappe.whitelist()
def get_sections_with_pending_work(programme=None, farm=None):
	filters = {"docstatus": 1, "status": ["in", ["Planned", "Issued"]]}
	if programme:
		filters["fertilizer_programme"] = programme
	plans = frappe.get_all("Block Fertilizer Plan", filters=filters, fields=["section"])
	counts = {}
	for p in plans:
		if p.section:
			counts[p.section] = counts.get(p.section, 0) + 1
	return sorted(
		[{"section": section, "pending_count": count} for section, count in counts.items()],
		key=lambda x: x["section"],
	)


@frappe.whitelist()
def get_pending_plans_for_section(section, programme=None):
	filters = {"docstatus": 1, "section": section, "status": ["in", ["Planned", "Issued"]]}
	if programme:
		filters["fertilizer_programme"] = programme
	plans = frappe.get_all(
		"Block Fertilizer Plan", filters=filters,
		fields=["name", "block", "fertilizer_product", "application_month", "total_kg_required", "status"],
		order_by="block, application_month",
	)
	_attach_request_status(plans)
	return _attach_product_names(plans)


def _attach_request_status(plans):
	for p in plans:
		requests = frappe.get_all(
			"Fertilizer Store Request", filters={"block_fertilizer_plan": p["name"]},
			fields=["name", "status"], order_by="creation desc", limit=1,
		)
		if requests:
			p["request_name"] = requests[0].name
			p["request_status"] = requests[0].status
		else:
			p["request_name"] = None
			p["request_status"] = None


@frappe.whitelist()
def get_sections_with_issued_work(programme=None, farm=None):
	filters = {"docstatus": 1, "status": "Issued"}
	if programme:
		filters["fertilizer_programme"] = programme
	plans = frappe.get_all("Block Fertilizer Plan", filters=filters, fields=["section"])
	counts = {}
	for p in plans:
		if p.section:
			counts[p.section] = counts.get(p.section, 0) + 1
	return sorted(
		[{"section": section, "pending_count": count} for section, count in counts.items()],
		key=lambda x: x["section"],
	)


@frappe.whitelist()
def get_issued_blocks_in_section(section, programme=None):
	filters = {"docstatus": 1, "section": section, "status": "Issued"}
	if programme:
		filters["fertilizer_programme"] = programme
	plans = frappe.get_all("Block Fertilizer Plan", filters=filters, fields=["block"])
	counts = {}
	for p in plans:
		counts[p.block] = counts.get(p.block, 0) + 1
	return sorted(
		[{"block": block, "issued_count": count} for block, count in counts.items()],
		key=lambda x: x["block"],
	)


@frappe.whitelist()
def get_all_sections(farm=None):
	return frappe.get_all("Section", filters={"is_active": 1},
	                       fields=["name", "section_name"], order_by="section_name")


@frappe.whitelist()
def get_blocks_in_section(section):
	return frappe.get_all("Farm Block", filters={"section": section}, fields=["name"], order_by="name")


@frappe.whitelist()
def get_home_metrics(programme=None, farm=None):
	plan_filter = {"docstatus": 1}
	if programme:
		plan_filter["fertilizer_programme"] = programme
	plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter, fields=["status"])

	total = len(plans)
	applied = sum(1 for p in plans if p.status in ("Applied", "Verified"))
	pending = sum(1 for p in plans if p.status in ("Planned", "Issued"))
	ready = sum(1 for p in plans if p.status == "Issued")

	mine = frappe.db.count("Fertilizer Application", {"docstatus": 1, "owner": frappe.session.user})
	today_count = frappe.db.count("Fertilizer Application", {"docstatus": 1, "application_date": today()})
	pending_requests = frappe.db.count(
		"Fertilizer Store Request", {"docstatus": ["<", 2], "status": ["not in", ["Issued", "Rejected"]]})

	return {
		"pending_applications": pending,
		"ready_to_record": ready,
		"progress_pct": round(applied / total * 100, 1) if total else 0,
		"applied": applied,
		"total_plans": total,
		"my_applications": mine,
		"applications_today": today_count,
		"pending_requests": pending_requests,
	}


@frappe.whitelist()
def get_applications_today(farm=None):
	return frappe.db.count("Fertilizer Application", {"docstatus": 1, "application_date": today()})


@frappe.whitelist()
def create_store_request(block_fertilizer_plan, quantity, employee=None):
	"""Create a Fertilizer Store Request from the field page."""
	plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)
	if not employee:
		employee = _current_employee()

	doc = frappe.get_doc({
		"doctype": "Fertilizer Store Request",
		"block_fertilizer_plan": block_fertilizer_plan,
		"block": plan.block,
		"fertilizer_product": plan.fertilizer_product,
		"application_month": plan.application_month,
		"quantity_requested_kg": flt(quantity),
		"requested_by": employee,
		"request_date": today(),
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_store_requests(programme=None, farm=None):
	filters = {}
	if programme:
		plan_names = frappe.get_all("Block Fertilizer Plan", filters={"fertilizer_programme": programme}, pluck="name")
		if not plan_names:
			return []
		filters["block_fertilizer_plan"] = ["in", plan_names]

	requests = frappe.get_all(
		"Fertilizer Store Request", filters=filters,
		fields=["name", "block", "fertilizer_product", "application_month", "quantity_requested_kg",
		        "request_date", "status", "docstatus"],
		order_by="creation desc", limit_page_length=100,
	)
	return _attach_product_names(requests)


@frappe.whitelist()
def record_application(block_fertilizer_plan, actual_quantity, applied_in_full=None,
                        partial_reason=None, employee=None, material_request=None,
                        operators=None, application_method=None, weather_conditions=None,
                        store_request=None):
	"""Create a Fertilizer Application from the field page."""
	plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

	if not employee:
		employee = _current_employee()

	if operators and isinstance(operators, str):
		operators = frappe.parse_json(operators)
	operators = operators or []

	for op in operators:
		if not _is_my_applicator(op, employee):
			frappe.throw(f"{op} is not on your team.", frappe.PermissionError)

	planned = flt(plan.total_kg_required)
	short = planned and flt(actual_quantity) < planned - max(planned * 0.01, 0.5)
	if short and not partial_reason:
		frappe.throw("A reason is required when less than the planned quantity is applied.")

	doc = frappe.get_doc({
		"doctype": "Fertilizer Application",
		"block_fertilizer_plan": block_fertilizer_plan,
		"material_request": material_request or store_request,
		"block": plan.block,
		"fertilizer_product": plan.fertilizer_product,
		"application_date": today(),
		"planned_quantity_kg": planned,
		"actual_quantity_applied_kg": flt(actual_quantity),
		"partial_reason": partial_reason,
		"application_method": application_method,
		"weather_conditions": weather_conditions,
		"supervisor": employee,
		"applicators": [{"employee": op} for op in operators],
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return {"name": doc.name, "status": "Applied"}


@frappe.whitelist()
def get_issued_request_for_plan(block_fertilizer_plan):
	mr = frappe.get_all(
		"Fertilizer Store Request",
		filters={"block_fertilizer_plan": block_fertilizer_plan, "docstatus": 1, "status": "Issued"},
		fields=["name"], limit=1,
	)
	return mr[0].name if mr else None


def _is_my_applicator(employee, supervisor):
	return bool(employee) and bool(supervisor) and frappe.db.exists(
		"Employee", {"name": employee, "custom_field_supervisor": supervisor, "status": "Active"}
	)


@frappe.whitelist()
def get_my_applicators():
	supervisor = _current_employee()
	if not supervisor:
		return []

	applicators = frappe.get_all(
		"Employee", filters={"custom_field_supervisor": supervisor, "status": "Active"},
		fields=["name", "employee_name", "custom_assigned_block"], order_by="employee_name",
	)
	if not applicators:
		return []

	today_attendance = {
		a.employee: a.status
		for a in frappe.get_all(
			"Field Attendance",
			filters={"employee": ["in", [a.name for a in applicators]], "attendance_date": today()},
			fields=["employee", "status"],
		)
	}
	for a in applicators:
		a["attendance_status"] = today_attendance.get(a.name)
	return applicators


@frappe.whitelist()
def get_applicators_for_block(block):
	supervisor = _current_employee()
	if not supervisor:
		return []
	return frappe.get_all(
		"Employee",
		filters={"custom_field_supervisor": supervisor, "custom_assigned_block": block, "status": "Active"},
		fields=["name", "employee_name"], order_by="employee_name",
	)


@frappe.whitelist()
def get_my_applicators_by_section():
	applicators = get_my_applicators()
	if not applicators:
		return []

	blocks = {a.custom_assigned_block for a in applicators if a.custom_assigned_block}
	block_section = {}
	if blocks:
		block_section = {
			b.name: b.section
			for b in frappe.get_all("Farm Block", filters={"name": ["in", list(blocks)]}, fields=["name", "section"])
		}

	sections = {}
	for a in applicators:
		block = a.custom_assigned_block
		section = block_section.get(block) or "Unassigned"
		block_label = block or "No block assigned"
		sections.setdefault(section, {}).setdefault(block_label, []).append(a)

	result = []
	for section, block_map in sections.items():
		block_list = sorted(
			[{"block": block, "applicators": apps} for block, apps in block_map.items()],
			key=lambda x: (x["block"] == "No block assigned", x["block"]),
		)
		result.append({"section": section, "blocks": block_list})

	return sorted(result, key=lambda x: (x["section"] == "Unassigned", x["section"]))


@frappe.whitelist()
def get_available_employees_for_team(search=None, limit=50):
	supervisor = _current_employee()
	filters = {"status": "Active", "custom_field_supervisor": ["is", "not set"]}
	company = frappe.db.get_value("Employee", supervisor, "company") if supervisor else None
	if company:
		filters["company"] = company

	or_filters = None
	if search and str(search).strip():
		term = f"%{str(search).strip()}%"
		or_filters = [["employee_name", "like", term], ["name", "like", term]]

	return frappe.get_all(
		"Employee", filters=filters, or_filters=or_filters,
		fields=["name", "employee_name", "designation"],
		order_by="employee_name", limit_page_length=cint(limit) or 50,
	)


@frappe.whitelist()
def add_applicators(employees, block=None):
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	employees = [e for e in (employees or []) if e]
	if not employees:
		frappe.throw("No applicators selected.")

	supervisor = _current_employee()
	if not supervisor:
		frappe.throw("You don't have an Employee record linked to your account.")

	if block and not frappe.db.exists("Farm Block", block):
		frappe.throw(f"Block {block} does not exist.")

	added, failed = [], []
	for employee in employees:
		row = frappe.db.get_value(
			"Employee", employee,
			["name", "employee_name", "status", "custom_field_supervisor"], as_dict=True,
		)
		if not row or row.status != "Active":
			failed.append({"employee": employee, "reason": "not an active employee"})
			continue
		if row.custom_field_supervisor and row.custom_field_supervisor != supervisor:
			failed.append({"employee": row.employee_name or employee, "reason": "already on another supervisor's team"})
			continue

		frappe.db.set_value("Employee", employee, "custom_field_supervisor", supervisor, update_modified=False)
		if block:
			frappe.db.set_value("Employee", employee, "custom_assigned_block", block, update_modified=False)
		added.append(row.employee_name or employee)

	frappe.db.commit()
	return {"added": added, "failed": failed, "block": block}


@frappe.whitelist()
def add_applicator(employee):
	supervisor = _current_employee()
	if not supervisor:
		frappe.throw("You don't have an Employee record linked to your account.")
	if not frappe.db.exists("Employee", {"name": employee, "status": "Active"}):
		frappe.throw("That employee doesn't exist or isn't active.")
	current_supervisor = frappe.db.get_value("Employee", employee, "custom_field_supervisor")
	if current_supervisor and current_supervisor != supervisor:
		frappe.throw("That employee is already on another supervisor's team.")
	frappe.db.set_value("Employee", employee, "custom_field_supervisor", supervisor)
	return {"employee": employee, "status": "added"}


@frappe.whitelist()
def remove_applicator(employee):
	supervisor = _current_employee()
	if not _is_my_applicator(employee, supervisor):
		frappe.throw("This employee is not on your team.", frappe.PermissionError)
	frappe.db.set_value("Employee", employee, "custom_field_supervisor", None)
	frappe.db.set_value("Employee", employee, "custom_assigned_block", None)
	return {"employee": employee, "status": "removed"}


@frappe.whitelist()
def assign_block(employee, block):
	supervisor = _current_employee()
	if not _is_my_applicator(employee, supervisor):
		frappe.throw("This employee is not on your team.", frappe.PermissionError)
	if block and not frappe.db.exists("Farm Block", block):
		frappe.throw(f"Block {block} does not exist.")
	frappe.db.set_value("Employee", employee, "custom_assigned_block", block or None)
	return {"employee": employee, "block": block}


@frappe.whitelist()
def mark_attendance(employee, status):
	if status not in ("Present", "Absent"):
		frappe.throw("Status must be Present or Absent.")
	supervisor = _current_employee()
	if not _is_my_applicator(employee, supervisor):
		frappe.throw("This employee is not on your team.", frappe.PermissionError)

	block = frappe.db.get_value("Employee", employee, "custom_assigned_block")
	farm = frappe.db.get_value("Farm Block", block, "farm") if block else None

	existing = frappe.db.exists("Field Attendance", {"employee": employee, "attendance_date": today()})
	if existing:
		doc = frappe.get_doc("Field Attendance", existing)
		doc.status = status
		doc.marked_by = supervisor
		doc.block = block
		doc.farm = farm
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({
			"doctype": "Field Attendance", "employee": employee, "attendance_date": today(),
			"status": status, "marked_by": supervisor, "block": block, "farm": farm,
		})
		doc.insert(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_attendance_by_block(attendance_date=None):
	supervisor = _current_employee()
	if not supervisor:
		return []

	on_date = attendance_date or today()
	applicators = frappe.get_all(
		"Employee", filters={"custom_field_supervisor": supervisor, "status": "Active"},
		fields=["name", "employee_name", "employee_number", "custom_assigned_block"],
		order_by="employee_name",
	)
	if not applicators:
		return []

	marked = {
		a.employee: a.status
		for a in frappe.get_all(
			"Field Attendance",
			filters={"employee": ["in", [a.name for a in applicators]], "attendance_date": on_date},
			fields=["employee", "status"],
		)
	}

	groups = {}
	for a in applicators:
		block = a.custom_assigned_block or "No block assigned"
		groups.setdefault(block, []).append({
			"name": a.name, "employee_name": a.employee_name, "employee_number": a.employee_number,
			"block": a.custom_assigned_block, "status": marked.get(a.name),
		})

	result = []
	for block, people in groups.items():
		result.append({
			"block": block, "applicators": people,
			"present": sum(1 for p in people if p["status"] == "Present"),
			"absent": sum(1 for p in people if p["status"] == "Absent"),
			"unmarked": sum(1 for p in people if not p["status"]),
		})
	result.sort(key=lambda g: (g["block"] == "No block assigned", g["block"]))
	return result


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_seasons():
	seasons = frappe.get_all("Fertilizer Programme", filters={"docstatus": 1}, fields=["season"], distinct=True)
	return ["All Seasons"] + sorted(set(s.season for s in seasons))


@frappe.whitelist()
def get_farms():
	"""Mutara has one farm; this exists for frontend call-site compatibility."""
	return frappe.get_all("CNP Farm", filters={"is_active": 1}, fields=["name"], order_by="name")


@frappe.whitelist()
def get_available_farms():
	farm = _the_farm()
	return [farm] if farm else []


@frappe.whitelist()
def get_dashboard_summary(season=None, farm=None):
	plan_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		plan_filter["season"] = season

	plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
	                        fields=["name", "status", "total_kg_required", "block"])

	total_plans = len(plans)
	applied = sum(1 for p in plans if p.status == "Applied")
	issued = sum(1 for p in plans if p.status == "Issued")
	planned = sum(1 for p in plans if p.status == "Planned")
	total_kg = sum(flt(p.total_kg_required) for p in plans)
	blocks = len(set(p.block for p in plans))

	pending_requests = frappe.db.count(
		"Fertilizer Store Request", {"docstatus": ["<", 2], "status": ["not in", ["Issued", "Rejected"]]})
	pct_applied = round(applied / total_plans * 100, 1) if total_plans else 0

	return {
		"total_plans": total_plans, "applied": applied, "issued": issued, "planned": planned,
		"total_kg": round(total_kg, 0), "blocks": blocks,
		"pending_requests": pending_requests, "pct_applied": pct_applied,
	}


@frappe.whitelist()
def get_monthly_breakdown(season=None, farm=None):
	prog_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		prog_filter["season"] = season
	programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

	monthly = {m: {"qty": 0, "cost": 0} for m in MONTHS}
	price_cache = {}

	def price(prod):
		if prod not in price_cache:
			price_cache[prod] = flt(frappe.db.get_value(
				"Item Price", {"item_code": prod, "buying": 1}, "price_list_rate"))
		return price_cache[prod]

	for prog in programmes:
		doc = frappe.get_doc("Fertilizer Programme", prog.name)
		for line in doc.get("programme_lines", []):
			m = line.application_month
			if m in monthly:
				monthly[m]["qty"] += flt(line.total_kg)
				monthly[m]["cost"] += flt(line.total_kg) * price(line.fertilizer_product)

	return [
		{"month": m[:3], "qty": round(monthly[m]["qty"], 0), "cost": round(monthly[m]["cost"], 0)}
		for m in MONTHS if monthly[m]["qty"] > 0
	]


@frappe.whitelist()
def get_product_breakdown(season=None, farm=None):
	prog_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		prog_filter["season"] = season
	programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

	products = {}
	for prog in programmes:
		doc = frappe.get_doc("Fertilizer Programme", prog.name)
		for line in doc.get("programme_lines", []):
			products[line.fertilizer_product] = products.get(line.fertilizer_product, 0) + flt(line.total_kg)

	rows = [{"product": p, "qty": round(q, 0)} for p, q in sorted(products.items(), key=lambda x: x[1], reverse=True)]
	return _attach_product_names(rows, "product", "product_name")


@frappe.whitelist()
def get_recent_activity(farm=None):
	apps = frappe.get_all(
		"Fertilizer Application", filters={"docstatus": 1},
		fields=["block", "fertilizer_product", "actual_quantity_applied_kg",
		        "application_date", "supervisor", "applied_in_full"],
		order_by="creation desc", limit=8,
	)
	return _attach_product_names(apps)


@frappe.whitelist()
def get_stock_levels(farm=None):
	calendar_names = frappe.get_all("Production Calendar", fields=["name"], pluck="name")
	products = []
	if calendar_names:
		products = frappe.get_all(
			"Fertilizer Schedule", filters={"parent": ["in", calendar_names]},
			pluck="fertilizer_product", distinct=True,
		)
	if not products:
		return []

	item_names = {
		row.item_code: row.item_name
		for row in frappe.get_all("Item", filters={"name": ["in", products]}, fields=["name as item_code", "item_name"])
	}

	warehouse = get_farm_warehouse()
	bin_filters = {"item_code": ["in", products]}
	if warehouse:
		bin_filters["warehouse"] = warehouse
	stock_by_code = get_grouped_sum("Bin", "actual_qty", "item_code", bin_filters)

	result = [
		{"product": item_names.get(code, code), "item_code": code, "qty": round(stock_by_code.get(code, 0), 0)}
		for code in products
	]
	return sorted(result, key=lambda x: x["product"])


@frappe.whitelist()
def get_budget_summary(season=None, farm=None):
	filters = {"docstatus": 1}
	if season and season != "All Seasons":
		filters["season"] = season

	budgets = frappe.get_all("Fertilizer Budget", filters=filters,
	                          fields=["name", "total_budget_ksh", "total_actual",
	                                  "cost_per_ha_budget", "cost_per_ha_actual"])

	total_budget = sum(flt(b.total_budget_ksh) for b in budgets)
	total_actual = sum(flt(b.total_actual) for b in budgets)
	cph_budget = [flt(b.cost_per_ha_budget) for b in budgets if b.cost_per_ha_budget]
	cph_actual = [flt(b.cost_per_ha_actual) for b in budgets if b.cost_per_ha_actual]

	return {
		"total_budget": round(total_budget, 0),
		"total_actual": round(total_actual, 0),
		"variance": round(total_actual - total_budget, 0),
		"pct_spent": round(total_actual / total_budget * 100, 1) if total_budget else 0,
		"cost_per_ha_budget": round(sum(cph_budget) / len(cph_budget), 0) if cph_budget else 0,
		"cost_per_ha_actual": round(sum(cph_actual) / len(cph_actual), 0) if cph_actual else 0,
	}


@frappe.whitelist()
def get_upcoming_and_overdue(programme=None, farm=None):
	today_date = getdate(today())
	plan_filter = {"docstatus": 1, "status": ["in", ["Planned", "Issued"]]}
	if programme:
		plan_filter["fertilizer_programme"] = programme

	plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
	                        fields=["block", "fertilizer_product", "application_month", "total_kg_required", "status"])

	upcoming, overdue = [], []
	for p in plans:
		if p.application_month not in MONTHS:
			continue
		idx = MONTHS.index(p.application_month) + 1
		year = today_date.year if idx >= today_date.month else today_date.year + 1
		due = getdate(f"{year}-{idx:02d}-01")
		days = date_diff(due, today_date)
		if 0 <= days <= 30:
			upcoming.append({**p, "days": days})
		past_year = today_date.year if idx < today_date.month else today_date.year - 1
		past_end = getdate(f"{past_year}-{idx:02d}-28")
		if today_date > past_end and days > 60:
			overdue.append(p)

	upcoming.sort(key=lambda x: x["days"])
	_attach_product_names(upcoming)
	_attach_product_names(overdue)
	return {"upcoming": upcoming[:10], "overdue": overdue[:10]}


@frappe.whitelist()
def get_leaf_deficiency_grid(season=None, farm=None):
	filters = {"docstatus": 1}
	if season and season != "All Seasons":
		filters["season"] = season
	analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name", "section", "yield_tier"])

	nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
	grid = []
	for a in analyses:
		doc = frappe.get_doc("Leaf Analysis", a.name)
		row = {"section": a.section, "yield_tier": a.yield_tier, "cells": {}}
		for r in doc.get("nutrient_results", []):
			if r.nutrient in nutrients:
				row["cells"][r.nutrient] = r.status or "-"
		grid.append(row)

	grid.sort(key=lambda r: (r["section"] or "", r["yield_tier"] or ""))
	return {"nutrients": nutrients, "grid": grid}


@frappe.whitelist()
def get_stock_coverage(season=None, farm=None):
	prog_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		prog_filter["season"] = season
	programme_names = frappe.get_all("Fertilizer Programme", filters=prog_filter, pluck="name")

	required = {}
	if programme_names:
		required = get_grouped_sum("Fertilizer Programme Line", "total_kg", "fertilizer_product",
		                            {"parent": ["in", programme_names]})

	warehouse = get_farm_warehouse()
	stock_by_product = {}
	if required:
		bin_filters = {"item_code": ["in", list(required.keys())]}
		if warehouse:
			bin_filters["warehouse"] = warehouse
		stock_by_product = get_grouped_sum("Bin", "actual_qty", "item_code", bin_filters)

	result = []
	for product, need in required.items():
		stock = stock_by_product.get(product, 0)
		result.append({
			"product": product, "need": round(need, 0), "stock": round(stock, 0),
			"covered": stock >= need, "shortfall": round(max(need - stock, 0), 0),
		})
	_attach_product_names(result, "product", "product_name")
	return sorted(result, key=lambda x: x["shortfall"], reverse=True)


# ---------------------------------------------------------------------------
# Managerial dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_manager_kpis(season=None, farm=None):
	plan_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		plan_filter["season"] = season

	plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter, fields=["status", "block", "total_kg_required"])
	total = len(plans)
	applied = sum(1 for p in plans if p.status == "Applied")
	pct_complete = round(applied / total * 100, 1) if total else 0

	bfilter = {"docstatus": 1}
	if season and season != "All Seasons":
		bfilter["season"] = season
	budgets = frappe.get_all("Fertilizer Budget", filters=bfilter,
	                          fields=["total_budget_ksh", "total_actual", "cost_per_ha_actual", "cost_per_ha_budget"])
	total_budget = sum(flt(b.total_budget_ksh) for b in budgets)
	total_actual = sum(flt(b.total_actual) for b in budgets)
	cph = [flt(b.cost_per_ha_actual) for b in budgets if b.cost_per_ha_actual]
	cph_b = [flt(b.cost_per_ha_budget) for b in budgets if b.cost_per_ha_budget]

	overdue = len(get_upcoming_and_overdue().get("overdue", []))
	pending = frappe.db.count("Fertilizer Store Request", {"status": "Requested"})

	return {
		"total_budget": round(total_budget, 0),
		"total_actual": round(total_actual, 0),
		"variance": round(total_actual - total_budget, 0),
		"variance_pct": round((total_actual - total_budget) / total_budget * 100, 1) if total_budget else 0,
		"cost_per_ha": round(sum(cph) / len(cph), 0) if cph else 0,
		"cost_per_ha_budget": round(sum(cph_b) / len(cph_b), 0) if cph_b else 0,
		"pct_complete": pct_complete,
		"blocks": len(set(p.block for p in plans)),
		"overdue": overdue,
		"pending_requests": pending,
	}


@frappe.whitelist()
def get_yield_tier_distribution(season=None, farm=None):
	filters = {}
	if season and season != "All Seasons":
		filters["season"] = season
	programmes = frappe.get_all("Fertilizer Programme", filters=filters, fields=["name", "crop"])

	counts = {}
	crop_cache = {}
	for p in programmes:
		if p.crop not in crop_cache:
			crop_cache[p.crop] = frappe.get_doc("Crop", p.crop)
		crop_doc = crop_cache[p.crop]

		rows = frappe.get_all("Programme Block Yield", filters={"parent": p.name}, fields=["yield_kg_ha"])
		for row in rows:
			try:
				tier_label, _ = get_yield_tier(crop_doc, row.yield_kg_ha)
			except Exception:
				continue
			counts[tier_label] = counts.get(tier_label, 0) + 1

	return [{"tier": tier, "count": count} for tier, count in counts.items()]


@frappe.whitelist()
def get_application_pace(season=None, farm=None):
	plan_filter = {"docstatus": 1}
	if season and season != "All Seasons":
		plan_filter["season"] = season
	plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter, fields=["application_month", "status"])

	planned = {m: 0 for m in MONTHS}
	applied = {m: 0 for m in MONTHS}
	for p in plans:
		if p.application_month in planned:
			planned[p.application_month] += 1
			if p.status == "Applied":
				applied[p.application_month] += 1

	return [{"month": m[:3], "planned": planned[m], "applied": applied[m]} for m in MONTHS if planned[m] > 0]


@frappe.whitelist()
def get_leaf_deficiency_summary(season=None, farm=None):
	filters = {"docstatus": 1}
	if season and season != "All Seasons":
		filters["season"] = season
	analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name"])

	nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
	deficient = {n: 0 for n in nutrients}
	for a in analyses:
		doc = frappe.get_doc("Leaf Analysis", a.name)
		for r in doc.get("nutrient_results", []):
			if r.nutrient in deficient and r.status == "Deficient":
				deficient[r.nutrient] += 1

	return [{"nutrient": n, "count": deficient[n]} for n in nutrients if deficient[n] > 0]


def _is_month_passed(month_name, today_date):
	if month_name not in MONTHS:
		return False
	month_idx = MONTHS.index(month_name) + 1
	year = today_date.year if month_idx <= today_date.month else today_date.year - 1
	month_end = getdate(f"{year}-{month_idx:02d}-28")
	return today_date > month_end


@frappe.whitelist()
def get_block_progress(farm=None, season=None):
	filters = {"docstatus": 1}
	if season:
		filters["season"] = season
	plans = frappe.get_all("Block Fertilizer Plan", filters=filters,
	                        fields=["block", "section", "application_month", "status"])

	today_date = getdate(today())
	priority = {"Behind Schedule": 0, "Pending": 1, "In Progress": 2, "Completed": 3}
	sections = {}

	for p in plans:
		if p.status in ("Applied", "Verified"):
			derived = "Completed"
		elif p.status == "Issued":
			derived = "In Progress"
		elif _is_month_passed(p.application_month, today_date):
			derived = "Behind Schedule"
		else:
			derived = "Pending"

		sec = sections.setdefault(p.section or "Unassigned", {})
		existing = sec.get(p.block)
		if not existing or priority[derived] < priority[existing]:
			sec[p.block] = derived

	result = []
	for section, blocks in sections.items():
		counts = {"Completed": 0, "In Progress": 0, "Pending": 0, "Behind Schedule": 0}
		for status in blocks.values():
			counts[status] += 1
		total = sum(counts.values())
		result.append({
			"section": section, "counts": counts, "total_blocks": total,
			"pct_complete": round(counts["Completed"] / total * 100, 1) if total else 0,
			"blocks": sorted([{"block": b, "status": s} for b, s in blocks.items()], key=lambda r: r["block"]),
		})

	return sorted(result, key=lambda r: r["section"])


@frappe.whitelist()
def get_farm_progress_overview(farm=None, season=None):
	sections = get_block_progress(season=season)
	counts = {"Completed": 0, "In Progress": 0, "Pending": 0, "Behind Schedule": 0}
	total_blocks = 0
	for s in sections:
		for k in counts:
			counts[k] += s["counts"][k]
		total_blocks += s["total_blocks"]

	return {
		"total_sections": len(sections), "total_blocks": total_blocks, "counts": counts,
		"pct_complete": round(counts["Completed"] / total_blocks * 100, 1) if total_blocks else 0,
	}


@frappe.whitelist()
def get_qty_planned_vs_actual(farm=None, season=None):
	prog_filter = {"docstatus": 1}
	if season:
		prog_filter["season"] = season
	programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

	planned = 0
	for prog in programmes:
		doc = frappe.get_doc("Fertilizer Programme", prog.name)
		planned += sum(flt(l.total_kg) for l in doc.get("programme_lines", []))

	plan_filter = {"docstatus": 1}
	if season:
		plan_filter["season"] = season
	plan_names = frappe.get_all("Block Fertilizer Plan", filters=plan_filter, pluck="name")

	actual = 0
	if plan_names:
		actual = flt(frappe.db.sql("""
			select sum(actual_quantity_applied_kg) from `tabFertilizer Application`
			where docstatus = 1 and block_fertilizer_plan in %(plans)s
		""", {"plans": plan_names})[0][0] or 0)

	remaining = max(planned - actual, 0)
	variance = actual - planned

	return {
		"planned_kg": round(planned, 1), "actual_kg": round(actual, 1),
		"remaining_kg": round(remaining, 1), "variance_kg": round(variance, 1),
		"variance_pct": round(variance / planned * 100, 1) if planned else 0,
	}


@frappe.whitelist()
def get_section_usage_breakdown(farm=None, season=None):
	prog_filter = {"docstatus": 1}
	if season:
		prog_filter["season"] = season
	programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

	planned = {}
	for prog in programmes:
		doc = frappe.get_doc("Fertilizer Programme", prog.name)
		for line in doc.get("programme_lines", []):
			planned[line.section] = planned.get(line.section, 0) + flt(line.total_kg)

	conditions = ["fa.docstatus = 1", "bfp.docstatus = 1"]
	values = {}
	if season:
		conditions.append("bfp.season = %(season)s")
		values["season"] = season

	rows = frappe.db.sql(f"""
		select bfp.section as section, sum(fa.actual_quantity_applied_kg) as actual_kg
		from `tabFertilizer Application` fa
		join `tabBlock Fertilizer Plan` bfp on bfp.name = fa.block_fertilizer_plan
		where {" and ".join(conditions)}
		group by bfp.section
	""", values, as_dict=True)
	actual = {r.section: flt(r.actual_kg) for r in rows}

	sections = sorted(set(list(planned.keys()) + list(actual.keys())))
	return [
		{"section": s, "planned_kg": round(planned.get(s, 0), 1), "actual_kg": round(actual.get(s, 0), 1)}
		for s in sections
	]


@frappe.whitelist()
def get_partial_applications(farm=None, season=None):
	filters = {"docstatus": 1, "applied_in_full": 0}
	apps = frappe.get_all("Fertilizer Application", filters=filters,
	                       fields=["name", "block", "fertilizer_product", "application_date",
	                               "planned_quantity_kg", "actual_quantity_applied_kg",
	                               "partial_reason", "block_fertilizer_plan"],
	                       order_by="application_date desc")

	if season:
		plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
		apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

	return _attach_product_names(apps)


@frappe.whitelist()
def get_operator_activity(farm=None, season=None, employees=None, group_by="supervisor"):
	if group_by == "applied_by":
		group_by = "supervisor"
	if group_by not in ("supervisor", "operator"):
		frappe.throw("group_by must be 'supervisor' or 'operator'.")

	if employees and isinstance(employees, str):
		employees = frappe.parse_json(employees)

	if group_by == "operator":
		filters = {"parenttype": "Fertilizer Application"}
		if employees:
			filters["employee"] = ["in", employees]
		rows = frappe.get_all("Fertilizer Application Applicator", filters=filters, fields=["employee", "parent"])
		parents = list({r.parent for r in rows})
		if not parents:
			return []
		apps_by_name = {
			a.name: a for a in frappe.get_all(
				"Fertilizer Application", filters={"docstatus": 1, "name": ["in", parents]},
				fields=["name", "actual_quantity_applied_kg", "block_fertilizer_plan"],
			)
		}
		if season:
			plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
			apps_by_name = {k: v for k, v in apps_by_name.items() if v.block_fertilizer_plan in plan_names}

		stats = {}
		for r in rows:
			app = apps_by_name.get(r.parent)
			if not app:
				continue
			s = stats.setdefault(r.employee, {"applications": 0, "total_kg": 0})
			s["applications"] += 1
			s["total_kg"] += flt(app.actual_quantity_applied_kg)

		return sorted(
			[{"operator": k, "applications": v["applications"], "total_kg": round(v["total_kg"], 1)}
			 for k, v in stats.items()],
			key=lambda x: x["applications"], reverse=True,
		)

	filters = {"docstatus": 1}
	if employees:
		filters["supervisor"] = ["in", employees]
	apps = frappe.get_all("Fertilizer Application", filters=filters,
	                       fields=["supervisor", "actual_quantity_applied_kg", "block_fertilizer_plan"])

	if season:
		plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
		apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

	stats = {}
	for a in apps:
		key = a.supervisor or "Unassigned"
		s = stats.setdefault(key, {"applications": 0, "total_kg": 0})
		s["applications"] += 1
		s["total_kg"] += flt(a.actual_quantity_applied_kg)

	return sorted(
		[{"supervisor": k, "applications": v["applications"], "total_kg": round(v["total_kg"], 1)}
		 for k, v in stats.items()],
		key=lambda x: x["applications"], reverse=True,
	)


@frappe.whitelist()
def get_variance_alerts(farm=None, season=None):
	settings = frappe.get_cached_doc("Crop Nutrition Planning Settings")
	threshold = flt(settings.variance_threshold_pct or 15)

	apps = frappe.get_all("Fertilizer Application", filters={"docstatus": 1},
	                       fields=["name", "block", "fertilizer_product", "application_date",
	                               "planned_quantity_kg", "actual_quantity_applied_kg", "variance_kg",
	                               "block_fertilizer_plan"])

	if season:
		plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
		apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

	alerts = []
	for a in apps:
		if not a.planned_quantity_kg:
			continue
		pct = abs(flt(a.variance_kg)) / flt(a.planned_quantity_kg) * 100
		if pct > threshold:
			alerts.append({**a, "variance_pct": round(pct, 1)})

	_attach_product_names(alerts)
	return sorted(alerts, key=lambda x: x["variance_pct"], reverse=True)


@frappe.whitelist()
def get_computed_budget(farm=None, season=None):
	prog_filter = {"docstatus": 1}
	if season:
		prog_filter["season"] = season
	programme_names = frappe.get_all("Fertilizer Programme", filters=prog_filter, pluck="name")

	required = {}
	if programme_names:
		required = get_grouped_sum("Fertilizer Programme Line", "total_kg", "fertilizer_product",
		                            {"parent": ["in", programme_names]})

	prices = {}
	if required:
		for row in frappe.get_all("Item Price", filters={"item_code": ["in", list(required.keys())], "buying": 1},
		                           fields=["item_code", "price_list_rate"]):
			prices.setdefault(row.item_code, flt(row.price_list_rate))

	lines, total = [], 0
	for product, qty in required.items():
		rate = prices.get(product, 0)
		cost = qty * rate
		total += cost
		lines.append({"product": product, "qty_kg": round(qty, 1), "unit_price": rate, "cost": round(cost, 0)})

	_attach_product_names(lines, "product", "product_name")
	return {"total_cost": round(total, 0), "lines": sorted(lines, key=lambda x: x["cost"], reverse=True)}


# ---------------------------------------------------------------------------
# Fertilizer products
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_product_items(product, farm=None):
	"""Candidate Items for a Fertilizer Product, with stock on hand."""
	doc = frappe.get_doc("Fertilizer Product", product)
	terms = _product_terms(doc)
	if not terms:
		return []

	warehouse = get_farm_warehouse()
	stock_sql = ("(select sum(b.actual_qty) from `tabBin` b where b.item_code = i.name"
	             + (" and b.warehouse = %(wh)s)" if warehouse else ")"))
	conditions = []
	values = {"item_group": doc.item_group or "Fertilizer"}
	if warehouse:
		values["wh"] = warehouse
	for i, term in enumerate(terms):
		conditions.append(f"(i.item_name like %(t{i})s or i.name like %(t{i})s)")
		values[f"t{i}"] = f"%{term}%"

	sql = f"""
		select i.name as item_code, i.item_name, i.stock_uom,
		       coalesce({stock_sql}, 0) as stock_qty
		from `tabItem` i
		where i.item_group = %(item_group)s and i.disabled = 0
		  and ({" or ".join(conditions)})
		order by stock_qty desc, i.item_name asc
	"""
	rows = frappe.db.sql(sql, values, as_dict=True)

	excludes = [e.lower() for e in _product_excludes(doc)]
	if excludes:
		rows = [
			r for r in rows
			if not any(e in (r.item_name or "").lower() or e in (r.item_code or "").lower() for e in excludes)
		]
	return rows


@frappe.whitelist()
def load_programme_products(programme):
	"""List the products this crop needs, leaving the Item for each
	unchosen - which Item to draw from is the agronomist's own call."""
	doc = frappe.get_doc("Fertilizer Programme", programme)
	if doc.docstatus == 1:
		frappe.throw("Cannot change products on a submitted programme.")

	nutrient_rules = frappe.get_all("Crop Nutrient Rule", filters={"crop": doc.crop}, fields=["fertilizer_product"])
	products, seen = [], set()
	for rule in nutrient_rules:
		if rule.fertilizer_product and rule.fertilizer_product not in seen:
			seen.add(rule.fertilizer_product)
			products.append(rule.fertilizer_product)

	if not products:
		frappe.throw(
			f"No nutrient rule on crop {doc.crop} names a Fertilizer Product yet. "
			"Set the Fertilizer Product field on the crop's nutrient rules first."
		)

	wh = get_farm_warehouse()
	already = {r.product: r.fertilizer_item for r in doc.get("product_selections", []) if r.fertilizer_item}
	doc.set("product_selections", [])
	for product in products:
		chosen = already.get(product)
		doc.append("product_selections", {
			"product": product, "fertilizer_item": chosen,
			"available_qty": get_stock_qty(chosen, wh) if chosen else 0,
		})
	doc.save()
	return {"products": products, "already_chosen": len(already)}


@frappe.whitelist()
def get_product_choices(programme, product):
	doc = frappe.get_doc("Fertilizer Programme", programme)
	nutrient_rules = frappe.get_all(
		"Crop Nutrient Rule",
		filters={"crop": doc.crop},
		fields=["fertilizer_product", "nutrient", "rate_per_tonne", "bag_weight_kg",
				"product_nutrient_pct", "apply_compost_netting", "nutrient_source_group"],
	)

	rule = None
	for row in nutrient_rules:
		if row.fertilizer_product == product:
			rule = {
				"nutrient": row.nutrient, "rate_per_tonne": row.rate_per_tonne,
				"bag_weight_kg": row.bag_weight_kg, "product_nutrient_pct": row.product_nutrient_pct,
				"apply_compost_netting": row.apply_compost_netting,
				"nutrient_source_group": row.nutrient_source_group, "rule_item": row.fertilizer_product,
			}
			break

	current = next((r.fertilizer_item for r in doc.get("product_selections", []) if r.product == product), None)
	return {"product": product, "rule": rule, "current": current, "options": get_product_items(product)}


@frappe.whitelist()
def set_product_item(programme, product, item):
	doc = frappe.get_doc("Fertilizer Programme", programme)
	if doc.docstatus == 1:
		frappe.throw("Cannot change products on a submitted programme.")

	wh = get_farm_warehouse()
	allowed = {o["item_code"] for o in get_product_items(product)}
	if item not in allowed:
		frappe.throw(f"{item} is not one of the Items that match {product}. Adjust the product's search terms if it should be.")

	for row in doc.get("product_selections", []):
		if row.product == product:
			row.fertilizer_item = item
			row.available_qty = get_stock_qty(item, wh)
			break
	else:
		doc.append("product_selections", {"product": product, "fertilizer_item": item, "available_qty": get_stock_qty(item, wh)})
	doc.save()
	return {"item": item, "available_qty": get_stock_qty(item, wh)}


# ---------------------------------------------------------------------------
# Pushed applications
# ---------------------------------------------------------------------------

@frappe.whitelist()
def push_application(plan, reason=None, scope="product"):
	"""Push a round that didn't happen, and everything after it, one month on."""
	doc = frappe.get_doc("Block Fertilizer Plan", plan)
	if doc.status in ("Applied", "Verified"):
		frappe.throw(f"{plan} is already {doc.status} - there is nothing to push.")

	filters = {
		"fertilizer_programme": doc.fertilizer_programme, "block": doc.block,
		"docstatus": ["<", 2], "status": ["in", ["Planned", "Issued"]],
	}
	if scope == "product":
		filters["fertilizer_product"] = doc.fertilizer_product

	siblings = frappe.get_all("Block Fertilizer Plan", filters=filters,
	                           fields=["name", "application_month", "application_year"])

	base_year = cint(doc.application_year) or _season_start_year(doc.season)

	def position(row):
		year = cint(row.application_year) or base_year
		return (year, MONTHS.index(row.application_month) if row.application_month in MONTHS else 0)

	here = position(frappe._dict({
		"application_month": doc.application_month,
		"application_year": doc.application_year or base_year,
	}))
	affected = sorted([r for r in siblings if position(r) >= here], key=position, reverse=True)

	moved = 0
	for row in affected:
		target = frappe.get_doc("Block Fertilizer Plan", row.name)
		year = cint(target.application_year) or base_year
		index = MONTHS.index(target.application_month) if target.application_month in MONTHS else 0
		index += 1
		if index > 11:
			index, year = 0, year + 1

		if not target.original_month:
			target.original_month = target.application_month
		target.application_month = MONTHS[index]
		target.application_year = year
		target.times_pushed = cint(target.times_pushed) + 1
		if target.name == doc.name and reason:
			target.push_reason = reason
		target.save(ignore_permissions=True)
		moved += 1

	frappe.db.commit()
	return {"moved": moved, "scope": scope}


def _season_start_year(season):
	import re
	match = re.search(r"(\d{4})", season or "")
	return cint(match.group(1)) if match else cint(frappe.utils.nowdate()[:4])


# ---------------------------------------------------------------------------
# The Agronomist Desk
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_agronomist_desk(season=None, farm=None):
	prog_filter = {}
	if season and season != "All Seasons":
		prog_filter["season"] = season

	fields = ["name", "season", "farm", "crop", "docstatus",
	          "period_type", "start_month", "end_month",
	          "production_calendar", "modified"]
	programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=fields,
	                             order_by="modified desc", limit_page_length=20)

	current = next((p for p in programmes if p.docstatus == 0), None) or (programmes[0] if programmes else None)
	detail = _build_programme_detail(current["name"]) if current else None

	return {
		"farm": _the_farm(),
		"farms": get_available_farms(),
		"seasons": get_seasons(),
		"metrics": get_home_metrics(),
		"programmes": programmes,
		"current": detail,
	}


def _build_programme_detail(programme_name):
	doc = frappe.get_doc("Fertilizer Programme", programme_name)
	nutrient_by_product = {
		fp.name: fp.nutrient for fp in frappe.get_all("Fertilizer Product", fields=["name", "nutrient"])
	}
	return {
		"name": doc.name, "season": doc.season, "farm": doc.farm, "crop": doc.crop,
		"docstatus": doc.docstatus,
		"period_type": doc.period_type, "start_month": doc.start_month, "end_month": doc.end_month,
		"production_calendar": doc.production_calendar,
		"blocks": len(doc.get("block_yield_data") or []),
		"lines": len(doc.get("programme_lines") or []),
		"sections": sorted({b.section for b in doc.get("block_yield_data") or [] if b.section}),
		"products": [
			{
				"product": r.product, "nutrient": nutrient_by_product.get(r.product),
				"item": r.fertilizer_item, "item_name": r.item_name,
				"available": flt(r.available_qty), "required": flt(r.required_qty), "shortfall": flt(r.shortfall),
			}
			for r in doc.get("product_selections") or []
		],
		"actions": _programme_actions(doc),
	}


@frappe.whitelist()
def get_programme_detail(programme):
	return _build_programme_detail(programme)


def _programme_actions(doc):
	"""What can be done to this programme right now, and what is blocking the
	rest - the page renders buttons from this, so the desk and server can
	never disagree about what is allowed."""
	if doc.docstatus != 0:
		return {"editable": False, "next": None, "blocked": "This programme is approved. Amend it by creating the next one."}

	blocks = len(doc.get("block_yield_data") or [])
	products = doc.get("product_selections") or []
	unchosen = [r.product for r in products if not r.fertilizer_item]
	lines = len(doc.get("programme_lines") or [])

	steps = [
		{"key": "pull_blocks", "label": "Pull blocks from farm", "done": blocks > 0, "detail": f"{blocks} blocks"},
		{"key": "load_products", "label": "Load products", "done": bool(products),
		 "detail": f"{len(products)} products" if products else "none yet"},
		{"key": "choose_items", "label": "Choose an item per product",
		 "done": bool(products) and not unchosen,
		 "detail": ("waiting on products" if not products else ", ".join(unchosen) if unchosen else "all chosen")},
		{"key": "calculate", "label": "Run the calculation", "done": lines > 0, "detail": f"{lines} lines"},
	]

	nxt = next((s["key"] for s in steps if not s["done"]), None)
	# No approval chain on Mutara - a calculated programme submits directly.
	# Product/item choice is a stock check that doesn't feed the calculation,
	# so it's shown as a step but doesn't hold up submission.
	ready = blocks > 0 and lines > 0

	return {
		"editable": True, "steps": steps, "next": nxt,
		"ready_to_send": ready,
		"blocked": None,
	}


@frappe.whitelist()
def desk_pull_blocks(programme):
	"""Pull the blocks in this programme's scope onto it."""
	doc = frappe.get_doc("Fertilizer Programme", programme)
	if doc.docstatus != 0:
		frappe.throw("Only a Draft programme's blocks can be pulled.")
	return {"blocks": doc.pull_blocks_from_farm()}


@frappe.whitelist()
def desk_calculate(programme):
	lines = calculate_programme(programme)
	return {"lines": lines}


@frappe.whitelist()
def desk_get_rate_grid(programme):
	"""The manual block-by-block rate override grid is a separate feature on
	top of the engine's own output - not built yet."""
	return CALC_ENGINE_PENDING


@frappe.whitelist()
def desk_save_rates(programme, rates):
	return CALC_ENGINE_PENDING


@frappe.whitelist()
def export_programme_excel(programme, section=None):
	frappe.throw("Programme export isn't available yet - it depends on the calculation engine, which is coming in the next phase.")


@frappe.whitelist()
def desk_delete_draft(programme):
	doc = frappe.get_doc("Fertilizer Programme", programme)
	doc.check_permission("delete")
	if doc.docstatus != 0:
		frappe.throw("Only a Draft programme can be deleted this way - cancel a submitted one first.")
	frappe.delete_doc("Fertilizer Programme", programme, ignore_permissions=True)
	return {"deleted": programme}


@frappe.whitelist()
def get_plan_queue(season=None, farm=None, limit=200):
	conditions = ["p.docstatus = 1", "p.status in ('Planned', 'Issued')"]
	values = {"limit": cint(limit) or 200}
	if season and season != "All Seasons":
		conditions.append("p.season = %(season)s")
		values["season"] = season

	return frappe.db.sql(f"""
		select p.block, p.section, count(*) as rounds,
		       sum(case when p.status = 'Issued' then 1 else 0 end) as issued,
		       sum(p.total_kg_required) as total_kg, min(p.application_month) as next_month
		from `tabBlock Fertilizer Plan` p
		where {" and ".join(conditions)}
		group by p.block, p.section
		order by rounds desc, p.block asc
		limit %(limit)s
	""", values, as_dict=True)


@frappe.whitelist()
def desk_submit_programme(programme):
	"""Submit the programme directly - on_submit creates its Block
	Fertilizer Plans."""
	doc = frappe.get_doc("Fertilizer Programme", programme)
	if doc.docstatus == 1:
		return {"docstatus": 1, "already": True}
	if not doc.get("programme_lines"):
		frappe.throw("Run the calculation before submitting - there are no programme lines yet.")
	doc.submit()
	doc.reload()
	return {"docstatus": doc.docstatus}


@frappe.whitelist()
def search_fertilizer_items(search=None, farm=None, limit=40):
	warehouse = get_farm_warehouse()
	conditions = ["i.disabled = 0", "i.item_group = 'Fertilizer'"]
	values = {"limit": cint(limit) or 40}
	if warehouse:
		values["wh"] = warehouse
	stock_sql = ("(select sum(b.actual_qty) from `tabBin` b where b.item_code = i.name"
	             + (" and b.warehouse = %(wh)s)" if warehouse else ")"))
	if search and str(search).strip():
		conditions.append("(i.item_name like %(q)s or i.name like %(q)s)")
		values["q"] = f"%{str(search).strip()}%"

	return frappe.db.sql(f"""
		select i.name as item_code, i.item_name, i.stock_uom,
		       coalesce({stock_sql}, 0) as stock_qty
		from `tabItem` i
		where {" and ".join(conditions)}
		order by stock_qty desc, i.item_name asc
		limit %(limit)s
	""", values, as_dict=True)


@frappe.whitelist()
def get_desk_blocks(season=None, farm=None):
	blocks = frappe.get_all(
		"Farm Block", fields=["name", "section", "farm", "area_ha", "tree_count", "projected_yield_kg_ha"],
		order_by="name asc", limit_page_length=0,
	)

	conditions = ["docstatus = 1"]
	values = {}
	if season and season != "All Seasons":
		conditions.append("season = %(season)s")
		values["season"] = season

	stats = {r.block: r for r in frappe.db.sql(f"""
		select block, count(*) as rounds,
		       sum(case when status in ('Applied','Verified') then 1 else 0 end) as done,
		       sum(case when status = 'Issued' then 1 else 0 end) as issued,
		       sum(total_kg_required) as planned_kg
		from `tabBlock Fertilizer Plan`
		where {" and ".join(conditions)}
		group by block
	""", values, as_dict=True)}

	out = []
	for b in blocks:
		s = stats.get(b.name)
		rounds = cint(s.rounds) if s else 0
		done = cint(s.done) if s else 0
		out.append({
			"block": b.name, "section": b.section, "farm": b.farm,
			"area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count),
			"last_yield": flt(b.projected_yield_kg_ha),
			"rounds": rounds, "done": done, "issued": cint(s.issued) if s else 0,
			"planned_kg": flt(s.planned_kg) if s else 0,
			"pct": round(done * 100.0 / rounds, 0) if rounds else 0,
			"state": ("Completed" if rounds and done == rounds
			          else "In progress" if done
			          else "Not started" if rounds else "No plan"),
		})
	return out


@frappe.whitelist()
def get_block_detail(block, season=None):
	info = frappe.db.get_value(
		"Farm Block", block,
		["name", "section", "farm", "area_ha", "tree_count", "projected_yield_kg_ha", "crop", "cost_center"],
		as_dict=True,
	)
	if not info:
		frappe.throw(f"No such block: {block}")

	filters = {"block": block, "docstatus": 1}
	if season and season != "All Seasons":
		filters["season"] = season
	plans = frappe.get_all(
		"Block Fertilizer Plan", filters=filters,
		fields=["name", "fertilizer_product", "application_month", "application_year",
		        "total_kg_required", "dose_per_tree_g", "application_rate_kg_ha",
		        "status", "yield_tier", "original_month", "times_pushed"],
		order_by="application_year asc, name asc",
	)
	_attach_product_names(plans)

	applied = frappe.get_all(
		"Fertilizer Application", filters={"block": block, "docstatus": 1},
		fields=["name", "fertilizer_product", "application_date", "actual_quantity_applied_kg",
		        "planned_quantity_kg", "variance_kg", "applied_in_full", "supervisor_name"],
		order_by="application_date desc", limit_page_length=50,
	)
	_attach_product_names(applied)

	planned_kg = sum(flt(p.total_kg_required) for p in plans)
	actual_kg = sum(flt(a.actual_quantity_applied_kg) for a in applied)
	done = len([p for p in plans if p.status in ("Applied", "Verified")])

	dose_by_product = {}
	for p in plans:
		row = dose_by_product.setdefault(p.fertilizer_product, {
			"product": p.fertilizer_product,
			"product_name": p.fertilizer_product_name or p.fertilizer_product,
			"dose_per_tree_g": 0,
		})
		row["dose_per_tree_g"] += flt(p.dose_per_tree_g)
	for row in dose_by_product.values():
		row["dose_per_tree_g"] = round(row["dose_per_tree_g"], 1)
	dose_by_product = sorted(dose_by_product.values(), key=lambda r: r["product_name"])

	peers = frappe.get_all("Farm Block", filters={"farm": info.farm}, pluck="projected_yield_kg_ha") or []
	peers = [flt(y) for y in peers if flt(y) > 0]
	best = max(peers) if peers else 0
	avg = (sum(peers) / len(peers)) if peers else 0

	return {
		"info": info, "plans": plans, "applied": applied,
		"planned_kg": round(planned_kg, 1), "actual_kg": round(actual_kg, 1),
		"dose_by_product": dose_by_product,
		"rounds": len(plans), "done": done,
		"pct": round(done * 100.0 / len(plans), 0) if plans else 0,
		"yield": {
			"block": flt(info.projected_yield_kg_ha), "farm_best": round(best, 0), "farm_avg": round(avg, 0),
			"vs_avg_pct": round((flt(info.projected_yield_kg_ha) - avg) / avg * 100, 0) if avg else 0,
		},
	}


@frappe.whitelist()
def get_desk_store_requests(limit=200, farm=None):
	rows = frappe.get_all(
		"Fertilizer Store Request",
		fields=["name", "block", "application_month", "fertilizer_product", "quantity_requested_kg",
		        "requested_by", "request_date", "status", "docstatus", "storekeeper"],
		order_by="request_date desc, name desc", limit_page_length=cint(limit) or 200,
	)
	for r in rows:
		if r.get("requested_by"):
			r["employee_name"] = frappe.db.get_value("Employee", r["requested_by"], "employee_name")
	return _attach_product_names(rows)


@frappe.whitelist()
def get_desk_applications(season=None, limit=100, farm=None):
	filters = {"docstatus": 1}
	rows = frappe.get_all(
		"Fertilizer Application", filters=filters,
		fields=["name", "block", "fertilizer_product", "application_date", "planned_quantity_kg",
		        "actual_quantity_applied_kg", "variance_kg", "applied_in_full", "partial_reason",
		        "application_method", "weather_conditions", "supervisor", "supervisor_name",
		        "block_fertilizer_plan", "material_request"],
		order_by="application_date desc, modified desc", limit_page_length=cint(limit) or 100,
	)
	if season and season != "All Seasons":
		names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
		rows = [r for r in rows if r.block_fertilizer_plan in names]
	_attach_product_names(rows)

	for r in rows:
		applicators = frappe.get_all("Fertilizer Application Applicator", filters={"parent": r.name},
		                              fields=["employee_name"], pluck="employee_name")
		r["applicators"] = [a for a in applicators if a]
	return rows


@frappe.whitelist()
def get_variance_by_section(season=None, farm=None):
	conditions = ["bfp.docstatus = 1"]
	values = {}
	if season and season != "All Seasons":
		conditions.append("bfp.season = %(season)s")
		values["season"] = season

	rows = frappe.db.sql(f"""
		select bfp.section, sum(bfp.total_kg_required) as planned,
		       coalesce(sum(fa.actual_quantity_applied_kg), 0) as actual,
		       count(distinct bfp.block) as blocks
		from `tabBlock Fertilizer Plan` bfp
		left join `tabFertilizer Application` fa on fa.block_fertilizer_plan = bfp.name and fa.docstatus = 1
		where {" and ".join(conditions)}
		group by bfp.section
		order by bfp.section asc
	""", values, as_dict=True)

	for r in rows:
		r["variance"] = round(flt(r.actual) - flt(r.planned), 1)
		r["pct"] = round(flt(r.actual) / flt(r.planned) * 100, 0) if flt(r.planned) else 0
	return rows


@frappe.whitelist()
def get_variance_by_block(section, season=None, farm=None):
	conditions = ["bfp.docstatus = 1", "bfp.section = %(section)s"]
	values = {"section": section}
	if season and season != "All Seasons":
		conditions.append("bfp.season = %(season)s")
		values["season"] = season

	rows = frappe.db.sql(f"""
		select bfp.block, sum(bfp.total_kg_required) as planned,
		       coalesce(sum(fa.actual_quantity_applied_kg), 0) as actual
		from `tabBlock Fertilizer Plan` bfp
		left join `tabFertilizer Application` fa on fa.block_fertilizer_plan = bfp.name and fa.docstatus = 1
		where {" and ".join(conditions)}
		group by bfp.block
		order by bfp.block asc
	""", values, as_dict=True)
	for r in rows:
		r["variance"] = round(flt(r.actual) - flt(r.planned), 1)
		r["pct"] = round(flt(r.actual) / flt(r.planned) * 100, 0) if flt(r.planned) else 0
	return rows


@frappe.whitelist()
def get_desk_stock(season=None, farm=None):
	warehouse = get_farm_warehouse()
	conditions = ["p.docstatus = 1", "p.status in ('Planned','Issued')"]
	values = {}
	if season and season != "All Seasons":
		conditions.append("p.season = %(season)s")
		values["season"] = season

	need = {r.fertilizer_product: flt(r.kg) for r in frappe.db.sql(f"""
		select fertilizer_product, sum(total_kg_required) as kg
		from `tabBlock Fertilizer Plan` p
		where {" and ".join(conditions)}
		group by fertilizer_product
	""", values, as_dict=True)}

	items = frappe.get_all("Item", filters={"item_group": "Fertilizer", "disabled": 0},
	                        fields=["name", "item_name", "stock_uom"], limit_page_length=0)
	bin_filters = {"item_code": ["in", [i.name for i in items]]} if items else {}
	if warehouse:
		bin_filters["warehouse"] = warehouse
	stock = get_grouped_sum("Bin", "actual_qty", "item_code", bin_filters) if items else {}

	out = []
	for i in items:
		held = flt(stock.get(i.name, 0))
		required = flt(need.get(i.name, 0))
		if not required and held <= 0:
			continue
		out.append({
			"item_code": i.name, "item_name": i.item_name, "uom": i.stock_uom,
			"stock": round(held, 1), "required": round(required, 1),
			"shortfall": round(max(required - held, 0), 1), "sufficient": held >= required,
			"in_programme": bool(required), "pct": round(held / required * 100, 0) if required else None,
		})
	out.sort(key=lambda r: (not r["in_programme"], r["sufficient"], -r["shortfall"]))
	return out


@frappe.whitelist()
def get_programme_summary(programme):
	doc = frappe.get_doc("Fertilizer Programme", programme)

	monthly = {m: 0.0 for m in MONTHS}
	for line in doc.get("programme_lines", []):
		if line.application_month in monthly:
			monthly[line.application_month] += flt(line.total_kg)
	months = [{"month": m[:3], "qty": round(q, 0)} for m, q in monthly.items() if q]

	prices, cost = {}, 0.0
	for row in doc.get("product_selections", []):
		if not row.fertilizer_item:
			continue
		if row.fertilizer_item not in prices:
			prices[row.fertilizer_item] = flt(frappe.db.get_value(
				"Item Price", {"item_code": row.fertilizer_item, "buying": 1}, "price_list_rate"))
		cost += flt(row.required_qty) * prices[row.fertilizer_item]

	plans = frappe.get_all("Block Fertilizer Plan",
	                        filters={"fertilizer_programme": programme, "docstatus": 1},
	                        fields=["status", "application_month"])
	total_rounds = len(plans)
	applied_rounds = sum(1 for p in plans if p.status in ("Applied", "Verified"))
	today_date = getdate(today())
	overdue_rounds = sum(
		1 for p in plans if p.status in ("Planned", "Issued") and _is_month_passed(p.application_month, today_date)
	)

	pending_requests = frappe.db.count(
		"Fertilizer Store Request",
		{"block_fertilizer_plan": ["in", frappe.get_all("Block Fertilizer Plan",
		                                                 filters={"fertilizer_programme": programme}, pluck="name") or [""]],
		 "status": ["not in", ["Issued", "Rejected"]]},
	)

	return {
		"monthly": months, "total_rounds": total_rounds, "applied_rounds": applied_rounds,
		"pct_applied": round(applied_rounds * 100.0 / total_rounds, 0) if total_rounds else 0,
		"overdue_rounds": overdue_rounds, "cost_estimate": round(cost, 0),
		"pending_requests": pending_requests,
	}


@frappe.whitelist()
def get_field_programmes(farm=None):
	return frappe.get_all(
		"Fertilizer Programme", filters={"docstatus": 1},
		fields=["name", "season", "farm", "crop", "period_type", "start_month", "end_month"],
		order_by="modified desc",
	)


@frappe.whitelist()
def get_section_overview(section, season=None):
	sec = frappe.db.get_value("Section", section, ["name", "section_name", "farm", "company", "is_active"], as_dict=True)
	if not sec:
		frappe.throw(f"No such section: {section}")

	blocks = frappe.get_all(
		"Farm Block", filters={"section": section},
		fields=["name", "block_number", "area_ha", "tree_count", "projected_yield_kg_ha", "crop", "variety", "planting_year"],
		order_by="name asc", limit_page_length=0,
	)

	stats = {}
	if blocks:
		conditions = ["docstatus = 1", "block in %(blocks)s"]
		values = {"blocks": [b.name for b in blocks]}
		if season and season != "All Seasons":
			conditions.append("season = %(season)s")
			values["season"] = season
		stats = {r.block: r for r in frappe.db.sql(f"""
			select block, count(*) as rounds,
			       sum(case when status in ('Applied','Verified') then 1 else 0 end) as done,
			       sum(total_kg_required) as planned_kg
			from `tabBlock Fertilizer Plan`
			where {" and ".join(conditions)}
			group by block
		""", values, as_dict=True)}

	out, total_rounds, total_done = [], 0, 0
	for b in blocks:
		s = stats.get(b.name)
		rounds = cint(s.rounds) if s else 0
		done = cint(s.done) if s else 0
		total_rounds += rounds
		total_done += done
		out.append({
			"block": b.name, "block_number": b.block_number,
			"area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count),
			"last_yield": flt(b.projected_yield_kg_ha),
			"crop": b.crop, "variety": b.variety, "planting_year": b.planting_year,
			"rounds": rounds, "done": done, "planned_kg": round(flt(s.planned_kg), 1) if s else 0,
			"pct": round(done * 100.0 / rounds, 0) if rounds else 0,
			"state": ("Completed" if rounds and done == rounds
			          else "In progress" if done
			          else "Not started" if rounds else "No plan"),
		})

	yields = [b["last_yield"] for b in out if b["last_yield"] > 0]
	return {
		"section": sec, "blocks": out,
		"totals": {
			"blocks": len(out), "area_ha": round(sum(b["area_ha"] for b in out), 2),
			"trees": sum(b["tree_count"] for b in out),
			"avg_yield": round(sum(yields) / len(yields), 0) if yields else 0,
			"rounds": total_rounds, "done": total_done,
			"pct": round(total_done * 100.0 / total_rounds, 0) if total_rounds else 0,
		},
	}


@frappe.whitelist()
def get_active_supervisors(window=15, farm=None):
	"""Supervisors, with whether they're using the field app right now.
	Presence comes from utils/presence.py, since the app's token logins
	leave no Frappe session to read."""
	import time
	from mutaracnp.mutaracnp.utils.presence import read_presence

	presence = read_presence()
	window = cint(window) or 15

	team_counts = {r.sup: r.n for r in frappe.db.sql("""
		select custom_field_supervisor as sup, count(*) as n from `tabEmployee`
		where status = 'Active' and ifnull(custom_field_supervisor, '') != ''
		group by custom_field_supervisor
	""", as_dict=True)}

	worker_users = frappe.get_all("Has Role", filters={"role": "Field Worker", "parenttype": "User"}, pluck="parent")
	by_user = {}
	if worker_users:
		by_user = {r.name: r for r in frappe.get_all(
			"Employee", filters={"user_id": ["in", worker_users], "status": "Active"},
			fields=["name", "user_id"])}

	candidates = set(team_counts)
	for emp in by_user.values():
		if emp.user_id in presence:
			candidates.add(emp.name)
	if not candidates:
		return {"supervisors": [], "summary": {"online": 0, "today": 0, "total": 0}, "window": window}

	sups = list(candidates)
	emps = {e.name: e for e in frappe.get_all(
		"Employee", filters={"name": ["in", sups], "status": "Active"},
		fields=["name", "employee_name", "employee_number", "user_id", "company"])}
	sups = list(emps)

	team = {}
	for r in frappe.get_all(
		"Employee", filters={"custom_field_supervisor": ["in", sups], "status": "Active"},
		fields=["custom_field_supervisor", "name", "employee_name", "custom_assigned_block"],
		order_by="employee_name asc", limit_page_length=0,
	):
		team.setdefault(r.custom_field_supervisor, []).append(
			{"name": r.employee_name or r.name, "block": r.custom_assigned_block})

	day = today()
	apps = {r.supervisor: r for r in frappe.db.sql("""
		select supervisor, count(*) as n, coalesce(sum(actual_quantity_applied_kg), 0) as kg
		from `tabFertilizer Application`
		where docstatus = 1 and application_date = %(d)s and supervisor in %(s)s
		group by supervisor""", {"d": day, "s": sups}, as_dict=True)}
	marked = {r.marked_by: r.n for r in frappe.db.sql("""
		select marked_by, count(*) as n from `tabField Attendance`
		where attendance_date = %(d)s and marked_by in %(s)s
		group by marked_by""", {"d": day, "s": sups}, as_dict=True)}

	n = now_datetime()
	since_midnight = n.hour * 3600 + n.minute * 60 + n.second
	now_ts = time.time()

	out = []
	for name in sups:
		e = emps[name]
		seen = presence.get(e.user_id) if e.user_id else None
		age = (now_ts - seen["ts"]) if seen else None
		state = ("none" if age is None
		         else "online" if age <= window * 60
		         else "today" if age <= since_midnight
		         else "away")
		a = apps.get(name)
		rows = team.get(name, [])
		out.append({
			"employee": name, "user": e.user_id, "name": e.employee_name, "number": e.employee_number,
			"state": state, "age_seconds": int(age) if age is not None else None,
			"via": seen["via"] if seen else None, "last_method": seen["method"] if seen else None,
			"team_size": len(rows), "team": rows[:30],
			"blocks": sorted({m["block"] for m in rows if m["block"]})[:6],
			"apps_today": cint(a.n) if a else 0, "kg_today": round(flt(a.kg), 1) if a else 0,
			"attendance_today": cint(marked.get(name, 0)),
		})

	order = {"online": 0, "today": 1, "away": 2, "none": 3}
	out.sort(key=lambda r: (order[r["state"]], r["age_seconds"] if r["age_seconds"] is not None else 1e12, r["name"] or ""))
	return {
		"supervisors": out,
		"summary": {
			"online": sum(1 for r in out if r["state"] == "online"),
			"today": sum(1 for r in out if r["state"] in ("online", "today")),
			"total": len(out),
		},
		"window": window,
	}
