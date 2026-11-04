frappe.ui.form.on("Fertilizer Programme", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(__("Pull Blocks from Farm"), function () {
			if (!frm.doc.farm) {
				frappe.msgprint(__("Please set the Farm first."));
				return;
			}
			frm.call("pull_blocks_from_farm").then((r) => {
				frm.reload_doc();
				frappe.show_alert({
					message: __("Pulled {0} block(s) from {1}.", [r.message, frm.doc.farm]),
					indicator: "green",
				});
			});
		}, __("Actions"));

		frm.add_custom_button(__("Run Calculation Engine"), function () {
			if (!frm.doc.block_yield_data || frm.doc.block_yield_data.length === 0) {
				frappe.msgprint(__("Please pull block yield data before running the calculation."));
				return;
			}
			if (!frm.doc.potassium_source) {
				frappe.msgprint(__("Please select a Potassium Source before running the calculation."));
				return;
			}
			frappe.call({
				method: "mutaracnp.mutaracnp.utils.calculation_engine.calculate_programme",
				args: { programme_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Calculating..."),
				callback(r) {
					if (r.message !== undefined) {
						frm.reload_doc();
						frappe.show_alert({
							message: __("Generated {0} programme line(s).", [r.message]),
							indicator: "green",
						});
					}
				},
			});
		}, __("Actions"));
	},

	crop(frm) {
		set_potassium_source_query(frm);
	},

	onload(frm) {
		set_potassium_source_query(frm);
	},
});

function set_potassium_source_query(frm) {
	if (!frm.doc.crop) return;
	frappe.db.get_list("Crop Nutrient Rule", {
		filters: { crop: frm.doc.crop, nutrient_source_group: ["is", "set"] },
		fields: ["fertilizer_product"],
		limit: 0,
	}).then((rows) => {
		const products = rows.map((r) => r.fertilizer_product).filter(Boolean);
		frm.set_query("potassium_source", () => ({ filters: { name: ["in", products] } }));
	});
}

frappe.ui.form.on("Programme Block Yield", {
	block(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.block) return;

		frappe.db.get_doc("Farm Block", row.block).then((block) => {
			frappe.model.set_value(cdt, cdn, "section", block.section);
			frappe.model.set_value(cdt, cdn, "area_ha", block.area_ha);
			frappe.model.set_value(cdt, cdn, "tree_count", block.tree_count);
			frappe.model.set_value(cdt, cdn, "yield_kg_ha", block.projected_yield_kg_ha);
		});
	},
});
