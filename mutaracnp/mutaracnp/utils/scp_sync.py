"""
One-directional, read-only sync from Mutara Orchards' existing farm-ops
suite (the "Avocado Yield" app, already installed and maintained
independently of MutaraCNP) into MutaraCNP's own Section and Farm Block.

Why this exists: Avocado Yield Block already holds the real block registry
(area, trees, variety, planting year), and Avocado Production Forecast
already holds the real projected yield per block per season - MutaraCNP
has no business asking anyone to re-type that. This module only reads from
those doctypes and never writes back to them; nothing here changes if
MutaraCNP is ever uninstalled.

The two apps aren't linked by ID - everything is matched by block_code
(e.g. "PH1-B1") as plain text, since that's how the source data itself is
structured (Avocado Production Forecast.orchard_block is a Data field, not
a Link). Section has no equivalent on that side at all, so it's derived
from the "PH1"/"PH2"-style prefix baked into each block_code.
"""

import frappe
from frappe.utils import flt

EXTERNAL_BLOCK_DOCTYPE = "Avocado Yield Block"
EXTERNAL_FORECAST_DOCTYPE = "Avocado Production Forecast"
FORECAST_CROP_PORTION = "Whole Season"


@frappe.whitelist()
def scp_sync_available():
	"""Whether the source app (Avocado Yield) is even installed on this
	site - it isn't on a plain dev bench, only on farms that already run
	that separate suite."""
	return bool(frappe.db.exists("DocType", EXTERNAL_BLOCK_DOCTYPE))


def _derive_section_name(block_code, farm_name):
	"""'PH1-B1' -> section 'PH1' under the given farm. Falls back to the
	whole code if there's no '-' to split on, rather than guessing further."""
	prefix = block_code.split("-")[0].strip() if "-" in block_code else block_code.strip()
	docname = f"{farm_name}-{prefix}"
	if not frappe.db.exists("Section", docname):
		frappe.get_doc({
			"doctype": "Section", "farm": farm_name, "section_name": prefix, "is_active": 1,
		}).insert(ignore_permissions=True)
	return docname


def _latest_whole_season_forecast(block_code):
	rows = frappe.get_all(
		EXTERNAL_FORECAST_DOCTYPE,
		filters={"orchard_block": block_code, "crop": FORECAST_CROP_PORTION},
		fields=["expected_kg", "entry_date"],
		order_by="entry_date desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def sync_blocks_from_scp(farm_name="Mutara", crop_name="Avocado"):
	if not scp_sync_available():
		frappe.throw(
			f"{EXTERNAL_BLOCK_DOCTYPE} isn't installed on this site - there's nothing to sync from."
		)

	external_blocks = frappe.get_all(
		EXTERNAL_BLOCK_DOCTYPE,
		fields=["block_code", "variety", "status", "area_ha", "total_trees", "live_trees", "planting_year"],
	)

	synced, skipped, with_forecast = 0, 0, 0
	for b in external_blocks:
		if not b.block_code:
			skipped += 1
			continue
		if b.status and b.status not in ("Active",):
			# Fallow/Replanting/Decommissioned blocks aren't being fertilized -
			# leave them out rather than importing a block there's no plan for.
			skipped += 1
			continue

		section = _derive_section_name(b.block_code, farm_name)
		tree_count = b.live_trees or b.total_trees or 0

		values = {
			"block_number": b.block_code.rsplit("-", 1)[-1] if "-" in b.block_code else b.block_code,
			"section": section,
			"farm": farm_name,
			"crop": crop_name,
			"area_ha": b.area_ha,
			"tree_count": tree_count,
			"variety": b.variety,
			"planting_year": b.planting_year,
		}

		forecast = _latest_whole_season_forecast(b.block_code)
		if forecast and flt(b.area_ha):
			values["projected_yield_kg_ha"] = round(flt(forecast.expected_kg) / flt(b.area_ha), 1)
			with_forecast += 1

		existing = frappe.db.exists("Farm Block", b.block_code)
		if existing:
			doc = frappe.get_doc("Farm Block", existing)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Farm Block", "block_name": b.block_code, **values}).insert(
				ignore_permissions=True
			)
		synced += 1

	frappe.db.commit()
	return {"synced": synced, "skipped": skipped, "with_forecast": with_forecast}
