"""Replay with a given news policy (experiment only): python replay_policy.py POLICY <replay_run.py args>"""
import runpy, sys
sys.path.insert(0, "src")
import norway_company_agent.site_facts as sf
sf.NEWS_POLICY = sys.argv[1]
sys.argv = ["scripts/replay_run.py"] + sys.argv[2:]
runpy.run_path("scripts/replay_run.py", run_name="__main__")
