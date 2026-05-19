"""v5-A2 stage classes.

All implement the v4 PipelineStage ABC (re-exported from `stages.`) so the
PipelineRunner v5 DAG executor can reuse the existing _run_stage()
fail-fast + progress + persist machinery.
"""
