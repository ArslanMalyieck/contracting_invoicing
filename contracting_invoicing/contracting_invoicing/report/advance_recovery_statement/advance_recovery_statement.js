// Copyright (c) 2026, Arslan

frappe.query_reports["Advance Recovery Statement"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "contract",
			label: __("Contract"),
			fieldtype: "Link",
			options: "Contracting Contract",
		},
	],
};
