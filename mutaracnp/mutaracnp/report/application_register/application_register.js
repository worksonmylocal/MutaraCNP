frappe.query_reports["Application Register"] = {
    filters: [
        {
            fieldname: "farm",
            label: "Farm",
            fieldtype: "Link",
            options: "CNP Farm"
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date"
        },
        {
            fieldname: "block",
            label: "Block",
            fieldtype: "Link",
            options: "Farm Block"
        },
        {
            fieldname: "fertilizer_product",
            label: "Fertilizer Product",
            fieldtype: "Link",
            options: "Item"
        },
        {
            fieldname: "supervisor",
            label: "Supervisor",
            fieldtype: "Link",
            options: "Employee"
        }
    ]
};
