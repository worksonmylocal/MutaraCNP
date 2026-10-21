frappe.query_reports["Section Fertilizer Plan"] = {
    filters: [
        {
            fieldname: "fertilizer_programme",
            label: "Fertilizer Programme",
            fieldtype: "Link",
            options: "Fertilizer Programme",
            reqd: 1
        },
        {
            fieldname: "section",
            label: "Section",
            fieldtype: "Link",
            options: "Section"
        },
        {
            fieldname: "fertilizer_product",
            label: "Fertilizer Product",
            fieldtype: "Link",
            options: "Item"
        }
    ]
};
