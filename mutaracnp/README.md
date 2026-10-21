### MutaraCNP

Mutara Fertilizer Planning Module

Built from the same shell as [UpandeCNP](https://github.com/worksonmylocal/UpandeCNP), adapted for a
single farm (Mutara) planning fertilizer for Avocado first, with Cabbages, Potatoes, Onions and
Passion Fruit already modelled as crops for later. Blocks carry a **projected** yield rather than a
previous year's actual, since Mutara has no harvest history yet.

The nutrient-rate calculation engine and the crop/product master data (tiers, rates, norms) are a
deliberately separate, later phase of work - this ships the full doctype/page/report/role shell and
UI so that work can land on top of it.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO
bench install-app mutaracnp
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/mutaracnp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
