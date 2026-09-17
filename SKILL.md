---
name: azure-acr-modeler
description: Model projected Azure Consumed Revenue (ACR) for a prospective or planned Azure workload, using live Azure retail pricing. Use this whenever the user wants to estimate Azure spend/consumption for a client or workload, project ACR over time (12/36 months), size compute (VMs, App Service) costs, or map projected consumption to Microsoft partner incentive tiers. Trigger on phrases like "model ACR", "estimate Azure consumption", "what would this workload cost on Azure", "Azure spend projection", or when the user is scoping a migration/deployment and wants a revenue/cost estimate to bring to a client or partner conversation.
---

# Azure ACR Modeler

Projects Azure Consumed Revenue (ACR) for a workload using **live** Azure retail
pricing, applies growth assumptions over a projection period, and outputs both
a chat summary and a downloadable Excel workbook.

Primary use case: sizing compute workloads (VMs, App Service) for a client
conversation, migration pitch, or partner-incentive planning exercise — before
real consumption data exists.

## Architecture note (read this first)

Live pricing is fetched by **the assistant itself**, via an Azure pricing MCP
tool (e.g. `azure_price_search`) — never by a script. A subprocess launched
from a script inside Claude's sandboxed VM cannot reach external APIs; only
the assistant's own tool calls can. So `scripts/calculate_acr.py` does pure
projection math on prices you've already resolved — it makes no network calls
of its own. If the MCP pricing tool isn't available in a given environment,
say so and stop rather than falling back to a script-side HTTP call — it will
fail with a network error in the sandbox.

## Workflow

### 1. Gather inputs

Ask (or infer from context) for each workload line item:
- **Name** (e.g. "Prod app servers")
- **Service**: `Virtual Machines` or `Azure App Service` are the two this skill
  is tuned for. Other services can work too — just pass through the Azure
  service name as it appears in the pricing tool's results.
- **SKU / size**: for VMs, the ARM SKU name (e.g. `Standard_D4s_v5`); for App
  Service, the tier name **with a space before the version letter** (e.g.
  `P1 v3`, not `P1v3` — the no-space form returns zero results even though it
  looks like a reasonable SKU string).
- **Region** (Azure region slug, e.g. `eastus`, `westeurope`)
- **Quantity** (how many instances)
- **Hours/month** (default 730 = always-on; ask if it's not always-on)
- **Monthly growth rate** (e.g. 0.02 for 2%/month; 0 for flat)
- **Projection length** (default 12 months; ask if they want 36 for
  longer-term partner planning)

Don't ask for exhaustive detail on a single default guess — if the user gives
a rough description ("about 4 mid-size VMs and an App Service plan, East US"),
propose reasonable SKUs (e.g. `Standard_D4s_v5`, `P1 v3`) and state the
assumption rather than blocking on every field.

### 2. Resolve pricing yourself, then compute the projection

For **each** line item, call the Azure pricing MCP tool yourself (do not
delegate this to a script) and apply these selection rules:

- **VMs**: prefer `priceType == "Consumption"`, exclude rows with "Windows"
  in the product name and "Spot"/"Low Priority" in the SKU or meter name,
  unless the user specifically asked for one of those. Windows reliably
  self-identifies in the product name for VMs (e.g. "...Dsv5 Series
  Windows"), so excluding it directly works.
- **App Service**: the OS distinction works the **opposite** way — two
  Consumption rows can share an identical SKU name (e.g. both "P1 v3") and
  only the Linux row self-identifies, via a product name ending in "-
  Linux". The Windows row is the plain, unlabeled product name and does
  **not** contain the word "Windows" anywhere. Confirmed live: querying
  "P1 v3" in eastus returns one row at $0.315/hr with product name "Azure
  App Service Premium v3 Plan" (Windows, unlabeled) and one at $0.155/hr
  with product name "Azure App Service Premium v3 Plan - Linux". Select by
  presence of "Linux" in the product name, not absence of "Windows" — the
  VM rule does not transfer here.
- If a line item's price can't be resolved (bad SKU/region/service name, or
  results too ambiguous to pick confidently), don't guess — leave that item
  with an `"error"` field describing why, and flag it to the user rather than
  silently defaulting to $0 or an arbitrary row.

Once every item has a resolved `unit_price` (or an explicit `error`), write
them to a JSON file matching the schema documented at the top of
`scripts/calculate_acr.py`, then run:

```bash
python scripts/calculate_acr.py --input workloads.json --output acr_projection.json
```

This script only does the math — compounding monthly growth, totalling across
line items — on prices you already resolved. It will flag any item you passed
through with an error and exclude it from totals; check for these and fix the
inputs (or re-resolve that item's price) before presenting results.

### 3. Present the chat summary

Give a concise summary: per-item monthly baseline, total monthly run-rate,
and cumulative ACR at the requested horizon(s) (12mo / 36mo). Keep it to a
short table, not a wall of numbers. If any items were unresolved, say so
plainly before the numbers rather than presenting a total that silently
excludes them.

### 4. Partner tier mapping (only if the user asks)

If the user wants the ACR figure mapped to a Microsoft partner incentive tier
or Solutions Partner designation, follow `references/partner_tiers.md` —
**do not state specific threshold dollar amounts from memory**; look them up
live, since they change independent of this skill.

### 5. Build the downloadable workbook

Use the `xlsx` skill's conventions (formulas not hardcoded results, blue
inputs / black formulas, `$#,##0` currency format) to build a workbook with:
- An **Inputs** tab: one row per workload item (service, SKU, region, qty,
  hours, unit price sourced from the API, growth rate) — unit price is a
  hardcoded input (blue) since it's a live lookup result, everything else
  downstream should be a formula.
- A **Projection** tab: month-by-month cost per item and total, computed via
  formulas referencing the Inputs tab (`=Inputs!$D2*(1+Inputs!$F2)^(Projection!A1-1)`
  style), not pasted-in numbers from the JSON.
- A **Summary** tab: total ACR at 12mo/36mo, monthly run-rate, and a note
  citing "Pricing source: Azure Retail Prices API, retrieved [date]" plus the
  growth-rate assumptions in plain language.

Save to the outputs directory and present it to the user with `present_files`.

## Known limits

- Pricing reflects **pay-as-you-go retail rates**, not negotiated/EA pricing,
  reservations, or savings plans. Say so in the Summary tab — real client ACR
  will typically be lower than sticker-price projections if they use
  reservations.
- The pricing tool returns many near-duplicate rows per SKU (Windows vs Linux,
  spot vs standard, low-priority, etc.) — apply the selection rules in step 2
  every time; don't assume the first result returned is the right one. Note
  the VM and App Service rules select on *opposite* signals (VM: exclude
  "Windows"; App Service: include "Linux") — don't reuse one for the other.
- App Service tier names need a space before the version letter (`P1 v3`, not
  `P1v3`) when searching — double-check this before reporting "no results" for
  an App Service SKU.
- This is a planning/pitch tool, not a substitute for the Azure Pricing
  Calculator or an actual Partner Center ACR report once real usage exists.
- `scripts/fetch_azure_prices.py` is kept in this skill only as a standalone,
  manual reference tool for testing SKU/meter names outside the sandbox (e.g.
  on your own machine). It is not called by `calculate_acr.py` and should not
  be invoked as part of the automated skill workflow.
