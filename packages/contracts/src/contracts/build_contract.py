"""Authoritative PM-004 contract builder. Generates schemas, not an API server."""
from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMAS = {}


def text(description, maximum=200, minimum=1, **extra):
    return dict(type="string", minLength=minimum, maxLength=maximum, description=description, **extra)


def number(description, minimum=0, maximum=2**53-1):
    return dict(type="integer", minimum=minimum, maximum=maximum, description=description)


def enum(description, *values):
    return dict(type="string", enum=list(values), description=description)


def ref(name, description=None):
    return {"$ref": f"#/$defs/{name}", **({"description": description} if description else {})}


def array(items, description, maximum=100, minimum=0, unique=False):
    return dict(type="array", items=items, minItems=minimum, maxItems=maximum,
                uniqueItems=unique, description=description)


def obj(description, fields, optional=()):
    return dict(type="object", description=description, properties=fields,
                required=[x for x in fields if x not in optional], additionalProperties=False)


def define(name, fields, description, optional=()):
    SCHEMAS[name] = obj(description, fields, optional)


ID = text("Opaque stable identifier; never a credential.", 80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
TIME = text("RFC3339 timestamp with timezone; server returns UTC.", 40, format="date-time")
VERSION = dict(type="string", const="1.0", description="Wire schema version; unsupported values are rejected.")
CURSOR = text("Opaque, caller-bound scan cursor. Never an acknowledgement.", 1024)
REVISION = number("Monotonic revision; compare within the referenced resource.", 1)
EMPTY = obj("No input fields.", {})
SCOPES = array(enum("Operational bot permission.", "messages:write", "events:read", "events:ack", "events:result"), "Explicit permissions for this bot only.", 4, 1, True)

define("Error", {"code": text("Stable machine error code.", 80), "message": text("Safe English explanation; no payload or credentials.", 500), "request_id": ID, "retryable": {"type":"boolean", "description":"Retry only following the documented error policy."}}, "All non-success JSON responses.")
define("User", {"user_id": ID, "username": text("Unique local username.",40,3,pattern="^[a-z0-9_-]+$"), "display_name":text("User-selected public display name.",80)}, "Local identity. Ownership is checked server-side, never trusted from a client role.")
define("Credentials", {"username": ref("UserUsername"), "password":text("Local password; write-only, never logged.",128,12,writeOnly=True)}, "Local login or registration credentials.")
SCHEMAS["UserUsername"] = deepcopy(SCHEMAS["User"]["properties"]["username"])
define("RegisterUser", {**SCHEMAS["Credentials"]["properties"], "display_name": text("Public display name.",80)}, "Create a local B2C account; the same user may own B2B bots.")
define("Session", {"user":ref("User"), "csrf_token":text("Session-bound anti-CSRF token for unsafe cookie-authenticated operations; not a bot key.",256), "expires_at":TIME}, "Session cookie is set in response headers; never store its value in a layout.")
define("BusinessProfileWrite", {"name":text("Name of this user's personal B2B workspace.",80)}, "Enable or rename your own B2B workspace; no client roles or tenant IDs.")
define("BusinessProfile", {"org_id":ID, "name":text("Workspace name.",80), "role":enum("Server-derived membership; team invitations are outside this pilot.","owner")}, "Personal owner organization; one per registered user.")
define("ConfirmPassword", {"password":deepcopy(SCHEMAS["Credentials"]["properties"]["password"])}, "Re-authenticate before account deactivation.")
define("BotCreate", {"name":text("Human-readable bot name.",80)}, "Owner creates a bot before exchanging its individual registration credential.")
define("Bot", {"bot_id":ID, "name":text("Human-readable bot name.",80), "state":enum("Registration state.","pending","active","revoked")}, "Owned bot metadata without secrets.")
define("BotDetails", {**SCHEMAS["Bot"]["properties"], "last_seen":{"oneOf":[TIME,{"type":"null"}],"description":"Last successful authenticated bot operation, or null."}}, "Owner-only bot detail; no credentials.")
define("BotIdentity", {"bot_id":ID,"key_id":ID,"scopes":SCOPES,"expires_at":TIME}, "Operational key identity; no owner/session secrets.")
define("Registration", {"bot":ref("Bot"), "registration_credential":text("One-time random credential; raw value only in this response.",256,32), "expires_at":TIME}, "Registration credential expires in 15 minutes; response is no-store.")
define("KeyIssue", {"scopes":SCOPES, "replaces_key_id":ID}, "Issue a key; when replaces_key_id is present, revoke the old key atomically.", ("replaces_key_id",))
define("KeyMetadata", {"key_id":ID, "prefix":text("Non-secret identification prefix.",16), "scopes":SCOPES, "expires_at":TIME, "revoked": {"type":"boolean","description":"Whether this key can no longer authenticate."}}, "Key inventory never returns a full secret.")
define("KeySecret", {"bot_id":ID, "key":ref("KeyMetadata"), "api_key":text("Random per-bot operational secret, returned once; store outside source control.",256,32)}, "Issued key. All scopes remain bounded by bot ownership; 90-day expiry.")
define("News", {"title":text("Plain-text headline.",200), "body":text("Plain-text news body; HTML is not interpreted.",20000,0)}, "A single news item.")
define("Money", {"amount_minor":number("Non-negative amount in the currency's minor units.",0,10**12), "currency":text("Supported ISO 4217 currency code; server validates its minor-unit mapping.",3,3,pattern="^[A-Z]{3}$")}, "Display amount only; never a payment authorization.")
define("Product", {"title":text("Plain-text product title.",200), "description":text("Plain-text description.",20000,0), "price":ref("Money"), "availability":enum("Current resource availability; actions recheck this value.","in_stock","out_of_stock","unavailable")}, "Catalog item; media uploads/external image fetching are deferred in schema 1.0.")
define("Point", {"x":number("Ordered numeric x coordinate; epoch milliseconds when x_kind=time.",-2**53+1), "y":{"type":"number","minimum":-10**12,"maximum":10**12,"description":"Finite numeric measurement; JSON NaN/Infinity are invalid."}}, "A chart point.")
define("Series", {"name":text("Series label.",80), "points":array(ref("Point"),"Strictly increasing unique x values per series.",1000,1)}, "One numeric series.")
define("Chart", {"title":text("Chart title.",200), "x_label":text("Horizontal axis label.",80), "x_kind":enum("Meaning of x coordinates.","number","time"), "y_label":text("Vertical axis label.",80), "unit":text("Measurement unit, e.g. views or EUR.",40), "series":array(ref("Series"),"Series have unique names and share axis semantics.",5,1)}, "Typed numeric data with explicit units; no executable transformations.")

# Exact object variants prevent untyped fields, HTML bindings or secret-bearing templates.
message_base = {"schema_version":VERSION, "message_id":ID, "channel_id":ID}
record_base = {**message_base, "resource_id":ID, "source_revision":REVISION, "occurred_at":TIME}
define("TextMessage", {**record_base, "kind":{"const":"text","type":"string","description":"Plain-text update normalized to a News record."}, "payload":ref("News")}, "Upsert a news resource from plain text.")
for kind, payload in (("news","News"),("product","Product"),("chart","Chart")):
    define(kind.title()+"Message", {**record_base, "kind":{"const":"data","type":"string","description":"Typed JSON resource update."}, "content_type":{"const":kind,"type":"string","description":"Schema of payload."}, "payload":ref(payload)}, "Replace the entire resource payload, never merge an arbitrary patch.")
define("DeleteMessage", {**record_base, "kind":{"const":"delete","type":"string","description":"Create a tombstone with a higher source revision."}}, "Remove current content; preserve revision tombstone for replay protection.")
define("EventMessage", {**message_base, "kind":{"const":"event","type":"string","description":"Notification hint, not a snapshot or business result."}, "event_name":enum("Supported event vocabulary.","news.published","catalog.changed"), "occurred_at":TIME, "resource_id":ID}, "Emit a bounded event about an existing resource; permissions still apply. Results use the result route.")
SCHEMAS["Message"] = {"description":"Exactly one supported message variant.","oneOf":[ref(x) for x in ("TextMessage","NewsMessage","ProductMessage","ChartMessage","DeleteMessage","EventMessage")]}
define("Receipt", {"message_id":ID, "receipt_id":ID, "data_revision":REVISION, "received_at":TIME}, "Durable transaction receipt; identical replay returns this same receipt. Events advance channel data_revision too.")
define("Source", {"channel_id":ID,"resource_id":ID}, "Reference only; it does not convey read permission.")
for kind, views in (("news",("article","compact")),("product",("card","list")),("chart",("bars","line","table"))):
    define(kind.title()+"Block", {"block_id":ID, "source":ref("Source"), "content_type":{"type":"string","const":kind,"description":"Expected source payload type."}, "view":enum("Compatible rendering only.",*views), "action_ids":array(ID,"Server-registered actions; product only in v1.",5,0,True) if kind=="product" else array(ID,"No actions supported on this block type in v1.",0)}, "Declarative block reference; no embedded source data, grants, keys or code.")
SCHEMAS["Block"]={"description":"Allowlisted typed visual block.","oneOf":[ref(x) for x in ("NewsBlock","ProductBlock","ChartBlock")]}
define("Layout", {"schema_version":VERSION,"template_version":REVISION,"theme":enum("Allowlisted color theme.","blue","ink"),"density":enum("Spacing preset.","comfortable","compact"),"blocks":array(ref("Block"),"Ordered unique block IDs; no HTML/JS/CSS or arbitrary expressions.",50)}, "Pure interface structure. Empty layout is valid; keys/rights are prohibited.")
define("ActionDefinition", {"action_id":ID,"resource_id":ID,"kind":enum("Allowed request-only operation.","request_purchase","add_to_cart"),"label":text("English action label.",60)}, "Owner-approved action backed by the channel's bot. Only quantity input is supported in v1; no payment.")
define("ChannelCreate", {"bot_id":ID,"slug":text("Unique shareable channel slug.",80,3,pattern="^[a-z0-9-]+$"),"title":text("Public channel title.",80),"visibility":enum("Read access policy.","public","selected")}, "Create a draft owned channel bound to an owned bot. Visibility defaults to selected.", ("visibility",))
define("ChannelDraft", {"title":text("Channel title.",80),"visibility":enum("Published read access policy.","public","selected"),"layout":ref("Layout"),"actions":array(ref("ActionDefinition"),"Unique action IDs validated against product resources.",50),"expected_template_version":number("Zero for a first draft; optimistic write guard.")}, "Draft replacement; source channels must equal this owned channel in B2B layouts.")
define("Channel", {"channel_id":ID, **SCHEMAS["ChannelCreate"]["properties"], "published": {"type":"boolean","description":"Whether a validated version is readable."}, "layout":ref("Layout"),"actions":array(ref("ActionDefinition"),"Published or draft actions for the authorized caller.",50)}, "Channel definition. Owner reads draft through management route; consumers read only published versions.")
SCHEMAS["ChannelCreate"]["properties"]["visibility"]["default"] = "selected"
define("Rollback", {"target_template_version":REVISION,"expected_template_version":REVISION}, "Restore a previously published layout as a new published version; current data is unchanged.")
define("PageVersion", {"channel":ref("Channel"),"created_at":TIME,"published_at":{"oneOf":[TIME,{"type":"null"}],"description":"First publication time, or null for a draft never published."}}, "Immutable saved definition; published_at records its first publication, channel.published marks the current published version.")
define("Publish", {"expected_template_version":REVISION}, "Atomically publish the validated draft at this version.")
define("Grant", {"user_id":ID}, "Read grant for an existing user; never a role or ownership grant.")
define("Record", {"source":ref("Source"),"source_revision":REVISION,"data_revision":REVISION,"updated_at":TIME,"content": {"description":"Typed payload.","oneOf":[ref("News"),ref("Product"),ref("Chart")]}}, "Authorized current content. Deleted/inaccessible resources are omitted, not sent as secret metadata.")
define("Snapshot", {"channel":ref("Channel"),"data_revision":number("Current channel data revision; zero before the first message."),"records":array(ref("Record"),"Only data needed by the published blocks.",50)}, "Readable snapshot; explicit permission check on every request.")
define("ActionInput", {"action_id":ID,"resource_id":ID,"observed_source_revision":REVISION,"quantity":number("Requested item count; bot may still reject.",1,99)}, "Create a request only after current access, availability, action and revision are revalidated.")
define("ActionRequest", {"action_request_id":ID,"channel_id":ID,"resource_id":ID,"action_id":ID,"state":enum("Business state; unknown is an unresolved display state, never success.","queued","processing","confirmed","failed","unknown","cancelled"),"created_at":TIME,"updated_at":TIME,"summary":text("Safe bot/server explanation.",500,0)}, "Read own request while source access remains valid. ACK only means durable receipt.")
define("BotEvent", {"event_id":ID,"action_request_id":ID,"actor_ref":ID,"channel_id":ID,"resource_id":ID,"action_id":ID,"quantity":number("Validated requested count.",1,99),"observed_source_revision":REVISION,"created_at":TIME}, "Action delivery with bot-scoped pseudonymous actor reference; no name, email, password or user tokens.")
define("EventPage", {"items":array(ref("BotEvent"),"Unacknowledged events from a bounded scan.",100),"next_cursor":{"oneOf":[CURSOR,{"type":"null"}],"description":"Null ends this scan. Start again without cursor; never use the last cursor forever."}}, "Reading has no delivery side effect; no lease is created by GET.")
define("Result", {"result_id":ID,"result_revision":REVISION,"state":enum("Bot business progress/result. Terminal results are immutable.","processing","confirmed","failed"),"summary":text("Plain text safe for the requesting user; no private diagnostics.",500,0),"external_reference":text("Optional opaque reference for reconciliation, never a secret or payment instruction.",100)}, "Idempotent ordered result; bot must ACK after durable local receipt before sending it.",( "external_reference",))
define("Ack", {"event_id":ID,"acknowledged_at":TIME}, "Durable receipt only; does not confirm purchase or stop result reconciliation.")
define("PersonalPage", {"page_id":ID,"title":text("Owner-selected personal page title.",80),"layout":ref("Layout")}, "Owned personal layout with independent source permissions.")
define("PageWrite", {"title":text("Personal page title.",80),"layout":ref("Layout"),"expected_template_version":number("Zero on create; exact current version on update.")}, "Atomic replacement with optimistic concurrency.")
define("ShareCreate", {"expires_at":TIME}, "Optional future expiry; omission means no expiry until revoked.",( "expires_at",))
define("Share", {"share_id":ID,"code":text("Random 192-bit base64url locator; never grants source access.",32,32,pattern="^[A-Za-z0-9_-]{32}$"),"expires_at":{"oneOf":[TIME,{"type":"null"}],"description":"Expiry or no time limit."}}, "Immutable server-stored template locator; sharing is not encryption.")
define("ImportInput", {"code":deepcopy(SCHEMAS["Share"]["properties"]["code"])}, "Code from the same server origin; cross-server migration is outside v1.")
define("ImportPreview", {"layout":ref("Layout"),"unavailable_blocks":array(ID,"Block IDs whose source cannot currently be read. No private names or timestamps.",50)}, "Layout only; source contents are never copied into a share.")
define("Preference", {"channel_id":ID,"events":array(enum("Selected event kind.","news.published","catalog.changed","request.status"),"Events shown in the open app; OS push is deferred.",3,0,True)}, "Per-user subscription; read rights are checked independently.")
define("Update", {"update_id":ID,"kind":enum("Hint or access invalidation.","channel.changed","request.status","access.revoked"),"target_id":ID,"revision":REVISION}, "No source payload; fetch authorized snapshot/status after the hint. Revocation removes cached content.")
define("UpdatePage", {"items":array(ref("Update"),"Authorized user update hints.",100),"next_cursor":CURSOR}, "Polling transport for v1; invalid/expired cursor requires full resync. SSE may be added later without changing payloads.")

def collection(name):
    cname=name+"List"
    if cname not in SCHEMAS:
        define(cname,{"items":array(ref(name),"Bounded list page.",100),"next_cursor":{"oneOf":[CURSOR,{"type":"null"}],"description":"Null at the end of the stable scan."}},"Caller-scoped list with limit/cursor pagination.")
    return cname


define('Workspace', {'org_id':ID,'name':text('Workspace name.',80),'role':enum('Current server-derived role.','owner','admin','editor')}, 'One immutable owner; members can belong to several workspaces.')
define('WorkspaceMember', {**SCHEMAS['User']['properties'],'role':enum('Workspace role.','owner','admin','editor')}, 'Registered local account in this workspace.')
define('MemberWrite', {'username':ref('UserUsername'),'role':enum('Owner-assigned role; ownership transfer is not supported.','admin','editor')}, 'Add or change a member by exact registered username; Owner only.')
PATHS={}
def endpoint(method,path,operation,description,request=None,response=None,status=200,auth="UserSession",scope=None,listing=False,params=()):
    parameters=[]
    for part in path.split('/'):
        if part.startswith('{'):
            parameter_schema = SCHEMAS['ChannelCreate']['properties']['slug'] if part=='{slug}' else (SCHEMAS['UserUsername'] if part=='{username}' else ID)
            parameters.append({"name":part[1:-1],"in":"path","required":True,"schema":parameter_schema})
    if listing:
        parameters += [{"name":"limit","in":"query","schema":number("Maximum results per page.",1,100)}, {"name":"cursor","in":"query","schema":CURSOR}]
    parameters += list(params)
    if auth=="UserSession" and method not in ("get","head"):
        parameters.append({"name":"X-CSRF-Token","in":"header","required":True,"schema":text("Token returned by the current session endpoint.",256)})
    headers={"Cache-Control":{"schema":{"type":"string","const":"no-store"},"description":"Private/session/secret responses must not be cached by shared intermediaries."}}
    responses={str(status):{"description":"Successful operation. "+description,"headers":headers}}
    if response:responses[str(status)]["content"]={"application/json":{"schema":ref(response)}}
    for code in (400,401,403,404,409,410,413,415,422,429,500,503):
        responses[str(code)]={"description":f"See protocol error table for HTTP {code}.","content":{"application/json":{"schema":ref("Error")}}}
    responses['429']['headers']={"Retry-After":{"required":True,"schema":{"type":"integer","minimum":1},"description":"Seconds before retry."}}
    op={"operationId":operation,"summary":description,"security":[] if auth is None else [{auth:[]}],"parameters":parameters,"responses":responses}
    if request is not None:op['requestBody']={"required":True,"content":{"application/json":{"schema":ref(request) if isinstance(request,str) else request}}}
    if scope:op['x-required-bot-scope']=scope
    PATHS.setdefault(path,{})[method]=op


endpoint('post','/v1/auth/register','registerUser','Create a local account; validate same-origin request.', 'RegisterUser','Session',201,None)
endpoint('post','/v1/auth/login','login','Create a revocable local session; validate same-origin request.', 'Credentials','Session',200,None)
endpoint('get','/v1/auth/session','session','Read the current session and CSRF token.',response='Session')
endpoint('delete','/v1/auth/session','logout','Revoke current session and clear cookie.',status=204)
endpoint('get','/v1/account/business-profile','readBusinessProfile','Read your own B2B organization; no arbitrary tenant parameter.',response='BusinessProfile')
endpoint('get','/v1/workspaces','listWorkspaces','List active workspaces of the current account.',response=collection('Workspace'),listing=True)
endpoint('get','/v1/workspaces/{org_id}/members','listWorkspaceMembers','List members; any current workspace member may read.',response=collection('WorkspaceMember'),listing=True)
endpoint('put','/v1/workspaces/{org_id}/members','setWorkspaceMember','Owner adds or changes Admin/Editor by exact username.','MemberWrite','WorkspaceMember')
endpoint('delete','/v1/workspaces/{org_id}/members/{user_id}','removeWorkspaceMember','Owner revokes membership; independent public/read grants remain valid. The owner cannot be removed.',status=204)
endpoint('put','/v1/account/business-profile','enableBusinessProfile','Enable or rename a personal B2B organization; owner membership is server-assigned.','BusinessProfileWrite','BusinessProfile')
endpoint('delete','/v1/account','deactivateAccount','Re-authenticate, revoke sessions, disable owned sources and remove memberships/grants. Username remains reserved.','ConfirmPassword',status=204)
endpoint('get','/v1/users/by-username/{username}','lookupRegisteredUser','Exact username lookup for a signed-in B2B owner; returns only public profile metadata.',response='User')
endpoint('post','/v1/bots','createBot','Create an owned bot and issue a one-time registration credential.','BotCreate','Registration',201)
endpoint('get','/v1/bots','listBots','List owned bots.',response=collection('Bot'),listing=True)
endpoint('get','/v1/bots/{bot_id}','readBot','Read owned bot status and last_seen.',response='BotDetails')
endpoint('get','/v1/bot/identity','readBotIdentity','Verify the operational credential and update last_seen.',response='BotIdentity',auth='BotBearer')
endpoint('post','/v1/bots/{bot_id}/registration','renewRegistration','Invalidate prior bootstrap credentials and issue a fresh one.',EMPTY,'Registration',201)
endpoint('post','/v1/bot-registrations/exchange','exchangeRegistration','Consume registration credential atomically; issue initial operational key.',EMPTY,'KeySecret',201,'RegistrationBearer')
endpoint('post','/v1/bots/{bot_id}/keys','issueBotKey','Issue or atomically rotate an owned bot key.','KeyIssue','KeySecret',201)
endpoint('get','/v1/bots/{bot_id}/keys','listBotKeys','List key metadata only.',response=collection('KeyMetadata'),listing=True)
endpoint('delete','/v1/bots/{bot_id}/keys/{key_id}','revokeBotKey','Revoke key immediately.',status=204)
endpoint('delete','/v1/bots/{bot_id}','revokeBot','Revoke all credentials and stop ingestion/new actions; disable published channels.',status=204)
endpoint('post','/v1/bot/messages','sendMessage','Validate, deduplicate and durably commit a message and snapshot/outbox.','Message','Receipt',200,'BotBearer','messages:write')
endpoint('get','/v1/bot/events','getEvents','Read unacknowledged actions; restart each completed scan without cursor.',response='EventPage',auth='BotBearer',scope='events:read',listing=True,params=({'name':'wait','in':'query','schema':number('Wait seconds; only first page may long poll.',0,25)},))
endpoint('post','/v1/bot/events/{event_id}/ack','ackEvent','Confirm durable receipt; replay returns same ACK.',EMPTY,'Ack',200,'BotBearer','events:ack')
endpoint('post','/v1/bot/events/{event_id}/result','reportResult','Report ordered business progress or immutable terminal result.','Result','ActionRequest',200,'BotBearer','events:result')
endpoint('get','/v1/bot/requests','listUnresolvedRequests','Reconcile acknowledged or unacknowledged nonterminal requests.',response=collection('BotEvent'),auth='BotBearer',scope='events:read',listing=True)
endpoint('post','/v1/channels','createChannel','Create an owned draft channel for an owned bot.','ChannelCreate','Channel',201)
endpoint('get','/v1/owner/channels','listOwnedChannels','List owned channels including drafts.',response=collection('Channel'),listing=True)
endpoint('get','/v1/owner/channels/{channel_id}','readDraft','Read an owned draft.',response='Channel')
endpoint('put','/v1/owner/channels/{channel_id}','replaceDraft','Validate and replace a channel draft.','ChannelDraft','Channel')
endpoint('post','/v1/owner/channels/{channel_id}/publish','publishChannel','Publish only a fully valid draft with compatible existing sources.','Publish','Channel')
define('OwnedResource', {**SCHEMAS['Record']['properties'], 'content_type':enum('Typed resource kind.','news','product','chart')}, 'Owner-only source inventory, including sources not used in a published layout.')
endpoint('get','/v1/owner/channels/{channel_id}/preview','previewChannel','Read the current draft with compatible live records.',response='Snapshot')
endpoint('get','/v1/owner/channels/{channel_id}/versions','listChannelVersions','Read immutable saved definitions.',response=collection('PageVersion'),listing=True)
endpoint('get','/v1/owner/channels/{channel_id}/resources','listChannelResources','Read current live source inventory.',response=collection('OwnedResource'),listing=True)
endpoint('post','/v1/owner/channels/{channel_id}/rollback','rollbackChannel','Publish a validated copy of a formerly published definition as a new version.','Rollback','Channel')
endpoint('delete','/v1/owner/channels/{channel_id}','deleteChannel','Unpublish immediately; revoke access and retain revision tombstones.',status=204)
endpoint('get','/v1/owner/channels/{channel_id}/grants','listGrants','List selected-member read grants.',response=collection('Grant'),listing=True)
endpoint('get','/v1/owner/channels/{channel_id}/audience','listAudience','Owner/Admin list public profiles of explicitly granted readers; no credentials.',response=collection('User'),listing=True)
endpoint('put','/v1/owner/channels/{channel_id}/grants/{user_id}','grantRead','Grant read access to an existing user; does not transfer ownership.',EMPTY,status=204)
endpoint('delete','/v1/owner/channels/{channel_id}/grants/{user_id}','revokeRead','Revoke read access and emit invalidation; recheck pending actions.',status=204)
endpoint('get','/v1/channels/{slug}','readChannel','Read a public or explicitly granted published snapshot.',response='Snapshot',auth=None)
PATHS['/v1/channels/{slug}']['get']['security']=[{}, {'UserSession':[]}]
PATHS['/v1/channels/{slug}']['get']['parameters'].append({'name':'If-None-Match','in':'header','schema':text('Previously received ETag; access is checked before conditional evaluation.',2048)})
PATHS['/v1/channels/{slug}']['get']['responses']['304']={'description':'Unchanged authorized representation; no body. All responses remain no-store.'}
PATHS['/v1/channels/{slug}']['get']['responses']['200']['headers']['ETag']={'schema':{'type':'string'},'description':'Representation validator bound to the current session, or anonymous audience.'}
idem={'name':'Idempotency-Key','in':'header','required':True,'schema':text('Stable retry identity; retained for 30 days or until pending work resolves.',128,8,pattern='^[A-Za-z0-9_-]+$')}
endpoint('post','/v1/channels/{channel_id}/actions','requestAction','Queue a request after current access/revision checks; replay returns the same request.','ActionInput','ActionRequest',202,params=(idem,))
endpoint('get','/v1/action-requests/{action_request_id}','readAction','Read own request with current source access.',response='ActionRequest')
define('Favorite', {'channel_id':ID,'available':{'type':'boolean','description':'Current source access.'},'title':text('Current readable published title.',80),'slug':SCHEMAS['ChannelCreate']['properties']['slug'],'unread':{'type':'boolean','description':'Published template or channel data advanced since last observation.'}}, 'Unavailable references return only channel_id and available=false.', ('title','slug','unread'))
SCHEMAS['Favorite']['allOf']=[{'if':{'properties':{'available':{'const':True}}},'then':{'required':['title','slug','unread']},'else':{'properties':{'title':False,'slug':False,'unread':False}}}]
define('Favorites', {'revision':number('Collection order revision.'),'items':array(ref('Favorite'),'Complete manually ordered collection; at most 100 saved channels.',100)}, 'Atomic bounded collection; no pagination. Metadata is reauthorized on every read.')
define('FavoriteOrder', {'expected_revision':number('Exact collection revision.'),'channel_ids':array(ID,'Exact permutation of current favorites.',100,0,True)}, 'Concurrent stale reorder returns 409; does not add or remove channels.')
define('FavoriteRevision', {'revision':number('Current collection revision.')}, 'Successful order revision.')
define('FavoriteSeen', {'data_revision':number('Observed snapshot data revision.'),'template_version':REVISION}, 'Monotonic observed revision markers; future revisions rejected.')
endpoint('get','/v1/favorites','listFavorites','Read the complete bounded favorites collection with current permissions.',response='Favorites')
endpoint('put','/v1/favorites/order','orderFavorites','Replace manual order with optimistic concurrency.','FavoriteOrder','FavoriteRevision')
endpoint('put','/v1/favorites/{channel_id}/seen','markFavoriteSeen','Mark only observed data and template revisions; never reduces seen markers.','FavoriteSeen',status=204)
define('SourceChannel',{'channel_id':ID},'Favorite reference; saving does not grant access.')
endpoint('put','/v1/favorites/{channel_id}','saveFavorite','Save an accessible channel idempotently.',EMPTY,status=204)
endpoint('delete','/v1/favorites/{channel_id}','removeFavorite','Remove own favorite idempotently.',status=204)
define('ResolvedPageBlock', {'block_id':ID,'available':{'type':'boolean','description':'Current source and published binding availability.'},'record':ref('Record'),'actions':array(ref('ActionDefinition'),'Currently published allowed actions bound to this personal block.',5),'slug':SCHEMAS['ChannelCreate']['properties']['slug'],'data_revision':number('Current channel change revision.')}, 'Unavailable blocks reveal only block_id and available=false.', ('record','actions','slug','data_revision'))
SCHEMAS['ResolvedPageBlock']['allOf']=[{'if':{'properties':{'available':{'const':True}}},'then':{'required':['record','actions','slug','data_revision']},'else':{'properties':{'record':False,'actions':False,'slug':False,'data_revision':False}}}]
define('PageSnapshot', {'page':ref('PersonalPage'),'blocks':array(ref('ResolvedPageBlock'),'One current result per personal block, in layout order.',50)}, 'Owned layout and independently authorized live source values; source payloads are not stored in the page.')
endpoint('post','/v1/personal-pages','createPage','Create an owned personal layout; up to 20 active pages. Account-scoped creation key prevents duplicates.','PageWrite','PersonalPage',201,params=(idem,))
endpoint('get','/v1/personal-pages','listPages','List owned personal pages.',response=collection('PersonalPage'),listing=True)
endpoint('get','/v1/personal-pages/{page_id}','readPage','Read own layout; source contents are fetched separately with current rights.',response='PersonalPage')
endpoint('get','/v1/personal-pages/{page_id}/snapshot','resolvePersonalPage','Resolve current published bindings and access independently for each source; unavailable blocks contain no source metadata.',response='PageSnapshot')
endpoint('put','/v1/personal-pages/{page_id}','replacePage','Replace owned layout using expected version.','PageWrite','PersonalPage')
endpoint('delete','/v1/personal-pages/{page_id}','deletePage','Delete own page and revoke its share locators.',status=204)
endpoint('post','/v1/personal-pages/{page_id}/shares','createShare','Store an immutable layout-only snapshot; never source payloads.','ShareCreate','Share',201)
endpoint('delete','/v1/shares/{share_id}','revokeShare','Stop new imports; existing copied layouts retain independent rights checks.',status=204)
endpoint('post','/v1/template-imports/preview','previewImport','Validate supported layout and mark inaccessible sources.','ImportInput','ImportPreview')
endpoint('post','/v1/template-imports','importTemplate','Create a new owned page; recheck access and share expiry.','ImportInput','PersonalPage',201,params=(idem,))
endpoint('put','/v1/preferences/{channel_id}','setPreference','Set own open-app event preferences for an accessible channel.','Preference','Preference')
endpoint('get','/v1/preferences','listPreferences','List own event preferences.',response=collection('Preference'),listing=True)
endpoint('get','/v1/updates','readUpdates','Poll authorized change hints; no cursor starts at current watermark and requires snapshot refresh.',response='UpdatePage',params=({'name':'cursor','in':'query','schema':CURSOR},))

for session_path, method, code in (('/v1/auth/register','post','201'),('/v1/auth/login','post','200'),('/v1/auth/session','delete','204'),('/v1/account','delete','204')):
    PATHS[session_path][method]['responses'][code]['headers']['Set-Cookie']={
        'schema': {'type':'string'},
        'description':'Set or expire marketob_session; HttpOnly; SameSite=Strict; Path=/; Secure except loopback HTTP. See protocol.'}


for workspace_path, workspace_method in (('/v1/bots','get'),('/v1/bots','post'),('/v1/owner/channels','get'),('/v1/users/by-username/{username}','get')):
    PATHS[workspace_path][workspace_method]['parameters'].append({'name':'X-Workspace-ID','in':'header','required':False,'schema':ID,'description':'Select a current workspace membership. Omission uses your personal owner workspace. Never grants access; IDs in resource routes independently resolve and verify their workspace.'})


def replace_refs(value):
    if isinstance(value,dict):
        return {k:(v.replace('#/$defs/','#/components/schemas/') if k=='$ref' else replace_refs(v)) for k,v in value.items()}
    if isinstance(value,list):return [replace_refs(x) for x in value]
    return value


def artifacts():
    bundle={"$schema":"https://json-schema.org/draft/2020-12/schema", "$id":"urn:marketob:contract:1.0", "$defs":SCHEMAS}
    spec={"openapi":"3.1.1","info":{"title":"MarkeTOB local pilot API","version":"1.0.6","description":"PM-004 design contract. No running server is delivered by this specification. See docs/api/PROTOCOL.md for normative state, authorization, limits and retry rules."},"servers":[{"url":"http://127.0.0.1:8000","description":"Loopback development only; remote deployments require HTTPS."}],"paths":PATHS,"components":{"schemas":SCHEMAS,"securitySchemes":{"UserSession":{"type":"apiKey","in":"cookie","name":"marketob_session","description":"HttpOnly server session; mutations require X-CSRF-Token and exact allowed Origin."},"BotBearer":{"type":"http","scheme":"bearer","description":"Per-bot operational key; never a user session or bootstrap credential."},"RegistrationBearer":{"type":"http","scheme":"bearer","description":"Single-use 15-minute registration credential, exchange endpoint only."}}}}
    return {"schemas.json":bundle,"openapi.json":replace_refs(spec)}


if __name__=='__main__':
    for filename,body in artifacts().items():
        (ROOT/filename).write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Generated {len(SCHEMAS)} schemas and {sum(len(x) for x in PATHS.values())} operations.')
