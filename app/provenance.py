"""Where every number on screen comes from. Shown when the user clicks the small (i) next to a number.

kind:   Observed = copied from a source file; Derived = computed by an AETHER rule; Assumption = set by the team.
files:  the CALIBER source files (Excel) the number is built from.
cols:   the columns used.
how:    the rule, in one or two sentences.
"""

SOURCES = {
    # ---------------- overview
    "high_risk": dict(title="High stockout risk", kind="Derived", files=["Movement Material", "PR PO", "FuncLoc list", "BoM"],
                      cols="Posting Date, Quantity · PR-Date, PO-Delivery Date · FuncLoc Criticallity · Stock",
                      how="For each part, 2,000 simulated lead times of demand. Chance to run out = share of runs where demand ≥ stock on hand. "
                          "Counted when the chance is ≥ 50% and the part sits on class A or S equipment."),
    "critical_empty": dict(title="Critical parts at zero stock", kind="Derived", files=["BoM", "FuncLoc list", "Movement Material"],
                           cols="Stock · FuncLoc Criticallity · Posting Date",
                           how="Stock = 0, highest class of its locations is A or S, and the part was issued at least once May 2025 – Sep 2026."),
    "capital": dict(title="Capital tied up", kind="Derived", files=["BoM", "PR PO"], cols="Stock · PO-Item Amount, PO-Currency",
                    how="Σ (stock − recommended max) × unit price, for parts above the recommended max. Unit price = median PO price in IDR. "
                        "2 implausible synthetic records are excluded."),
    "reorder": dict(title="Reorder now", kind="Derived", files=["BoM", "Movement Material", "PR PO", "FuncLoc list"],
                    cols="Stock · issues · lead times · class",
                    how="Stock ≤ recommended min (the simulated reorder point at the class service level), and the part has demand or is an insurance spare."),
    "planning": dict(title="Planning type fixes", kind="Derived", files=["BoM", "Movement Material", "FuncLoc list"],
                     cols="MRP Type · Posting Date · FuncLoc Criticallity",
                     how="Non Stock (min–max 0/0) but issued 3+ times in the last 12 months → Stock Item. "
                         "Stock Item never issued in 17 months on class B/C equipment → Non Stock."),
    "stock_value": dict(title="Stock value", kind="Derived", files=["BoM", "PR PO"], cols="Stock · PO-Item Amount, PO-Currency",
                        how="Stock × median PO unit price in IDR (USD 18,000, EUR 20,600, SGD 14,000, JPY 115). "
                            "Parts never bought use the fleet median price."),
    "health": dict(title="Stock health", kind="Derived", files=["BoM", "Movement Material"], cols="Stock · Posting Date",
                   how="Potentially obsolete candidate: stock > 0, never issued in the recorded 17 months. Non-moving by recorded issues: not issued in 12 months. Slow-moving by recorded issues: ≤ 2 issues in 12 months and above max. "
                       "Excess: above max. Below reorder point: under min."),
    "demand_class": dict(title="Demand pattern", kind="Derived", files=["Movement Material"], cols="Posting Date, Quantity",
                         how="Monthly totals May 2025 – Sep 2026. ADI = 17 ÷ months with demand; CV² = (std ÷ mean)² of non-zero months. "
                             "Cut-offs 1.32 and 0.49 (Syntetos & Boylan, 2005)."),
    "consumption": dict(title="Consumption value per month", kind="Derived", files=["Movement Material", "PR PO"],
                        cols="Posting Date, Quantity · PO-Item Amount, PO-Currency",
                        how="Σ issued quantity × median PO unit price (IDR) per month. Only parts with a purchase history (1,250) are valued; "
                            "the 2 implausible synthetic records are excluded."),
    # ---------------- part page
    "stock": dict(title="Stock now", kind="Observed", files=["BoM"], cols="Stock", how="Copied from BoM.xlsx."),
    "minmax_now": dict(title="Min / max now", kind="Observed", files=["BoM"], cols="Min.Qty, Max.Qty",
                       how="The parameters in the system today. Every Non Stock part has 0 / 0."),
    "minmax_new": dict(title="Recommended min / max", kind="Derived", files=["Movement Material", "PR PO", "FuncLoc list"],
                       cols="issues · lead times · class",
                       how="Min = reorder point from 2,000 simulated lead-time demands at the class service level (A 99%, S 97.5%, B 95%, C 90%). "
                           "Max = min + economic order quantity √(2 × annual demand × IDR 750,000 ÷ (25% × unit price))."),
    "forecast": dict(title="Forecast per month", kind="Derived", files=["Movement Material"], cols="Posting Date, Quantity",
                     how="SES (α 0.15) for smooth and erratic demand; SBA (Croston with Syntetos–Boylan correction) for intermittent and lumpy."),
    "lead_time": dict(title="Promised lead time", kind="Derived", files=["PR PO"], cols="PR-Date, PO-Delivery Date",
                      how="Median days from purchase requisition to the PO delivery date for this part; fleet median (42 days) if never bought. "
                          "PO-Delivery Date is a promised date: there is no goods-receipt date in the data (DEF-06)."),
    "p_stockout": dict(title="Chance to run out", kind="Derived", files=["Movement Material", "PR PO", "BoM"],
                       cols="issues · lead times · Stock",
                       how="Share of 2,000 simulated lead times in which demand reaches the stock on hand."),
    "unit_price": dict(title="Unit price", kind="Derived", files=["PR PO"], cols="PO-Item Amount, PO-Currency",
                       how="Median PO price per unit in IDR. PO-Item Amount is read as a unit price (it does not grow with quantity)."),
    "service_level": dict(title="Target service level", kind="Assumption", files=[], cols="",
                          how="Set by the team per class: A 99%, S 97.5%, B 95%, C 90%. Change it on the scenarios page."),
    "breakdowns": dict(title="Breakdowns", kind="Observed", files=["Notif History", "BoM"], cols="Notification Type = N2, Functional Location",
                       how="Emergency notifications (N2) on the functional locations where this part is installed, May 2025 – Sep 2026."),
    "late": dict(title="Promised later than requested", kind="Derived", files=["PR PO"], cols="PR-Delivery Date, PO-Delivery Date",
                 how="Share of purchase lines whose promised PO delivery date is later than the date requested on the PR. Not a measured late delivery (DEF-06)."),
    # ---------------- INSpire Command Center KPIs (Feature Spec 3.1)
    "below_min": dict(title="Issued Stock Items below Min", kind="Derived", files=["BoM", "Movement Material"], cols="MRP Type, Stock, Min.Qty · Posting Date",
                      how="Stock Item, issued at least once May 2025 – Sep 2026, stock < Min. A comparison, not a stockout: what Min means is not confirmed (DEF-02)."),
    "min_below_ltd": dict(title="Min below promised lead-time demand", kind="Derived", files=["BoM", "Movement Material", "PR PO"],
                          cols="Min.Qty · Quantity · PR-Date, PO-Delivery Date",
                          how="Stock Item, issued, promised interval known: (units issued ÷ 518 days) × median promised interval > Min. "
                              "Assumes Min is a reorder point (DEF-02). Tested on 672 parts."),
    "nonstock_issued": dict(title="Demand without a stocking policy", kind="Observed", files=["BoM", "Movement Material"], cols="MRP Type · Material Number",
                            how="Non Stock parts (no Min/Max) issued at least once in the window; share = their issue lines over all issue lines."),
    "abnormal": dict(title="Abnormal consumption", kind="Derived", files=["Movement Material"], cols="Posting Date · Quantity",
                     how="A month is abnormal when its issued quantity is above BOTH 3 × the part's median non-zero month and "
                         "mean + 3 standard deviations. Needs at least 3 months with use. Flags a spike to check (turnaround, wrong posting, "
                         "new failure mode); it does not change the forecast by itself."),
    "reorder_by": dict(title="Reorder by", kind="Derived", files=["BoM", "Movement Material", "PR PO"], cols="Stock · Quantity · PR-Date, PO-Delivery Date",
                       how="Days until stock falls to the reorder point at the forecast rate: (stock − reorder point) ÷ (forecast per month ÷ 30.4), "
                           "counted from the stock date 1 Oct 2026. 0 = already at or below the reorder point: order now."),
    "evidence": dict(title="Evidence grade", kind="Derived", files=["Movement Material", "PR PO", "Material Master"],
                     cols="Posting Date · PR-Date, PO-Delivery Date · Material Type · Min/Max",
                     how="Team rule D-24. Simulation population T3 (665 parts): Stock Item, issued, promised lead time and unit amount "
                         "from PO history, non-zero recorded Min or Max. Grade A (228) = T3 with at least 6 active months: the proposed "
                         "Min/Max is a candidate. Grade B and parts outside T3: the Min/Max is scenario-configured, low confidence, "
                         "and needs a reason to approve. Demand class: D0 never issued, D1 1-2 months, D2 3-5, D3+ 6 or more."),
    "engine_risk": dict(title="Simulated shortfall risk", kind="Scenario", files=["Team engine eng_health_flags.csv"], cols="stockout_risk_level, shortfall_probability_max",
                     how="Team engine run RUN-277fc4b966e6, Monte Carlo 1,000 replications under the recorded Min/Max reading (unverified, D-02). "
                         "Assessed for the 228 Grade A parts only (D-24); others are 'not assessed'. Simulated, never an actual stockout."),
    "engine_rec": dict(title="Recommended action", kind="Derived", files=["Team engine eng_recommendation.csv"], cols="recommended_action, action_label, reason, trigger_condition",
                     how="Team engine rule on the simulation: Reorder when recorded stock is at or below the proposed s and the simulated shortfall "
                         "probability is above 0.10; Reduce when days above Max exceed 50% (thresholds D-25, analyst-selected). Shown for demand "
                         "scenario A and PR PO view ED, X2 at 95%. Every row is a candidate that needs review."),
    "engine_grade": dict(title="Evidence and abstention", kind="Derived", files=["Team engine eng_material_tier.csv", "eng_recommendation.csv"], cols="policy_grade, recommended_action",
                     how="Parameters only for the 228 Grade A parts (D-24). 4,595 parts get Monitor from a recorded-issue flag, 2,658 get no action "
                         "because evidence is too thin. The product withholds a number rather than inventing one."),
    "engine_ho": dict(title="Held-out test", kind="Scenario", files=["Team engine eng_kpi_summary.csv"], cols="AV-1, run_set HO",
                     how="Parameters fitted on 2025-05 to 2026-03 only, then replayed on 2026-04 to 2026-09 for 197 Grade A parts. Count of parts "
                         "with any simulated shortage: recorded Min/Max (R0) vs proposed X2. Demand A, view ED, opening-stock rule K30; the range "
                         "covers all 12 scenario combinations. Lower shortages come with more stock on hand (trade-off, not a free gain)."),
    "idle_stock_item": dict(title="Idle Stock Items", kind="Observed", files=["BoM", "Movement Material"], cols="MRP Type, Stock · Posting Date",
                            how="Stock Item with stock on hand and no issue May 2025 – Sep 2026."),
    "wo_bom_match": dict(title="Work order to BoM match", kind="Observed", files=["Movement Material", "Notif History", "BoM"],
                         cols="Order · Functional Location · Material No",
                         how="Issue rows whose order appears in Notif History (2,791) and whose part is in the BoM of that notification's location. "
                             "Low match = maintenance work and spare-part master data are poorly linked."),
    "equipment_category": dict(title="Equipment category", kind="Assumption", files=["FuncLoc list"], cols="Functional Location, FunctLocDescrip.",
                               how="Inferred from the tag (PP- pump, HE- exchanger, BF- furnace, PRV- safety valve, -M motor ...) and the description. "
                                   "A team rule, not a field in the data."),
    "component": dict(title="Component placement", kind="Assumption", files=["BoM"], cols="Material Desc.",
                      how="A part is placed on a drawing component by keywords in its description: BEARING → bearing, SEAL/PACKING → seal, "
                          "COUPLING → coupling, IMPELLER/CASING → casing, TUBE/BUNDLE → tube bundle, GASKET → flanges. Others: 'Other parts'."),
    "simulation": dict(title="Policy simulation", kind="Scenario", files=["Movement Material", "PR PO", "BoM"], cols="Posting Date, Quantity · promised intervals · Stock, Min, Max",
                       how="365 simulated days × 100–300 runs. Daily issues ~ Poisson of the part's own rate, sizes resampled from its history, "
                           "promised intervals resampled from its PR PO lines; the same random days for every policy (common random numbers). "
                           "SIMULATED under stated assumptions, not observed: stock applies on day 0 (S-01), no open orders at the start (S-02), "
                           "Min = reorder level and Max = order-up-to (S-03, unverified), parts independent (S-08). A simulated shortage is never a real stockout."),
}
