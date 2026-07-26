-- description: Retire unlinked legacy Paper sessions and their owned records
-- compatibility: preserves only shadow sessions owned by paper_accounts
-- rollback: irreversible data cleanup requiring a verified pre-migration backup to restore legacy evidence

update decision_signals
set paper_session_id=null,
    paper_signal_id=null,
    status=case when status='handed_off' then 'active' else status end
where paper_session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_daily_job_events
where job_id in (
    select id from paper_daily_jobs
    where session_id in (
        select id from paper_sessions
        where id not in (select shadow_session_id from paper_accounts)
    )
);

delete from paper_daily_jobs
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_run_checkpoints
where paper_run_id in (
    select id from paper_walkforward_runs
    where session_id in (
        select id from paper_sessions
        where id not in (select shadow_session_id from paper_accounts)
    )
);

delete from paper_constraint_decisions
where intent_id in (
    select id from paper_order_intents
    where session_id in (
        select id from paper_sessions
        where id not in (select shadow_session_id from paper_accounts)
    )
);

delete from paper_order_fills
where intent_id in (
    select id from paper_order_intents
    where session_id in (
        select id from paper_sessions
        where id not in (select shadow_session_id from paper_accounts)
    )
);

delete from paper_order_transitions
where intent_id in (
    select id from paper_order_intents
    where session_id in (
        select id from paper_sessions
        where id not in (select shadow_session_id from paper_accounts)
    )
);

delete from paper_ledger_entries
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_reconciliation_records
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_order_intents
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_lean_order_events
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_walkforward_runs
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_daily_reports
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_portfolio_snapshots
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_positions
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_orders
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_signals
where session_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from tasks
where related_id in (
    select id from paper_sessions
    where id not in (select shadow_session_id from paper_accounts)
);

delete from paper_sessions
where id not in (select shadow_session_id from paper_accounts);
