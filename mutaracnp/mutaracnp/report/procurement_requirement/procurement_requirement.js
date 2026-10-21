frappe.query_reports["Procurement Requirement"] = {
    filters: [
        {
            fieldname: "fertilizer_programme",
            label: "Fertilizer Programme",
            fieldtype: "Link",
            options: "Fertilizer Programme",
            reqd: 1
        }
    ]
};
