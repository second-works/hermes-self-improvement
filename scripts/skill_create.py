#!/usr/bin/env python3
"""Trusted controller only; generated Python is never imported on the host."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from delegation.skill_creation import Controller
from evaluation.core import EvaluationError,load_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['prepare','freeze','public','accept','read','use','respond','evaluate','audit'])
    p.add_argument('--run'); p.add_argument('--candidate-sha'); p.add_argument('--trial',type=int)
    p.add_argument('--case'); p.add_argument('--request'); p.add_argument('--response')
    a=p.parse_args(); c=Controller(Path(__file__).resolve().parents[1])
    try:
        if a.action=='prepare': result=c.prepare()
        elif a.action=='freeze': result=c.freeze(a.run)
        elif a.action=='public': result=c.public(a.run,a.candidate_sha)
        elif a.action=='accept': result=c.accept(a.run,a.candidate_sha)
        elif a.action=='read': result=c.handoff(a.run,a.trial)
        elif a.action=='use': result=c.use(a.run,a.trial,a.case,load_json(a.request))
        elif a.action=='respond': result=c.respond(a.run,a.trial,a.case,a.response)
        elif a.action=='evaluate': result=c.evaluate(a.run)
        else: result=c.audit(a.run)
        print(json.dumps(result,ensure_ascii=False)); return 0
    except (EvaluationError,OSError,ValueError,TypeError,KeyError) as error:
        print(json.dumps({'status':'STOPPED','reason':str(error) if isinstance(error,EvaluationError) else type(error).__name__})); return 2


if __name__=='__main__': sys.exit(main())
