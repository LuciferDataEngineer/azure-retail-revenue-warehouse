# Sources and reuse

Sources reviewed **4 November 2026, Australia/Melbourne**. Machine timestamps can show 3 November UTC. This is an independent implementation, without endorsement by the source authors, UCI, Microsoft or the project guide's author.

## Historical source data

**Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. [DOI: 10.24432/C5BW33](https://doi.org/10.24432/C5BW33).** [Dataset and dictionary](https://archive.ics.uci.edu/dataset/352/online+retail); [direct ZIP](https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip).

The source describes 541,909 transaction lines from one UK online retailer, dated 1 December 2010 through 9 December 2011. It includes invoice/product identifiers, descriptions, quantities, timestamps, unit prices in sterling, customer identifiers and countries. Invoice codes beginning with C indicate cancellations. The website's missing-value metadata should not substitute for inspecting the workbook; this implementation measures actual missingness.

UCI marks this dataset **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**. Credit the author, dataset, DOI and licence when sharing source-derived outputs, and indicate transformations. This repository converts workbook rows into daily Parquet deliveries, applies documented contracts, represents absent customers with an Unknown member, classifies signed amounts and publishes aggregate results. No endorsement is implied. Source files and row-level derived data are downloaded locally and excluded from Git; committed aggregate observations are attributed to this dataset under CC BY 4.0. Original code and documentation are MIT, and synthetic fixtures are original invented examples.

Observed download identity:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| UCI ZIP | 23,715,478 | `f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b` |
| `Online Retail.xlsx` | 23,715,344 | `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d` |

These identify the bytes retrieved now, not a proven original 2015 publication snapshot. Retained manifests record each observed version, retrieval time and processing contract. Do not overwrite them when an upstream file changes.

## Current relevance, with a clear boundary

The ONS [23 October 2026 retail release](https://www.ons.gov.uk/businessindustryandtrade/retailindustry/bulletins/retailsales/september2026) reports changes in online sales and revisions to prior monthly estimates. That is a current example of why retail reporting needs clear metric definitions and correction handling. ONS describes Great Britain aggregate statistics; the UCI workbook is a historical sample from one business. This project does not combine them, infer present-day revenue from 2010–2011 transactions or forecast an industry trend. The ONS publication is context only, not pipeline input.

## Original implementation

The user selected [five Azure data engineering project specifications](https://app.notion.com/p/5-Production-Grade-Azure-Data-Engineering-Projects-Grow-Data-Skills-407924178a6181b9a1e8d5482fe40644). This implements the second pattern, scheduled retail ELT, with original source adapters, SQL, infrastructure and tests. No restricted course assets are copied. Daily arrivals are a **simulation** derived from historical invoice dates; the source is a single workbook, not a live daily feed.
