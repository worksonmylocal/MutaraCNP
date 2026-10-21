frappe.query_reports["Budget vs Actual Cost"] = {
    filters: [
        {
            fieldname: "fertilizer_budget",
            label: "Fertilizer Budget",
            fieldtype: "Link",
            options: "Fertilizer Budget",
            reqd: 1
        }
    ]
};
