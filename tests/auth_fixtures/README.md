# Static test credentials (ADR-0038)

NKey/JWT credentials for the auth test suite, generated once with `nsc` and
checked in. **Test-only material** — the operator/account signing keys were
discarded after generation; nothing here grants access to any real system.

| File | What it is |
|------|------------|
| `operator.jwt` | Operator JWT (`oam-test`), referenced by the test server config |
| `account-TEST.jwt` | Account JWT (`TEST`), JetStream enabled, preloaded into the memory resolver |
| `worker.creds` | User with default (full) permissions in the account |
| `denied.creds` | User with `deny-pub mesh.>` and `deny-sub mesh.>` |

Regenerate (rarely needed):

```bash
nsc add operator --name oam-test
nsc add account --name TEST
nsc edit account TEST --js-mem-storage -1 --js-disk-storage -1 --js-streams -1 --js-consumer -1
nsc add user --account TEST --name worker
nsc add user --account TEST --name denied --deny-pub 'mesh.>' --deny-sub 'mesh.>'
```

Then copy the JWTs from the nsc store and the `.creds` from the nsc keys dir,
and update the account public key in `tests/test_auth.py` (`ACCOUNT_PUBLIC_KEY`).

The test server runs with a `MEMORY` resolver and `resolver_preload`, so no
`nsc push` or resolver directory is involved at test time.
