# Olist Brazilian E-Commerce workspace

A separate real-data workspace imports the official public Kaggle ZIP into data/olist.duckdb. The UCI GBP tables and synthetic demonstration remain separate. Source: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), CC BY-NC-SA 4.0 as identified on its dataset card. Attribution and license appear in About this data and /api/datasets.

## Actual import

The official download in data/olist_source.zip contains nine CSVs. Counts: 99,441 orders, 99,441 customer rows, 112,650 item rows, 103,886 payment rows, 99,224 review rows, 32,951 products, 3,095 sellers, 1,000,163 geolocation rows and 71 category translations. Raw source tables are retained with file hashes. No generated records are substituted.

olist_order_facts contains one row per order. Item prices/freight, payment values and review scores are aggregated separately by order before joining. This prevents multiple items, payments and reviews from multiplying sales or order counts. Primary orders/customer conflicts reject import; exact source duplicates are removed in preparation. Invalid component numeric values and orphan component rows are excluded and counted. The official import had no excluded invalid/orphan component rows. Geolocation has 261,831 exact duplicate rows in the preparation report; it is retained as raw data and not joined into the analytical workflow.

The application uses three explicit eligible cohorts:

| View | Eligible orders | Policy |
|---|---:|---|
| Sales | 96,478 | Delivered orders with eligible item prices |
| Delivery | 96,470 | Delivered orders with actual/estimated delivery dates and nonnegative elapsed delivery time |
| Reviews | 95,824 | Comparable delivered orders with valid review scores |

The raw order purchase dates span 2016-09-04 to 2018-10-17. Each implemented view spans 2016-09-15 to 2018-08-29. The copilot and controls use the active view's eligible bounds. All time-series and period filters refer to purchase dates; they are order cohorts, not delivery-date buckets. Coverage warnings identify the incomplete final month.

## Metric definitions

- Sales value (BRL): sum of item prices on delivered orders. Freight, payments and canceled orders are excluded. This is merchandise sales value, not accounting profit.
- Eligible orders: distinct order IDs in the selected view, dates and filters.
- Average order value (BRL): delivered merchandise sales value divided by distinct eligible orders; freight excluded.
- Late delivery rate: percentage of comparable delivered orders whose actual delivery calendar date exceeds the promised calendar date. Delivery later in the day on the promised date is on time. Missing dates and non-delivered orders are excluded.
- Average delivery time: elapsed days from purchase to customer delivery among comparable delivered orders.
- Average review score: average of each eligible order's mean valid review score. Multiple review rows are averaged within order first; a heavily reviewed order does not get extra weight.
- Reviewed orders: distinct eligible comparable delivered orders with valid reviews.
- Low review rate: percentage of eligible reviewed orders whose mean score is at most 2.

Review scores are limited to 1-5. Missing reviews are excluded only from the review view, and missing delivery information only from delivery/review cohorts. City/state filters use customer delivery geography. State codes such as SP and RJ are source values. Rates and averages use bar charts, not pie-chart shares.

## Questions and demonstration

Select Olist Brazil real data, then ask:

1. Show monthly sales value for 2017.
2. Top 5 states by late delivery rate in 2017.
3. Compare review scores for late and on-time deliveries in 2017.
4. What about SP?
5. Save this view. Approve the confirmation, change the view and reopen it.
6. Compare sales in October 2017 and November 2017.
7. Why did sales change?

The same controller retrieves pages, plans typed filters/dates/sorts/top-N, validates controls, queries DuckDB, applies UI actions and verifies applied state. Every answer has an evidence link and expandable metric/dataset/filter/date/SQL evidence. Workspace switches clear foreign-dataset conversation metrics. Explanation follow-ups preserve the chosen comparison periods. Sales-change explanations show numerical state contributors plus a residual; review/delivery associations do not establish causal effects.

The initial tested scope is Sales, Delivery and Reviews with state, city, order status and delivery-status controls. Seller/product/category/payment-method rankings, geography maps, free-text review sentiment, net refunds, profit, taxes, predictions and external-platform UI control are not implemented. Their source tables are retained for future work. The existing synthetic operational demo and UCI sales workflow remain available.

## Windows

The official ZIP is already downloaded and imported in this workspace. Stop your running server with Ctrl+C, then:

```powershell
.\start.bat
```

Open http://localhost:8004 and press Ctrl+F5. No key, model installation or dataset reimport is needed for this addition. The existing .env provider configuration is preserved.

To reproduce the download and import on a different checkout:

```powershell
Invoke-WebRequest -Uri 'https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce' -OutFile 'data/olist_source.zip'
.\.venv\Scripts\python.exe -m backend.data.import_olist data/olist_source.zip
```

The importer also accepts a directory containing the original named CSV files. If Kaggle changes access requirements, use Download on the official dataset page and import the resulting ZIP. Import builds a temporary DuckDB file and replaces the database after successful validation; stop the application before reimporting on Windows.

## Measured validation

See eval/reports/olist_independent.json, olist_browser.json and olist_live.json. These separate independent numerical calculations, actual browser verification and actual model request status. Browser tests use an isolated rules-mode server; live model samples verify backend state separately. No arbitrary-question or multilingual success claim is made.

Reproduce checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run_olist_checks
.\.venv\Scripts\python.exe -m eval.verify_olist_browser --url http://localhost:8004
```

The independent oracle reads original CSV files using csv.DictReader and Decimal, without using importer normalization or semantic SQL for expected values. It checks view eligibility/coverage, annual totals and averages, late-delivery state rankings, late versus on-time review means, a period delta and nonmultiplying order/payment/review joins. Browser checks cover three destinations on desktop and phone, top-N, SP follow-ups, exact evidence navigation, saved-view confirmation/reopen and switching back to UCI and synthetic.


Final measured results: 103 unit/integration tests passed; 40/40 independent Olist numerical checks; 8 desktop/mobile browser requests across all three destinations, including source links and saved-view reopening; 10 UCI feature browser requests passed. The unchanged synthetic benchmark retained 350/350 intents and 323/323 acceptable destinations and states, with no failures. Three configured Groq model requests succeeded with backend state verification; these are individual samples and separate from the rules-mode browser run.
