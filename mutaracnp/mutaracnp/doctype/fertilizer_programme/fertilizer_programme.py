import frappe
from frappe.model.document import Document


class FertilizerProgramme(Document):

	def on_submit(self):
		self.create_block_fertilizer_plans()

	def on_cancel(self):
		self.cancel_block_fertilizer_plans()

	@frappe.whitelist()
	def pull_blocks_from_farm(self):
		"""Populate block_yield_data from every active Farm Block under this
		programme's Farm - the single source of truth for area/tree_count/
		section, replacing manual re-entry. Yield comes from the block's
		projected yield, not a previous year's actual, since Mutara has no
		harvest history yet."""
		if not self.farm:
			frappe.throw("Please set the Farm first.")

		blocks = frappe.get_all(
			"Farm Block",
			filters={"farm": self.farm},
			fields=["name", "section", "area_ha", "tree_count", "projected_yield_kg_ha"],
		)

		self.set("block_yield_data", [])
		for block in blocks:
			self.append("block_yield_data", {
				"block": block.name,
				"section": block.section,
				"area_ha": block.area_ha,
				"tree_count": block.tree_count,
				"yield_kg_ha": block.projected_yield_kg_ha,
			})

		self.save()
		return len(blocks)

	def create_block_fertilizer_plans(self):
		created = 0
		for line in self.get("programme_lines", []):
			if frappe.db.exists("Block Fertilizer Plan", {
				"fertilizer_programme": self.name,
				"block": line.block,
				"fertilizer_product": line.fertilizer_product,
				"application_month": line.application_month,
			}):
				continue

			plan = frappe.get_doc({
				"doctype": "Block Fertilizer Plan",
				"fertilizer_programme": self.name,
				"season": self.season,
				"block": line.block,
				"fertilizer_product": line.fertilizer_product,
				"application_month": line.application_month,
				"yield_tier": line.yield_tier,
				"application_rate_kg_ha": line.kg_per_ha_rate,
				"dose_per_tree_g": line.dose_per_tree_g,
				"tree_count": self.get_tree_count(line.block),
				"total_kg_required": line.total_kg,
				"status": "Planned",
			})
			plan.insert(ignore_permissions=True)
			plan.submit()
			created += 1

		frappe.msgprint(f"{created} Block Fertilizer Plan(s) created.", alert=True)

	def get_tree_count(self, block_name):
		return frappe.db.get_value("Farm Block", block_name, "tree_count") or 0

	def cancel_block_fertilizer_plans(self):
		plans = frappe.get_all(
			"Block Fertilizer Plan",
			filters={"fertilizer_programme": self.name, "docstatus": 1},
			fields=["name"],
		)
		for p in plans:
			frappe.get_doc("Block Fertilizer Plan", p.name).cancel()
