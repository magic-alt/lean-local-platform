-- Description: advance the legacy Web end-date setting to the 2026-07-13 platform default

update settings
set value_json = '"2026-07-13"'
where `key` = 'defaultEnd'
  and value_json = '"2024-12-31"';
