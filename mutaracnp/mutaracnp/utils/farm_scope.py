"""
Shared helper to keep the `farm` (and, where present, `section`/`company`)
fields in sync on doctypes that reference a Farm Block, a Fertilizer
Programme, or a CNP Farm directly. Mutara is single-farm, so there is no
scoping decision to make here - these just save the caller from re-deriving
a two-hop chain (Block -> Section -> Farm) by hand on every doctype that
carries a `block` link.
"""

import frappe


def set_farm_from_block(doc, method=None):
	"""doc_events target for doctypes carrying a `block` link (Fertilizer
	Store Request, Fertilizer Application, Block Fertilizer Plan). Also sets
	`section` where the doctype has that field - harmless no-op otherwise."""
	if doc.get("block"):
		info = frappe.db.get_value("Farm Block", doc.block, ["farm", "section"], as_dict=True)
		if info:
			doc.farm = info.farm
			if doc.meta.has_field("section"):
				doc.section = info.section


def set_farm_from_programme(doc, method=None):
	"""doc_events target for doctypes carrying a `fertilizer_programme` link
	(Fertilizer Budget)."""
	if doc.get("fertilizer_programme"):
		doc.farm = frappe.db.get_value("Fertilizer Programme", doc.fertilizer_programme, "farm")


def set_company_from_farm(doc, method=None):
	"""doc_events target for any doctype carrying both a `farm` link and a
	`company` field. CNP Farm has no company field of its own - its
	warehouse's Company is the only reliable source."""
	if doc.get("farm"):
		warehouse = frappe.db.get_value("CNP Farm", doc.farm, "warehouse")
		doc.company = frappe.db.get_value("Warehouse", warehouse, "company") if warehouse else None


def mark_plan_issued_from_request(doc, method=None):
	"""doc_events target for Fertilizer Store Request. When the storekeeper's
	workflow action moves a request to Issued, flip the linked Block
	Fertilizer Plan's status too, so the field app's Record Application flow
	sees it as ready."""
	if doc.get("status") == "Issued" and doc.get("block_fertilizer_plan"):
		frappe.db.set_value("Block Fertilizer Plan", doc.block_fertilizer_plan, "status", "Issued")
