"""Builds the downloadable Excel workbook for a Fertilizer Programme.

Follows the agronomist's own template (ported from UpandeCNP): one flat
table, Section and Block as the first columns, then every product's figures
side by side - a Kg/Ha for the tier the block sits in and a Kg/Ha for the
block itself (the same unless the block's leaf/soil adjustments differ from
the rest of its tier), then one column pair per round, headed by the month
it falls in, with that round's share of the product's annual total under the
month (e.g. "20%" under "November") and the per-tree gram dose next to it.
A product with no real application anywhere in the programme is left out.
"""

import re
from collections import Counter
from io import BytesIO

import frappe
from frappe.utils import cint, flt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from mutaracnp.mutaracnp.utils.rounding import round_half_up

HEADER_FILL = PatternFill("solid", fgColor="E5E7EB")
CENTER = Alignment(horizontal="center", vertical="center")


def build_programme_workbook(doc, section=None):
	"""doc: a Fertilizer Programme Document. section: when given, only that
	section's blocks are included. Returns the .xlsx bytes."""
	blocks = {
		b.block: {"section": b.section, "area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count)}
		for b in doc.get("block_yield_data", [])
		if not section or b.section == section
	}

	lines = [l for l in doc.get("programme_lines", []) if l.block in blocks]
	codes = {l.fertilizer_product for l in lines}
	item_names = dict(frappe.get_all("Item", filters={"name": ["in", list(codes)]},
									 fields=["name", "item_name"], as_list=True)) if codes else {}

	products = {}          # code -> display name
	yield_tier = {}        # block -> yield tier label
	# (block, product) -> [(month, total_kg, dose_per_tree_g)], in round order
	# (programme_lines follows the Production Calendar's own row order).
	rounds = {}
	product_months = {}    # product -> months in round order

	for line in lines:
		code = line.fertilizer_product
		products[code] = item_names.get(code) or code
		yield_tier.setdefault(line.block, line.yield_tier)
		rounds.setdefault((line.block, code), []).append(
			(line.application_month, flt(line.total_kg), flt(line.dose_per_tree_g))
		)
		seen = product_months.setdefault(code, [])
		if line.application_month not in seen:
			seen.append(line.application_month)

	def block_total(block, code):
		return sum(total_kg for _, total_kg, _ in rounds.get((block, code), []))

	def block_kg_ha(block, code):
		area = blocks.get(block, {}).get("area_ha") or 0
		return round(block_total(block, code) / area, 2) if area else 0

	product_list = [
		(code, name) for code, name in sorted(products.items(), key=lambda p: p[1])
		if sum(block_total(b, code) for b in blocks) > 0
	]

	# Tier Kg/Ha is the rate most of a tier's blocks carry - the mode, not an
	# average, so one block with different adjustments doesn't drag it.
	tier_kg_ha = {}
	for code, _ in product_list:
		by_tier = {}
		for block in blocks:
			tier = yield_tier.get(block)
			if tier:
				by_tier.setdefault(tier, []).append(block_kg_ha(block, code))
		for tier, values in by_tier.items():
			tier_kg_ha[(tier, code)] = Counter(values).most_common(1)[0][0]

	sections = {}
	for block, info in blocks.items():
		sections.setdefault(info["section"] or "(No section)", []).append(block)

	wb = Workbook()
	ws = wb.active
	ws.title = re.sub(r"[\\/*?:\[\]]", "-", doc.name or "Programme")[:31]

	fixed_cols = 5  # Section, Block, Area, No of Trees, Tier
	col_span = {code: 2 + 2 * len(product_months.get(code, [])) for code, _ in product_list}

	def header(row, col, value):
		cell = ws.cell(row=row, column=col, value=value)
		cell.font = Font(bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = CENTER

	product_row, sub_row = 1, 2
	for col, label in enumerate(("Section", "Block", "Area", "No of Trees", "Tier"), start=1):
		header(product_row, col, label)
		ws.merge_cells(start_row=product_row, start_column=col, end_row=sub_row, end_column=col)

	col = fixed_cols + 1
	for code, name in product_list:
		header(product_row, col, name)
		ws.merge_cells(start_row=product_row, start_column=col, end_row=product_row,
					   end_column=col + col_span[code] - 1)
		header(sub_row, col, "Kg/Ha (Tier)")
		header(sub_row, col + 1, "Kg/Ha (Block)")
		col += 2
		for month in product_months[code]:
			header(sub_row, col, month)
			header(sub_row, col + 1, "G/Tree")
			col += 2

	row = sub_row + 1
	for section_name in sorted(sections):
		section_start_row = row
		for block in sorted(sections[section_name]):
			info = blocks[block]
			tier = yield_tier.get(block)
			for c, value in ((2, block), (3, info["area_ha"]), (4, info["tree_count"]), (5, tier or "—")):
				ws.cell(row=row, column=c, value=value).alignment = CENTER

			col = fixed_cols + 1
			for code, _ in product_list:
				this_block = block_kg_ha(block, code)
				for value in (tier_kg_ha.get((tier, code), this_block), this_block):
					ws.cell(row=row, column=col, value=value).alignment = CENTER
					col += 1

				by_month = {m: (total_kg, dose) for m, total_kg, dose in rounds.get((block, code), [])}
				annual_total = sum(total_kg for total_kg, _ in by_month.values())
				for month in product_months[code]:
					total_kg, dose = by_month.get(month, (0, 0))
					pct = int(round_half_up(total_kg / annual_total * 100)) if annual_total else 0
					ws.cell(row=row, column=col, value=f"{pct}%").alignment = CENTER
					ws.cell(row=row, column=col + 1, value=round(dose, 1)).alignment = CENTER
					col += 2
			row += 1

		ws.cell(row=section_start_row, column=1, value=section_name).alignment = CENTER
		if row - 1 > section_start_row:
			ws.merge_cells(start_row=section_start_row, start_column=1, end_row=row - 1, end_column=1)

	for letter, width in zip("ABCDE", (24, 16, 10, 12, 10)):
		ws.column_dimensions[letter].width = width
	col = fixed_cols + 1
	for code, _ in product_list:
		ws.column_dimensions[get_column_letter(col)].width = 13
		ws.column_dimensions[get_column_letter(col + 1)].width = 13
		col += 2
		for _ in product_months.get(code, []):
			ws.column_dimensions[get_column_letter(col)].width = 16
			ws.column_dimensions[get_column_letter(col + 1)].width = 10
			col += 2

	buf = BytesIO()
	wb.save(buf)
	return buf.getvalue()
