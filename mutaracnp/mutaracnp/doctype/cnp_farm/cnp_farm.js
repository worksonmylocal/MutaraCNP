frappe.ui.form.on("CNP Farm", {
	refresh(frm) {
		frappe.call("mutaracnp.mutaracnp.utils.scp_sync.scp_sync_available").then((r) => {
			if (!r.message) return;

			frm.add_custom_button(__("Sync Blocks from Avocado Yield"), function () {
				frappe.confirm(
					__("Pull the current block registry and latest season's forecast from Avocado Yield Block / Avocado Production Forecast? This only reads from that app - nothing is written back to it, and existing Sections/Farm Blocks here are updated to match, not duplicated."),
					() => {
						frappe.call({
							method: "mutaracnp.mutaracnp.utils.scp_sync.sync_blocks_from_scp",
							args: { farm_name: frm.doc.farm_name },
							freeze: true,
							freeze_message: __("Syncing..."),
							callback(r) {
								if (!r.message) return;
								const m = r.message;
								frappe.show_alert({
									message: __("{0} block(s) synced ({1} with a projected yield, {2} skipped).",
										[m.synced, m.with_forecast, m.skipped]),
									indicator: "green",
								});
							},
						});
					}
				);
			}, __("Actions"));
		});
	},
});
