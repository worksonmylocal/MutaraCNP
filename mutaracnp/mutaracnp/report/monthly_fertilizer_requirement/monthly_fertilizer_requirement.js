frappe.query_reports["Monthly Fertilizer Requirement"] = {
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
