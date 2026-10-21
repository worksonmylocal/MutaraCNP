### MutaraCNP

Mutara Fertilizer Planning Module

Built on the same shell as [UpandeCNP](https://github.com/worksonmylocal/UpandeCNP), adapted for Mutara:

- Single farm (Mutara), rather than a multi-farm group.
- Avocado is the primary crop being actively planned for, with Cabbages, Potatoes, Onions and Passion Fruit carried as master data for when they come online.
- Yield-tier classification runs off a **projected** yield (Mutara has no harvest history yet), not a previous year's actual yield.

The nutrient-rate calculation engine and seeded crop/product master data (rates, tiers, norms) are a deferred follow-up — this app currently ships the full doctype/page/report/role shell and UI with that phase's endpoints stubbed.

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
