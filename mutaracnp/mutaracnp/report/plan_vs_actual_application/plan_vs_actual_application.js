frappe.query_reports["Plan vs Actual Application"] = {
    filters: [
        {
            fieldname: "farm",
            label: "Farm",
            fieldtype: "Link",
            options: "CNP Farm"
        },
        {
            fieldname: "season",
            label: "Season",
            fieldtype: "Data"
        },
        {
            fieldname: "block",
            label: "Block",
            fieldtype: "Link",
            options: "Farm Block"
        }
    ]
};
