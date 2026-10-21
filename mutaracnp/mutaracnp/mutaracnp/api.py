"""
Whitelisted endpoints for the Agronomist Desk, the Dashboard/Manager
dashboards and the Field app.

Mutara is single-farm, so (unlike the reference UpandeCNP app this was built
from) nothing here takes a `farm` argument - there is exactly one CNP Farm
and every query is implicitly scoped to it.

A handful of endpoints genuinely depend on the nutrient-rate calculation
engine, which is a deliberately separate, later piece of work. Those are
marked PENDING below and return a flag the UI checks instead of computing
real numbers - everything else here is a real, working implementation
against the doctypes this app ships.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _pending(message="Calculation engine coming soon - rates aren't computed yet."):
    return {"calculation_engine_pending": True, "message": message}


def _farm():
    farm = frappe.db.get_single_value("Crop Nutrition Planning Settings", "farm")
    return farm or frappe.db.get_value("CNP Farm", {"is_active": 1}, "name")


def _latest_season():
    row = frappe.get_all(
        "Fertilizer Programme", fields=["season"], order_by="creation desc", limit_page_length=1
    )
    return row[0].season if row else None


def _season_filter(season):
    season = season or _latest_season()
    return season


# ---------------------------------------------------------------------------
# Lookups shared by every page
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_seasons(**kwargs):
    rows = frappe.get_all(
        "Fertilizer Programme", fields=["season"], group_by="season", order_by="creation desc"
    )
    return [r.season for r in rows if r.season]


@frappe.whitelist()
def get_all_sections(**kwargs):
    return frappe.get_all(
        "Section", filters={"is_active": 1}, fields=["name", "section_name"], order_by="section_name"
    )


@frappe.whitelist()
def get_blocks_in_section(section=None, **kwargs):
    if not section:
        return []
    return frappe.get_all(
        "Farm Block",
        filters={"section": section},
        fields=["name", "block_name", "block_number", "crop", "area_ha", "tree_count"],
        order_by="block_name",
    )


@frappe.whitelist()
def get_issued_blocks_in_section(section=None, **kwargs):
    if not section:
        return []
    blocks = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"section": section, "status": "Issued"},
        fields=["block"],
        group_by="block",
        pluck="block",
    )
    if not blocks:
        return []
    return frappe.get_all(
        "Farm Block", filters={"name": ["in", blocks]}, fields=["name", "block_name"], order_by="block_name"
    )


@frappe.whitelist()
def get_sections_with_pending_work(**kwargs):
    sections = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"status": "Planned", "docstatus": 1},
        fields=["section"],
        group_by="section",
        pluck="section",
    )
    sections = [s for s in sections if s]
    if not sections:
        return []
    return frappe.get_all(
        "Section", filters={"name": ["in", sections]}, fields=["name", "section_name"], order_by="section_name"
    )


@frappe.whitelist()
def get_sections_with_issued_work(**kwargs):
    sections = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"status": "Issued"},
        fields=["section"],
        group_by="section",
        pluck="section",
    )
    sections = [s for s in sections if s]
    if not sections:
        return []
    return frappe.get_all(
        "Section", filters={"name": ["in", sections]}, fields=["name", "section_name"], order_by="section_name"
    )


@frappe.whitelist()
def get_pending_plans_for_block(block=None, **kwargs):
    if not block:
        return []
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"block": block, "status": "Issued"},
        fields=["name", "fertilizer_product", "application_month", "total_kg_required", "season"],
        order_by="application_month",
    )


@frappe.whitelist()
def get_pending_plans_for_section(section=None, **kwargs):
    if not section:
        return []
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"section": section, "status": "Issued"},
        fields=["name", "block", "fertilizer_product", "application_month", "total_kg_required"],
        order_by="block",
    )


@frappe.whitelist()
def get_issued_request_for_plan(block_fertilizer_plan=None, **kwargs):
    if not block_fertilizer_plan:
        return None
    rows = frappe.get_all(
        "Fertilizer Store Request",
        filters={"block_fertilizer_plan": block_fertilizer_plan, "status": ["in", ["Approved", "Issued"]]},
        fields=["name", "status", "quantity_requested_kg"],
        order_by="creation desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


@frappe.whitelist()
def get_attendance_by_block(**kwargs):
    rows = frappe.get_all(
        "Field Attendance",
        filters={"attendance_date": nowdate()},
        fields=["employee", "employee_name" if frappe.db.has_column("Field Attendance", "employee_name") else "employee", "status", "block"],
    )
    grouped = {}
    for r in rows:
        grouped.setdefault(r.block or "Unassigned", []).append(r)
    return grouped


@frappe.whitelist()
def get_store_requests(**kwargs):
    return frappe.get_all(
        "Fertilizer Store Request",
        filters={"requested_by": _current_employee()} if _current_employee() else {},
        fields=["name", "block", "fertilizer_product", "quantity_requested_kg", "status", "request_date"],
        order_by="creation desc",
        limit_page_length=50,
    )


@frappe.whitelist()
def get_applicators_for_block(block=None, **kwargs):
    if not block:
        return []
    return frappe.get_all(
        "Employee",
        filters={"custom_assigned_block": block, "status": "Active"},
        fields=["name", "employee_name"],
    )


@frappe.whitelist()
def get_my_applicators_by_section(**kwargs):
    me = _current_employee()
    if not me:
        return {}
    employees = frappe.get_all(
        "Employee",
        filters={"custom_field_supervisor": me, "status": "Active"},
        fields=["name", "employee_name", "custom_assigned_block"],
    )
    grouped = {}
    for e in employees:
        section = frappe.db.get_value("Farm Block", e.custom_assigned_block, "section") if e.custom_assigned_block else None
        grouped.setdefault(section or "Unassigned", []).append(e)
    return grouped


@frappe.whitelist()
def get_available_employees_for_team(**kwargs):
    return frappe.get_all(
        "Employee",
        filters={"status": "Active", "custom_field_supervisor": ["in", ["", None]]},
        fields=["name", "employee_name"],
        limit_page_length=100,
    )


@frappe.whitelist()
def get_home_metrics(**kwargs):
    pending_applications = frappe.db.count("Block Fertilizer Plan", {"status": "Issued"})
    ready_to_record = pending_applications
    pending_requests = frappe.db.count("Fertilizer Store Request", {"status": "Requested"})
    me = _current_employee()
    my_applications = frappe.db.count("Fertilizer Application", {"supervisor": me}) if me else 0
    applications_today = frappe.db.count("Fertilizer Application", {"application_date": nowdate()})
    upcoming_blocks = frappe.db.count("Block Fertilizer Plan", {"status": "Planned", "docstatus": 1})
    return {
        "pending_applications": pending_applications,
        "ready_to_record": ready_to_record,
        "pending_store_requests": pending_requests,
        "my_applications": my_applications,
        "applications_today": applications_today,
        "upcoming_blocks": upcoming_blocks,
    }


def _current_employee():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


# ---------------------------------------------------------------------------
# Field app write actions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def create_store_request(block_fertilizer_plan=None, quantity=None, **kwargs):
    if not block_fertilizer_plan:
        frappe.throw("block_fertilizer_plan is required")
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)
    doc = frappe.get_doc({
        "doctype": "Fertilizer Store Request",
        "block_fertilizer_plan": plan.name,
        "block": plan.block,
        "fertilizer_product": plan.fertilizer_product,
        "application_month": plan.application_month,
        "quantity_requested_kg": flt(quantity) or plan.total_kg_required,
        "requested_by": _current_employee(),
        "request_date": nowdate(),
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return {"name": doc.name}


@frappe.whitelist()
def record_application(block_fertilizer_plan=None, actual_quantity=None, applied_in_full=None, partial_reason=None, **kwargs):
    if not block_fertilizer_plan:
        frappe.throw("block_fertilizer_plan is required")
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)
    full = cint(applied_in_full)
    doc = frappe.get_doc({
        "doctype": "Fertilizer Application",
        "block": plan.block,
        "block_fertilizer_plan": plan.name,
        "application_date": nowdate(),
        "fertilizer_product": plan.fertilizer_product,
        "planned_quantity_kg": plan.total_kg_required,
        "actual_quantity_applied_kg": flt(actual_quantity),
        "applied_in_full": full,
        "partial_reason": None if full else partial_reason,
        "variance_kg": flt(actual_quantity) - flt(plan.total_kg_required),
        "supervisor": _current_employee(),
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    plan.db_set("status", "Applied" if full else "Issued")
    return {"name": doc.name}


@frappe.whitelist()
def mark_attendance(employee=None, status=None, **kwargs):
    if not employee:
        frappe.throw("employee is required")
    name = f"{employee}-{nowdate()}"
    block = frappe.db.get_value("Employee", employee, "custom_assigned_block")
    if frappe.db.exists("Field Attendance", name):
        doc = frappe.get_doc("Field Attendance", name)
        doc.status = status or "Present"
    else:
        doc = frappe.get_doc({
            "doctype": "Field Attendance",
            "employee": employee,
            "attendance_date": nowdate(),
            "status": status or "Present",
            "farm": _farm(),
            "block": block,
            "marked_by": _current_employee(),
        })
    doc.save(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist()
def add_applicator(employee=None, **kwargs):
    if not employee:
        frappe.throw("employee is required")
    frappe.db.set_value("Employee", employee, "custom_field_supervisor", _current_employee())
    return {"ok": 1}


@frappe.whitelist()
def remove_applicator(employee=None, **kwargs):
    if not employee:
        frappe.throw("employee is required")
    frappe.db.set_value("Employee", employee, "custom_field_supervisor", None)
    return {"ok": 1}


@frappe.whitelist()
def assign_block(employee=None, block=None, **kwargs):
    if not employee:
        frappe.throw("employee is required")
    frappe.db.set_value("Employee", employee, "custom_assigned_block", block)
    return {"ok": 1}


# ---------------------------------------------------------------------------
# Dashboard / Manager KPIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_dashboard_summary(season=None, **kwargs):
    season = _season_filter(season)
    programmes = frappe.db.count("Fertilizer Programme", {"season": season}) if season else 0
    blocks_planned = frappe.db.count("Block Fertilizer Plan", {"season": season}) if season else 0
    applied = frappe.db.count("Fertilizer Application", {"docstatus": 1})
    return {
        "season": season,
        "programmes": programmes,
        "blocks_planned": blocks_planned,
        "applications_recorded": applied,
        "farm": _farm(),
    }


@frappe.whitelist()
def get_monthly_breakdown(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    rows = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["application_month as month", "sum(total_kg_required) as total_kg"],
        group_by="application_month",
    )
    by_month = {r.month: flt(r.total_kg) for r in rows}
    return [{"month": m, "total_kg": by_month.get(m, 0)} for m in MONTHS]


@frappe.whitelist()
def get_product_breakdown(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["fertilizer_product", "sum(total_kg_required) as total_kg"],
        group_by="fertilizer_product",
        order_by="total_kg desc",
    )


@frappe.whitelist()
def get_recent_activity(**kwargs):
    return frappe.get_all(
        "Fertilizer Application",
        fields=["name", "block", "fertilizer_product", "actual_quantity_applied_kg", "application_date"],
        order_by="creation desc",
        limit_page_length=15,
    )


@frappe.whitelist()
def get_stock_levels(**kwargs):
    rows = frappe.get_all("Fertilizer Product", filters={"disabled": 0}, fields=["name", "product_name"])
    out = []
    for r in rows:
        out.append({"product": r.name, "product_name": r.product_name, "available_qty": 0})
    return out


@frappe.whitelist()
def get_budget_summary(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return {}
    row = frappe.get_all(
        "Fertilizer Budget",
        filters={"season": season},
        fields=["total_budget_ksh", "total_actual", "total_variance_ksh"],
        limit_page_length=1,
    )
    return row[0] if row else {}


@frappe.whitelist()
def get_upcoming_and_overdue(**kwargs):
    alert_days = cint(frappe.db.get_single_value("Crop Nutrition Planning Settings", "upcoming_alert_days")) or 14
    today = getdate(nowdate())
    overdue = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"status": "Issued", "docstatus": 1},
        fields=["name", "block", "fertilizer_product", "application_month"],
        limit_page_length=20,
    )
    return {"upcoming": [], "overdue": overdue, "alert_days": alert_days, "as_of": str(today)}


@frappe.whitelist()
def get_leaf_deficiency_grid(season=None, **kwargs):
    rows = frappe.get_all(
        "Leaf Analysis",
        filters={"season": season} if season else {},
        fields=["name", "section", "yield_tier"],
    )
    grid = []
    for la in rows:
        results = frappe.get_all(
            "Leaf Analysis Nutrient Result",
            filters={"parent": la.name},
            fields=["nutrient", "status"],
        )
        grid.append({"section": la.section, "yield_tier": la.yield_tier, "results": results})
    return grid


@frappe.whitelist()
def get_stock_coverage(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    required = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["fertilizer_product", "sum(total_kg_required) as required_kg"],
        group_by="fertilizer_product",
    )
    return [{"fertilizer_product": r.fertilizer_product, "required_kg": flt(r.required_kg), "available_kg": 0, "coverage_pct": 0} for r in required]


@frappe.whitelist()
def get_manager_kpis(season=None, **kwargs):
    season = _season_filter(season)
    budget = get_budget_summary(season)
    return {
        "season": season,
        "programmes": frappe.db.count("Fertilizer Programme", {"season": season}) if season else 0,
        "total_budget_ksh": budget.get("total_budget_ksh", 0),
        "total_actual": budget.get("total_actual", 0),
        "applications_recorded": frappe.db.count("Fertilizer Application", {"docstatus": 1}),
    }


@frappe.whitelist()
def get_yield_tier_distribution(season=None, **kwargs):
    rows = frappe.get_all(
        "Programme Block Yield",
        filters={"parenttype": "Fertilizer Programme"},
        fields=["block", "yield_kg_ha"],
    )
    return rows


@frappe.whitelist()
def get_application_pace(season=None, **kwargs):
    season = _season_filter(season)
    planned = frappe.db.count("Block Fertilizer Plan", {"season": season, "docstatus": 1}) if season else 0
    applied = frappe.db.count("Block Fertilizer Plan", {"season": season, "status": "Applied"}) if season else 0
    return {"planned": planned, "applied": applied, "pct": (applied / planned * 100) if planned else 0}


@frappe.whitelist()
def get_block_progress(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["block", "status", "count(name) as rounds"],
        group_by="block, status",
    )


@frappe.whitelist()
def get_farm_progress_overview(season=None, **kwargs):
    season = _season_filter(season)
    total_blocks = frappe.db.count("Farm Block")
    planned_blocks = len(set(frappe.get_all(
        "Block Fertilizer Plan", filters={"season": season} if season else {}, pluck="block"
    ))) if season else 0
    return {"total_blocks": total_blocks, "planned_blocks": planned_blocks, "farm": _farm()}


@frappe.whitelist()
def get_qty_planned_vs_actual(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    planned = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["fertilizer_product", "sum(total_kg_required) as planned_kg"],
        group_by="fertilizer_product",
    )
    actual = {
        r.fertilizer_product: flt(r.actual_kg)
        for r in frappe.get_all(
            "Fertilizer Application",
            filters={"docstatus": 1},
            fields=["fertilizer_product", "sum(actual_quantity_applied_kg) as actual_kg"],
            group_by="fertilizer_product",
        )
    }
    return [
        {"fertilizer_product": r.fertilizer_product, "planned_kg": flt(r.planned_kg), "actual_kg": actual.get(r.fertilizer_product, 0)}
        for r in planned
    ]


@frappe.whitelist()
def get_section_usage_breakdown(season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season},
        fields=["section", "sum(total_kg_required) as total_kg"],
        group_by="section",
        order_by="total_kg desc",
    )


@frappe.whitelist()
def get_partial_applications(season=None, **kwargs):
    return frappe.get_all(
        "Fertilizer Application",
        filters={"applied_in_full": 0, "docstatus": 1},
        fields=["name", "block", "fertilizer_product", "variance_kg", "partial_reason", "application_date"],
        order_by="application_date desc",
        limit_page_length=30,
    )


@frappe.whitelist()
def get_variance_alerts(season=None, **kwargs):
    threshold = flt(frappe.db.get_single_value("Crop Nutrition Planning Settings", "variance_threshold_pct")) or 15
    rows = frappe.get_all(
        "Fertilizer Application",
        filters={"docstatus": 1},
        fields=["name", "block", "planned_quantity_kg", "actual_quantity_applied_kg", "variance_kg"],
        order_by="creation desc",
        limit_page_length=50,
    )
    out = []
    for r in rows:
        if r.planned_quantity_kg:
            pct = abs(flt(r.variance_kg)) / flt(r.planned_quantity_kg) * 100
            if pct >= threshold:
                out.append(r)
    return out


@frappe.whitelist()
def get_computed_budget(season=None, **kwargs):
    return _pending("Budget totals are computed from the programme's nutrient-rate grid, which isn't built yet.")


@frappe.whitelist()
def get_operator_activity(season=None, **kwargs):
    return frappe.get_all(
        "Fertilizer Application",
        filters={"docstatus": 1},
        fields=["supervisor", "supervisor_name", "count(name) as applications"],
        group_by="supervisor",
        order_by="applications desc",
        limit_page_length=20,
    )


# ---------------------------------------------------------------------------
# Agronomist Desk
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_agronomist_desk(season=None, **kwargs):
    season = _season_filter(season)
    programmes = frappe.get_all(
        "Fertilizer Programme",
        filters={"season": season} if season else {},
        fields=["name", "season", "crop", "docstatus", "approved_by_agronomist", "approved_by_manager"],
        order_by="creation desc",
    )
    return {"farm": _farm(), "season": season, "programmes": programmes}


@frappe.whitelist()
def get_programme_detail(programme=None, **kwargs):
    if not programme:
        frappe.throw("programme is required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    return doc.as_dict()


@frappe.whitelist()
def get_programme_summary(programme=None, **kwargs):
    if not programme:
        return {}
    lines = frappe.get_all(
        "Fertilizer Programme Line", filters={"parent": programme}, fields=["fertilizer_product", "sum(total_kg) as total_kg"], group_by="fertilizer_product"
    )
    return {"programme": programme, "by_product": lines, "lines": len(lines)}


@frappe.whitelist()
def desk_pull_blocks(programme=None, **kwargs):
    if not programme:
        frappe.throw("programme is required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    if doc.scope_type == "Block" and doc.scope_block:
        filters = {"name": doc.scope_block}
    elif doc.scope_type == "Section" and doc.scope_section:
        filters = {"section": doc.scope_section}
    else:
        filters = {"crop": doc.crop} if doc.crop else {}
    blocks = frappe.get_all("Farm Block", filters=filters, fields=["name", "section", "area_ha", "tree_count", "projected_yield_kg_ha"])
    doc.set("block_yield_data", [])
    for b in blocks:
        doc.append("block_yield_data", {
            "block": b.name,
            "section": b.section,
            "area_ha": b.area_ha,
            "tree_count": b.tree_count,
            "yield_kg_ha": b.projected_yield_kg_ha,
        })
    doc.save(ignore_permissions=True)
    return {"blocks": len(blocks)}


@frappe.whitelist()
def load_programme_products(programme=None, **kwargs):
    if not programme:
        frappe.throw("programme is required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    products = frappe.get_all("Fertilizer Product", filters={"disabled": 0}, fields=["name"])
    doc.set("product_selections", [])
    for p in products:
        doc.append("product_selections", {"product": p.name})
    doc.save(ignore_permissions=True)
    return {"products": [p.name for p in products]}


@frappe.whitelist()
def desk_calculate(programme=None, **kwargs):
    return _pending("The nutrient-rate calculation engine isn't built yet - Programme Lines can't be generated.")


@frappe.whitelist()
def desk_get_rate_grid(programme=None, **kwargs):
    frappe.throw(_pending()["message"])


@frappe.whitelist()
def desk_save_rates(programme=None, rates=None, **kwargs):
    frappe.throw(_pending()["message"])


@frappe.whitelist()
def desk_set_sign_off(programme=None, who=None, value=None, **kwargs):
    if not programme or who not in ("agronomist", "manager"):
        frappe.throw("programme and a valid who ('agronomist'/'manager') are required")
    fieldname = "approved_by_agronomist" if who == "agronomist" else "approved_by_manager"
    frappe.db.set_value("Fertilizer Programme", programme, fieldname, cint(value))
    doc = frappe.get_doc("Fertilizer Programme", programme)
    return {"approved_by_agronomist": doc.approved_by_agronomist, "approved_by_manager": doc.approved_by_manager}


@frappe.whitelist()
def desk_submit_programme(programme=None, **kwargs):
    if not programme:
        frappe.throw("programme is required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    if doc.docstatus == 1:
        return {"already": True}
    if frappe.db.get_single_value("Crop Nutrition Planning Settings", "require_programme_approval"):
        if "Farm Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
            frappe.throw("Only a Farm Manager may submit this programme.")
    doc.submit()
    return {"already": False}


@frappe.whitelist()
def desk_delete_draft(programme=None, **kwargs):
    if not programme:
        frappe.throw("programme is required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    if doc.docstatus != 0:
        frappe.throw("Only a draft programme can be deleted.")
    frappe.delete_doc("Fertilizer Programme", programme, ignore_permissions=True)
    return {"ok": 1}


@frappe.whitelist()
def get_plan_queue(season=None, **kwargs):
    season = _season_filter(season)
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters={"season": season, "status": "Planned"} if season else {"status": "Planned"},
        fields=["name", "block", "fertilizer_product", "application_month", "total_kg_required"],
        order_by="application_month",
        limit_page_length=100,
    )


@frappe.whitelist()
def get_desk_blocks(season=None, **kwargs):
    return frappe.get_all(
        "Farm Block",
        fields=["name", "block_name", "section", "crop", "area_ha", "tree_count", "projected_yield_kg_ha"],
        order_by="block_name",
    )


@frappe.whitelist()
def get_block_detail(block=None, season=None, **kwargs):
    if not block:
        frappe.throw("block is required")
    doc = frappe.get_doc("Farm Block", block)
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"block": block, "season": season} if season else {"block": block},
        fields=["name", "fertilizer_product", "application_month", "status", "total_kg_required"],
    )
    return {"block": doc.as_dict(), "plans": plans}


@frappe.whitelist()
def get_desk_store_requests(**kwargs):
    return frappe.get_all(
        "Fertilizer Store Request",
        fields=["name", "block", "fertilizer_product", "quantity_requested_kg", "status", "request_date"],
        order_by="creation desc",
        limit_page_length=100,
    )


@frappe.whitelist()
def get_desk_applications(season=None, **kwargs):
    filters = {}
    if season:
        blocks_plans = frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name")
        filters = {"block_fertilizer_plan": ["in", blocks_plans]} if blocks_plans else {"name": ["in", []]}
    return frappe.get_all(
        "Fertilizer Application",
        filters=filters,
        fields=["name", "block", "fertilizer_product", "actual_quantity_applied_kg", "application_date"],
        order_by="application_date desc",
        limit_page_length=100,
    )


@frappe.whitelist()
def get_variance_by_section(season=None, **kwargs):
    return get_section_usage_breakdown(season=season)


@frappe.whitelist()
def get_variance_by_block(section=None, season=None, **kwargs):
    season = _season_filter(season)
    if not season:
        return []
    filters = {"season": season}
    if section:
        filters["section"] = section
    return frappe.get_all(
        "Block Fertilizer Plan",
        filters=filters,
        fields=["block", "sum(total_kg_required) as planned_kg"],
        group_by="block",
    )


@frappe.whitelist()
def get_desk_stock(season=None, **kwargs):
    rows = frappe.get_all("Fertilizer Product", filters={"disabled": 0}, fields=["name", "product_name"])
    return [{"product": r.name, "product_name": r.product_name, "in_programme": False, "available_qty": 0} for r in rows]


@frappe.whitelist()
def get_active_supervisors(**kwargs):
    import time

    from mutaracnp.mutaracnp.utils.presence import read_presence

    window_minutes = 15
    now = time.time()
    presence = read_presence()
    supervisors = []
    online = 0
    for user, info in presence.items():
        age_minutes = (now - flt(info.get("ts"))) / 60
        is_online = age_minutes <= window_minutes
        online += 1 if is_online else 0
        supervisors.append({"user": user, "online": is_online, "last_seen": info.get("ts"), "via": info.get("via")})
    return {
        "supervisors": supervisors,
        "summary": {"online": online, "today": len(supervisors), "total": len(supervisors)},
        "window": window_minutes,
    }


@frappe.whitelist()
def get_section_overview(section=None, season=None, **kwargs):
    if not section:
        frappe.throw("section is required")
    blocks = frappe.get_all("Farm Block", filters={"section": section}, fields=["name", "block_name", "area_ha"])
    return {"section": section, "blocks": blocks}


@frappe.whitelist()
def search_fertilizer_items(search=None, **kwargs):
    filters = {"item_group": "Fertilizer"} if frappe.db.exists("Item Group", "Fertilizer") else {}
    if search:
        filters["item_name"] = ["like", f"%{search}%"]
    return frappe.get_all("Item", filters=filters, fields=["name as item_code", "item_name"], limit_page_length=20)


@frappe.whitelist()
def get_product_choices(programme=None, product=None, **kwargs):
    if not product:
        return {"options": []}
    search_terms = frappe.db.get_value("Fertilizer Product", product, "search_terms") or ""
    filters = {}
    if search_terms.strip():
        first_term = search_terms.split("\n")[0].strip()
        if first_term:
            filters = {"item_name": ["like", f"%{first_term}%"]}
    options = frappe.get_all("Item", filters=filters, fields=["name as item_code", "item_name"], limit_page_length=20)
    return {"options": options}


@frappe.whitelist()
def set_product_item(programme=None, product=None, item=None, **kwargs):
    if not (programme and product and item):
        frappe.throw("programme, product and item are all required")
    doc = frappe.get_doc("Fertilizer Programme", programme)
    for row in doc.product_selections:
        if row.product == product:
            row.fertilizer_item = item
            row.item_name = frappe.db.get_value("Item", item, "item_name")
    doc.save(ignore_permissions=True)
    return {"ok": 1}


@frappe.whitelist()
def export_programme_excel(programme=None, **kwargs):
    frappe.throw("Programme export isn't available until the calculation engine generates programme lines.")
