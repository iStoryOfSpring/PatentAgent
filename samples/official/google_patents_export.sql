-- Reproducible Google Patents Public Data export for the three validation domains.
-- Run in BigQuery, then export the result as newline-delimited JSON.
-- Source schema: patents-public-data.patents.publications
SELECT
  publication_number, application_number, country_code, kind_code,
  family_id, publication_date, filing_date, grant_date, priority_date,
  title_localized, abstract_localized, claims_localized,
  description_localized, inventor, assignee, ipc, cpc, citation
FROM `patents-public-data.patents.publications`
WHERE publication_number IN (
  'US-11476497-B2', -- solid-state battery
  'US-11325075-B2', -- carbon capture
  'US-11958200-B2'  -- industrial robotics
)
ORDER BY publication_number;
