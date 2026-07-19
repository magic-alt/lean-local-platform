-- description: Accelerate provider instrument watermark lookups

create index if not exists idx_provider_raw_dataset_instrument_date
    on provider_raw_records(dataset_key, instrument_code, business_date);
