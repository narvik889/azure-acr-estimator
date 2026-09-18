# Azure ACR Modeler — a Claude Skill

A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that projects **Azure Consumed Revenue (ACR)** for a prospective workload using **live** Azure retail pricing — instead of an LLM guessing at numbers from memory, or a human spending twenty minutes to a few hours per estimate in the Azure Pricing Calculator.

Give it a rough workload description ("about 4 mid-size VMs and an App Service plan, East US"), and it resolves real prices, projects cost forward with a growth assumption, and outputs both a chat summary and a downloadable, auditable Excel workbook.

Read the full backstory — including the sandbox networking dead end and the App Service pricing gotcha that cost the most time — in the [blog post](#) that goes with this repo.

## Why this exists

Estimating what a workload will cost on Azure is mechanical work: pull live pricing, apply a few reasonable assumptions, project it forward, hand it to whoever needs the number. Mechanical work done slightly differently every time is exactly where inconsistency creeps in — and an LLM prompted cold on the same task is non-deterministic by default. This skill fixes the assumptions and the workflow so the same input produces the same output every time, while still pulling real, current prices rather than stale training data.

## What it covers today

- **Virtual Machines** and **Azure App Service** compute costs
- Pay-as-you-go (Consumption) retail pricing — not negotiated/EA pricing, reservations, or savings plans
- 12- or 36-month growth projections with a per-item monthly growth rate
- An auditable Excel workbook (formulas, not pasted-in numbers) with Inputs / Projection / Summary tabs
- Optional mapping to current Microsoft partner incentive tiers (looked up live, never hardcoded)

**Not yet covered:** storage, network egress, backup, monitoring, and other non-compute costs. See [`SKILL.md`](./SKILL.md) → "Known limits" for the full list.

## Requirements

- Claude (Desktop or Cowork) with skills enabled
- **An Azure pricing MCP server**, connected to Claude. This skill's price-fetching step assumes a tool like `azure_price_search` is available — it does *not* fetch pricing itself (see [Architecture](#architecture) below for why). This was built and tested against [AzurePricingMCP](https://github.com/msftnadavbh/AzurePricingMCP); any MCP server that exposes equivalent Azure Retail Prices API search functionality should work.
- Python 3.9+ (stdlib only — no external packages required for the scripts themselves)

## Setup

1. Install and connect an Azure pricing MCP server to Claude (see [AzurePricingMCP](https://github.com/msftnadavbh/AzurePricingMCP) for one option, or use your own).
2. Copy this folder into your Claude skills directory.
3. Confirm the skill is picked up — ask Claude something like *"estimate Azure cost for 4 D4s_v5 VMs in East US"* and it should trigger.

## Usage

Just describe the workload in plain language — exact SKUs, or a rough description Claude can propose reasonable defaults for:

> "Model 12-month ACR for 4 Standard_D4s_v5 VMs in East US growing 2%/month, plus 2x App Service P1 v3 flat."

Claude will resolve live prices for each line item, run the projection, and hand back a chat summary plus a downloadable workbook.

To try the math engine standalone without Claude, see [`workloads.example.json`](./workloads.example.json):

```bash
python scripts/calculate_acr.py --input workloads.example.json --output acr_projection.json
```

This reproduces a 12-month ACR of **$10,234.95** using the example's pre-resolved prices — useful for sanity-checking the projection logic itself, independent of live pricing.

Then build the workbook from that same projection:

```bash
python scripts/build_workbook.py --input acr_projection.json --output acr_workbook.xlsx
python /mnt/skills/public/xlsx/scripts/recalc.py acr_workbook.xlsx   # mandatory — see below
```

The whole pipeline (price resolution → math → workbook, including the recalc step) has been run end-to-end and verified: zero formula errors, and the Summary tab's `12-month ACR` cell — a live formula, not a pasted number — resolves to the same $10,234.95 as the standalone script above.

## Architecture

The one thing worth understanding before you extend this: **`calculate_acr.py` makes zero network calls.** A subprocess launched from a script inside Claude's sandboxed environment can't reach external APIs — only Claude itself can, through its own tool calls. So pricing is always resolved by Claude via the MCP tool *first*, and only the already-priced result is handed to the script, which does pure projection math. `scripts/fetch_azure_prices.py` is kept only as a standalone CLI for manually testing SKU/meter names outside the sandbox — it is not part of the automated skill workflow. Full detail in [`SKILL.md`](./SKILL.md).

## Repo layout

```
azure-acr-modeler/
├── SKILL.md                    # Full workflow, selection rules, known limits
├── workloads.example.json      # Sample input for calculate_acr.py
├── scripts/
│   ├── calculate_acr.py        # Pure projection math — no network calls
│   ├── build_workbook.py       # Builds the Inputs/Projection/Summary workbook from calculate_acr.py's output
│   └── fetch_azure_prices.py   # Standalone manual-testing CLI only
└── references/
    └── partner_tiers.md        # How to map ACR to partner incentive tiers
```

## Known limits

See the "Known limits" section of [`SKILL.md`](./SKILL.md) for the full, current list — pricing assumptions, SKU selection quirks, and what this tool is (and isn't) a substitute for.

## Contributing

Feedback and PRs welcome — especially selection-rule fixes for services beyond VMs and App Service, since each one so far has had its own naming quirks.

## License

[MIT](./LICENSE)
