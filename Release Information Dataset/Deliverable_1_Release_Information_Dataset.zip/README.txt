DELIVERABLE 1: RELEASE INFORMATION DATASET

Project: CloudWatch AI - Cloud Service Change Analyst

Dataset size:
- Curated records: 14
- Provider represented: Google Cloud

Files:
- release_information_dataset.csv
- release_information_dataset.xlsx

Dataset fields include:
- provider
- title
- summary
- content
- url
- published_at
- category
- services
- source
- collected_at
- collection_type
- dataset_review

Collection and curation:
The dataset was obtained from the project's live collection pipeline.
A generic page-heading record was removed during manual curation.
The remaining records were selected from the collected Google Cloud entries.

Limitations:
- Some scraped entries may contain boilerplate or imperfect text boundaries.
- Some records have generic titles.
- Categories are assigned using keyword-based classification.
- Publication dates may be missing or may reflect extracted source-page dates.
- Some entries may contain mixed or noisy content.
- Records should be checked against their official source URLs before being treated as authoritative.

This is a manually curated dataset derived from live collection.
It is not a fully manually verified ground-truth dataset.

The original collected dataset is preserved separately in the project.
