from datetime import datetime, timedelta

from case_data import primary_refs, good_mirror_refs, missing_tag_mirror_refs, stale_commit_mirror_refs, \
    missing_branch_mirror_refs
from alerts import rule_error_accumulation
from mirror_health import GitMirrorHealth, prepare_mirror_health_objects


def test_rule_error_accumulation():
    repo_path = 'multiple-failure-testing'
    repo_lookup = {}
    alert_threshold = 1
    prepare_mirror_health_objects(repo_path=repo_path, repos_for_project=repo_lookup,
                                  primary_repo_fqdn='example.com',
                                  mirror_hosts=['5.5.5.1', '5.5.5.2', '5.5.5.3'])
    ghm: GitMirrorHealth
    for ghm in repo_lookup[repo_path]:
        placeholder_ts = datetime.now()
        ghm.index_snapshot = good_mirror_refs
        ghm.up = 1
        ghm.sync_errors_total = 0
        ghm.git_port_open = 1
        ghm.in_service = 1
        ghm.last_in_sync = placeholder_ts

    # Clean test
    subject, message = rule_error_accumulation(repos_for_project=repo_lookup[repo_path], threshold=alert_threshold)
    assert subject == ''
    assert message == ''


    # 1 unhealthy mirror test
    unhealthy_repo: GitMirrorHealth = repo_lookup[repo_path][1]
    unhealthy_repo.index_snapshot = stale_commit_mirror_refs
    unhealthy_repo.last_in_sync = unhealthy_repo.last_in_sync - timedelta(minutes=15)
    unhealthy_repo.sync_errors_total = 2

    subject, message = rule_error_accumulation(repos_for_project=repo_lookup[repo_path], threshold=alert_threshold)
    assert subject != ''
    assert message != ''
    assert 'error threshold of 2' in subject
    assert '1 (allowed)' in subject
    assert '5.5.5.1 ' in message
    assert '5.5.5.2' not in message
    assert '5.5.5.3' not in message
    assert 'abc60f2af612b3505ab33e4c427991f055929014        refs/heads/dev' in message # From the primary
    assert 'abc60f2af612b3505ab33e4c427991f055921111        refs/heads/dev' in message # From the secondary
    print(subject)
    print(message)


if __name__ == '__main__':
    test_rule_error_accumulation()

