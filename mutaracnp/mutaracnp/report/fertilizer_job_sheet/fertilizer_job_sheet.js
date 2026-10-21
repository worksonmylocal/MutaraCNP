frappe.query_reports["Fertilizer Job Sheet"] = {
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
        },
        {
            fieldname: "application_month",
            label: "Application Month",
            fieldtype: "Select",
            options: "\nJanuary\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember"
        },
        {
            fieldname: "status",
            label: "Status",
            fieldtype: "Select",
            options: "\nPlanned\nIssued\nApplied\nVerified"
        }
    ]
};
