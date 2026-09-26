# Setup × Intraday P×V × Forward Outcome

Isolated **read-only research** slice. Not a production module.

## Isolation

This directory does not:

- change Candidate Router, Elite, Rotation Watch, scanner `GROUP_RANK`, or frozen P×V
- write Camera / earning-learning / live-candidate artifacts
- start live-shadow, Telegram, Streamlit, or VPS services
- touch `/opt/mrbot-camera` or `/opt/mrbot-rotation-watch`

It **reads** existing CSV snapshots in the repo and writes only under
`research/setup_intraday_pxv_forward/`.

## Run

```bash
python3 research/setup_intraday_pxv_forward/run_study.py
```

Outputs:

- `REPORT.md` — inventory, chronology, tables, findings
- `artifacts/*.csv` — machine-readable tables
