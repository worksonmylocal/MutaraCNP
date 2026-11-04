"""
Crop-agnostic fertilizer programme calculation engine, ported from UpandeCNP's
proven engine (the one actually running for Lokitela), with three tweaks for
Mutara:

  1. Yield tier classification runs off Farm Block.projected_yield_kg_ha, via
     Programme Block Yield.yield_kg_ha, instead of a previous year's actual -
     Mutara has no harvest history yet. No change to the classification
     logic itself, only to which number feeds it (see
     fertilizer_programme.py's pull_blocks_from_farm).
  2. A second adjustment source, soil buildup, sits alongside the leaf
     analysis adjustment rather than replacing it: both are looked up per
     (Section, Yield Tier) and summed before being applied to the rate.
     Leaf analysis uses each crop's own leaf_adjustment_pct; soil buildup
     uses one global per-nutrient factor from Crop Nutrition Planning
     Settings, since soil chemistry response doesn't vary by crop the way
     leaf uptake does.
  3. Crop Nutrient Rule is looked up as its own doctype (frappe.get_all),
     not a child table on Crop - it was promoted to a standalone, listable
     page so removal/rate factors are editable without opening the Crop
     form.

All yield tiers, nutrient rates, bag compositions, and leaf/soil norms are
master data (Crop / Crop Yield Tier / Crop Nutrient Rule / Leaf Analysis Norm
/ Soil Analysis Norm / Crop Nutrition Planning Settings) rather than
hardcoded constants, so a new crop can be onboarded by adding data, not code.

Algorithm:
  1. Each block is classified into a yield tier from its projected yield
     (Kg/Ha), using the crop's Crop Yield Tier thresholds.
  2. Blocks are grouped by (Section, Tier) - independently per section, never
     farm-wide - since each section's tier group gets its own area total and
     its own resulting Kg/Ha rate.
  3. For each nutrient rule (CAN/N, TSP/P, MOP+K2SO4/K, ...): compute the
     product's kg/ha requirement for the group, net off compost where
     applicable, scale by area, apply the group's combined leaf+soil
     adjustment, and distribute back to each block as a total kg and a
     per-tree gram dose.
  4. Alternative-source nutrients (rows sharing a nutrient_source_group, e.g.
     MOP vs K2SO4) are all computed as candidates; only the one matching the
     Programme's potassium_source feeds into programme_lines.
  5. Annual per-block totals are split across months using the Production
     Calendar's Fertilizer Schedule.
"""

import frappe
from frappe.utils import cint, flt

from mutaracnp.mutaracnp.utils.rounding import round_half_up


def get_nutrient_rules(crop_name):
	return frappe.get_all(
		"Crop Nutrient Rule",
		filters={"crop": crop_name},
		fields=[
			"fertilizer_product", "nutrient", "rate_per_tonne", "bag_weight_kg",
			"product_nutrient_pct", "apply_compost_netting", "nutrient_source_group",
		],
	)


def get_yield_tier(crop_doc, yield_kg_ha):
	"""min_yield_kg_ha is an exclusive lower bound, max_yield_kg_ha an inclusive
	upper bound; blank means unbounded on that side."""
	yield_kg_ha = flt(yield_kg_ha)
	for tier in sorted(crop_doc.yield_tiers, key=lambda t: t.sort_order or 0):
		min_y, max_y = tier.min_yield_kg_ha, tier.max_yield_kg_ha
		below_max = (not max_y) or yield_kg_ha <= flt(max_y)
		above_min = (not min_y) or yield_kg_ha > flt(min_y)
		if above_min and below_max:
			return tier.tier_label, flt(tier.tier_tonnage)
	frappe.throw(f"No yield tier on crop {crop_doc.name} matches {yield_kg_ha} Kg/Ha.")


def group_blocks_by_section_tier(programme, crop_doc):
	"""Groups Programme Block Yield rows by (section, tier_label). Grouping is
	always per-section - a tier's totals in Section 1 are independent of the
	same tier's totals in Section 2."""
	groups = {}
	for row in programme.get("block_yield_data", []):
		tier_label, tier_tonnage = get_yield_tier(crop_doc, row.yield_kg_ha)
		key = (row.section, tier_label)
		group = groups.setdefault(key, {"tier_tonnage": tier_tonnage, "total_area_ha": 0, "blocks": []})
		group["total_area_ha"] += flt(row.area_ha)
		group["blocks"].append({
			"block": row.block,
			"area_ha": flt(row.area_ha),
			"tree_count": cint(row.tree_count),
		})
	return groups


def get_leaf_adjustment_pct(crop_doc, norm, section, yield_tier):
	"""Leaf Analysis is keyed 1:1 by (Section, Yield Tier) - looked up directly,
	no manual selection step. Returns +leaf_adjustment_pct if the norm's
	nutrient result is below midpoint, -leaf_adjustment_pct if strictly above
	the high bound (no midpoint buffer on that side), else 0."""
	leaf_analysis = frappe.db.get_value(
		"Leaf Analysis", {"section": section, "yield_tier": yield_tier}, "name"
	)
	if not leaf_analysis:
		frappe.throw(f"No Leaf Analysis found for Section {section} / Tier {yield_tier}.")

	result_value = frappe.db.get_value(
		"Leaf Analysis Nutrient Result",
		{"parent": leaf_analysis, "nutrient": norm.nutrient},
		"result_value",
	)
	if result_value is None:
		return 0

	adjustment = flt(crop_doc.leaf_adjustment_pct)
	if flt(result_value) < flt(norm.midpoint):
		return adjustment
	if flt(result_value) > flt(norm.high):
		return -adjustment
	return 0


def get_soil_buildup_pct(buildup_factors, norm, section, yield_tier):
	"""Soil Analysis is keyed 1:1 by (Section, Yield Tier), the same grain as
	Leaf Analysis. Returns +buildup_factor if the soil test result is below
	midpoint, -buildup_factor if strictly above the high bound, else 0. The
	factor itself is global per nutrient (Crop Nutrition Planning Settings),
	not per crop - soil chemistry response doesn't vary by crop the way leaf
	uptake does."""
	soil_analysis = frappe.db.get_value(
		"Soil Analysis", {"section": section, "yield_tier": yield_tier}, "name"
	)
	if not soil_analysis:
		frappe.throw(f"No Soil Analysis found for Section {section} / Tier {yield_tier}.")

	result_value = frappe.db.get_value(
		"Soil Analysis Nutrient Result",
		{"parent": soil_analysis, "nutrient": norm.nutrient},
		"result_value",
	)
	if result_value is None:
		return 0

	factor = flt(buildup_factors.get(norm.nutrient))
	if flt(result_value) < flt(norm.midpoint):
		return factor
	if flt(result_value) > flt(norm.high):
		return -factor
	return 0


def calculate_product_for_group(rule, tier_tonnage, group_area_ha, adjustment_pct, crop_doc):
	"""The 6-step per-product pattern, identical for every nutrient rule.
	adjustment_pct is the combined leaf + soil adjustment for this group and
	nutrient."""
	nutrient_need_per_ha = round_half_up(flt(rule.rate_per_tonne) * tier_tonnage)

	compost_offset = 0
	if rule.apply_compost_netting:
		# Per the agronomist's worked example (25kg compost x 2.5 -> 62.5 -> 63kg N),
		# this is a literal multiplier, not dose x (pct/100) - a true 2.5% of 25kg
		# compost would only be 0.625kg, which is not what was specified.
		compost_offset = round_half_up(flt(crop_doc.compost_dose_kg) * flt(crop_doc.compost_n_pct))
	nutrient_needed = nutrient_need_per_ha - compost_offset

	nutrient_kg_per_bag = flt(rule.bag_weight_kg) * flt(rule.product_nutrient_pct) / 100
	product_kg_per_ha = (
		round_half_up((nutrient_needed / nutrient_kg_per_bag) * flt(rule.bag_weight_kg))
		if nutrient_kg_per_bag else 0
	)

	total_product_kg = product_kg_per_ha * group_area_ha
	adjusted_total = total_product_kg * (1 + adjustment_pct / 100)
	final_product_kg_per_ha = adjusted_total / group_area_ha if group_area_ha else 0

	return {
		"product_kg_per_ha": round_half_up(product_kg_per_ha, 2),
		"total_product_kg": round_half_up(total_product_kg, 2),
		"final_product_kg_per_ha": final_product_kg_per_ha,
	}


def distribute_to_blocks(blocks, final_product_kg_per_ha, fertilizer_product, yield_tier, section):
	lines = []
	for block in blocks:
		block_total_kg = block["area_ha"] * final_product_kg_per_ha
		dose_per_tree_g = (
			round_half_up((block_total_kg / block["tree_count"]) * 1000, 1)
			if block["tree_count"] else 0
		)
		lines.append({
			"block": block["block"],
			"section": section,
			"fertilizer_product": fertilizer_product,
			"yield_tier": yield_tier,
			"kg_per_ha_rate": round_half_up(final_product_kg_per_ha, 2),
			"total_kg": round_half_up(block_total_kg, 2),
			"dose_per_tree_g": dose_per_tree_g,
		})
	return lines


def apply_monthly_schedule(annual_lines, calendar_doc):
	schedule_map = {}
	for row in calendar_doc.get("fertilizer_schedule", []):
		schedule_map.setdefault(row.fertilizer_product, []).append(
			(row.application_month, flt(row.percentage) / 100.0)
		)

	monthly_lines = []
	for line in annual_lines:
		schedule = schedule_map.get(line["fertilizer_product"])
		if not schedule:
			frappe.throw(
				f"No monthly application schedule configured for {line['fertilizer_product']} "
				f"on Production Calendar {calendar_doc.name}."
			)
		for month, fraction in schedule:
			monthly_lines.append({
				**line,
				"application_month": month,
				"kg_per_ha_rate": round_half_up(line["kg_per_ha_rate"] * fraction, 2),
				"total_kg": round_half_up(line["total_kg"] * fraction, 2),
				"dose_per_tree_g": round_half_up(line["dose_per_tree_g"] * fraction, 1),
			})
	return monthly_lines


@frappe.whitelist()
def calculate_programme(programme_name):
	programme = frappe.get_doc("Fertilizer Programme", programme_name)

	if programme.docstatus == 1:
		frappe.throw("Cannot recalculate a submitted programme.")
	if not programme.potassium_source:
		frappe.throw("Please select a Potassium Source before running the calculation.")

	crop_doc = frappe.get_doc("Crop", programme.crop)
	calendar_doc = frappe.get_doc("Production Calendar", programme.production_calendar)
	nutrient_rules = get_nutrient_rules(crop_doc.name)

	leaf_norms = {
		n.nutrient: n
		for n in frappe.get_all(
			"Leaf Analysis Norm",
			filters={"crop": crop_doc.name},
			fields=["nutrient", "low", "high", "midpoint"],
		)
	}
	soil_norms = {
		n.nutrient: n
		for n in frappe.get_all(
			"Soil Analysis Norm",
			filters={"crop": crop_doc.name},
			fields=["nutrient", "low", "high", "midpoint"],
		)
	}
	buildup_factors = {
		row.nutrient: row.buildup_factor
		for row in frappe.get_single("Crop Nutrition Planning Settings").soil_buildup_factors
	}

	groups = group_blocks_by_section_tier(programme, crop_doc)

	annual_lines = []
	potassium_candidates = []

	for (section, tier_label), group in groups.items():
		for rule in nutrient_rules:
			leaf_norm = leaf_norms.get(rule.nutrient)
			soil_norm = soil_norms.get(rule.nutrient)
			leaf_pct = get_leaf_adjustment_pct(crop_doc, leaf_norm, section, tier_label) if leaf_norm else 0
			soil_pct = get_soil_buildup_pct(buildup_factors, soil_norm, section, tier_label) if soil_norm else 0
			adjustment_pct = flt(leaf_pct) + flt(soil_pct)

			result = calculate_product_for_group(
				rule, group["tier_tonnage"], group["total_area_ha"], adjustment_pct, crop_doc
			)

			if rule.nutrient_source_group:
				# Use the leaf+soil-adjusted final figures here too, so the
				# comparison reflects what would actually be applied - not the
				# pre-adjustment baseline distribute_to_blocks() uses for
				# whichever gets selected.
				final_per_ha = round_half_up(result["final_product_kg_per_ha"], 2)
				potassium_candidates.append({
					"section": section,
					"yield_tier": tier_label,
					"fertilizer_product": rule.fertilizer_product,
					"nutrient": rule.nutrient,
					"product_kg_per_ha": final_per_ha,
					"total_product_kg": round_half_up(final_per_ha * group["total_area_ha"], 2),
					"is_selected": rule.fertilizer_product == programme.potassium_source,
				})
				if rule.fertilizer_product != programme.potassium_source:
					continue

			annual_lines += distribute_to_blocks(
				group["blocks"], result["final_product_kg_per_ha"],
				rule.fertilizer_product, tier_label, section,
			)

	monthly_lines = apply_monthly_schedule(annual_lines, calendar_doc)

	programme.set("programme_lines", [])
	for line in monthly_lines:
		programme.append("programme_lines", line)

	programme.set("potassium_candidates", [])
	for candidate in potassium_candidates:
		programme.append("potassium_candidates", candidate)

	programme.save()
	return len(monthly_lines)
