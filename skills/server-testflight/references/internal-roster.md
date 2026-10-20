# Fixed internal tester roster

The roster helper uses Python's standard library and Apple's public API. Configure it only on the trusted coordinator server. Real app/group IDs, emails and the token provider path stay in private files outside Git, mode 0600. The config can invoke a local token-provider argv; that command must output only a short-lived Apple JWT and must not be run interactively or logged. The helper captures it in memory and only uses it on Apple's API origin.

Private config shape:

```json
{
  "app_id": "YOUR_APP_ID",
  "bundle_id": "org.example.app",
  "group_id": "YOUR_INTERNAL_GROUP_ID",
  "roster_file": "/etc/testflight/internal-testers.json",
  "token_command": ["/usr/local/lib/testflight/print-short-lived-token"],
  "direct_network": false
}
```

Private roster shape:

```json
[
  {"email": "existing@example.org"},
  {"email": "authorized-role-change@example.org", "allow_add_marketing": true, "allow_app_access": true},
  {"email": "new@example.org", "first_name": "Demo", "last_name": "Tester", "allow_team_invitation": true, "allow_app_access": true}
]
```

These are documentation examples, not a real roster. Supply the actual invite display names in private configuration. For existing team users, attempt the intended group association through the API and use its response/readback as authority. Do not require Marketing or change roles merely because their role labels appear ineligible; existing customer-support/finance members have been accepted directly by the API. Marketing is used for authorized new team invitations, not as a prerequisite for every existing member. New team invitations are limited to the intended App and do not grant provisioning access. Do not grant Admin to make testing easier.

```sh
python3 scripts/sync_internal_testers.py --config /etc/testflight/internal-roster-config.json
```

Reuse one account-private roster across the user's iOS projects. Each project keeps its own app/group IDs and config but points to the shared roster file. When the user authorizes automatic inclusion for future releases, remember that scope in private local/server configuration; do not hardcode a personal list into the public skill. Adding people to existing unrelated Apps now still requires that scope to be explicit.

Put this command in each project's server-side finish adapter before reporting internal release success. It is idempotent: known pending team invitations and existing group memberships are reused; unrelated people are not removed. A new user must first accept their App Store Connect team invitation, and then accept the TestFlight invitation after the next reconciliation. The intended internal group must already have automatic access to new builds. The helper refuses external groups or mismatched Apps/bundles.

`--resend-pending` resends TestFlight invitations for already-present INVITED testers only when explicitly requested. Default output redacts email addresses into entry numbers; `--show-emails` is for a private operator session. Partial failures return nonzero after attempting other roster entries; never describe that as all users being enrolled. Pending team acceptance is reported separately and does not prevent uploading a build.

References: [Users](https://developer.apple.com/documentation/appstoreconnectapi/users), [user invitations](https://developer.apple.com/documentation/appstoreconnectapi/user-invitations), [internal testers](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers).

## Manage people

```sh
python3 scripts/manage_roster.py list --roster /etc/testflight/internal-testers.json
python3 scripts/manage_roster.py add --roster /etc/testflight/internal-testers.json --email tester@example.org
python3 scripts/manage_roster.py remove --roster /etc/testflight/internal-testers.json --email tester@example.org
```

Real emails are private command arguments, not repository content. Run list/edit commands in a private operator session. Add authorization flags only for user-authorized team invitations, marketing role additions or app access. New team invitations need first/last display names using Apple's accepted character set.

The editor stores an object with `testers` and `removed` arrays; existing list-only rosters remain readable. Removal is an explicit exclusion: reconciliation removes that tester from this Skill's configured group using the group relationship API, verifies the result, and leaves the Apple team account/roles and unmanaged groups alone. To revoke immediately across managed projects, reconcile every registered project config. There is no scheduled background job; normal future releases reconcile automatically.

Existing `allow_add_marketing` fields in private rosters are retained for compatibility but no longer cause a role mutation. Group association and API readback are authoritative; changing team roles is a separate explicitly authorized administration task.
