"""Event-stream triage profile - Tviheimr readiness slice HG-T3.

Roadmap: a triage profile for connector event streams: input schema
(source, kind, time, payload digest), verdict schema (urgency, route,
escalate yes/no, basis). Deterministic-first: identical events give
identical verdicts unless a model judgment is explicitly in the loop,
in which case the basis says so.

Design rules, enforced in code:
- Every event in a stream gets exactly one verdict, in order. Nothing
  is dropped silently: invalid events and duplicate events receive a
  shed verdict (route='shed'), logged like any other verdict.
- Rules are an ordered, named table; first match wins and the winning
  rule id is recorded in basis, so every verdict carries its basis.
- No model is used by default. If a caller explicitly passes a model
  callable, it is consulted only for the default-review case and the
  basis records 'model:<name>' - never silently.
Stdlib only. Plain library code - no service form assumed.
"""
from __future__ import annotations
import hashlib, json
from collections.abc import Mapping
from datetime import datetime
__all__=['TriageProfile','payload_digest','triage_stream','EVENT_FIELDS','VERDICT_FIELDS']
EVENT_FIELDS=('source','kind','time')
VERDICT_FIELDS=('urgency','route','escalate','basis')
_CRITICAL={'fire','smoke','breach','intrusion','explosion','flood','critical'}
_HIGH={'failure','failed','error','outage','down','attack','leak'}
_MEDIUM={'warning','warn','degraded','slow','retry','threshold'}
_LOW={'heartbeat','ok','info','ping','metric','telemetry','routine'}

def payload_digest(payload):
    raw=json.dumps(payload,sort_keys=True,default=str,ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def _tokens(event):
    parts=[str(event.get('source','')),str(event.get('kind',''))]
    p=event.get('payload')
    if isinstance(p,Mapping):
        parts += [str(k) for k in p.keys()]
        parts += [str(v) for v in p.values() if isinstance(v,(str,int,float,bool))]
    text=' '.join(parts).lower()
    return set(''.join(c if c.isalnum() else ' ' for c in text).split())

def _valid_time(v):
    if isinstance(v,(int,float)): return True
    if isinstance(v,str):
        try: datetime.fromisoformat(v.replace('Z','+00:00')); return True
        except ValueError: return False
    return False

class TriageProfile:
    name='event-stream-triage'
    def __init__(self, model=None, model_name=None):
        self.model=model; self.model_name=model_name or getattr(model,'name','model')
    def validate(self,event):
        if not isinstance(event,Mapping): return ['event is not an object']
        errs=[]
        for f in EVENT_FIELDS:
            if f not in event or event[f] in (None,''): errs.append(f'missing {f}')
        if 'time' in event and event.get('time') not in (None,'') and not _valid_time(event['time']): errs.append('unparseable time')
        if 'payload' not in event and not event.get('payload_digest'): errs.append('missing payload/payload_digest')
        return errs
    def digest_of(self,event):
        if isinstance(event,Mapping) and event.get('payload_digest'): return str(event['payload_digest'])
        if isinstance(event,Mapping) and 'payload' in event: return payload_digest(event['payload'])
        return payload_digest(None)
    def triage_one(self,event, index=None, seen=None):
        digest=self.digest_of(event) if isinstance(event,Mapping) else payload_digest(None)
        base={'index':index,'source':event.get('source') if isinstance(event,Mapping) else None,'kind':event.get('kind') if isinstance(event,Mapping) else None,'time':event.get('time') if isinstance(event,Mapping) else None,'payload_digest':digest,'deterministic':self.model is None,'model_used':False,'slice':'HG-T3'}
        errs=self.validate(event)
        if errs:
            return {**base,'urgency':'none','route':'shed','escalate':False,'basis':'schema:shed invalid event - '+'; '.join(errs)}
        if seen is not None and digest in seen:
            return {**base,'urgency':'none','route':'shed','escalate':False,'basis':f'duplicate:shed payload_digest already seen at index {seen[digest]}'}
        if seen is not None: seen[digest]=index
        toks=_tokens(event); sev=str((event.get('payload') or {}).get('severity','')).lower() if isinstance(event.get('payload'),Mapping) else ''
        def hit(words):
            for w in sorted(words):
                if w in toks or w==sev: return w
            return None
        w=hit(_CRITICAL)
        if w: return {**base,'urgency':'critical','route':'escalate','escalate':True,'basis':f'rules:critical-signal:{w}'}
        w=hit(_HIGH)
        if w: return {**base,'urgency':'high','route':'escalate','escalate':True,'basis':f'rules:high-signal:{w}'}
        w=hit(_MEDIUM)
        if w: return {**base,'urgency':'medium','route':'notify','escalate':False,'basis':f'rules:medium-signal:{w}'}
        w=hit(_LOW)
        if w: return {**base,'urgency':'low','route':'archive','escalate':False,'basis':f'rules:low-signal:{w}'}
        if self.model is not None:
            try:
                mv=str(self.model(event)).lower()
                if mv in ('critical','high'): return {**base,'urgency':mv,'route':'escalate','escalate':True,'basis':f'model:{self.model_name} default-review override','deterministic':False,'model_used':True}
                return {**base,'urgency':'medium','route':'review','escalate':False,'basis':f'model:{self.model_name} default-review','deterministic':False,'model_used':True}
            except Exception as e:
                return {**base,'urgency':'medium','route':'review','escalate':False,'basis':f'rules:no-signal default-review; model-error:{type(e).__name__}','model_used':False}
        return {**base,'urgency':'medium','route':'review','escalate':False,'basis':'rules:no-signal default-review'}
    def triage_stream(self,events):
        seen={}; out=[]
        for i,ev in enumerate(events): out.append(self.triage_one(ev,index=i,seen=seen))
        return out

def triage_stream(events, profile=None):
    return (profile or TriageProfile()).triage_stream(list(events))
