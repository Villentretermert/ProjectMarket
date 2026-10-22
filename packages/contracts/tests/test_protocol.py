"""Contract failure/recovery scenarios; they do not certify an HTTP implementation."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from jsonschema import ValidationError, Draft202012Validator
from openapi_spec_validator import validate as validate_openapi
from contracts.build_contract import SCHEMAS, artifacts
from contracts.reference_model import ProtocolModel, Rejected, validate

ROOT = Path(__file__).resolve().parents[1] / "src" / "contracts"
MESSAGE = {'schema_version':'1.0','message_id':'m_1','channel_id':'ch_shop','resource_id':'item_notebook','source_revision':1,'occurred_at':'2026-10-21T09:42:00Z','kind':'data','content_type':'product','payload':{'title':'Daily notebook','description':'A5 dotted pages','price':{'amount_minor':1800,'currency':'EUR'},'availability':'in_stock'}}
ACTION = {'action_id':'buy_notebook','resource_id':'item_notebook','observed_source_revision':1,'quantity':1}
RESULT = {'result_id':'r_1','result_revision':1,'state':'confirmed','summary':'Request accepted; no payment has been taken.'}


def model():
    value = ProtocolModel()
    value.ingest(MESSAGE)
    return value


def test_generated_artifacts_are_current_and_valid():
    for name, expected in artifacts().items():
        assert json.loads((ROOT/name).read_text(encoding='utf-8')) == expected
    validate_openapi(artifacts()['openapi.json'])
    for schema in SCHEMAS.values():
        Draft202012Validator.check_schema(schema)


def test_fields_have_descriptions():
    for name, schema in SCHEMAS.items():
        for field, definition in schema.get('properties',{}).items():
            assert 'description' in definition or '$ref' in definition, (name,field)


def test_message_replay_is_durable_receipt_not_new_revision():
    m=model()
    assert m.ingest(deepcopy(MESSAGE)) == 1
    assert m.data_revision == 1


def test_changed_body_same_message_id_conflicts():
    m=model(); body=deepcopy(MESSAGE); body['payload']['title']='Changed'
    with pytest.raises(Rejected, match='idempotency_conflict'):m.ingest(body)


def test_out_of_order_and_tombstone_replay():
    m=model(); delete={k:v for k,v in MESSAGE.items() if k not in ('payload','content_type')}
    delete.update(kind='delete',source_revision=3,message_id='delete_3')
    m.ingest(delete)
    old=deepcopy(MESSAGE); old.update(message_id='late_2',source_revision=2)
    with pytest.raises(Rejected,match='stale_source_revision'):m.ingest(old)
    assert m.deleted


def test_unknown_schema_rejected():
    body=deepcopy(MESSAGE); body['schema_version']='2.0'
    with pytest.raises(ValidationError):validate('Message',body)


def test_stale_and_unavailable_action():
    m=model(); changed=dict(ACTION,observed_source_revision=2)
    with pytest.raises(Rejected,match='resource_changed'):m.request('bob','req_a',changed)
    m.availability='out_of_stock'
    with pytest.raises(Rejected,match='resource_unavailable'):m.request('bob','req_a',ACTION)
    assert not m.events


def test_action_retry_does_not_repeat_side_effect():
    m=model(); a=m.request('bob','req_a',ACTION)
    assert m.request('bob','req_a',deepcopy(ACTION)) == a
    assert len(m.events)==1
    with pytest.raises(Rejected,match='idempotency_conflict'):m.request('bob','req_a',dict(ACTION,quantity=2))


def test_pagination_and_new_scan_do_not_lose_unacked_or_new_events():
    m=model()
    for i in range(3):m.request('bob',f'req_{i}',ACTION)
    page,cursor=m.scan(limit=2); assert page==[1,2]
    m.request('bob','req_new',ACTION)
    page,cursor=m.scan(cursor,limit=2); assert page==[3] and cursor is None
    page,_=m.scan(); assert page==[1,2,3,4]  # GET has not acknowledged anything.


def test_ack_does_not_mean_success_and_unresolved_survives_consumer_restart():
    m=model(); e=m.request('bob','req_a',ACTION); m.ack(e); m.ack(e)
    assert m.scan()==([],None)
    assert m.client_status('bob',e)=='queued'
    assert m.unresolved()==[e]


def test_result_requires_ack_and_terminal_is_immutable():
    m=model(); e=m.request('bob','req_a',ACTION)
    with pytest.raises(Rejected,match='ack_required'):m.result(e,RESULT)
    m.ack(e); assert m.result(e,RESULT)=='confirmed'
    assert m.result(e,deepcopy(RESULT))=='confirmed'
    with pytest.raises(Rejected,match='terminal_conflict'):m.result(e,dict(RESULT,result_id='r_2',result_revision=2,state='failed'))
    assert m.unresolved()==[]


def test_results_are_ordered_and_changed_replay_conflicts():
    m=model(); e=m.request('bob','req_a',ACTION);m.ack(e)
    m.result(e,dict(RESULT,state='processing'))
    with pytest.raises(Rejected,match='idempotency_conflict'):m.result(e,RESULT)
    with pytest.raises(Rejected,match='stale_result_revision'):m.result(e,dict(RESULT,result_id='r_2'))
    assert m.result(e,dict(RESULT,result_id='r_2',result_revision=2))=='confirmed'


def test_revocation_prevents_replay_read_and_undelivered_action():
    m=model();e=m.request('bob','req_a',ACTION);m.revoke('bob')
    assert m.scan()==([],None)
    with pytest.raises(Rejected,match='source_unavailable'):m.request('bob','req_a',ACTION)
    with pytest.raises(Rejected,match='source_unavailable'):m.client_status('bob',e)
    with pytest.raises(Rejected,match='request_cancelled'):m.ack(e)


def test_revocation_after_ack_requires_reconciliation_not_fake_failure():
    m=model();e=m.request('bob','req_a',ACTION);m.ack(e);m.revoke('bob')
    assert m.requests[e]['state']=='unknown' and m.unresolved()==[e]
    assert m.result(e,RESULT)=='confirmed'  # Record actual outcome, do not re-execute.
    with pytest.raises(Rejected):m.client_status('bob',e)


def test_revoked_bot_key_blocks_even_duplicate_reads_and_writes():
    m=model();m.key_active=False
    with pytest.raises(Rejected,match='invalid_credentials'):m.ingest(MESSAGE)
    with pytest.raises(Rejected,match='invalid_credentials'):m.scan()


def test_wrong_bot_channel_rejected():
    with pytest.raises(Rejected,match='source_forbidden'):model().ingest(dict(MESSAGE,channel_id='ch_foreign'))


def test_unconfigured_currency_rejected():
    body=deepcopy(MESSAGE);body['payload']['price']['currency']='ZZZ'
    with pytest.raises(Rejected,match='unsupported_currency'):validate('Message',body)


@pytest.mark.parametrize('field,value',[('api_key','placeholder'),('grants',['bob']),('script','alert(1)'),('html','<h1>unsafe</h1>')])
def test_shared_layout_rejects_secret_rights_or_code_fields(field,value):
    layout={'schema_version':'1.0','template_version':1,'theme':'blue','density':'comfortable','blocks':[],field:value}
    with pytest.raises(ValidationError):validate('Layout',layout)


def test_incompatible_visualization_rejected():
    layout={'schema_version':'1.0','template_version':1,'theme':'blue','density':'comfortable','blocks':[{'block_id':'b1','source':{'channel_id':'ch_news','resource_id':'story1'},'content_type':'news','view':'bars','action_ids':[]}]}
    with pytest.raises(ValidationError):validate('Layout',layout)


def test_duplicate_blocks_and_invalid_chart_order_rejected():
    block={'block_id':'b1','source':{'channel_id':'ch_news','resource_id':'story1'},'content_type':'news','view':'article','action_ids':[]}
    with pytest.raises(Rejected,match='duplicate_block'):validate('Layout',{'schema_version':'1.0','template_version':1,'theme':'blue','density':'comfortable','blocks':[block,block]})
    chart=deepcopy(MESSAGE);chart.update(content_type='chart',payload={'title':'Views','x_label':'Day','x_kind':'number','y_label':'Views','unit':'views','series':[{'name':'Main','points':[{'x':2,'y':5},{'x':1,'y':6}]}]})
    with pytest.raises(Rejected,match='invalid_chart_order'):validate('Message',chart)


def test_wire_size_unicode_and_nonfinite_numbers():
    body=deepcopy(MESSAGE);body['payload']['description']='x'*262145
    with pytest.raises(Rejected,match='payload_too_large'):validate('Message',body)
    body['payload']['price']['amount_minor']=float('nan')
    with pytest.raises(ValueError):validate('Message',body)


def test_examples_match_expected_schema_outcome():
    for item in json.loads((ROOT/'examples/cases.json').read_text(encoding='utf-8')):
        if item['valid']:
            validate(item['schema'],item['value'])
        else:
            with pytest.raises((ValidationError,Rejected,ValueError)):
                validate(item['schema'],item['value'])
