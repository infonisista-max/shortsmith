"""Quality gates (PRD `qa.technical`, `qa.critic`).

`technical` runs the T checks in order and writes `out/qa.json` (10.1); `gate` is the
interface the pipeline's `qa` step calls, with the real gate and a fake (12.1). The
vision critic (10.2) arrives with ticket 033.
"""
