# Docker deployment

Docker Compose remains a supported first-class deployment. Use:

```bash
python scripts/platformctl.py --mode docker --profile full start
```

The `core`, `ml`, `observability`, `full`, and `dev` profiles select
logical service sets without changing application or task semantics.
