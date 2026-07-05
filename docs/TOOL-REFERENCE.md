<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Tool Reference

Generated from the server's tool registry by scripts/gen_tool_reference.py.
Do not edit by hand: regenerate after any tool change.


36 tools.


## `commit_changes`

Commit the staged buffer; requires a fresh confirm token.


| Parameter | Type | Required |
|---|---|---|
| `message` | string | no |
| `confirm` | string | yes |


## `create_branch`

Create a branch. head_commit_id defaults to the session branch head.


| Parameter | Type | Required |
|---|---|---|
| `name` | string | yes |
| `head_commit_id` | string | no |


## `create_element`

Stage creation of a new element under an owner (buffer-only).


| Parameter | Type | Required |
|---|---|---|
| `type` | string | yes |
| `name` | string | yes |
| `owner` | string | yes |


## `create_project`

Create a project (name, optional description). The session stays bound to its configured project.


| Parameter | Type | Required |
|---|---|---|
| `name` | string | yes |
| `description` | string | no |


## `create_relationship`

Stage a typed relationship (buffer-only). Sets explicit source/target plus the type's concrete end fields (Subclassification, Specialization, Subsetting, Redefinition, FeatureTyping, Dependency); other types take concrete ends via properties.


| Parameter | Type | Required |
|---|---|---|
| `type` | string | yes |
| `source` | string | yes |
| `target` | string | yes |
| `owner` | string | no |
| `properties` | object | no |


## `create_tag`

Tag a commit (checkpoint). commit_id defaults to the session branch head.


| Parameter | Type | Required |
|---|---|---|
| `name` | string | yes |
| `commit_id` | string | no |


## `delete_branch`

Delete a branch (destructive; requires confirm: true). Outcome is verified via the branch list; the default branch is refused.


| Parameter | Type | Required |
|---|---|---|
| `branch_id` | string | yes |
| `confirm` | boolean | yes |


## `delete_element`

Stage deletion of a single element (buffer-only; refuses if it owns children).


| Parameter | Type | Required |
|---|---|---|
| `element_id` | string | yes |


## `delete_project`

Delete a project (destructive; requires confirm: true). The session's configured project is refused; outcome is verified via the project list.


| Parameter | Type | Required |
|---|---|---|
| `project_id` | string | yes |
| `confirm` | boolean | yes |


## `delete_subtree`

Stage deletion of an element and its owned subtree (buffer-only).


| Parameter | Type | Required |
|---|---|---|
| `element_id` | string | yes |


## `diff_commits`

Diff two commits -> {created, deleted, modified} element-id lists (client-side; pilot lacks native diff).


| Parameter | Type | Required |
|---|---|---|
| `base_commit` | string | yes |
| `compare_commit` | string | yes |


## `discard_changes`

Discard the staged buffer without committing.


## `find_by_name`

Find elements by declaredName, optional type filter. commit_id defaults to head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `name` | string | yes |
| `type` | string | no |


## `get_children`

One level of owned children with id/name/type. commit_id defaults to head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `element_id` | string | yes |


## `get_commit`

Fetch a single commit record (previousCommit, description, created).


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | yes |


## `get_commit_changes`

Full DataVersion change records of a commit (deletions have payload null).


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | yes |


## `get_commits`

List commits for the configured project. Order is not guaranteed to be newest-first (use resolve_head/get_commit for the actual head).


## `get_element`

Fetch a single element (raw JSON, full fidelity) at a commit. commit_id defaults to the branch head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `element_id` | string | yes |


## `get_licence`

Report the current licence state (valid, reason, tier, customer, expires, days_remaining, expires_soon, seats, features, source) from the in-memory state loaded once at server start. Always available; shows why authoring is locked when unlicensed.


## `get_project`

Project metadata (name, description, default branch). Optional project_id overrides the configured project.


| Parameter | Type | Required |
|---|---|---|
| `project_id` | string | no |


## `get_relationships`

Typed relationship elements touching an element (matches explicit source/target). direction: in|out|both. commit_id defaults to head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `element_id` | string | yes |
| `direction` | string | no |


## `get_root_elements`

Root (unowned) elements at a commit: the entry point into a model. Filtered client-side (the pilot's /roots does not exclude owned elements). commit_id defaults to the branch head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |


## `list_branches`

List branches (id, name, head commit). Optional project_id overrides the configured project.


| Parameter | Type | Required |
|---|---|---|
| `project_id` | string | no |


## `list_projects`

List projects visible to this API endpoint.


## `list_tags`

List tags (name, tagged commit). Optional project_id overrides the configured project.


| Parameter | Type | Required |
|---|---|---|
| `project_id` | string | no |


## `merge_branch`

Squash-merge a source branch onto a target branch as one commit (requires confirm: true). Refuses with conflicting element ids if both branches changed the same element.


| Parameter | Type | Required |
|---|---|---|
| `source_branch_id` | string | yes |
| `target_branch_id` | string | yes |
| `description` | string | no |
| `confirm` | boolean | yes |


## `modify_element`

Stage a modification to an existing element (buffer-only).


| Parameter | Type | Required |
|---|---|---|
| `element_id` | string | yes |
| `changes` | object | yes |


## `move_element`

Stage a rehome of an element to a new owner (buffer-only; modifies its OwningMembership at the commit). commit_id defaults to the branch head.


| Parameter | Type | Required |
|---|---|---|
| `element_id` | string | yes |
| `new_owner` | string | yes |
| `commit_id` | string | no |


## `nav_traverse`

Traverse owned-member hierarchy from a root element (cycle-safe). commit_id defaults to the branch head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `root` | string | yes |
| `max_depth` | integer | no |
| `follow_relationships` | boolean | no |
| `include_names` | boolean | no |


## `ping`

Minimal liveness probe: confirms the endpoint is reachable.


## `query_elements`

Query elements at a commit with opaque-cursor pagination. commit_id defaults to the branch head.


| Parameter | Type | Required |
|---|---|---|
| `commit_id` | string | no |
| `filter` | object | no |
| `cursor` | string | no |
| `page_size` | integer | no |


## `review_changes`

Return the staged ops + a confirm token (must be reviewed before commit).


## `set_branch`

Retarget this session at a branch: staged commits and default read head follow it. Refused while staged work exists.


| Parameter | Type | Required |
|---|---|---|
| `branch_id` | string | yes |


## `stage_batch`

Stage many operations atomically (all-or-nothing, buffer-only). Ops: {op: create|relate|modify|delete, ...}; create ops accept a caller-minted element_id so later ops in the batch can reference it.


| Parameter | Type | Required |
|---|---|---|
| `operations` | array | yes |


## `stats`

Return a snapshot of server metrics counters.


## `update_project`

Rename or re-describe a project. project_id defaults to the configured project. Only provided fields change.


| Parameter | Type | Required |
|---|---|---|
| `project_id` | string | no |
| `name` | string | no |
| `description` | string | no |
