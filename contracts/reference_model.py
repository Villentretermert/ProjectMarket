"""Small executable protocol model for PM-004 failure cases, not production storage.

It deliberately has no HTTP, real credentials, concurrency or persistence. Backend
tests must replay these scenarios against PostgreSQL before making runtime claims.
"""
from copy import deepcopy
import json
from .build_contract import SCHEMAS
from jsonschema import Draft202012Validator, FormatChecker


class Rejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate(name, value):
    wire = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(wire) > 262144:
        raise Rejected('payload_too_large')
    schema = {'$defs': SCHEMAS, '$ref': f'#/$defs/{name}'}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    if name == 'Message' and value.get('content_type') == 'product':
        if value['payload']['price']['currency'] not in {'EUR','USD','RUB'}:
            raise Rejected('unsupported_currency')
    if name == 'Message' and value.get('content_type') == 'chart':
        series = value['payload']['series']
        if len({s['name'] for s in series}) != len(series):
            raise Rejected('duplicate_series')
        for item in series:
            xs = [p['x'] for p in item['points']]
            if xs != sorted(set(xs)):
                raise Rejected('invalid_chart_order')
    if name == 'Layout':
        ids = [b['block_id'] for b in value['blocks']]
        if len(ids) != len(set(ids)):
            raise Rejected('duplicate_block')


def fingerprint(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class ProtocolModel:
    """Single-bot/single-resource model. Identities and time are test inputs only."""
    def __init__(self):
        self.source_revision = 0
        self.data_revision = 0
        self.messages = {}
        self.requests = {}
        self.idempotency = {}
        self.events = []
        self.allowed = {'bob'}
        self.key_active = True
        self.deleted = False
        self.availability = 'in_stock'

    def authenticate(self):
        if not self.key_active:
            raise Rejected('invalid_credentials')

    def ingest(self, body):
        self.authenticate()
        validate('Message', body)
        if body['channel_id'] != 'ch_shop':
            raise Rejected('source_forbidden')
        mid, digest = body['message_id'], fingerprint(body)
        if mid in self.messages:
            old, receipt = self.messages[mid]
            if old != digest:
                raise Rejected('idempotency_conflict')
            return receipt
        if body['kind'] != 'event':
            if body['source_revision'] <= self.source_revision:
                raise Rejected('stale_source_revision')
            self.source_revision = body['source_revision']
            self.deleted = body['kind'] == 'delete'
            self.availability = body.get('payload', {}).get('availability', 'in_stock')
        elif self.deleted or not self.source_revision:
            raise Rejected('source_unavailable')
        self.data_revision += 1
        receipt = self.data_revision
        self.messages[mid] = (digest, receipt)
        return receipt

    def check_access(self, actor):
        if actor not in self.allowed:
            raise Rejected('source_unavailable')

    def request(self, actor, idem, body):
        self.check_access(actor)  # Replay never bypasses a later rights revocation.
        validate('ActionInput', body)
        key = (actor, idem)
        digest = fingerprint(body)
        if key in self.idempotency:
            old, event_id = self.idempotency[key]
            if old != digest:
                raise Rejected('idempotency_conflict')
            return event_id
        if self.deleted or self.availability != 'in_stock':
            raise Rejected('resource_unavailable')
        if body['resource_id'] != 'item_notebook' or body['action_id'] != 'buy_notebook':
            raise Rejected('action_not_allowed')
        if body['observed_source_revision'] != self.source_revision:
            raise Rejected('resource_changed')
        event_id = len(self.events) + 1
        self.events.append(event_id)
        self.requests[event_id] = {'actor': actor, 'acked': False, 'state': 'queued', 'results': {}, 'revision': 0}
        self.idempotency[key] = (digest, event_id)
        return event_id

    def scan(self, cursor=None, limit=100):
        self.authenticate()
        # A scan fixes its upper bound. New events arrive in the next fresh scan.
        after, upper = cursor if cursor is not None else (0, len(self.events))
        pending = [i for i in self.events if after < i <= upper and not self.requests[i]['acked'] and self.requests[i]['state'] != 'cancelled']
        page = pending[:limit]
        next_cursor = (page[-1], upper) if len(pending) > limit else None
        return page, next_cursor

    def ack(self, event_id):
        self.authenticate()
        req = self.requests[event_id]
        if req['state'] == 'cancelled':
            raise Rejected('request_cancelled')
        req['acked'] = True

    def unresolved(self):
        self.authenticate()
        return [i for i, r in self.requests.items() if r['state'] in ('queued', 'processing', 'unknown')]

    def result(self, event_id, body):
        self.authenticate()
        validate('Result', body)
        req = self.requests[event_id]
        digest = fingerprint(body)
        old = req['results'].get(body['result_id'])
        if old:
            if old != digest:
                raise Rejected('idempotency_conflict')
            return req['state']
        if not req['acked']:
            raise Rejected('ack_required')
        if req['state'] in ('confirmed', 'failed', 'cancelled'):
            raise Rejected('terminal_conflict')
        if body['result_revision'] <= req['revision']:
            raise Rejected('stale_result_revision')
        req.update(state=body['state'], revision=body['result_revision'])
        req['results'][body['result_id']] = digest
        return req['state']

    def revoke(self, actor):
        self.allowed.discard(actor)
        for req in self.requests.values():
            if req['actor'] == actor and req['state'] in ('queued','processing','unknown'):
                req['state'] = 'unknown' if req['acked'] else 'cancelled'

    def client_status(self, actor, event_id):
        self.check_access(actor)
        req = self.requests[event_id]
        if req['actor'] != actor:
            raise Rejected('request_not_found')
        return deepcopy(req)['state']
