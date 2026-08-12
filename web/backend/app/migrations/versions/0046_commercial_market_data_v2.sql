-- description: Add the provider-neutral commercial market-data v2 schema
-- rollback: stop v2 writers, retain source evidence, and remove the additive v2 tables in reverse dependency order through a reviewed forward migration

create table if not exists market_schema_versions_v2 (
    version text primary key,
    contract_version text not null,
    state text not null,
    prepared_at datetime(6) not null,
    activated_at datetime(6),
    preparation_report_json json not null,
    check (state in ('prepared','active','retired'))
);

create table if not exists data_providers_v2 (
    id text primary key,
    provider_key text not null unique,
    display_name text not null,
    priority integer not null default 100,
    status text not null default 'active',
    metadata_json json not null,
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    check (priority >= 0),
    check (status in ('active','disabled','retired'))
);

create table if not exists provider_datasets_v2 (
    id text primary key,
    provider_id text not null,
    dataset_key text not null,
    api_name text not null,
    asset_class text not null,
    contract_version text not null,
    storage_tier text not null,
    status text not null,
    permission_status text not null default 'unknown',
    documentation_url text,
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    unique(provider_id,dataset_key,contract_version),
    foreign key (provider_id) references data_providers_v2(id),
    check (storage_tier in ('canonical','typed_source','columnar')),
    check (status in ('active','retired')),
    check (permission_status in ('unknown','available','empty','denied','retryable'))
);

create table if not exists dataset_contract_versions_v2 (
    id text primary key,
    provider_dataset_id text not null,
    contract_version text not null,
    effective_from date not null,
    effective_to date,
    natural_key_json json not null,
    fields_json json not null,
    contract_sha256 text not null,
    created_at datetime(6) not null,
    unique(provider_dataset_id,contract_version),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (effective_to is null or effective_to >= effective_from)
);

create table if not exists ingestion_runs_v2 (
    id text primary key,
    provider_dataset_id text not null,
    request_json json not null,
    status text not null,
    started_at datetime(6) not null,
    finished_at datetime(6),
    observed_rows bigint not null default 0,
    accepted_rows bigint not null default 0,
    rejected_rows bigint not null default 0,
    raw_object_id text,
    payload_sha256 text,
    error text,
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (status in ('queued','running','success','partial','failed','cancelled')),
    check (observed_rows >= 0 and accepted_rows >= 0 and rejected_rows >= 0)
);

create table if not exists source_observations_v2 (
    id text primary key,
    provider_dataset_id text not null,
    ingestion_run_id text not null,
    natural_key_hash text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    current_natural_key_hash varchar(64) generated always as (case when is_current = 1 then natural_key_hash else null end) stored,
    published_at datetime(6),
    source_updated_at datetime(6),
    observed_at datetime(6) not null,
    valid_from datetime(6),
    valid_to datetime(6),
    payload_hash text not null,
    source_table text not null,
    source_row_id text not null,
    unique(provider_dataset_id,natural_key_hash,revision_no),
    unique(provider_dataset_id,current_natural_key_hash),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    foreign key (ingestion_run_id) references ingestion_runs_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1)),
    check (valid_to is null or valid_from is null or valid_to >= valid_from)
);

create index if not exists idx_source_observations_v2_current
    on source_observations_v2(provider_dataset_id,natural_key_hash,is_current);
create index if not exists idx_source_observations_v2_observed
    on source_observations_v2(provider_dataset_id,observed_at);

create table if not exists source_priority_rules_v2 (
    id text primary key,
    fact_type text not null,
    asset_class text,
    market text,
    provider_id text not null,
    priority integer not null,
    valid_from datetime(6) not null,
    valid_to datetime(6),
    reason text not null,
    created_at datetime(6) not null,
    unique(fact_type,asset_class,market,provider_id,valid_from),
    foreign key (provider_id) references data_providers_v2(id),
    check (priority >= 0),
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists fact_resolution_log_v2 (
    id text primary key,
    fact_type text not null,
    business_key_hash text not null,
    selected_observation_id text not null,
    candidate_observation_ids_json json not null,
    rule_id text,
    decision_reason text not null,
    selected_at datetime(6) not null,
    unique(fact_type,business_key_hash,selected_at),
    foreign key (selected_observation_id) references source_observations_v2(id),
    foreign key (rule_id) references source_priority_rules_v2(id)
);

create table if not exists market_venues_v2 (
    id text primary key,
    venue_code text not null unique,
    name text not null,
    country_code text not null,
    timezone text not null,
    currency text,
    status text not null default 'active',
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    check (status in ('active','inactive','retired'))
);

create table if not exists market_instruments_v2 (
    id text primary key,
    asset_class text not null,
    instrument_type text not null,
    venue_id text,
    primary_symbol text not null,
    name text,
    currency text,
    issuer_id text,
    listed_date date,
    delisted_date date,
    expiry_date date,
    status text not null,
    lot_size decimal(28,8),
    tick_size decimal(20,8),
    contract_multiplier decimal(28,8),
    metadata_json json not null,
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    unique(asset_class,venue_id,primary_symbol),
    foreign key (venue_id) references market_venues_v2(id),
    check (asset_class in ('equity','index','future','option')),
    check (status in ('pending','active','suspended','expired','delisted','retired')),
    check (delisted_date is null or listed_date is null or delisted_date >= listed_date),
    check (lot_size is null or lot_size > 0),
    check (tick_size is null or tick_size > 0),
    check (contract_multiplier is null or contract_multiplier > 0)
);

create index if not exists idx_market_instruments_v2_status
    on market_instruments_v2(asset_class,venue_id,status,listed_date,delisted_date);

create table if not exists market_instrument_identifiers_v2 (
    id text primary key,
    instrument_id text not null,
    provider_id text,
    identifier_type text not null,
    identifier_value text not null,
    valid_from date not null,
    valid_to date,
    is_primary integer not null default 0,
    created_at datetime(6) not null,
    unique(provider_id,identifier_type,identifier_value,valid_from),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    check (is_primary in (0,1)),
    check (valid_to is null or valid_to >= valid_from)
);

create index if not exists idx_market_identifiers_v2_instrument
    on market_instrument_identifiers_v2(instrument_id,identifier_type,valid_from,valid_to);

create table if not exists market_instrument_relations_v2 (
    id text primary key,
    parent_instrument_id text not null,
    child_instrument_id text not null,
    relation_type text not null,
    valid_from date not null,
    valid_to date,
    source_observation_id text,
    unique(parent_instrument_id,child_instrument_id,relation_type,valid_from),
    foreign key (parent_instrument_id) references market_instruments_v2(id),
    foreign key (child_instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (parent_instrument_id <> child_instrument_id),
    check (valid_to is null or valid_to >= valid_from)
);

create table if not exists market_trading_sessions_v2 (
    venue_id text not null,
    trade_date date not null,
    session_type text not null default 'regular',
    is_open integer not null,
    open_at datetime(6),
    close_at datetime(6),
    previous_trade_date date,
    next_trade_date date,
    source_observation_id text,
    primary key (venue_id,trade_date,session_type),
    foreign key (venue_id) references market_venues_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (is_open in (0,1)),
    check (close_at is null or open_at is null or close_at >= open_at)
);

create table if not exists market_daily_bars_v2 (
    id text primary key,
    instrument_id text not null,
    trade_date date not null,
    resolution text not null default 'daily',
    data_type text not null default 'trade',
    adjustment text not null default 'raw',
    provider_id text not null,
    open decimal(20,8),
    high decimal(20,8),
    low decimal(20,8),
    close decimal(20,8),
    previous_close decimal(20,8),
    settlement decimal(20,8),
    previous_settlement decimal(20,8),
    delivery_settlement decimal(20,8),
    change_value decimal(20,8),
    change_percent decimal(20,10),
    volume decimal(28,4),
    amount decimal(28,4),
    open_interest decimal(28,4),
    open_interest_change decimal(28,4),
    adjustment_factor decimal(28,12),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    recorded_at datetime(6) not null,
    unique(instrument_id,trade_date,resolution,data_type,adjustment,provider_id,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1)),
    check (high is null or low is null or high >= low),
    check (open is null or high is null or open <= high),
    check (open is null or low is null or open >= low),
    check (close is null or high is null or close <= high),
    check (close is null or low is null or close >= low),
    check (volume is null or volume >= 0),
    check (amount is null or amount >= 0),
    check (open_interest is null or open_interest >= 0)
);

create index if not exists idx_market_daily_bars_v2_instrument
    on market_daily_bars_v2(instrument_id,trade_date,is_current);
create index if not exists idx_market_daily_bars_v2_cross_section
    on market_daily_bars_v2(trade_date,data_type,adjustment,is_current,instrument_id);

create table if not exists market_daily_bar_selections_v2 (
    instrument_id text not null,
    trade_date date not null,
    resolution text not null,
    data_type text not null,
    adjustment text not null,
    bar_id text not null unique,
    decision_reason text not null,
    selected_at datetime(6) not null,
    primary key (instrument_id,trade_date,resolution,data_type,adjustment),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (bar_id) references market_daily_bars_v2(id)
);

create view if not exists current_market_daily_bars_v2 as
select b.* from market_daily_bars_v2 b
join market_daily_bar_selections_v2 s on s.bar_id=b.id
where b.is_current=1;

create table if not exists market_daily_metrics_v2 (
    id text primary key,
    instrument_id text not null,
    trade_date date not null,
    provider_id text not null,
    turnover_rate decimal(20,10),
    free_float_turnover_rate decimal(20,10),
    volume_ratio decimal(20,10),
    pe decimal(20,10),
    pe_ttm decimal(20,10),
    pb decimal(20,10),
    ps decimal(20,10),
    ps_ttm decimal(20,10),
    dividend_yield decimal(20,10),
    dividend_yield_ttm decimal(20,10),
    total_shares decimal(28,4),
    float_shares decimal(28,4),
    free_float_shares decimal(28,4),
    total_market_value decimal(28,4),
    circulating_market_value decimal(28,4),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,trade_date,provider_id,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists market_trading_status_v2 (
    id text primary key,
    instrument_id text not null,
    trade_date date not null,
    provider_id text not null,
    is_tradeable integer not null,
    is_suspended integer not null,
    can_buy integer not null,
    can_sell integer not null,
    is_st integer not null,
    upper_limit decimal(20,8),
    lower_limit decimal(20,8),
    minimum_margin_rate decimal(20,10),
    reason text,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,trade_date,provider_id,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (is_tradeable in (0,1) and is_suspended in (0,1)),
    check (can_buy in (0,1) and can_sell in (0,1) and is_st in (0,1)),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists equity_issuers_v2 (
    id text primary key,
    legal_name text not null,
    unified_credit_code text,
    country_code text not null default 'CN',
    province text,
    city text,
    registered_capital decimal(28,4),
    established_date date,
    metadata_json json not null,
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    unique(unified_credit_code)
);

create table if not exists equity_listings_v2 (
    instrument_id text primary key,
    issuer_id text not null,
    board text,
    list_status text not null,
    list_date date not null,
    delist_date date,
    issue_price decimal(20,8),
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (issuer_id) references equity_issuers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (delist_date is null or delist_date >= list_date)
);

create table if not exists equity_share_capital_v2 (
    id text primary key,
    instrument_id text not null,
    effective_date date not null,
    total_shares decimal(28,4),
    float_shares decimal(28,4),
    free_float_shares decimal(28,4),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,effective_date,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists financial_reports_v2 (
    id text primary key,
    instrument_id text not null,
    report_type text not null,
    fiscal_period_end date not null,
    announcement_date date not null,
    effective_at datetime(6) not null,
    currency text,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,report_type,fiscal_period_end,announcement_date,provider_id,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create index if not exists idx_financial_reports_v2_pit
    on financial_reports_v2(instrument_id,effective_at,report_type,fiscal_period_end);

create table if not exists financial_facts_v2 (
    report_id text not null,
    field_name text not null,
    value_decimal decimal(38,8),
    value_text text,
    unit text,
    scale integer not null default 0,
    primary key (report_id,field_name),
    foreign key (report_id) references financial_reports_v2(id),
    check (value_decimal is not null or value_text is not null)
);

create table if not exists index_definitions_v2 (
    instrument_id text primary key,
    publisher text,
    category text,
    index_style text,
    base_date date,
    base_point decimal(20,8),
    weighting_rule text,
    description text,
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id)
);

create table if not exists index_memberships_v2 (
    id text primary key,
    index_instrument_id text not null,
    member_instrument_id text not null,
    announced_at datetime(6),
    effective_from date not null,
    effective_to date,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(index_instrument_id,member_instrument_id,effective_from,provider_id,revision_no),
    foreign key (index_instrument_id) references market_instruments_v2(id),
    foreign key (member_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (effective_to is null or effective_to >= effective_from),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create index if not exists idx_index_memberships_v2_pit
    on index_memberships_v2(index_instrument_id,effective_from,effective_to,member_instrument_id);

create table if not exists index_weights_v2 (
    id text primary key,
    index_instrument_id text not null,
    member_instrument_id text not null,
    weight_date date not null,
    weight decimal(20,10) not null,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(index_instrument_id,member_instrument_id,weight_date,provider_id,revision_no),
    foreign key (index_instrument_id) references market_instruments_v2(id),
    foreign key (member_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (weight >= 0),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create index if not exists idx_index_weights_v2_date
    on index_weights_v2(index_instrument_id,weight_date,is_current,member_instrument_id);

create table if not exists futures_contract_terms_v2 (
    instrument_id text primary key,
    product_code text not null,
    delivery_month text,
    trade_unit text,
    per_unit decimal(28,8),
    quote_unit text,
    delivery_method text,
    last_trade_date date,
    last_delivery_date date,
    trading_hours text,
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (per_unit is null or per_unit > 0)
);

create table if not exists futures_settlement_params_v2 (
    id text primary key,
    instrument_id text not null,
    trade_date date not null,
    settlement decimal(20,8),
    trading_fee_rate decimal(20,10),
    trading_fee_per_contract decimal(20,8),
    delivery_fee decimal(20,8),
    minimum_margin_rate decimal(20,10),
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(instrument_id,trade_date,revision_no),
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists futures_continuous_mappings_v2 (
    id text primary key,
    continuous_instrument_id text not null,
    mapped_instrument_id text not null,
    trade_date date not null,
    provider_id text not null,
    source_observation_id text not null,
    revision_no integer not null,
    is_current integer not null default 1,
    unique(continuous_instrument_id,trade_date,provider_id,revision_no),
    foreign key (continuous_instrument_id) references market_instruments_v2(id),
    foreign key (mapped_instrument_id) references market_instruments_v2(id),
    foreign key (provider_id) references data_providers_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (continuous_instrument_id <> mapped_instrument_id),
    check (revision_no > 0),
    check (is_current in (0,1))
);

create table if not exists option_contract_terms_v2 (
    instrument_id text primary key,
    underlying_instrument_id text not null,
    option_type text not null,
    call_put text not null,
    exercise_style text,
    exercise_price decimal(20,8) not null,
    settlement_month text,
    maturity_date date not null,
    last_exercise_date date,
    last_delivery_date date,
    list_price decimal(20,8),
    quote_unit text,
    contract_unit decimal(28,8),
    minimum_price_change decimal(20,8),
    source_observation_id text,
    foreign key (instrument_id) references market_instruments_v2(id),
    foreign key (underlying_instrument_id) references market_instruments_v2(id),
    foreign key (source_observation_id) references source_observations_v2(id),
    check (call_put in ('call','put','C','P')),
    check (exercise_price >= 0),
    check (contract_unit is null or contract_unit > 0),
    check (minimum_price_change is null or minimum_price_change > 0)
);

create index if not exists idx_option_contract_terms_v2_chain
    on option_contract_terms_v2(underlying_instrument_id,maturity_date,call_put,exercise_price);

create table if not exists columnar_datasets_v2 (
    id text primary key,
    provider_dataset_id text not null,
    asset_class text not null,
    resolution text not null,
    storage_engine text not null,
    table_or_root text not null,
    schema_version text not null,
    status text not null,
    created_at datetime(6) not null,
    updated_at datetime(6) not null,
    unique(provider_dataset_id,resolution,storage_engine,schema_version),
    foreign key (provider_dataset_id) references provider_datasets_v2(id),
    check (storage_engine in ('clickhouse','parquet')),
    check (status in ('building','ready','failed','retired'))
);

create table if not exists columnar_partitions_v2 (
    id text primary key,
    dataset_id text not null,
    partition_key text not null,
    first_timestamp datetime(6),
    last_timestamp datetime(6),
    row_count bigint not null,
    byte_size bigint not null,
    content_sha256 text not null,
    storage_location text not null,
    status text not null,
    created_at datetime(6) not null,
    unique(dataset_id,partition_key,content_sha256),
    foreign key (dataset_id) references columnar_datasets_v2(id),
    check (row_count >= 0 and byte_size >= 0),
    check (last_timestamp is null or first_timestamp is null or last_timestamp >= first_timestamp),
    check (status in ('pending','ready','quarantined','retired'))
);

create index if not exists idx_columnar_partitions_v2_range
    on columnar_partitions_v2(dataset_id,first_timestamp,last_timestamp,status);
