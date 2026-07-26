-- description: Enforce immutable Paper account ledger sequence identity
-- compatibility: additive unique index; existing duplicate sequences must be reconciled before migration
-- rollback: drop index uq_paper_account_ledger_sequence

create unique index if not exists uq_paper_account_ledger_sequence
    on paper_ledger_entries(paper_account_id, account_generation, ledger_sequence);
